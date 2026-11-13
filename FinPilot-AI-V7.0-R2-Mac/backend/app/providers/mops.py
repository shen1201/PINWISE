from __future__ import annotations

import asyncio
import time

from ..core.config import Settings
from ..core.http_client import ResilientHttpClient
from ..core.models import CompanyProfile, DisclosureEvent, HealthResult
from .tpex import TPExProvider
from .twse import TWSEProvider


class MOPSProvider:
    """MOPS data exposed through documented TWSE/TPEx OpenAPI datasets.

    The MOPS website itself blocks unattended direct requests and does not publish a
    stable general-purpose JSON API for the pages used here.  This provider therefore
    uses the exchange OpenAPI datasets whose titles explicitly identify MOPS company
    data, and preserves that provenance on every record.
    """

    name = "MOPS"

    def __init__(self, settings: Settings, http: ResilientHttpClient, twse: TWSEProvider, tpex: TPExProvider):
        self.settings = settings
        self.http = http
        self.twse = twse
        self.tpex = tpex

    async def company(self, symbol: str) -> CompanyProfile | None:
        results = await asyncio.gather(self.twse.company(symbol), self.tpex.company(symbol), return_exceptions=True)
        for result in results:
            if isinstance(result, CompanyProfile):
                return result
        errors = [result for result in results if isinstance(result, Exception)]
        if len(errors) == len(results):
            raise errors[0]
        return None

    async def disclosures(self, symbol: str | None = None, limit: int = 200) -> list[DisclosureEvent]:
        results = await asyncio.gather(self.twse.disclosures(symbol), self.tpex.disclosures(symbol), return_exceptions=True)
        errors = [result for result in results if isinstance(result, Exception)]
        if len(errors) == len(results):
            raise errors[0]
        listed, otc = [result if isinstance(result, list) else [] for result in results]
        rows = sorted(listed + otc, key=lambda item: item.published_at or item.metadata.fetched_at, reverse=True)
        return rows[:limit]

    async def health(self) -> HealthResult:
        started = time.perf_counter()
        results = await asyncio.gather(self.twse.disclosures(), self.tpex.disclosures(), return_exceptions=True)
        if all(isinstance(result, Exception) for result in results):
            raise results[0]
        listed, otc = [result if isinstance(result, list) else [] for result in results]
        partial = any(isinstance(result, Exception) for result in results)
        rows = listed + otc
        latest = max((row.published_at for row in rows if row.published_at), default=None)
        return HealthResult(
            source=self.name,
            status="degraded" if partial or not rows else "healthy",
            latency_ms=round((time.perf_counter() - started) * 1000),
            record_count=len(rows),
            latest_data_at=latest,
            message=("部分市場連線失敗，已保留可用的重大訊息" if partial else "已取得上市與上櫃每日重大訊息；直接 MOPS 網頁查詢不作自動爬取") if rows else "端點可連線，但目前沒有重大訊息資料列",
            endpoint=f"{self.settings.twse_base_url}/opendata/t187ap04_L + {self.settings.tpex_base_url}/mopsfin_t187ap04_O",
        )
