from __future__ import annotations

import asyncio
import json
import re
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..core.models import CompanyProfile, DisclosureEvent, HealthResult, MarketQuote, NewsItem, PricePoint, SourceMetadata


PREVIEW_DATE = date(2026, 10, 8)
PREVIEW_SOURCE = "https://preview.finpilot.invalid/isolated-data"
PREVIEW_ROWS = {
    "2330": {"name": "台積電", "full": "台灣積體電路製造股份有限公司", "market": "TWSE", "industry": "24", "close": 100.0},
    "2454": {"name": "聯發科", "full": "聯發科技股份有限公司", "market": "TWSE", "industry": "24", "close": 80.0},
    "3374": {"name": "精材", "full": "精材科技股份有限公司", "market": "TPEX", "industry": "24", "close": 50.0},
    "3535": {"name": "晶彩科", "full": "晶彩科技股份有限公司", "market": "TPEX", "industry": "25", "close": 40.0},
    "2327": {"name": "國巨", "full": "國巨股份有限公司", "market": "TWSE", "industry": "28", "close": 100.0},
    "2492": {"name": "華新科", "full": "華新科技股份有限公司", "market": "TWSE", "industry": "28", "close": 80.0},
    "3026": {"name": "禾伸堂", "full": "禾伸堂企業股份有限公司", "market": "TWSE", "industry": "28", "close": 60.0},
    "5425": {"name": "台半", "full": "台灣半導體股份有限公司", "market": "TPEX", "industry": "24", "close": 50.0},
    "0050": {"name": "元大台灣50", "full": "元大台灣卓越50證券投資信託基金", "market": "TWSE", "industry": None, "close": 60.0},
    "0056": {"name": "元大高股息", "full": "元大台灣高股息證券投資信託基金", "market": "TWSE", "industry": None, "close": 38.0},
    "006208": {"name": "富邦台50", "full": "富邦台灣采吉50證券投資信託基金", "market": "TWSE", "industry": None, "close": 120.0},
    "00713": {"name": "元大台灣高息低波", "full": "元大台灣高股息低波動證券投資信託基金", "market": "TWSE", "industry": None, "close": 52.0},
    "00878": {"name": "國泰永續高股息", "full": "國泰台灣ESG永續高股息證券投資信託基金", "market": "TWSE", "industry": None, "close": 22.0},
    "00891": {"name": "中信關鍵半導體", "full": "中國信託臺灣ESG永續關鍵半導體證券投資信託基金", "market": "TWSE", "industry": None, "close": 18.0},
    "00919": {"name": "群益台灣精選高息", "full": "群益台灣精選高息證券投資信託基金", "market": "TWSE", "industry": None, "close": 24.0},
    "00927": {"name": "群益半導體收益", "full": "群益台灣半導體收益證券投資信託基金", "market": "TWSE", "industry": None, "close": 20.0},
    "0052": {"name": "富邦科技", "full": "富邦台灣科技指數證券投資信託基金", "market": "TWSE", "industry": None, "close": 145.0},
}


def _metadata(source: str, raw: str, *, start: date | None = PREVIEW_DATE, end: date | None = PREVIEW_DATE) -> SourceMetadata:
    return SourceMetadata(
        source=source,
        source_url=PREVIEW_SOURCE,
        raw_source=f"PINWISE 隔離預覽資料：{raw}",
        period_start=start,
        period_end=end,
        stale=False,
        data_status="fixture",
    )


