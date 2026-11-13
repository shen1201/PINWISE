from __future__ import annotations

import asyncio
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from ..core.config import Settings
from ..core.http_client import ResilientHttpClient, UpstreamError
from ..core.models import HealthResult, NewsItem, SourceMetadata
from ..core.normalization import clean_text, is_stale
from .twse import TWSEProvider


class NewsProvider:
    name = "官方新聞"

    def __init__(self, settings: Settings, http: ResilientHttpClient, twse: TWSEProvider):
        self.settings = settings
        self.http = http
        self.twse = twse

    async def items(self, limit: int = 50) -> list[NewsItem]:
        # The OpenAPI feed exposes titles, links and dates and is suitable for the API.
        # A failed OpenAPI request may fall back once to official RSS. Full
        # article bodies are never copied and RSS retains its own provenance.
        try:
            return await self.twse.news(limit=limit)
        except (UpstreamError, ValueError):
            return await self.rss_items(limit=limit)

    async def rss_items(self, limit: int = 20) -> list[NewsItem]:
        xml_text = await self.http.get_text(self.name, self.settings.twse_news_rss_url, min_interval=0.5)
        root = ET.fromstring(xml_text)
        result = []
        for node in root.findall("./channel/item")[:limit]:
            title = clean_text(node.findtext("title")) or "未提供標題"
            link = urljoin(self.settings.twse_news_rss_url, clean_text(node.findtext("link")) or self.settings.twse_news_rss_url)
            published = None
            raw_date = clean_text(node.findtext("pubDate"))
            if raw_date:
                try:
                    published = parsedate_to_datetime(raw_date)
                except (TypeError, ValueError):
                    pass
            result.append(NewsItem(
                title=title,
                url=link,
                published_at=published,
                source="TWSE RSS",
                metadata=SourceMetadata(
                    **self.http.provenance(self.settings.twse_news_rss_url),
                    source="TWSE RSS",
                    source_url=self.settings.twse_news_rss_url,
                    raw_source="TWSE 官方新聞 RSS（僅標題、日期與原文連結）",
                    period_start=published.date() if published else None,
                    period_end=published.date() if published else None,
                    stale=is_stale(published, 24 * 14),
                ),
            ))
        return result

    async def health(self) -> HealthResult:
        started = time.perf_counter()
        results = await asyncio.gather(self.twse.news(10), self.rss_items(10), return_exceptions=True)
        if all(isinstance(row, Exception) for row in results):
            raise UpstreamError(self.name, "官方新聞 OpenAPI 與 RSS 均無法取得資料")
        openapi, rss = [row if isinstance(row, list) else [] for row in results]
        failures = [str(row) for row in results if isinstance(row, Exception)]
        latest_values = [item.published_at for item in openapi + rss if item.published_at]
        latest = max(latest_values, default=None)
        return HealthResult(
            source=self.name,
            status="healthy" if openapi and rss else "degraded",
            latency_ms=round((time.perf_counter() - started) * 1000),
            record_count=len(openapi) + len(rss),
            latest_data_at=latest,
            message="TWSE OpenAPI 與官方 RSS 均可讀取；僅保存標題、日期與原文連結" if openapi and rss else "至少一個官方新聞管道沒有資料；" + "；".join(failures),
            endpoint=f"{self.settings.twse_base_url}/news/newsList + {self.settings.twse_news_rss_url}",
        )
