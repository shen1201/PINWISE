import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.app.services.feedback import FeedbackEntry, FeedbackStore
from backend.app.services.research_jobs import JsonJobStore


class FeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_stores_rating_without_content_and_hashes_visitor(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "feedback" / "feedback.jsonl"
            await FeedbackStore(path).add(FeedbackEntry(feature="research", rating="bad", reason="data_wrong", item_id="research_1"), "visitor-abc")
            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual((row["rating"], row["reason"]), ("bad", "data_wrong"))
            self.assertNotEqual(row["visitor"], "visitor-abc")
            self.assertEqual(set(row), {"at", "visitor", "feature", "rating", "reason", "item_id"})

    def test_rejects_free_text_reason(self):
        with self.assertRaises(ValidationError):
            FeedbackEntry(feature="assistant", rating="bad", reason="任何文字", item_id="a1")

    async def test_comment_is_optional_masked_and_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "feedback.jsonl"
            text = "希望先講結論，聯絡我 abc@example.com 或 0912-345-678，身分證 A123456789，代號 2330 不要遮"
            await FeedbackStore(path).add(FeedbackEntry(feature="assistant", rating="bad", reason="hard_to_read", item_id="a1", comment=text), "v")
            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("希望先講結論", row["comment"])
            for leaked in ("abc@example.com", "0912-345-678", "A123456789"):
                self.assertNotIn(leaked, row["comment"])
            self.assertIn("2330", row["comment"])
        with self.assertRaises(ValidationError):
            FeedbackEntry(feature="assistant", rating="ok", item_id="a2", comment="字" * 301)

    async def test_stops_writing_at_size_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "feedback.jsonl"
            path.write_bytes(b"x" * 5_000_000)
            added = await FeedbackStore(path).add(FeedbackEntry(feature="picker", rating="ok", item_id="p1"), "v")
            self.assertFalse(added)


class DeleteTests(unittest.IsolatedAsyncioTestCase):
    async def test_json_store_delete_removes_file_and_tolerates_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "job_1.json"
            target.write_text("{}", encoding="utf-8")
            store = JsonJobStore(Path(folder))
            await store.delete("job_1")
            self.assertFalse(target.exists())
            await store.delete("job_1")
