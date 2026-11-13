"""Optional PostgreSQL persistence.

Without DATABASE_URL the backend keeps its original JSON files, so local runs,
tests and teammates without PostgreSQL behave exactly as before.  Calls use a
synchronous psycopg pool inside worker threads: psycopg's async mode cannot run
on Windows' default event loop.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, TypeVar
from urllib.parse import urlparse, urlunparse

from psycopg import Connection, connect, sql
from psycopg_pool import ConnectionPool

T = TypeVar("T")

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 帳號（密碼只存 scrypt 雜湊）與登入工作階段（只存 token 的 SHA-256）
CREATE TABLE IF NOT EXISTS users (
    id             BIGSERIAL PRIMARY KEY,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS user_sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS user_sessions_user ON user_sessions (user_id);

-- 資料擁有者：訪客為 "local" 或後端簽發的訪客 ID；登入帳號為 "user:<users.id>"
CREATE TABLE IF NOT EXISTS visitors (
    id                TEXT PRIMARY KEY,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ui_state          JSONB NOT NULL DEFAULT '{}'::jsonb,
    state_updated_at  TIMESTAMPTZ,
    conversations_updated_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS user_preferences (
    visitor_id         TEXT PRIMARY KEY REFERENCES visitors(id) ON DELETE CASCADE,
    completed          BOOLEAN NOT NULL DEFAULT false,
    experience         TEXT,
    explanation_style  TEXT,
    horizon            TEXT,
    risk_tolerance     TEXT,
    objective          TEXT,
    liquidity          TEXT,
    market             TEXT,
    updated_at         TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    visitor_id  TEXT NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
    symbol      TEXT NOT NULL,
    position    INTEGER NOT NULL,
    PRIMARY KEY (visitor_id, symbol)
);

CREATE TABLE IF NOT EXISTS comparison_items (
    visitor_id  TEXT NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
    symbol      TEXT NOT NULL,
    position    INTEGER NOT NULL,
    PRIMARY KEY (visitor_id, symbol)
);

CREATE TABLE IF NOT EXISTS candidate_items (
    visitor_id        TEXT NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
    id                TEXT NOT NULL,
    symbol            TEXT NOT NULL,
    name              TEXT,
    research_task_id  TEXT,
    thesis            TEXT,
    added_at          TIMESTAMPTZ,
    position          INTEGER NOT NULL,
    payload           JSONB NOT NULL,
    PRIMARY KEY (visitor_id, id)
);

CREATE TABLE IF NOT EXISTS conversations (
    visitor_id      TEXT NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
    id              TEXT NOT NULL,
    title           TEXT NOT NULL,
    pinned          BOOLEAN NOT NULL DEFAULT false,
    assistant_mode  TEXT,
    memory          JSONB NOT NULL DEFAULT '{}'::jsonb,
    position        INTEGER NOT NULL,
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (visitor_id, id)
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    visitor_id       TEXT NOT NULL,
    conversation_id  TEXT NOT NULL,
    id               TEXT NOT NULL,
    position         INTEGER NOT NULL,
    role             TEXT NOT NULL,
    text             TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ,
    payload          JSONB NOT NULL,
    PRIMARY KEY (visitor_id, conversation_id, id),
    FOREIGN KEY (visitor_id, conversation_id) REFERENCES conversations(visitor_id, id) ON DELETE CASCADE
);

-- 研究 Agent 任務與逐步 trace
CREATE TABLE IF NOT EXISTS research_jobs (
    id              TEXT PRIMARY KEY,
    owner_id        TEXT NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
    status          TEXT NOT NULL,
    query           TEXT NOT NULL,
    fingerprint     TEXT NOT NULL,
    progress        INTEGER NOT NULL,
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    error_code      TEXT,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    payload         JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS research_jobs_owner_updated ON research_jobs (owner_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS research_events (
    job_id       TEXT NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    sequence     INTEGER NOT NULL,
    event_id     TEXT NOT NULL,
    phase        TEXT NOT NULL,
    agent        TEXT NOT NULL,
    action       TEXT NOT NULL,
    source       TEXT NOT NULL,
    status       TEXT NOT NULL,
    progress     INTEGER NOT NULL,
    occurred_at  TIMESTAMPTZ NOT NULL,
    duration_ms  INTEGER,
    payload      JSONB NOT NULL,
    PRIMARY KEY (job_id, sequence)
);

-- Gemini 每日用量（全站總量為當日所有列的加總）
CREATE TABLE IF NOT EXISTS gemini_usage (
    day         DATE NOT NULL,
    visitor_id  TEXT NOT NULL,
    calls       INTEGER NOT NULL DEFAULT 0,
    tokens      BIGINT NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, visitor_id)
);
"""


def _database_name(url: str) -> str:
    name = urlparse(url).path.lstrip("/")
    if not name:
        raise ValueError("DATABASE_URL 必須包含資料庫名稱，例如 postgresql://user:pass@127.0.0.1:5432/finpilot")
    return name


def _maintenance_url(url: str) -> str:
    return urlunparse(urlparse(url)._replace(path="/postgres"))


def ensure_database(url: str) -> bool:
    """Create the target database when missing. Returns True if it was created."""
    name = _database_name(url)
    try:
        with connect(url, connect_timeout=5):
            return False
    except Exception:
        pass
    with connect(_maintenance_url(url), autocommit=True, connect_timeout=5) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if exists:
            return False
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        return True


class Database:
    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 5):
        self.url = url
        self._min_size = min_size
        self._max_size = max_size
        self.pool: ConnectionPool | None = None

    def open(self) -> None:
        ensure_database(self.url)
        self.pool = ConnectionPool(self.url, min_size=self._min_size, max_size=self._max_size,
                                   kwargs={"connect_timeout": 5}, open=True)
        self.pool.wait(timeout=10)
        self.call(self._migrate)

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
            self.pool = None

    @staticmethod
    def _migrate(conn: Connection) -> None:
        conn.execute(SCHEMA)
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            (SCHEMA_VERSION,),
        )

    def call(self, operation: Callable[[Connection], T]) -> T:
        if self.pool is None:
            raise RuntimeError("資料庫尚未連線")
        # The pool commits on success and rolls back if the operation raises.
        with self.pool.connection() as conn:
            return operation(conn)

    async def run(self, operation: Callable[[Connection], T]) -> T:
        return await asyncio.to_thread(self.call, operation)


def ensure_visitor(conn: Connection, visitor_id: str) -> None:
    conn.execute(
        "INSERT INTO visitors (id) VALUES (%s) ON CONFLICT (id) DO UPDATE SET last_seen_at = now()",
        (visitor_id,),
    )


def database_summary(conn: Connection) -> dict[str, Any]:
    tables = [
        "users", "user_sessions", "visitors", "user_preferences", "watchlist_items", "comparison_items", "candidate_items",
        "conversations", "conversation_messages", "research_jobs", "research_events", "gemini_usage",
    ]
    counts = {}
    for table in tables:
        counts[table] = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
    return {"schema_version": SCHEMA_VERSION, "row_counts": counts}
