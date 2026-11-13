from __future__ import annotations

import json
import logging
import time
from datetime import timezone

from ..core.config import Settings
from ..core.http_client import ResilientHttpClient
from ..core.models import CompanyProfile, DisclosureEvent, HealthResult, MarketQuote, NewsItem, SourceMetadata
from ..core.normalization import clean_text, is_stale, parse_datetime, parse_integer, parse_number, parse_roc_date


# 這些類股指數是多個子類股的合併，排行時排除以免重複計算。
_AGGREGATE_SECTORS = {"水泥窯製", "塑膠化工", "機電", "化學生技醫療", "電子工業"}


class TWSEProvider:
    name = "TWSE"

    def __init__(self, settings: Settings, http: ResilientHttpClient):
        self.settings = settings
        self.http = http

    def _url(self, path: str) -> str:
        return f"{self.settings.twse_base_url}/{path.lstrip('/')}"

    async def _rows(self, path: str):
        data = await self.http.get_json(self.name, self._url(path), min_interval=0.25)
        if not isinstance(data, list):
            raise ValueError("TWSE 回傳格式不是資料列陣列")
        return data

    def _quote_from_row(self, row) -> MarketQuote:
        url = self._url("exchangeReport/STOCK_DAY_ALL")
        symbol = clean_text(row.get("Code")) or ""
        trade_date = parse_roc_date(row.get("Date"))
        return MarketQuote(
            symbol=symbol,
            name=clean_text(row.get("Name")),
            market="TWSE",
            trade_date=trade_date,
            open=parse_number(row.get("OpeningPrice")),
            high=parse_number(row.get("HighestPrice")),
            low=parse_number(row.get("LowestPrice")),
            close=parse_number(row.get("ClosingPrice")),
            change=parse_number(row.get("Change")),
            volume_shares=parse_integer(row.get("TradeVolume")),
            trade_value_twd=parse_integer(row.get("TradeValue")),
            transactions=parse_integer(row.get("Transaction")),
            metadata=SourceMetadata(
                **self.http.provenance(url),
                source=self.name,
                source_url=url,
                raw_source="TWSE OpenAPI：上市個股日成交資訊",
                period_start=trade_date,
                period_end=trade_date,
                stale=is_stale(trade_date, self.settings.stale_hours),
            ),
        )

    async def market_summary(self) -> list[dict]:
        """加權指數與上市成交金額（官方盤後日資料，最近數個交易日，舊到新）。"""
        rows = await self._rows("exchangeReport/FMTQIK")
        return [{
            "date": parse_roc_date(row.get("Date")),
            "index": parse_number(row.get("TAIEX")),
            "change": parse_number(row.get("Change")),
            "trade_value_twd": parse_integer(row.get("TradeValue")),
        } for row in rows if clean_text(row.get("Date"))]

    async def fund_list(self) -> list[dict]:
        """上市基金代號與中文名稱（用來判斷 ETF 的投信）。"""
        rows = await self.http.get_json(self.name, self._url("opendata/t187ap47_L"), cache_ttl=12 * 60 * 60, min_interval=0.25)
        if not isinstance(rows, list):
            raise ValueError("TWSE 回傳格式不是資料列陣列")
        return [{"code": clean_text(row.get("基金代號")), "name": clean_text(row.get("基金中文名稱")) or ""} for row in rows]

    async def sector_indexes(self) -> list[dict]:
        """上市各類股指數的收盤與漲跌幅（官方盤後資料），不含合併類股。"""
        rows = await self._rows("exchangeReport/MI_INDEX")
        sectors = []
        for row in rows:
            name = clean_text(row.get("指數")) or ""
            if not name.endswith("類指數") or name[:-3] in _AGGREGATE_SECTORS:
                continue
            sectors.append({
                "name": name[:-3],
                "date": parse_roc_date(row.get("日期")),
                "close": parse_number(row.get("收盤指數")),
                "change_pct": parse_number(row.get("漲跌百分比")),
            })
        return sectors

    async def top_volume(self) -> list[dict]:
        """集中市場當日成交量前二十名（官方盤後資料，成交量單位為股）。"""
        rows = await self._rows("exchangeReport/MI_INDEX20")
        items = []
        for row in rows:
            close, amount = parse_number(row.get("ClosingPrice")), parse_number(row.get("Change"))
            direction = str(row.get("Dir") or "").strip()  # clean_text 會把「-」當空值，這裡要保留
            # 官方漲跌方向另外放在 Dir；方向不明時不猜正負。
            change = -amount if direction == "-" and amount is not None else amount if direction == "+" else 0.0 if amount == 0 else None
            previous = close - change if close is not None and change is not None else None
            items.append({
                "rank": parse_integer(row.get("Rank")),
                "code": clean_text(row.get("Code")),
                "name": clean_text(row.get("Name")),
                "date": parse_roc_date(row.get("Date")),
                "volume": parse_integer(row.get("TradeVolume")),
                "close": close,
                "change_pct": round(change / previous * 100, 2) if previous else None,
            })
        return items

    async def quotes(self) -> list[MarketQuote]:
        rows = await self._rows("exchangeReport/STOCK_DAY_ALL")
        return [self._quote_from_row(row) for row in rows if clean_text(row.get("Code"))]

    async def quote(self, symbol: str) -> MarketQuote | None:
        rows = await self._rows("exchangeReport/STOCK_DAY_ALL")
        row = next((item for item in rows if clean_text(item.get("Code")) == symbol), None)
        return self._quote_from_row(row) if row else None

    async def company(self, symbol: str) -> CompanyProfile | None:
        url = self._url("opendata/t187ap03_L")
        rows = await self._rows("opendata/t187ap03_L")
        row = next((item for item in rows if clean_text(item.get("公司代號")) == symbol), None)
        if not row:
            return None
        report_date = parse_roc_date(row.get("出表日期"))
        return CompanyProfile(
            symbol=symbol,
            name=clean_text(row.get("公司名稱")),
            short_name=clean_text(row.get("公司簡稱")),
            market="TWSE",
            industry_code=clean_text(row.get("產業別")),
            listing_date=parse_roc_date(row.get("上市日期")),
            website=clean_text(row.get("網址")),
            paid_in_capital_twd=parse_number(row.get("實收資本額")),
            issued_shares=parse_integer(row.get("已發行普通股數或TDR原股發行股數")),
            metadata=SourceMetadata(
                **self.http.provenance(url),
                source="MOPS/TWSE",
                source_url=url,
                raw_source="MOPS 上市公司基本資料（由 TWSE OpenAPI 發布）",
                period_start=report_date,
                period_end=report_date,
                stale=is_stale(report_date, 24 * 14),
            ),
        )

    def _companies_snapshot_path(self):
        data_dir = getattr(self.settings, "data_dir", None)
        return data_dir / "cache" / "twse_companies.json" if data_dir else None

    async def companies(self) -> list[CompanyProfile]:
        """上市公司基本資料。來源暫時壞掉時（例如回傳不是 JSON），依序改用：
        1. 上次成功取得的名單（存在 data/cache）；2. 當日行情裡的代號與名稱（沒有產業別）。
        否則所有上市公司名稱都比對不到，助手會把「台積電」當成不明標的。"""
        snapshot = self._companies_snapshot_path()
        try:
            rows = await self._rows("opendata/t187ap03_L")
        except Exception as exc:
            logging.getLogger(__name__).warning("TWSE 公司基本資料取得失敗，改用備援：%s", exc)
            cached = self._read_companies_snapshot(snapshot)
            if cached:
                return cached
            return await self._companies_from_quotes()
        result = self._companies_from_rows(rows)
        if result and snapshot:
            try:
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                snapshot.write_text(json.dumps([row.model_dump(mode="json") for row in result], ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        return result

    @staticmethod
    def _read_companies_snapshot(path) -> list[CompanyProfile]:
        if not path or not path.exists():
            return []
        try:
            rows = [CompanyProfile.model_validate(row) for row in json.loads(path.read_text(encoding="utf-8"))]
        except (OSError, ValueError):
            return []
        for row in rows:
            row.metadata.stale = True
        return rows

    async def _companies_from_quotes(self) -> list[CompanyProfile]:
        url = self._url("exchangeReport/STOCK_DAY_ALL")
        quotes = await self.quotes()
        return [CompanyProfile(
            symbol=quote.symbol, name=quote.name, short_name=quote.name, market="TWSE",
            metadata=SourceMetadata(
                **self.http.provenance(url), source="TWSE", source_url=url,
                raw_source="TWSE 每日收盤行情（公司基本資料暫時無法取得時的備援，只有代號與名稱）",
                period_start=quote.trade_date, period_end=quote.trade_date, stale=True,
            ),
        ) for quote in quotes if quote.symbol and quote.name]

    def _companies_from_rows(self, rows) -> list[CompanyProfile]:
        result = []
        for row in rows:
            symbol = clean_text(row.get("公司代號"))
            if not symbol:
                continue
            report_date = parse_roc_date(row.get("出表日期"))
            result.append(CompanyProfile(
                symbol=symbol,
                name=clean_text(row.get("公司名稱")),
                short_name=clean_text(row.get("公司簡稱")),
                market="TWSE",
                industry_code=clean_text(row.get("產業別")),
                listing_date=parse_roc_date(row.get("上市日期")),
                website=clean_text(row.get("網址")),
                paid_in_capital_twd=parse_number(row.get("實收資本額")),
                issued_shares=parse_integer(row.get("已發行普通股數或TDR原股發行股數")),
                metadata=SourceMetadata(
                    **self.http.provenance(self._url("opendata/t187ap03_L")),
                    source="MOPS/TWSE", source_url=self._url("opendata/t187ap03_L"),
                    raw_source="MOPS 上市公司基本資料（由 TWSE OpenAPI 發布）",
                    period_start=report_date, period_end=report_date,
                    stale=is_stale(report_date, 24 * 14),
                ),
            ))
        return result

    async def disclosures(self, symbol: str | None = None) -> list[DisclosureEvent]:
        url = self._url("opendata/t187ap04_L")
        rows = await self._rows("opendata/t187ap04_L")
        result = []
        for row in rows:
            code = clean_text(row.get("公司代號")) or ""
            if symbol and code != symbol:
                continue
            published = parse_datetime(row.get("發言日期"), row.get("發言時間"))
            result.append(DisclosureEvent(
                symbol=code,
                company_name=clean_text(row.get("公司名稱")),
                market="TWSE",
                published_at=published,
                event_date=parse_roc_date(row.get("事實發生日")),
                title=clean_text(row.get("主旨 ")) or clean_text(row.get("主旨")) or "未提供主旨",
                description=clean_text(row.get("說明")),
                article=clean_text(row.get("符合條款")),
                metadata=SourceMetadata(
                    **self.http.provenance(url),
                    source="MOPS/TWSE",
                    source_url=url,
                    raw_source="MOPS 上市公司每日重大訊息（由 TWSE OpenAPI 發布）",
                    period_start=published.date() if published else None,
                    period_end=published.date() if published else None,
                    stale=is_stale(published, self.settings.stale_hours),
                ),
            ))
        return result

    async def news(self, limit: int = 50) -> list[NewsItem]:
        url = self._url("news/newsList")
        rows = await self._rows("news/newsList")
        result = []
        for row in rows[:limit]:
            published = parse_datetime(row.get("Date"))
            result.append(NewsItem(
                title=clean_text(row.get("Title")) or "未提供標題",
                url=clean_text(row.get("Url")) or url,
                published_at=published,
                source="TWSE",
                metadata=SourceMetadata(
                    **self.http.provenance(url),
                    source="TWSE",
                    source_url=url,
                    raw_source="TWSE OpenAPI：證交所新聞",
                    period_start=published.date() if published else None,
                    period_end=published.date() if published else None,
                    stale=is_stale(published, 24 * 14),
                ),
            ))
        return result

    async def health(self) -> HealthResult:
        started = time.perf_counter()
        url = self._url("exchangeReport/STOCK_DAY_ALL")
        rows = await self._rows("exchangeReport/STOCK_DAY_ALL")
        dates = [value for row in rows if (value := parse_roc_date(row.get("Date")))]
        latest = max(dates, default=None)
        stale = is_stale(latest, self.settings.stale_hours)
        return HealthResult(
            source=self.name,
            status="stale" if stale else "healthy",
            latency_ms=round((time.perf_counter() - started) * 1000),
            record_count=len(rows),
            latest_data_at=latest,
            message="已連線；資料可能過期" if stale else "已連線並取得上市日成交資料",
            endpoint=url,
        )