class PreviewExchangeProvider:
    def __init__(self, market: str):
        self.market = market
        self.name = f"{market}（隔離預覽）"

    def _row(self, symbol: str) -> dict[str, Any] | None:
        row = PREVIEW_ROWS.get(symbol)
        return row if row and row["market"] == self.market else None

    def _quote(self, symbol: str, row: dict[str, Any]) -> MarketQuote:
        close = float(row["close"])
        return MarketQuote(
            symbol=symbol,
            name=row["name"],
            market=self.market,
            trade_date=PREVIEW_DATE,
            open=round(close * 0.99, 2),
            high=round(close * 1.02, 2),
            low=round(close * 0.98, 2),
            close=close,
            change=round(close * 0.01, 2),
            volume_shares=1_000_000 + int(symbol) % 500_000,
            trade_value_twd=int(close * 1_000_000),
            transactions=8_000 + int(symbol) % 2_000,
            metadata=_metadata(self.name, "固定日行情；不連接交易所"),
        )

    def _company(self, symbol: str, row: dict[str, Any]) -> CompanyProfile:
        return CompanyProfile(
            symbol=symbol,
            name=row["full"],
            short_name=row["name"],
            market=self.market,
            industry_code=row["industry"],
            listing_date=date(2000, 1, 1),
            website=None,
            paid_in_capital_twd=None,
            issued_shares=None,
            metadata=_metadata(f"MOPS/{self.market}（隔離預覽）", "固定公司清單；不連接 MOPS"),
        )

    async def quotes(self) -> list[MarketQuote]:
        return [self._quote(symbol, row) for symbol, row in PREVIEW_ROWS.items() if row["market"] == self.market]

    async def quote(self, symbol: str) -> MarketQuote | None:
        row = self._row(symbol)
        return self._quote(symbol, row) if row else None

    async def companies(self) -> list[CompanyProfile]:
        return [self._company(symbol, row) for symbol, row in PREVIEW_ROWS.items() if row["market"] == self.market]

    async def company(self, symbol: str) -> CompanyProfile | None:
        row = self._row(symbol)
        return self._company(symbol, row) if row else None

    async def disclosures(self, symbol: str | None = None) -> list[DisclosureEvent]:
        rows = []
        for code, row in PREVIEW_ROWS.items():
            if row["market"] != self.market or (symbol and code != symbol) or row["industry"] is None:
                continue
            rows.append(DisclosureEvent(
                symbol=code,
                company_name=row["name"],
                market=self.market,
                published_at=datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc),
                event_date=date(2026, 10, 7),
                title="隔離預覽公告：資料管道驗收",
                description="此內容只用於線上預覽，不代表真實公司公告。",
                metadata=_metadata(f"MOPS/{self.market}（隔離預覽）", "固定重大訊息；不連接 MOPS"),
            ))
        return rows

    async def news(self, limit: int = 50) -> list[NewsItem]:
        if self.market != "TWSE":
            return []
        return [NewsItem(
            title="PINWISE 隔離預覽新聞資料",
            url=PREVIEW_SOURCE,
            published_at=datetime(2026, 10, 8, 1, 0, tzinfo=timezone.utc),
            source="TWSE（隔離預覽）",
            summary="固定驗收內容，不代表真實新聞。",
            metadata=_metadata("TWSE（隔離預覽）", "固定新聞標題；不連接外部網站"),
        )][:limit]

    async def health(self) -> HealthResult:
        return HealthResult(
            source=self.market,
            status="healthy",
            record_count=len(await self.quotes()),
            latest_data_at=PREVIEW_DATE,
            message="隔離預覽資料已啟用；未連接真實交易所",
            endpoint=PREVIEW_SOURCE,
        )


class PreviewFinMindProvider:
    name = "FinMind（隔離預覽）"

    async def market(self, symbol: str) -> str:
        return str(PREVIEW_ROWS.get(symbol, {}).get("market") or "UNKNOWN")

    async def history(self, symbol: str, start_date: date, end_date: date) -> list[PricePoint]:
        row = PREVIEW_ROWS.get(symbol)
        if not row:
            return []
        result: list[PricePoint] = []
        cursor = max(start_date, date(2026, 1, 2))
        final = min(end_date, PREVIEW_DATE)
        index = 0
        base = float(row["close"]) * 0.82
        total_days = max(1, (PREVIEW_DATE - date(2026, 1, 2)).days)
        while cursor <= final:
            if cursor.weekday() < 5:
                ratio = (cursor - date(2026, 1, 2)).days / total_days
                close = round(base + (float(row["close"]) - base) * ratio + ((index % 7) - 3) * 0.08, 2)
                result.append(PricePoint(
                    symbol=symbol,
                    market=row["market"],
                    trade_date=cursor,
                    open=round(close * 0.995, 2),
                    high=round(close * 1.012, 2),
                    low=round(close * 0.988, 2),
                    close=close,
                    change=round(close * 0.003, 2),
                    volume_shares=900_000 + (index % 15) * 12_000,
                    trade_value_twd=int(close * (900_000 + (index % 15) * 12_000)),
                    transactions=7_500 + index % 800,
                    metadata=_metadata(self.name, "固定歷史日價；不連接 FinMind", start=start_date, end=end_date),
                ))
                index += 1
            cursor += timedelta(days=1)
        return result

    async def health(self) -> HealthResult:
        return HealthResult(
            source="FinMind",
            status="healthy",
            record_count=len(PREVIEW_ROWS),
            latest_data_at=PREVIEW_DATE,
            message="隔離預覽歷史資料已啟用；未連接 FinMind",
            endpoint=PREVIEW_SOURCE,
        )


