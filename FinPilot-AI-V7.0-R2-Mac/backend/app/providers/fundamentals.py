"""Official valuation, monthly revenue and earnings from TWSE / TPEx OpenAPI.

All six datasets are free, key-less official publications:
- valuation (P/E, dividend yield, P/B): TWSE BWIBBU_ALL, TPEx peratio analysis
- monthly revenue (MOPS): TWSE t187ap05_L, TPEx mopsfin_t187ap05_O
- cumulative earnings incl. EPS (MOPS): TWSE t187ap14_L, TPEx mopsfin_t187ap14_O
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from ..core.config import Settings
from ..core.http_client import ResilientHttpClient
from ..core.models import FundamentalSnapshot, HealthResult, SourceMetadata
from ..core.normalization import clean_text, is_stale, parse_number, parse_roc_date

CACHE_SECONDS = 1800


def _pct(value: Any) -> float | None:
    number = parse_number(value)
    return None if number is None else round(number, 2)


def _ratio(value: Any) -> float | None:
    number = parse_number(value)
    # Exchanges publish 0 or blank when a ratio is not meaningful (e.g. losses).
    return None if number is None or number <= 0 else round(number, 2)


def _roc_month(value: Any) -> str | None:
    digits = re.sub(r"\D", "", clean_text(value) or "")
    if len(digits) == 5:
        return f"{int(digits[:3]) + 1911}-{digits[3:]}"
    return None


def _first(row: dict[str, Any], *keys: str) -> Any:
    return next((row[key] for key in keys if key in row and clean_text(row[key]) is not None), None)


class FundamentalsProvider:
    name = "官方基本面"

    def __init__(self, settings: Settings, http: ResilientHttpClient):
        self.settings = settings
        self.http = http
        self.errors: dict[str, str] = {}

    def _endpoints(self) -> dict[tuple[str, str], str]:
        twse, tpex = self.settings.twse_base_url, self.settings.tpex_base_url
        return {
            ("TWSE", "valuation"): f"{twse}/exchangeReport/BWIBBU_ALL",
            ("TWSE", "revenue"): f"{twse}/opendata/t187ap05_L",
            ("TWSE", "earnings"): f"{twse}/opendata/t187ap14_L",
            ("TPEX", "valuation"): f"{tpex}/tpex_mainboard_peratio_analysis",
            ("TPEX", "revenue"): f"{tpex}/mopsfin_t187ap05_O",
            ("TPEX", "earnings"): f"{tpex}/mopsfin_t187ap14_O",
        }

    async def _rows(self, url: str) -> list[dict[str, Any]]:
        data = await self.http.get_json(self.name, url, cache_ttl=CACHE_SECONDS, min_interval=0.25)
        if not isinstance(data, list):
            raise ValueError("官方 OpenAPI 回傳格式不是資料列陣列")
        return data

    async def snapshots(self) -> dict[str, FundamentalSnapshot]:
        endpoints = self._endpoints()
        results = await asyncio.gather(*(self._rows(url) for url in endpoints.values()), return_exceptions=True)
        self.errors = {}
        snapshots: dict[str, dict[str, Any]] = {}

        def entry(symbol: str, market: str) -> dict[str, Any]:
            return snapshots.setdefault(symbol, {"symbol": symbol, "market": market, "sources": []})

        for (market, kind), url, rows in zip(endpoints, endpoints.values(), results):
            if isinstance(rows, Exception):
                self.errors[f"{market} {kind}"] = str(rows) or type(rows).__name__
                continue
            for row in rows:
                symbol = clean_text(_first(row, "Code", "SecuritiesCompanyCode", "公司代號"))
                if not symbol:
                    continue
                item = entry(symbol, market)
                item["name"] = item.get("name") or clean_text(_first(row, "Name", "CompanyName", "公司名稱"))
                item["sources"].append(url)
                if kind == "valuation":
                    item.update(
                        valuation_date=parse_roc_date(_first(row, "Date")),
                        pe_ratio=_ratio(_first(row, "PEratio", "PriceEarningRatio")),
                        dividend_yield_pct=_pct(_first(row, "DividendYield", "YieldRatio")),
                        pb_ratio=_ratio(_first(row, "PBratio", "PriceBookRatio")),
                    )
                elif kind == "revenue":
                    item.update(
                        industry_name=clean_text(row.get("產業別")) or item.get("industry_name"),
                        revenue_month=_roc_month(row.get("資料年月")),
                        revenue_thousand_twd=parse_number(row.get("營業收入-當月營收")),
                        revenue_mom_pct=_pct(row.get("營業收入-上月比較增減(%)")),
                        revenue_yoy_pct=_pct(row.get("營業收入-去年同月增減(%)")),
                        revenue_ytd_yoy_pct=_pct(row.get("累計營業收入-前期比較增減(%)")),
                    )
                else:
                    year = parse_number(_first(row, "年度", "Year"))
                    quarter = clean_text(row.get("季別"))
                    revenue = parse_number(row.get("營業收入"))
                    operating = parse_number(row.get("營業利益"))
                    item.update(
                        industry_name=item.get("industry_name") or clean_text(row.get("產業別")),
                        eps_period=f"{int(year) + 1911} 年第 {quarter} 季累計" if year and quarter else None,
                        eps_ytd=parse_number(_first(row, "基本每股盈餘(元)", "基本每股盈餘")),
                        operating_margin_pct=round(operating / revenue * 100, 2) if revenue and operating is not None else None,
                    )

        result = {}
        for symbol, item in snapshots.items():
            sources = list(dict.fromkeys(item.pop("sources")))
            valuation_date = item.get("valuation_date")
            result[symbol] = FundamentalSnapshot(**item, sources=sources, metadata=SourceMetadata(
                **self.http.provenance(sources[0]),
                source="TWSE／TPEx／MOPS", source_url=sources[0],
                raw_source="官方 OpenAPI：本益比／殖利率／股價淨值比、月營收、綜合損益（EPS）",
                period_start=valuation_date, period_end=valuation_date,
                stale=is_stale(valuation_date, self.settings.stale_hours) if valuation_date else False,
            ))
        return result

    async def snapshot(self, symbol: str) -> FundamentalSnapshot | None:
        return (await self.snapshots()).get(symbol)

    async def health(self) -> HealthResult:
        started = time.perf_counter()
        snapshots = await self.snapshots()
        dates = [item.valuation_date for item in snapshots.values() if item.valuation_date]
        ok = bool(snapshots) and not self.errors
        return HealthResult(
            source=self.name, status="healthy" if ok else ("degraded" if snapshots else "error"),
            latency_ms=round((time.perf_counter() - started) * 1000), record_count=len(snapshots),
            latest_data_at=max(dates, default=None),
            message="已取得上市櫃估值、月營收與 EPS" if ok else f"部分資料集失敗：{'、'.join(self.errors) or '無資料'}",
            endpoint=next(iter(self._endpoints().values())),
        )
