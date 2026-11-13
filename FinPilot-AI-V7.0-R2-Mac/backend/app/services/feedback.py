from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..core.models import utc_now

MAX_FILE_BYTES = 5_000_000
COMMENT_LIMIT = 300
# 使用者自己打的回饋可能不小心寫到個人資料：存檔前遮掉 email、手機與身分證字號。
_PERSONAL = [
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "［已遮蔽 email］"),
    (re.compile(r"(?<!\d)09\d{2}[- ]?\d{3}[- ]?\d{3}(?!\d)"), "［已遮蔽電話］"),
    (re.compile(r"(?<![A-Za-z])[A-Za-z][12]\d{8}(?!\d)"), "［已遮蔽身分證］"),
]


def clean_comment(text: str | None) -> str | None:
    if text is None:
        return None
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()
    for pattern, mask in _PERSONAL:
        value = pattern.sub(mask, value)
    return value[:COMMENT_LIMIT] or None


class FeedbackEntry(BaseModel):
    """評分、固定選項的原因，以及使用者自願填寫的短回饋（遮蔽個資、300 字內）。
    不接受提問內容或回答內容。"""

    feature: Literal["research", "assistant", "picker"]
    rating: Literal["useful", "ok", "bad", "cleared"]
    reason: Literal["data_wrong", "hard_to_read", "too_slow", "off_topic"] | None = None
    item_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    comment: str | None = Field(default=None, max_length=COMMENT_LIMIT)


class FeedbackStore:
    """匿名回饋，一行一筆；同一筆改評分時以最後一行為準。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()

    async def add(self, entry: FeedbackEntry, visitor_id: str) -> bool:
        row = entry.model_dump()
        comment = clean_comment(row.pop("comment"))
        if comment:
            row["comment"] = comment
        line = json.dumps({
            "at": utc_now().isoformat(),
            "visitor": hashlib.sha256(visitor_id.encode("utf-8")).hexdigest()[:12],
            **row,
        }, ensure_ascii=False)

        def write() -> bool:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size >= MAX_FILE_BYTES:
                return False
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")
            return True

        async with self._lock:
            return await asyncio.to_thread(write)
