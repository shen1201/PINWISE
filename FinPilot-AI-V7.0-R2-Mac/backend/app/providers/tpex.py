from __future__ import annotations

import time

from ..core.config import Settings
from ..core.http_client import ResilientHttpClient
from ..core.models import CompanyProfile, DisclosureEvent, HealthResult, MarketQuote, SourceMetadata
from ..core.normalization import clean_text, is_stale, parse_datetime, parse_integer, parse_number, parse_roc_date


class TPExProvider:
    name = "TPEx"

    def __init__(self, settings: Settings, http: ResilientHttpClient):
        self.settings = settings
        self.http = http

    def _url(self, path: str) -> str:
        return f"{self.settings.tpex_base_url}/{path.lstrip('/')}"

    async def _rows(self, path: str):
        data = await self.http.get_json(self.name, self._url(path), min_interval=0.25)
        if not isinstance(data, list):
            raise ValueError("TPEx 回傳格式不是資料列陣列")
        return data

    async def market_summary(self) -> list[dict]:
        """櫃買指數與上櫃成交金額（官方盤後日資料，最近數個交易日，舊到新）。"""
        rows = await self._rows("tpex_daily_trading_index")
        return [{
            "date": parse_roc_date(row.get("Date")),
            "index": parse_number(row.get("TPExIndex")),
            "change": parse_number(row.get("Change")),
            "trade_value_twd": parse_integer(row.get("TradeAmount")),
        } for row in rows if clean_text(row.get("Date"))]

    def _quote_from_row(self, row) -> MarketQuote:
        url = self._url("tpex_mainboard_quotes")
        symbol = clean_text(row.get("SecuritiesCompanyCode")) or ""
        trade_date = parse_roc_date(row.get("Date"))
        return MarketQuote(
            symbol=symbol,
            name=clean_text(row.get("CompanyName")),
            market="TPEX",
            trade_date=trade_date,
            open=parse_number(row.get("Open")),
            high=parse_number(row.get("High")),
            low=parse_number(row.get("Low")),
            close=parse_number(row.get("Close")),
            change=parse_number(row.get("Change")),
            volume_shares=parse_integer(row.get("TradingShares")),
            trade_value_twd=parse_integer(row.get("TransactionAmount")),
            transactions=parse_integer(row.get("TransactionNumber")),
            metadata=SourceMetadata(
                **self.http.provenance(url),
                source=self.name,
                source_url=url,
                raw_source="TPEx OpenAPI：上櫃股票收盤行情",
                period_start=trade_date,
                period_end=trade_date,
                stale=is_stale(trade_date, self.settings.stale_hours),
            ),
        )

    async def quotes(self) -> list[MarketQuote]:
        rows = await self._rows("tpex_mainboard_quotes")
        return [self._quote_from_row(row) for row in rows if clean_text(row.get("SecuritiesCompanyCode"))]

    async def quote(self, symbol: str) -> MarketQuote | None:
        rows = await self._rows("tpex_mainboard_quotes")
        row = next((item for item in rows if clean_text(item.get("SecuritiesCompanyCode")) == symbol), None)
        return self._quote_from_row(row) if row else None

    async def company(self, symbol: str) -> CompanyProfile | None:
        url = self._url("mopsfin_t187ap03_O")
        rows = await self._rows("mopsfin_t187ap03_O")
        row = next((item for item in rows if clean_text(item.get("SecuritiesCompanyCode")) == symbol), None)
        if not row:
            return None
        report_date = parse_roc_date(row.get("Date"))
        return CompanyProfile(
            symbol=symbol,
            name=clean_text(row.get("CompanyName")),
            short_name=clean_text(row.get("CompanyAbbreviation")),
            market="TPEX",
            industry_code=clean_text(row.get("SecuritiesIndustryCode")),
            listing_date=parse_roc_date(row.get("DateOfListing")),
            website=clean_text(row.get("WebAddress")),
            paid_in_capital_twd=parse_number(row.get("Paidin.Capital.NTDollars")),
            issued_shares=parse_integer(row.get("IssueShares")),
            metadata=SourceMetadata(
                **self.http.provenance(url),
                source="MOPS/TPEx",
                source_url=url,
                raw_source="MOPS 上櫃公司基本資料（由 TPEx OpenAPI 發布）",
                period_start=report_date,
                period_end=report_date,
                stale=is_stale(report_date, 24 * 14),
            ),
        )

    async def companies(self) -> list[CompanyProfile]:
        rows = await self._rows("mopsfin_t187ap03_O")
        result = []
        for row in rows:
            symbol = clean_text(row.get("SecuritiesCompanyCode"))
            if not symbol:
                continue
            report_date = parse_roc_date(row.get("Date"))
            result.append(CompanyProfile(
                symbol=symbol,
                name=clean_text(row.get("CompanyName")),
                short_name=clean_text(row.get("CompanyAbbreviation")),
                market="TPEX",
                industry_code=clean_text(row.get("SecuritiesIndustryCode")),
                listing_date=parse_roc_date(row.get("DateOfListing")),
                website=clean_text(row.get("WebAddress")),
                paid_in_capital_twd=parse_number(row.get("Paidin.Capital.NTDollars")),
                issued_shares=parse_integer(row.get("IssueShares")),
                metadata=SourceMetadata(
                    **self.http.provenance(self._url("mopsfin_t187ap03_O")),
                    source="MOPS/TPEx", source_url=self._url("mopsfin_t187ap03_O"),
                    raw_source="MOPS 上櫃公司基本資料（由 TPEx OpenAPI 發布）",
                    period_start=report_date, period_end=report_date,
                    stale=is_stale(report_date, 24 * 14),
                ),
            ))
        return result

    async def disclosures(self, symbol: str | None = None) -> list[DisclosureEvent]:
        url = self._url("mopsfin_t187ap04_O")
        rows = await self._rows("mopsfin_t187ap04_O")
        result = []
        for row in rows:
            code = clean_text(row.get("SecuritiesCompanyCode")) or ""
            if symbol and code != symbol:
                continue
            published = parse_datetime(row.get("發言日期"), row.get("發言時間"))
            result.append(DisclosureEvent(
                symbol=code,
                company_name=clean_text(row.get("CompanyName")),
                market="TPEX",
                published_at=published,
                event_date=parse_roc_date(row.get("事實發生日")),
                title=clean_text(row.get("主旨")) or "未提供主旨",
                description=clean_text(row.get("說明")),
                article=clean_text(row.get("符合條款")),
                metadata=SourceMetadata(
                    **self.http.provenance(url),
                    source="MOPS/TPEx",
                    source_url=url,
                    raw_source="MOPS 上櫃公司每日重大訊息（由 TPEx OpenAPI 發布）",
                    period_start=published.date() if published else None,
                    period_end=published.date() if published else None,
                    stale=is_stale(published, self.settings.stale_hours),
                ),
            ))
        return result

    async def health(self) -> HealthResult:
        started = time.perf_counter()
        url = self._url("tpex_mainboard_quotes")
        rows = await self._rows("tpex_mainboard_quotes")
        dates = [value for row in rows if (value := parse_roc_date(row.get("Date")))]
        latest = max(dates, default=None)
        stale = is_stale(latest, self.settings.stale_hours)
        return HealthResult(
            source=self.name,
            status="stale" if stale else "healthy",
            latency_ms=round((time.perf_counter() - started) * 1000),
            record_count=len(rows),
            latest_data_at=latest,
            message="已連線；資料可能過期" if stale else "已連線並取得上櫃收盤行情",
            endpoint=url,
        )
