from __future__ import annotations

import re
import time

from ..core.config import Settings
from ..core.models import HealthResult, InvestorConference, SourceMetadata
from .mops import MOPSProvider


IR_PATTERN = re.compile(r"法人說明會|法說會|investor\s*conference", re.IGNORECASE)


class InvestorRelationsProvider:
    name = "公司法說會"

    def __init__(self, settings: Settings, mops: MOPSProvider):
        self.settings = settings
        self.mops = mops

    async def conferences(self, symbol: str | None = None, limit: int = 100) -> list[InvestorConference]:
        events = await self.mops.disclosures(symbol=symbol, limit=500)
        result = []
        for event in events:
            searchable = "\n".join(filter(None, [event.title, event.description]))
            if not IR_PATTERN.search(searchable):
                continue
            metadata = SourceMetadata(
                source=event.metadata.source,
                source_url=event.metadata.source_url,
                fetched_at=event.metadata.fetched_at,
                raw_source="MOPS 每日重大訊息中的法人說明會公告",
                period_start=event.metadata.period_start,
                period_end=event.metadata.period_end,
                missing=False,
                stale=event.metadata.stale,
                data_status=event.metadata.data_status,
            )
            result.append(InvestorConference(
                symbol=event.symbol,
                company_name=event.company_name,
                market=event.market,
                announced_at=event.published_at,
                event_date=event.event_date,
                title=event.title,
                details=event.description,
                metadata=metadata,
            ))
        return result[:limit]

    async def health(self) -> HealthResult:
        started = time.perf_counter()
        # A zero count is a valid daily result; endpoint health is inherited from the
        # successfully fetched MOPS disclosure feeds rather than from event presence.
        events = await self.mops.disclosures(limit=500)
        conferences = [event for event in events if IR_PATTERN.search("\n".join(filter(None, [event.title, event.description])))]
        latest = max((event.published_at for event in events if event.published_at), default=None)
        return HealthResult(
            source=self.name,
            status="degraded",
            latency_ms=round((time.perf_counter() - started) * 1000),
            record_count=len(conferences),
            latest_data_at=latest,
            message="已連線每日法說會公告；MOPS 歷史法說會頁面沒有穩定公開 JSON API，故未宣稱完整歷史覆蓋",
            endpoint=f"{self.settings.twse_base_url}/opendata/t187ap04_L + {self.settings.tpex_base_url}/mopsfin_t187ap04_O",
        )
