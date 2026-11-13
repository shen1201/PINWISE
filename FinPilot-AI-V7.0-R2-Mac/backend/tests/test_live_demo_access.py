from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.models import ResearchRequest, ResearchResponse
from backend.app.security.preview_security import (
    DemoSessionError,
    DemoSessionManager,
    GeminiUsageBudget,
    PreviewAccessMiddleware,
    PreviewLimitError,
    current_visitor_id,
    validate_preview_settings,
)
from backend.app.services.research_jobs import ResearchJobManager


ORIGIN = "https://finpilot-demo.example"
SECRET = "demo-session-secret-with-at-least-32-characters"


class DemoSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sessions = DemoSessionManager(
            SECRET, ttl_seconds=3600, issue_limit_per_minute=3, allowed_origins=(ORIGIN,)
        )

    async def test_signed_session_is_origin_limited_and_tamper_resistant(self):
        issued = await self.sessions.issue("203.0.113.9", ORIGIN)
        visitor_id = self.sessions.validate(issued["access_token"])
        self.assertTrue(visitor_id)
        with self.assertRaises(DemoSessionError):
            await self.sessions.issue("203.0.113.9", "https://attacker.example")
        with self.assertRaises(DemoSessionError):
            self.sessions.validate(issued["access_token"] + "x")

    async def test_two_visitors_have_independent_request_budgets(self):
        first = await self.sessions.issue("203.0.113.10", ORIGIN)
        second = await self.sessions.issue("203.0.113.11", ORIGIN)
        app = FastAPI()

        @app.get("/api/whoami")
        async def whoami():
            return {"ok": True}

        app.add_middleware(
            PreviewAccessMiddleware,
            required=False,
            token=None,
            rate_limit_per_minute=1,
            system_rate_limit_per_minute=10,
            session_manager=self.sessions,
        )
        with TestClient(app) as client:
            one = {"Authorization": f"Bearer {first['access_token']}"}
            two = {"Authorization": f"Bearer {second['access_token']}"}
            self.assertEqual(client.get("/api/whoami", headers=one).status_code, 200)
            self.assertEqual(client.get("/api/whoami", headers=one).status_code, 429)
            self.assertEqual(client.get("/api/whoami", headers=two).status_code, 200)
            self.assertEqual(client.get("/api/whoami").status_code, 401)

    async def test_demo_configuration_requires_secret_and_cors(self):
        base = dict(preview_auth_required=False, preview_token=None, demo_access_enabled=True)
        with self.assertRaisesRegex(RuntimeError, "DEMO_SESSION_SECRET"):
            validate_preview_settings(SimpleNamespace(**base, demo_session_secret="short", cors_origins=(ORIGIN,)))
        with self.assertRaisesRegex(RuntimeError, "CORS"):
            validate_preview_settings(SimpleNamespace(**base, demo_session_secret=SECRET, cors_origins=()))


class VisitorBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_and_per_visitor_gemini_budgets_are_both_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            budget = GeminiUsageBudget(
                Path(directory) / "usage.json",
                call_limit=3,
                token_limit=1000,
                visitor_call_limit=1,
                visitor_token_limit=500,
            )
            marker = current_visitor_id.set("visitor-a")
            try:
                reservation = await budget.reserve("hello", 10)
                await reservation.commit({"total_token_count": 8})
                with self.assertRaises(PreviewLimitError):
                    await budget.reserve("again", 10)
            finally:
                current_visitor_id.reset(marker)
            marker = current_visitor_id.set("visitor-b")
            try:
                reservation = await budget.reserve("hello", 10)
                await reservation.commit({"total_token_count": 8})
            finally:
                current_visitor_id.reset(marker)


class _FastResearchService:
    def __init__(self):
        self.gemini = SimpleNamespace(settings=SimpleNamespace(gemini_model="fixture-model"))

    async def run(self, request, *, emit, checkpoint):
        await checkpoint()
        await asyncio.sleep(0)
        return ResearchResponse(
            query=request.query,
            summary="isolated",
            risks=[], candidates=[], evidence=[], trace=[], model="fixture-model",
        )


class ResearchOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_job_id_cannot_cross_visitor_boundary_or_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            manager = ResearchJobManager(_FastResearchService(), path)
            job = await manager.create(ResearchRequest(query="研究 2330"), "visitor-a")
            self.assertIsNone(await manager.get(job.id, "visitor-b"))
            await manager.tasks[job.id]
            reopened = ResearchJobManager(_FastResearchService(), path)
            self.assertIsNone(await reopened.get(job.id, "visitor-b"))
            loaded = await reopened.get(job.id, "visitor-a")
            self.assertEqual(loaded.status, "completed")


if __name__ == "__main__":
    unittest.main()
