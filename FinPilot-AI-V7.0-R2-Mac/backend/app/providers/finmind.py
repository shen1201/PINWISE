from __future__ import annotations

import time
from datetime import date, timedelta
from urllib.parse import urlencode

from ..core.config import Settings
from ..core.http_client import ResilientHttpClient, UpstreamError
from ..core.models import HealthResult, PricePoint, SourceMetadata
from ..core.normalization import is_stale, parse_integer, parse_number


class FinMindProvider:
    name = "FinMind"

    def __init__(self, settings: Settings, http: ResilientHttpClient):
        self.settings = settings
        self.http = http

    @property
    def data_url(self) -> str:
        return f"{self.settings.finmind_base_url}/data"

    def _headers(self) -> dict[str, str] | None:
        return {"Authorization": f"Bearer {self.settings.finmind_token}"} if self.settings.finmind_token else None

    def _forget(self, params: dict) -> None:
        drop = getattr(self.http, "drop", None)
        if drop:
            drop(self.data_url, params)

    async def market(self, symbol: str) -> str:
        # 上市櫃別幾乎不變：成功結果保留 12 小時，每張卡片／每次研究就只需要再查一次歷史價，省下一半額度。
        params = {"dataset": "TaiwanStockInfo"}
        payload = await self.http.get_json(
            self.name,
            self.data_url,
            params=params,
            headers=self._headers(),
            min_interval=0.6,
            cache_ttl=12 * 60 * 60,
        )
        if payload.get("status") != 200:
            # FinMind 額度用完時仍回 HTTP 200，只在內容標示錯誤；不可把錯誤內容記 12 小時。
            self._forget(params)
            return "UNKNOWN"
        rows = [row for row in (payload.get("data") or []) if str(row.get("stock_id")) == symbol]
        if not rows:
            return "UNKNOWN"
        latest = max(rows, key=lambda row: str(row.get("date") or ""))
        return {"twse": "TWSE", "tpex": "TPEX", "emerging": "EMERGING"}.get(str(latest.get("type") or "").lower(), "UNKNOWN")

    async def index_history(self, data_id: str, start_date: date, end_date: date) -> list[dict]:
        """大盤指數日收盤、漲跌與成交金額（舊到新）。data_id：TAIEX 加權、TPEx 櫃買。"""
        params = {"dataset": "TaiwanStockPrice", "data_id": data_id,
                  "start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
        payload = await self.http.get_json(self.name, self.data_url, params=params, headers=self._headers(), min_interval=0.5)
        if payload.get("status") != 200:
            self._forget(params)
            raise UpstreamError(self.name, payload.get("msg") or "FinMind 回傳錯誤", status_code=int(payload.get("status") or 502))
        points = {}
        for row in payload.get("data") or []:
            if str(row.get("stock_id")) != data_id or not isinstance(row.get("close"), (int, float)) or row["close"] <= 0:
                continue
            spread, money = row.get("spread"), row.get("Trading_money")
            points[str(row.get("date"))] = {
                "index": float(row["close"]),
                "change": float(spread) if isinstance(spread, (int, float)) else None,
                "trade_value_twd": int(money) if isinstance(money, (int, float)) else None,
            }
        return [{"date": day, **values} for day, values in sorted(points.items())]

    async def history(self, symbol: str, start_date: date, end_date: date) -> list[PricePoint]:
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        market = await self.market(symbol)
        payload = await self.http.get_json(self.name, self.data_url, params=params, headers=self._headers(), min_interval=0.6)
        if payload.get("status") != 200:
            # 額度暫時用完等錯誤不記入快取，額度恢復後下一次請求就能立即取得資料。
            self._forget(params)
            status = int(payload.get("status") or 502)
            message = payload.get("msg") or "FinMind 回傳錯誤"
            raise UpstreamError(self.name, message, status_code=status)
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            raise UpstreamError(self.name, "歷史行情回傳格式不是資料列陣列")
        result = []
        seen = set()
        for row in rows:
            if str(row.get("stock_id")) != symbol:
                raise UpstreamError(self.name, "歷史行情包含不屬於請求標的的資料，已拒絕使用")
            try:
                trade_date = date.fromisoformat(str(row.get("date")))
            except ValueError:
                continue
            if not start_date <= trade_date <= end_date or trade_date in seen:
                continue
            seen.add(trade_date)
            # FinMind 明確以 0 表示「原始來源沒有公告價格」；保留 0，不轉成缺值。
            result.append(PricePoint(
                symbol=str(row.get("stock_id") or symbol),
                market=market,
                trade_date=trade_date,
                open=parse_number(row.get("open")),
                high=parse_number(row.get("max")),
                low=parse_number(row.get("min")),
                close=parse_number(row.get("close")),
                change=parse_number(row.get("spread")),
                volume_shares=parse_integer(row.get("Trading_Volume")),
                trade_value_twd=parse_integer(row.get("Trading_money")),
                transactions=parse_integer(row.get("Trading_turnover")),
                metadata=SourceMetadata(
                    **self.http.provenance(self.data_url, params),
                    source=self.name,
                    source_url=f"{self.data_url}?{urlencode(params)}",
                    raw_source="FinMind TaiwanStockPrice（原始提供機關：交易所公開資料）",
                    period_start=start_date,
                    period_end=end_date,
                    missing=False,
                    stale=is_stale(trade_date, self.settings.stale_hours),
                ),
            ))
        return result

    async def health(self) -> HealthResult:
        started = time.perf_counter()
        today = date.today()
        rows = await self.history("2330", today - timedelta(days=14), today)
        latest = max((row.trade_date for row in rows), default=None)
        stale = is_stale(latest, 24 * 7)
        quota = "Token 模式" if self.settings.finmind_token else "匿名免費模式"
        return HealthResult(
            source=self.name,
            status="stale" if stale else "healthy",
            latency_ms=round((time.perf_counter() - started) * 1000),
            record_count=len(rows),
            latest_data_at=latest,
            message=f"已連線（{quota}）" + ("；最近資料可能過期" if stale else ""),
            endpoint=self.data_url,
        )
