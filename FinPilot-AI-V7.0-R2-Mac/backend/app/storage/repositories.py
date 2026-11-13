"""PostgreSQL-backed stores used when DATABASE_URL is configured."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from .database import Database, ensure_visitor
from ..core.models import ResearchJob
from ..security.preview_security import GeminiUsageBudget

# Front-end state keys stored in their own tables; everything else stays in visitors.ui_state.
_PREFERENCE_FIELDS = {
    "completed": "completed", "experience": "experience", "explanationStyle": "explanation_style",
    "horizon": "horizon", "riskTolerance": "risk_tolerance", "objective": "objective",
    "liquidity": "liquidity", "market": "market", "updatedAt": "updated_at",
}


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _symbols(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(str(value) for value in values if isinstance(value, (str, int)) and str(value)))


class PostgresJobStore:
    """Research jobs in research_jobs; each Agent trace step as a research_events row."""

    def __init__(self, database: Database):
        self.database = database

    async def save(self, job: ResearchJob, owner_id: str) -> None:
        payload = job.model_dump(mode="json")

        def write(conn: Connection) -> None:
            ensure_visitor(conn, owner_id)
            conn.execute(
                """
                INSERT INTO research_jobs (id, owner_id, status, query, fingerprint, progress, model,
                    prompt_version, error_code, created_at, updated_at, completed_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status, progress = EXCLUDED.progress, error_code = EXCLUDED.error_code,
                    updated_at = EXCLUDED.updated_at, completed_at = EXCLUDED.completed_at, payload = EXCLUDED.payload
                """,
                (job.id, owner_id, job.status, job.request.query, job.fingerprint, job.progress, job.model,
                 job.prompt_version, (job.error or {}).get("code"), job.created_at, job.updated_at,
                 job.completed_at, Jsonb(payload)),
            )
            if job.events:
                with conn.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO research_events (job_id, sequence, event_id, phase, agent, action, source,
                            status, progress, occurred_at, duration_ms, payload)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (job_id, sequence) DO NOTHING
                        """,
                        [(job.id, event.sequence, event.id, event.phase, event.agent, event.action, event.source,
                          event.status, event.progress, event.at, event.duration_ms,
                          Jsonb(event.model_dump(mode="json"))) for event in job.events],
                    )

        await self.database.run(write)

    async def delete(self, job_id: str) -> None:
        def remove(conn: Connection) -> None:
            conn.execute("DELETE FROM research_jobs WHERE id = %s", (job_id,))

        await self.database.run(remove)

    async def load(self, job_id: str) -> tuple[str, ResearchJob] | None:
        def read(conn: Connection):
            return conn.execute("SELECT owner_id, payload FROM research_jobs WHERE id = %s", (job_id,)).fetchone()

        row = await self.database.run(read)
        if row is None:
            return None
        try:
            return str(row[0]), ResearchJob.model_validate(row[1])
        except ValueError:
            return None


