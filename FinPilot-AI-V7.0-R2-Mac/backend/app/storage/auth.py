"""Username/password accounts stored in PostgreSQL.

Passwords are hashed with scrypt (Python standard library); sessions are random
tokens of which only the SHA-256 is stored.  A signed-in request carries the
token in X-FinPilot-Session and every per-visitor store (workspace, research
jobs, Gemini budget) then uses the owner id "user:<id>".
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.responses import JSONResponse
from psycopg import Connection, errors

from .database import Database
from ..security.preview_security import current_visitor_id

SESSION_HEADER = b"x-finpilot-session"
SESSION_DAYS = 30
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
PASSWORD_MIN, PASSWORD_MAX = 8, 128
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 64}
# Hashed once so an unknown username costs the same time as a wrong password.
_DUMMY_HASH: str | None = None


class AccountError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected) // 2)
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def owner_id(user_id: int) -> str:
    return f"user:{user_id}"


def _public(row) -> dict[str, Any]:
    user_id, username, created_at = row
    return {"id": user_id, "username": username, "owner_id": owner_id(user_id),
            "created_at": created_at.isoformat() if created_at else None}


def validate_credentials(username: str, password: str) -> str:
    username = (username or "").strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise AccountError("invalid_username", "帳號需為 3–32 個英文字母、數字或 _ . -")
    if not PASSWORD_MIN <= len(password or "") <= PASSWORD_MAX:
        raise AccountError("invalid_password", f"密碼長度需為 {PASSWORD_MIN}–{PASSWORD_MAX} 個字元")
    return username.lower()


class AccountRepository:
    def __init__(self, database: Database):
        self.database = database

    async def register(self, username: str, password: str) -> dict[str, Any]:
        name = validate_credentials(username, password)
        password_hash = await asyncio.to_thread(hash_password, password)

        def insert(conn: Connection):
            return conn.execute(
                "INSERT INTO users (username, password_hash, last_login_at) VALUES (%s, %s, now()) "
                "RETURNING id, username, created_at",
                (name, password_hash),
            ).fetchone()

        try:
            return _public(await self.database.run(insert))
        except errors.UniqueViolation:
            raise AccountError("username_taken", "這個帳號已被註冊") from None

    async def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        global _DUMMY_HASH
        name = (username or "").strip().lower()

        def read(conn: Connection):
            return conn.execute(
                "SELECT id, username, created_at, password_hash FROM users WHERE username = %s", (name,),
            ).fetchone()

        row = await self.database.run(read) if USERNAME_PATTERN.fullmatch(name) else None
        if row is None:
            _DUMMY_HASH = _DUMMY_HASH or await asyncio.to_thread(hash_password, secrets.token_hex(8))
            await asyncio.to_thread(verify_password, password or "", _DUMMY_HASH)
            return None
        if not await asyncio.to_thread(verify_password, password or "", row[3]):
            return None
        await self.database.run(lambda conn: conn.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (row[0],)))
        return _public(row[:3])

    async def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)

        def write(conn: Connection) -> None:
            conn.execute("DELETE FROM user_sessions WHERE expires_at < now()")
            conn.execute("INSERT INTO user_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                         (_token_hash(token), user_id, expires))

        await self.database.run(write)
        return token

    async def resolve(self, token: str) -> dict[str, Any] | None:
        if not token or len(token) > 200:
            return None

        def read(conn: Connection):
            return conn.execute(
                "SELECT u.id, u.username, u.created_at FROM user_sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = %s AND s.expires_at > now()", (_token_hash(token),),
            ).fetchone()

        row = await self.database.run(read)
        return _public(row) if row else None

    async def delete_session(self, token: str) -> None:
        await self.database.run(lambda conn: conn.execute(
            "DELETE FROM user_sessions WHERE token_hash = %s", (_token_hash(token),)))


class LoginRateLimiter:
    """At most `limit` register/login attempts per client per minute."""

    def __init__(self, limit: int = 10):
        self.limit = limit
        self._attempts: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            recent = [stamp for stamp in self._attempts.get(key, []) if now - stamp < 60]
            if len(recent) >= self.limit:
                self._attempts[key] = recent
                return False
            recent.append(now)
            self._attempts[key] = recent
            return True


class AccountSessionMiddleware:
    """Map a valid X-FinPilot-Session to the account's owner id for /api requests."""

    def __init__(self, app, accounts: AccountRepository | None):
        self.app = app
        self.accounts = accounts

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        token = ""
        if self.accounts and path.startswith("/api/"):
            token = next((value.decode("latin-1") for key, value in scope.get("headers", [])
                          if key.lower() == SESSION_HEADER), "").strip()
        if not token:
            await self.app(scope, receive, send)
            return
        user = await self.accounts.resolve(token)
        if user is None:
            if not path.startswith("/api/auth/"):
                # Never fall back to the guest store: that would mix an account's data into guest data.
                response = JSONResponse({"detail": "登入已過期，請重新登入", "code": "account_session_invalid"},
                                        status_code=401, headers={"Cache-Control": "no-store"})
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        scope["finpilot.visitor_id"] = user["owner_id"]
        scope["finpilot.user"] = user
        scope["finpilot.session_token"] = token
        context_token = current_visitor_id.set(user["owner_id"])
        try:
            await self.app(scope, receive, send)
        finally:
            current_visitor_id.reset(context_token)