class PreviewNewsProvider:
    name = "官方新聞（隔離預覽）"

    def __init__(self, twse: PreviewExchangeProvider):
        self.twse = twse

    async def items(self, limit: int = 50) -> list[NewsItem]:
        return await self.twse.news(limit)

    async def rss_items(self, limit: int = 20) -> list[NewsItem]:
        return await self.twse.news(limit)

    async def health(self) -> HealthResult:
        return HealthResult(source="官方新聞", status="healthy", record_count=1, latest_data_at=PREVIEW_DATE,
                            message="隔離預覽資料已啟用；未連接新聞來源", endpoint=PREVIEW_SOURCE)


class PreviewIRProvider:
    name = "公司法說會（隔離預覽）"

    async def conferences(self, symbol: str | None = None, limit: int = 100) -> list[Any]:
        return []

    async def health(self) -> HealthResult:
        return HealthResult(source="公司法說會", status="degraded", record_count=0, latest_data_at=PREVIEW_DATE,
                            message="隔離預覽未提供法說資料，缺漏會保留", endpoint=PREVIEW_SOURCE)


class PreviewGeminiProvider:
    """Deterministic model-shaped fixture. It never opens a network connection."""

    name = "Gemini（隔離替身）"
    available = True
    is_fixture = True

    def __init__(self, settings):
        self.settings = replace(settings, gemini_model="finpilot-preview-fixture")

    async def health(self) -> HealthResult:
        return HealthResult(source="Gemini", status="disabled", record_count=0,
                            message="真實 Gemini 已關閉；使用隔離替身且不產生成本", endpoint=None)

    @staticmethod
    def _payload(prompt: str) -> dict[str, Any]:
        start = prompt.find("{")
        if start < 0:
            return {}
        try:
            return json.loads(prompt[start:])
        except (ValueError, TypeError):
            return {}

    async def generate_research(self, prompt: str) -> dict[str, Any]:
        payload = self._payload(prompt)
        symbols = [str(value) for value in payload.get("verified_symbols", []) if str(value) in PREVIEW_ROWS]
        await asyncio.sleep(0.08)
        return {
            "summary": "這是隔離預覽研究；量化數值以後端保存的程式計算指標為準，不代表目前市場狀況。",
            "risks": ["隔離資料不是目前行情", "預覽資料不包含完整公告與法說", "正式判斷前必須重新取得真實來源"],
            "candidates": symbols,
            "evidence_notes": ["只使用隔離預覽資料"],
            "invalidation_conditions": ["切換至真實資料後結果可能改變", "來源日期或欄位改變時需重新計算", "缺漏資料補齊後需重新檢查"],
            "limitations": ["本次未呼叫 Gemini、交易所、FinMind、MOPS、新聞或法說來源"],
            "_usage": {"total_token_count": 0, "fixture": True},
        }

    async def stream_assistant(self, prompt: str):
        payload = self._payload(prompt)
        tools = payload.get("tool_results") or []
        message = str(payload.get("current_message") or "")
        if tools:
            answers = []
            for tool in tools:
                if tool.get("status") != "completed":
                    continue
                data = tool.get("data") or {}
                if tool.get("tool") == "market_snapshot":
                    quote = data.get("quote") or {}
                    answers.append(
                        f"{tool.get('symbol')} {data.get('name') or ''} 在 {quote.get('trade_date') or data.get('as_of')} "
                        f"的隔離日收盤為 {quote.get('close')} 元。這是固定預覽資料，不是即時報價。"
                    )
            text = "\n".join(answers) or "隔離預覽資料中沒有足夠欄位可回答；未改用真實來源。"
        elif re.search(r"roe", message, re.I):
            text = "ROE 用來觀察公司運用股東權益創造獲利的效率；仍需搭配產業、負債與期間一起判讀。這是隔離預覽回答。"
        else:
            text = "這是 PINWISE 隔離預覽回答。真實 Gemini 與外部資料來源均未啟用。"
        for index in range(0, len(text), 12):
            yield {"text": text[index:index + 12]}
            await asyncio.sleep(0.025)
        yield {"usage": {"total_token_count": 0, "fixture": True}}
