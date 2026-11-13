from __future__ import annotations

import os
import time
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["FINPILOT_SKIP_DOTENV"] = "1"

import httpx
from fastapi.testclient import TestClient

from backend.app import main as api
from backend.app.core.config import load_settings
from backend.app.core.http_client import ResilientHttpClient, UpstreamError
from backend.app.core.models import HealthResult, MarketQuote, PricePoint, SourceMetadata
from backend.app.security.preview_security import DemoSessionError, DemoSessionManager
from backend.app.core.provenance import require_live_data
from backend.app.providers.finmind import FinMindProvider
from backend.app.providers.gemini import GeminiProvider
from backend.app.providers.news import NewsProvider
from backend.app.services.analytics import completeness, price_metrics
from backend.app.services.market import MarketService
from backend.app.services.research import ResearchService, compact_prompt_evidence


def metadata(**kwargs):
    return SourceMetadata(source="FinMind", source_url="https://api.finmindtrade.com/api/v4/data", raw_source="public", **kwargs)


class ProvenanceTests(unittest.TestCase):
    def test_coverage_counts_evidence_not_configured_providers(self):
        rows = [dict(source="2327 歷史日行情", evidence_id="a", url="https://example.org/data", data_status="real"),
                dict(source="2327 公司基本資料", evidence_id="b", url="https://example.org/company", data_status="cache", stale=True),
                dict(source="Gemini", url="https://example.org/model", data_status="real"),
                dict(source="preview", url="https://preview.finpilot.invalid/source", data_status="real"),
                dict(source="fixture", url="https://example.org/data", data_status="fixture"),
                dict(source="unverified", url="https://example.org/data", data_status="unverified"),
                dict(source="missing", missing=True, data_status="missing")]
        coverage = completeness(rows)
        self.assertEqual(coverage["available_sources"], 2)
        self.assertEqual(coverage["total_sources"], 7)
        self.assertEqual(coverage["verified_evidence_ids"], ["a", "b"])
        self.assertEqual(coverage["fixture_sources"], 1)
        self.assertEqual(coverage["stale_sources"], 1)

    def test_live_guard_rejects_nested_fixture_and_invalid_links(self):
        for value in ({"rows": [{"metadata": {"data_status": "fixture"}}]},
                      {"source_url": "https://preview.finpilot.invalid/evidence"}):
            with self.assertRaises(ValueError):
                require_live_data(value)
        require_live_data({"source_url": "https://example.org/evidence", "data_status": "real"})

    def test_metrics_reject_cross_symbol_data_and_zero_closes(self):
        point = lambda code, day, close: PricePoint(symbol=code, trade_date=date(2026, 10, day), close=close, metadata=metadata())
        with self.assertRaises(ValueError):
            price_metrics([point("2327", 1, 100), point("2492", 2, 110)])
        result = price_metrics([point("2327", 1, 100), point("2327", 2, 0), point("2327", 3, 120), point("2327", 3, 120)])
        self.assertEqual(result["observations"], 2)
        self.assertEqual(result["period_return_pct"], 20)
        self.assertEqual(result["period_end"], "2026-10-03")

    def test_evidence_preserves_fetch_date_symbol_and_actual_period(self):
        fetched = datetime(2026, 10, 10, tzinfo=timezone.utc)
        rows = [PricePoint(symbol="2327", trade_date=date(2026, 10, day), close=100+day,
                           metadata=metadata(data_status="cache", fetched_at=fetched)) for day in (8, 9)]
        item = ResearchService._evidence("2327 歷史日行情", rows)
        self.assertEqual(item["fetched_at"], fetched.isoformat())
        self.assertEqual(item["subjects"], ["2327"])
        self.assertEqual(item["period_start"], "2026-10-08")
        self.assertEqual(item["latest_data_at"], "2026-10-09")
        self.assertEqual(item["data_status"], "cache")

    def test_prompt_compaction_does_not_mutate_full_evidence(self):
        original = {"source": "2327 歷史日行情", "data_status": "real", "data": [{"close": n, "metadata": {"source": "FinMind"}} for n in range(30)]}
        compact = compact_prompt_evidence([original])[0]
        self.assertEqual(len(original["data"]), 30)
        self.assertEqual(compact["data"], [{"close": 28}, {"close": 29}])
        self.assertEqual(compact["data_status"], "real")


class ProviderProvenanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_response_keeps_original_network_fetch_time(self):
        client = ResilientHttpClient(1, 0, 100)
        response = httpx.Response(200, json={"ok": True})
        try:
            with patch.object(client._client, "get", AsyncMock(return_value=response)) as request:
                await client.get_json("test", "https://example.org/public", min_interval=0)
                first = client.provenance("https://example.org/public")
                await client.get_json("test", "https://example.org/public", min_interval=0)
                cached = client.provenance("https://example.org/public")
            self.assertEqual(first["data_status"], "real")
            self.assertEqual(cached["data_status"], "cache")
            self.assertEqual(first["fetched_at"], cached["fetched_at"])
            request.assert_awaited_once()
        finally:
            await client.close()

    async def test_finmind_rejects_wrong_symbol_and_filters_period_duplicates(self):
        fake = SimpleNamespace(get_json=AsyncMock(), provenance=lambda *_: {"data_status": "real"})
        provider = FinMindProvider(load_settings(read_dotenv=False), fake)
        provider.market = AsyncMock(return_value="TWSE")
        fake.get_json.return_value = {"status": 200, "data": [{"stock_id": "2492", "date": "2026-10-08", "close": 100}]}
        with self.assertRaises(UpstreamError):
            await provider.history("2327", date(2026, 10, 1), date(2026, 10, 8))
        fake.get_json.return_value = {"status": 200, "data": [{"stock_id": "2327", "date": day, "close": 100} for day in ("2026-09-30", "2026-10-08", "2026-10-08", "2026-10-09")]}
        rows = await provider.history("2327", date(2026, 10, 1), date(2026, 10, 8))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].symbol, "2327")
        self.assertIn("data_id=2327", rows[0].metadata.source_url)

    async def test_news_health_preserves_working_feed_when_rss_fails(self):
        twse = SimpleNamespace(news=AsyncMock(return_value=[SimpleNamespace(published_at=None)]))
        provider = NewsProvider(load_settings(read_dotenv=False), None, twse)
        provider.rss_items = AsyncMock(side_effect=UpstreamError("TWSE RSS", "連線逾時"))
        result = await provider.health()
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.record_count, 1)

    async def test_news_research_falls_back_once_to_rss_and_fails_honestly(self):
        twse = SimpleNamespace(news=AsyncMock(side_effect=UpstreamError("TWSE", "連線逾時")))
        provider = NewsProvider(load_settings(read_dotenv=False), None, twse)
        provider.rss_items = AsyncMock(return_value=["rss-public-record"])
        self.assertEqual(await provider.items(3), ["rss-public-record"])
        provider.rss_items.assert_awaited_once_with(limit=3)
        provider.rss_items = AsyncMock(side_effect=UpstreamError("RSS", "連線逾時"))
        with self.assertRaises(UpstreamError):
            await provider.health()

    async def test_mops_total_failure_never_claims_endpoints_are_connected(self):
        from backend.app.providers.mops import MOPSProvider
        exchange = SimpleNamespace(disclosures=AsyncMock(side_effect=UpstreamError("TWSE", "連線逾時")))
        with self.assertRaises(UpstreamError):
            await MOPSProvider(load_settings(read_dotenv=False), None, exchange, exchange).health()

    async def test_passive_scope_excludes_unrelated_high_turnover_electronics(self):
        service = MarketService(twse=None, tpex=None, mops=None, finmind=None)
        quotes = [MarketQuote(symbol=code, name=code, market="TWSE", close=100,
                              trade_value_twd=value, metadata=metadata(data_status="real"))
                  for code, value in (("2059", 9999), ("2327", 1000), ("2492", 800), ("4958", 9000))]
        service.universe = AsyncMock(return_value=(quotes, {}))
        scope = await service.resolve_industry_scope("台灣被動元件")
        self.assertEqual(scope["symbols"], ["2327", "2492"])
        self.assertEqual(set(scope["membership_references"]), {"2327", "2492"})

    async def test_gemini_missing_key_never_sends_network_request(self):
        settings = load_settings(read_dotenv=False)
        fake = SimpleNamespace(get_json=AsyncMock())
        gemini = GeminiProvider(settings, fake)
        result = await gemini.health()
        self.assertEqual(result.status, "pending")
        with self.assertRaises(RuntimeError):
            await gemini.generate_research("test")
        fake.get_json.assert_not_awaited()

    async def test_model_metadata_probe_does_not_claim_generation(self):
        from dataclasses import replace
        settings = replace(load_settings(read_dotenv=False), gemini_api_key="test-only-not-real", gemini_model="test-model")
        fake = SimpleNamespace(get_json=AsyncMock(return_value={"name": "models/test-model"}))
        result = await GeminiProvider(settings, fake).health()
        self.assertEqual(result.status, "healthy")
        self.assertIn("未測試生成", result.message)
        self.assertTrue(fake.get_json.call_args.args[1].endswith("/models/test-model"))

    async def test_gemini_quota_failure_blocks_further_calls(self):
        from dataclasses import replace
        settings = replace(load_settings(read_dotenv=False), gemini_api_key="test-only-not-real")
        gemini = GeminiProvider(settings, None)
        gemini._record(time.perf_counter(), status=429)
        with self.assertRaisesRegex(RuntimeError, "停止後續生成"):
            await gemini.generate_research("must not send")

    async def test_invite_session_is_required_and_global_expiry_caps_ttl(self):
        manager = DemoSessionManager("test-secret-long-enough-32-characters", ttl_seconds=1800,
            issue_limit_per_minute=10, allowed_origins=("https://example.org",), invite_token="test-only-invitation", expires_at=1100)
        with patch("backend.app.security.preview_security.time.time", return_value=1000):
            with self.assertRaises(DemoSessionError):
                await manager.issue("client", "https://example.org")
            result = await manager.issue("client", "https://example.org", "test-only-invitation")
            self.assertEqual(result["expires_in"], 100)
            self.assertTrue(manager.validate(result["access_token"]))
        with patch("backend.app.security.preview_security.time.time", return_value=1101):
            with self.assertRaises(DemoSessionError):
                manager.validate(result["access_token"])
            with self.assertRaises(DemoSessionError):
                await manager.issue("client", "https://example.org", "test-only-invitation")


