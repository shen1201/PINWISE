"""PostgreSQL storage tests.

Skipped unless FINPILOT_TEST_DATABASE_URL points at a disposable database, e.g.
postgresql://postgres:<password>@127.0.0.1:5432/finpilot_test (created if missing).
Every test truncates all FinPilot tables in that database.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.app.core.models import ResearchRequest, ResearchResponse
from backend.app.security.preview_security import PreviewLimitError, current_visitor_id
from backend.app.services.research_jobs import ResearchJobManager

TEST_DATABASE_URL = os.getenv("FINPILOT_TEST_DATABASE_URL")


class FakeResearchService:
    def __init__(self):
        self.gemini = SimpleNamespace(settings=SimpleNamespace(gemini_model="fake-model"))

    async def run(self, request, *, emit, checkpoint):
        await emit(id="source", sequence=1, phase="data", agent="Data Agent", action="取得資料", detail="TWSE",
                   source="TWSE", status="completed", progress=40, at="2026-10-14T00:00:00Z", duration_ms=12,
                   attempt=1, metadata={"rows": 3})
        await checkpoint()
        await emit(id="done", sequence=2, phase="persistence", agent="Report Agent", action="保存", detail="完成",
                   source="FinPilot", status="completed", progress=100, at="2026-10-14T00:00:01Z", duration_ms=1,
                   attempt=1, metadata={})
        return ResearchResponse(query=request.query, summary="done", risks=["risk"], candidates=["2330"],
                                evidence=[], trace=[], model="fake-model")


@unittest.skipUnless(TEST_DATABASE_URL, "FINPILOT_TEST_DATABASE_URL 未設定；略過 PostgreSQL 測試")
class PostgresStorageTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from backend.app.storage.database import Database
        cls.database = Database(TEST_DATABASE_URL)
        cls.database.open()

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    async def asyncSetUp(self):
        from backend.app.storage.repositories import PostgresJobStore, PostgresUsageBudget, WorkspaceRepository
        await self.database.run(lambda conn: conn.execute(
            "TRUNCATE users, user_sessions, visitors, research_jobs, research_events, gemini_usage, user_preferences, "
            "watchlist_items, comparison_items, candidate_items, conversations, conversation_messages CASCADE"))
        self.job_store = PostgresJobStore(self.database)
        self.workspace = WorkspaceRepository(self.database)
        self.budget_type = PostgresUsageBudget
        self.temp = tempfile.TemporaryDirectory()

    async def asyncTearDown(self):
        self.temp.cleanup()

    def count(self, table: str, where: str = "", params=()) -> int:
        return self.database.call(lambda conn: conn.execute(f"SELECT count(*) FROM {table} {where}", params).fetchone()[0])

    async def wait_terminal(self, manager, job_id, owner_id="local"):
        for _ in range(200):
            job = await manager.get(job_id, owner_id)
            if job.status in {"completed", "failed", "cancelled"}:
                return job
            await asyncio.sleep(0.01)
        self.fail("job did not finish")

    async def test_research_job_and_trace_are_stored_and_reopened(self):
        manager = ResearchJobManager(FakeResearchService(), Path(self.temp.name), store=self.job_store)
        job = await manager.create(ResearchRequest(query="研究 2330"), owner_id="visitor-a")
        final = await self.wait_terminal(manager, job.id, "visitor-a")
        self.assertEqual(final.status, "completed")
        self.assertEqual(self.count("research_events", "WHERE job_id = %s", (job.id,)), len(final.events))
        self.assertEqual(list(Path(self.temp.name).iterdir()), [], "PostgreSQL 模式不應再寫 JSON 檔")

        reopened = ResearchJobManager(FakeResearchService(), Path(self.temp.name), store=self.job_store)
        loaded = await reopened.get(job.id, "visitor-a")
        self.assertEqual(loaded.result.summary, "done")
        self.assertIsNone(await reopened.get(job.id, "visitor-b"), "其他使用者不可讀取")

    async def test_interrupted_job_is_marked_failed_after_restart(self):
        manager = ResearchJobManager(FakeResearchService(), Path(self.temp.name), store=self.job_store)
        job = await manager.create(ResearchRequest(query="研究 2330 重啟"))
        task = manager.tasks[job.id]
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        reopened = ResearchJobManager(FakeResearchService(), Path(self.temp.name), store=self.job_store)
        loaded = await reopened.get(job.id)
        self.assertEqual(loaded.status, "failed")
        self.assertEqual(loaded.error["code"], "server_restarted")

    async def test_usage_budget_persists_across_instances(self):
        token = current_visitor_id.set("visitor-a")
        try:
            budget = self.budget_type(self.database, call_limit=5, token_limit=10_000, visitor_call_limit=1,
                                      visitor_token_limit=10_000)
            reservation = await budget.reserve("hello", 10)
            await reservation.commit({"total_token_count": 42})
            again = self.budget_type(self.database, call_limit=5, token_limit=10_000, visitor_call_limit=1,
                                     visitor_token_limit=10_000)
            with self.assertRaises(PreviewLimitError):
                await again.reserve("hello", 10)
        finally:
            current_visitor_id.reset(token)
        row = self.database.call(lambda conn: conn.execute(
            "SELECT calls, tokens FROM gemini_usage WHERE visitor_id = 'visitor-a'").fetchone())
        self.assertEqual(row, (1, 42))

    async def test_workspace_state_round_trip_and_replacement(self):
        state = {
            "page": "picker", "displayMode": "dark", "workspaceSavedAt": "2026-10-14T01:00:00.000Z",
            "personalPrefs": {"completed": True, "experience": "", "explanationStyle": "清楚易懂", "horizon": "長期",
                              "riskTolerance": "可接受小幅波動", "objective": "股息收入", "liquidity": "可長期投入",
                              "market": "台股", "updatedAt": "2026-10-14T01:00:00.000Z"},
            "tracked": ["2330", "0050", "2330"],
            "compareSymbols": ["2330", "2454"],
            "candidateList": [{"id": "candidate_2330_1", "symbol": "2330", "name": "台積電", "thesis": "龍頭",
                               "addedAt": "2026-10-14T01:00:00.000Z", "extra": {"kept": True}}],
        }
        await self.workspace.save_state("visitor-a", state)
        loaded = (await self.workspace.load("visitor-a"))["state"]
        self.assertEqual(loaded["page"], "picker")
        self.assertEqual(loaded["tracked"], ["2330", "0050"])
        self.assertEqual(loaded["compareSymbols"], ["2330", "2454"])
        self.assertEqual(loaded["candidateList"][0]["extra"], {"kept": True})
        self.assertEqual(loaded["personalPrefs"]["objective"], "股息收入")
        self.assertTrue(loaded["personalPrefs"]["completed"])
        self.assertEqual(self.count("watchlist_items"), 2)

        await self.workspace.save_state("visitor-a", {**state, "tracked": ["0050"], "candidateList": []})
        loaded = (await self.workspace.load("visitor-a"))["state"]
        self.assertEqual(loaded["tracked"], ["0050"])
        self.assertEqual(loaded["candidateList"], [])
        self.assertIsNone((await self.workspace.load("visitor-b"))["state"], "其他使用者不可讀取")

    async def test_conversations_round_trip(self):
        conversations = [{
            "id": "conversation_1", "title": "殖利率", "createdAt": "2026-10-14T01:00:00.000Z",
            "updatedAt": "2026-10-14T01:05:00.000Z", "pinned": True, "assistantMode": "新手模式",
            "memory": {"version": 2, "recent_symbols": ["0056"]},
            "messages": [
                {"id": "m1", "role": "user", "text": "什麼是殖利率", "at": "2026-10-14T01:00:00.000Z"},
                {"id": "m2", "role": "assistant", "text": "殖利率是…", "completionState": "completed"},
            ],
        }]
        await self.workspace.save_conversations("visitor-a", conversations)
        loaded = (await self.workspace.load("visitor-a"))["conversations"]
        self.assertEqual(loaded, conversations)
        self.assertEqual(self.count("conversation_messages"), 2)

        await self.workspace.save_conversations("visitor-a", [])
        self.assertEqual((await self.workspace.load("visitor-a"))["conversations"], [])
        self.assertEqual(self.count("conversation_messages"), 0)


    async def test_account_register_login_session_and_logout(self):
        from backend.app.storage.auth import AccountError, AccountRepository
        accounts = AccountRepository(self.database)
        user = await accounts.register("Alice", "s3cret-pass")
        self.assertEqual((user["username"], user["owner_id"]), ("alice", f"user:{user['id']}"))
        stored = self.database.call(lambda conn: conn.execute("SELECT password_hash FROM users").fetchone()[0])
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertNotIn("s3cret-pass", stored)

        with self.assertRaises(AccountError) as duplicate:
            await accounts.register("ALICE", "another-pass")
        self.assertEqual(duplicate.exception.code, "username_taken")

        self.assertIsNone(await accounts.authenticate("alice", "wrong-pass"))
        self.assertIsNone(await accounts.authenticate("nobody", "s3cret-pass"))
        self.assertEqual((await accounts.authenticate("ALICE", "s3cret-pass"))["id"], user["id"])

        token = await accounts.create_session(user["id"])
        stored_token = self.database.call(lambda conn: conn.execute("SELECT token_hash FROM user_sessions").fetchone()[0])
        self.assertNotEqual(stored_token, token, "資料庫只存 token 雜湊")
        self.assertEqual((await accounts.resolve(token))["owner_id"], user["owner_id"])
        self.assertIsNone(await accounts.resolve("forged-token"))

        await accounts.delete_session(token)
        self.assertIsNone(await accounts.resolve(token))

    async def test_expired_session_is_rejected(self):
        from backend.app.storage.auth import AccountRepository
        accounts = AccountRepository(self.database)
        user = await accounts.register("bob_01", "s3cret-pass")
        token = await accounts.create_session(user["id"])
        self.database.call(lambda conn: conn.execute("UPDATE user_sessions SET expires_at = now() - interval '1 second'"))
        self.assertIsNone(await accounts.resolve(token))


if __name__ == "__main__":
    unittest.main()
