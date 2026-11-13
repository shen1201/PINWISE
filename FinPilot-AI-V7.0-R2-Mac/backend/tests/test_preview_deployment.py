from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.config import load_settings
from backend.app.security.preview_security import GeminiUsageBudget, PreviewAccessMiddleware, PreviewLimitError, validate_preview_settings
from backend.app.providers.preview import PreviewExchangeProvider, PreviewFinMindProvider, PreviewGeminiProvider


class PreviewAccessTests(unittest.TestCase):
    def _client(self, *, rate=10):
        app = FastAPI()

        @app.get("/healthz")
        async def healthz():
            return {"status": "ok"}

        @app.get("/api/health")
        async def api_health():
            return {"protected": True}

        app.add_middleware(PreviewAccessMiddleware, required=True, token="0123456789abcdef", rate_limit_per_minute=rate)
        return TestClient(app)

    def test_api_is_protected_but_minimal_health_probe_is_public(self):
        with self._client() as client:
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertEqual(client.get("/api/health").status_code, 401)
            self.assertEqual(client.get("/api/health", headers={"Authorization": "Bearer wrong"}).status_code, 403)
            response = client.get("/api/health", headers={"Authorization": "Bearer 0123456789abcdef"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"protected": True})

    def test_rate_limit_is_enforced_after_authentication(self):
        with self._client(rate=2) as client:
            headers = {"Authorization": "Bearer 0123456789abcdef"}
            self.assertEqual(client.get("/api/health", headers=headers).status_code, 200)
            self.assertEqual(client.get("/api/health", headers=headers).status_code, 200)
            response = client.get("/api/health", headers=headers)
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response.headers)

    def test_auth_configuration_requires_a_nontrivial_token(self):
        with self.assertRaisesRegex(RuntimeError, "至少需要 16"):
            validate_preview_settings(SimpleNamespace(preview_auth_required=True, preview_token="short", cors_origins=()))


class PreviewBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_budget_is_reserved_and_persisted_before_call(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            budget = GeminiUsageBudget(path, call_limit=1, token_limit=100)
            reservation = await budget.reserve("hello", 10)
            self.assertTrue(path.is_file())
            await reservation.commit({"total_token_count": 7})
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["calls"], 1)
            self.assertEqual(stored["tokens"], 7)
            with self.assertRaises(PreviewLimitError):
                await budget.reserve("second", 10)


class PreviewFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_market_history_and_model_do_not_need_network_or_key(self):
        twse = PreviewExchangeProvider("TWSE")
        quote = await twse.quote("2330")
        self.assertEqual(quote.close, 100.0)
        history = await PreviewFinMindProvider().history("2330", quote.trade_date.replace(month=9), quote.trade_date)
        self.assertGreater(len(history), 10)
        settings = load_settings(read_dotenv=False)
        gemini = PreviewGeminiProvider(settings)
        self.assertTrue(gemini.available)
        chunks = [chunk async for chunk in gemini.stream_assistant('{"current_message":"ROE 是什麼？"}')]
        self.assertIn("隔離預覽", "".join(item.get("text", "") for item in chunks))
        self.assertEqual(chunks[-1]["usage"]["total_token_count"], 0)


if __name__ == "__main__":
    unittest.main()