class SourceStatusTests(unittest.TestCase):
    def test_later_network_failure_replaces_previous_healthy_status(self):
        from datetime import timedelta
        result = HealthResult(source="TWSE", status="healthy", message="previous check")
        observation = {"source": "TWSE", "checked_at": result.checked_at+timedelta(seconds=1),
                       "data_status": "missing", "http_status": None}
        with patch.dict(api.source_health_results, {"TWSE": result}, clear=True), \
             patch.dict(api.http._observations, {"endpoint": observation}, clear=True):
            rows = api._source_configuration_status()
        self.assertEqual(next(row for row in rows if row["source"] == "TWSE")["connection_status"], "error")

    def test_remote_origin_integration_without_external_requests(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, "-m", "qa.p3_security_acceptance"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"status": "pass"', result.stdout)

    def test_source_refresh_preserves_observed_health_without_reprobing(self):
        result = HealthResult(source="TWSE", status="stale", latest_data_at=date(2026, 10, 8), message="public daily")
        with patch.dict(api.source_health_results, {"TWSE": result}, clear=True), TestClient(api.app) as client:
            rows = client.get("/api/sources/status").json()
        twse = next(row for row in rows if row["source"] == "TWSE")
        self.assertEqual(twse["connection_status"], "stale")
        self.assertEqual(twse["latest_data_at"], "2026-10-08")

    def test_runtime_config_contains_mode_but_no_credentials(self):
        with TestClient(api.app) as client:
            response = client.get("/runtime-config.js")
            self.assertEqual(response.status_code, 200)
            self.assertIn('"dataMode": "live"', response.text)
            for value in ("api_key", "session_secret", "invite_token"):
                self.assertNotIn(value, response.text.lower())
            for path in ("/.env", "/backend/", "/docs/acceptance/p3/live-api.json"):
                self.assertEqual(client.get(path).status_code, 404)