class PostgresUsageBudget(GeminiUsageBudget):
    """Same daily ceilings as the JSON budget, stored one row per visitor per UTC day."""

    def __init__(self, database: Database, **limits):
        super().__init__(None, **limits)
        self.database = database

    async def _load(self) -> dict[str, Any]:
        day = self._day()

        def read(conn: Connection):
            return conn.execute("SELECT visitor_id, calls, tokens FROM gemini_usage WHERE day = %s", (day,)).fetchall()

        rows = await self.database.run(read)
        visitors = {visitor: {"calls": int(calls), "tokens": int(tokens)} for visitor, calls, tokens in rows}
        return {
            "day": day,
            "calls": sum(item["calls"] for item in visitors.values()),
            "tokens": sum(item["tokens"] for item in visitors.values()),
            "visitors": visitors,
        }

    async def _save(self, value: dict[str, Any]) -> None:
        rows = [(value["day"], visitor, int(item.get("calls", 0)), int(item.get("tokens", 0)))
                for visitor, item in value.get("visitors", {}).items()]

        def write(conn: Connection) -> None:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO gemini_usage (day, visitor_id, calls, tokens) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (day, visitor_id) DO UPDATE SET
                        calls = EXCLUDED.calls, tokens = EXCLUDED.tokens, updated_at = now()
                    """,
                    rows,
                )

        if rows:
            await self.database.run(write)


class WorkspaceRepository:
    """Per-visitor front-end workspace: preferences, lists, conversations and UI settings."""

    def __init__(self, database: Database):
        self.database = database

    async def load(self, visitor_id: str) -> dict[str, Any]:
        def read(conn: Connection) -> dict[str, Any]:
            visitor = conn.execute(
                "SELECT ui_state, state_updated_at, conversations_updated_at FROM visitors WHERE id = %s",
                (visitor_id,),
            ).fetchone()
            if visitor is None:
                return {"state": None, "conversations": None, "state_updated_at": None, "conversations_updated_at": None}
            ui_state, state_updated_at, conversations_updated_at = visitor
            state = None
            if state_updated_at is not None:
                state = dict(ui_state or {})
                prefs = conn.execute(
                    "SELECT completed, experience, explanation_style, horizon, risk_tolerance, objective, "
                    "liquidity, market, updated_at FROM user_preferences WHERE visitor_id = %s",
                    (visitor_id,),
                ).fetchone()
                if prefs is not None:
                    columns = list(_PREFERENCE_FIELDS)
                    state["personalPrefs"] = {
                        key: (_iso(value) if key == "updatedAt" else value) for key, value in zip(columns, prefs)
                    }
                state["tracked"] = [row[0] for row in conn.execute(
                    "SELECT symbol FROM watchlist_items WHERE visitor_id = %s ORDER BY position", (visitor_id,))]
                state["compareSymbols"] = [row[0] for row in conn.execute(
                    "SELECT symbol FROM comparison_items WHERE visitor_id = %s ORDER BY position", (visitor_id,))]
                state["candidateList"] = [row[0] for row in conn.execute(
                    "SELECT payload FROM candidate_items WHERE visitor_id = %s ORDER BY position", (visitor_id,))]
            conversations = None
            if conversations_updated_at is not None:
                conversations = []
                messages: dict[str, list[dict[str, Any]]] = {}
                for conversation_id, payload in conn.execute(
                    "SELECT conversation_id, payload FROM conversation_messages WHERE visitor_id = %s "
                    "ORDER BY conversation_id, position", (visitor_id,)):
                    messages.setdefault(conversation_id, []).append(payload)
                for conversation_id, payload in conn.execute(
                    "SELECT id, payload FROM conversations WHERE visitor_id = %s ORDER BY position", (visitor_id,)):
                    conversations.append({**payload, "messages": messages.get(conversation_id, [])})
            return {
                "state": state, "conversations": conversations,
                "state_updated_at": _iso(state_updated_at), "conversations_updated_at": _iso(conversations_updated_at),
            }

        return await self.database.run(read)

    async def save_state(self, visitor_id: str, state: dict[str, Any]) -> None:
        remaining = dict(state)
        prefs = remaining.pop("personalPrefs", None)
        tracked = _symbols(remaining.pop("tracked", []))
        compare = _symbols(remaining.pop("compareSymbols", []))
        candidates = [item for item in remaining.pop("candidateList", []) or [] if isinstance(item, dict) and item.get("symbol")]

        def write(conn: Connection) -> None:
            ensure_visitor(conn, visitor_id)
            conn.execute(
                "UPDATE visitors SET ui_state = %s, state_updated_at = now() WHERE id = %s",
                (Jsonb(remaining), visitor_id),
            )
            if isinstance(prefs, dict):
                values = [prefs.get(key) for key in _PREFERENCE_FIELDS]
                values[0] = bool(values[0])
                values[-1] = _timestamp(values[-1])
                conn.execute(
                    """
                    INSERT INTO user_preferences (visitor_id, completed, experience, explanation_style, horizon,
                        risk_tolerance, objective, liquidity, market, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (visitor_id) DO UPDATE SET
                        completed = EXCLUDED.completed, experience = EXCLUDED.experience,
                        explanation_style = EXCLUDED.explanation_style, horizon = EXCLUDED.horizon,
                        risk_tolerance = EXCLUDED.risk_tolerance, objective = EXCLUDED.objective,
                        liquidity = EXCLUDED.liquidity, market = EXCLUDED.market, updated_at = EXCLUDED.updated_at
                    """,
                    (visitor_id, *values),
                )
            with conn.cursor() as cursor:
                for table, symbols in (("watchlist_items", tracked), ("comparison_items", compare)):
                    cursor.execute(f"DELETE FROM {table} WHERE visitor_id = %s", (visitor_id,))
                    cursor.executemany(
                        f"INSERT INTO {table} (visitor_id, symbol, position) VALUES (%s, %s, %s)",
                        [(visitor_id, symbol, index) for index, symbol in enumerate(symbols)],
                    )
                cursor.execute("DELETE FROM candidate_items WHERE visitor_id = %s", (visitor_id,))
                seen: set[str] = set()
                rows = []
                for index, item in enumerate(candidates):
                    item_id = str(item.get("id") or f"candidate_{item['symbol']}")
                    if item_id in seen:
                        continue
                    seen.add(item_id)
                    rows.append((visitor_id, item_id, str(item["symbol"]), item.get("name"), item.get("researchTaskId"),
                                 item.get("thesis"), _timestamp(item.get("addedAt")), index, Jsonb(item)))
                cursor.executemany(
                    """
                    INSERT INTO candidate_items (visitor_id, id, symbol, name, research_task_id, thesis,
                        added_at, position, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )

        await self.database.run(write)

    async def save_conversations(self, visitor_id: str, conversations: list[dict[str, Any]]) -> None:
        def write(conn: Connection) -> None:
            ensure_visitor(conn, visitor_id)
            conn.execute("UPDATE visitors SET conversations_updated_at = now() WHERE id = %s", (visitor_id,))
            conn.execute("DELETE FROM conversations WHERE visitor_id = %s", (visitor_id,))
            seen: set[str] = set()
            conversation_rows, message_rows = [], []
            for position, conversation in enumerate(conversations):
                if not isinstance(conversation, dict) or not conversation.get("id"):
                    continue
                conversation_id = str(conversation["id"])
                if conversation_id in seen:
                    continue
                seen.add(conversation_id)
                body = {key: value for key, value in conversation.items() if key != "messages"}
                conversation_rows.append((
                    visitor_id, conversation_id, str(conversation.get("title") or "新對話"),
                    bool(conversation.get("pinned")), conversation.get("assistantMode"),
                    Jsonb(conversation.get("memory") if isinstance(conversation.get("memory"), dict) else {}),
                    position, _timestamp(conversation.get("createdAt")), _timestamp(conversation.get("updatedAt")),
                    Jsonb(body),
                ))
                message_ids: set[str] = set()
                for index, message in enumerate(conversation.get("messages") or []):
                    if not isinstance(message, dict):
                        continue
                    message_id = str(message.get("id") or f"message_{index}")
                    if message_id in message_ids:
                        message_id = f"{message_id}_{index}"
                    message_ids.add(message_id)
                    message_rows.append((
                        visitor_id, conversation_id, message_id, index, str(message.get("role") or "user"),
                        str(message.get("text") or ""), _timestamp(message.get("at")), Jsonb(message),
                    ))
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO conversations (visitor_id, id, title, pinned, assistant_mode, memory, position,
                        created_at, updated_at, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    conversation_rows,
                )
                cursor.executemany(
                    """
                    INSERT INTO conversation_messages (visitor_id, conversation_id, id, position, role, text,
                        created_at, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    message_rows,
                )

        await self.database.run(write)
