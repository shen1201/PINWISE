from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.responses import JSONResponse


class PreviewLimitError(RuntimeError):
    """A server-enforced preview capacity or spending boundary was reached."""


class DemoSessionError(RuntimeError):
    def __init__(self, message: str, code: str = "demo_session_invalid"):
        super().__init__(message)
        self.code = code


current_visitor_id: ContextVar[str] = ContextVar("finpilot_visitor_id", default="local")


def visitor_id_from_scope(scope) -> str:
    value = scope.get("finpilot.visitor_id")
    return value if isinstance(value, str) and value else "local"


class DemoSessionManager:
    """Issue stateless, short-lived visitor credentials signed only by the backend."""

    def __init__(self, secret: str, *, ttl_seconds: int, issue_limit_per_minute: int, allowed_origins=(), invite_token=None, expires_at=0):
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = max(900, min(86400, ttl_seconds))
        self.issue_limit = max(1, issue_limit_per_minute)
        self.allowed_origins = frozenset(origin.rstrip("/") for origin in allowed_origins)
        self.invite_token = invite_token
        self.expires_at = expires_at
        self._issues: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    def _signature(self, payload: str) -> str:
        return self._encode(hmac.new(self.secret, payload.encode("ascii"), hashlib.sha256).digest())

    async def issue(self, client_key: str, origin: str | None, invite: str | None = None) -> dict[str, Any]:
        if self.expires_at and time.time() >= self.expires_at:
            raise DemoSessionError("測試入口已到期", "demo_access_expired")
        normalized_origin = (origin or "").rstrip("/")
        if self.allowed_origins and normalized_origin not in self.allowed_origins:
            raise DemoSessionError("此來源未獲准建立訪客工作階段", "demo_origin_not_allowed")
        now_mono = time.monotonic()
        async with self._lock:
            rows = [stamp for stamp in self._issues.get(client_key, []) if now_mono - stamp < 60]
            if len(rows) >= self.issue_limit:
                self._issues[client_key] = rows
                raise DemoSessionError("建立訪客工作階段過於頻繁，請稍後再試", "demo_session_rate_limited")
            rows.append(now_mono)
            self._issues[client_key] = rows
        if self.invite_token and not secrets.compare_digest(invite or "", self.invite_token):
            raise DemoSessionError("需要有效的測試邀請碼", "demo_invite_required")
        issued = int(time.time())
        expires = min(issued + self.ttl_seconds, self.expires_at) if self.expires_at else issued + self.ttl_seconds
        payload = self._encode(json.dumps({
            "v": 1,
            "sid": secrets.token_urlsafe(18),
            "iat": issued,
            "exp": expires,
        }, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        token = f"{payload}.{self._signature(payload)}"
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": expires - issued,
            "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
        }

    def validate(self, token: str) -> str:
        if self.expires_at and time.time() >= self.expires_at:
            raise DemoSessionError("測試入口已到期", "demo_access_expired")
        try:
            payload, signature = token.split(".", 1)
            if not secrets.compare_digest(signature, self._signature(payload)):
                raise DemoSessionError("訪客工作階段簽章無效")
            value = json.loads(self._decode(payload))
            if value.get("v") != 1 or not isinstance(value.get("sid"), str):
                raise DemoSessionError("訪客工作階段格式無效")
            if int(value.get("exp", 0)) <= int(time.time()):
                raise DemoSessionError("訪客工作階段已到期", "demo_session_expired")
            return value["sid"]
        except DemoSessionError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise DemoSessionError("訪客工作階段無效") from exc


def validate_preview_settings(settings) -> None:
    if settings.preview_auth_required and (not settings.preview_token or len(settings.preview_token) < 16):
        raise RuntimeError("FINPILOT_PREVIEW_AUTH_REQUIRED=true 時，FINPILOT_PREVIEW_TOKEN 至少需要 16 個字元")
    if settings.preview_auth_required and not settings.cors_origins:
        print("PINWISE 預覽保護已啟用；尚未設定跨網域來源，只有同源請求可使用 API。")
    if getattr(settings, "demo_access_enabled", False):
        secret = getattr(settings, "demo_session_secret", None) or ""
        if len(secret) < 32:
            raise RuntimeError("FINPILOT_DEMO_ACCESS_ENABLED=true 時，FINPILOT_DEMO_SESSION_SECRET 至少需要 32 個字元")
        if not settings.cors_origins:
            raise RuntimeError("公開 Demo 必須設定 FINPILOT_CORS_ORIGINS")


class PreviewAccessMiddleware:
    """Protect API/docs and apply a small in-process per-client request budget.

    `/healthz` stays public so Render can perform readiness checks. It returns no
    settings, source state, records, or credentials. Every `/api` operation is
    protected when preview auth is enabled.
    """

    def __init__(self, app, *, required: bool, token: str | None, rate_limit_per_minute: int,
                 system_rate_limit_per_minute: int | None = None, session_manager: DemoSessionManager | None = None):
        self.app = app
        self.required = required
        self.token = token or ""
        self.rate_limit = max(1, rate_limit_per_minute)
        self.system_rate_limit = max(self.rate_limit, system_rate_limit_per_minute or self.rate_limit)
        self.session_manager = session_manager
        self._requests: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _header(scope, name: bytes) -> str:
        for key, value in scope.get("headers", []):
            if key.lower() == name:
                return value.decode("latin-1")
        return ""

    async def _allowed_rate(self, key: str, limit: int) -> tuple[bool, int]:
        now = time.monotonic()
        async with self._lock:
            rows = [stamp for stamp in self._requests.get(key, []) if now - stamp < 60]
            if len(rows) >= limit:
                self._requests[key] = rows
                retry_after = max(1, round(60 - (now - rows[0])))
                return False, retry_after
            rows.append(now)
            self._requests[key] = rows
        return True, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        protected = (path.startswith("/api/") and path != "/api/demo/session") or path in {"/api", "/docs", "/openapi.json", "/redoc"}
        if not protected or method == "OPTIONS":
            await self.app(scope, receive, send)
            return
        visitor_id = "local"
        if self.session_manager:
            authorization = self._header(scope, b"authorization")
            supplied = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
            try:
                visitor_id = self.session_manager.validate(supplied) if supplied else ""
            except DemoSessionError as exc:
                response = JSONResponse(
                    {"detail": str(exc), "code": exc.code}, status_code=401,
                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
            if not visitor_id:
                response = JSONResponse(
                    {"detail": "需要有效的訪客工作階段", "code": "demo_session_required"}, status_code=401,
                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
        elif self.required:
            authorization = self._header(scope, b"authorization")
            supplied = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
            if not supplied:
                supplied = self._header(scope, b"x-finpilot-preview-token").strip()
            if not supplied:
                response = JSONResponse(
                    {"detail": "此預覽 API 需要存取權杖", "code": "preview_auth_required"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
            if not secrets.compare_digest(supplied, self.token):
                response = JSONResponse(
                    {"detail": "預覽存取權杖不正確", "code": "preview_auth_invalid"},
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
            visitor_id = hashlib.sha256(supplied.encode("utf-8")).hexdigest()[:24]
        allowed, retry_after = await self._allowed_rate(f"visitor:{visitor_id}", self.rate_limit)
        if not allowed:
            response = JSONResponse(
                {"detail": "預覽 API 每分鐘呼叫上限已達，本次未執行", "code": "preview_rate_limited"},
                status_code=429,
                headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        global_allowed, global_retry_after = await self._allowed_rate("system", self.system_rate_limit)
        if not global_allowed:
            response = JSONResponse(
                {"detail": "展示系統目前忙碌，請稍後再試", "code": "demo_system_rate_limited"},
                status_code=429,
                headers={"Retry-After": str(global_retry_after), "Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        scope["finpilot.visitor_id"] = visitor_id
        context_token = current_visitor_id.set(visitor_id)
        try:
            await self.app(scope, receive, send)
        finally:
            current_visitor_id.reset(context_token)


class ConcurrencyLimiter:
    def __init__(self, limit: int, label: str, *, per_visitor_limit: int | None = None):
        self.limit = max(1, limit)
        self.label = label
        self.active = 0
        self.per_visitor_limit = max(1, per_visitor_limit or self.limit)
        self.by_visitor: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, visitor_id: str | None = None) -> None:
        visitor_id = visitor_id or current_visitor_id.get()
        async with self._lock:
            if self.active >= self.limit:
                raise PreviewLimitError(f"{self.label}同時執行上限已達（{self.limit}）")
            if self.by_visitor.get(visitor_id, 0) >= self.per_visitor_limit:
                raise PreviewLimitError(f"每位訪客的{self.label}同時執行上限已達（{self.per_visitor_limit}）")
            self.active += 1
            self.by_visitor[visitor_id] = self.by_visitor.get(visitor_id, 0) + 1

    async def release(self, visitor_id: str | None = None) -> None:
        visitor_id = visitor_id or current_visitor_id.get()
        async with self._lock:
            self.active = max(0, self.active - 1)
            count = max(0, self.by_visitor.get(visitor_id, 0) - 1)
            if count:
                self.by_visitor[visitor_id] = count
            else:
                self.by_visitor.pop(visitor_id, None)


@dataclass
class UsageReservation:
    budget: "GeminiUsageBudget"
    reserved_tokens: int
    visitor_id: str
    completed: bool = False

    async def commit(self, usage: dict[str, Any] | None) -> None:
        if self.completed:
            return
        actual = None
        if usage:
            for key in ("total_token_count", "total_tokens"):
                value = usage.get(key)
                if isinstance(value, (int, float)) and value >= 0:
                    actual = int(value)
                    break
        await self.budget._finish(self.reserved_tokens, actual, self.visitor_id)
        self.completed = True


class GeminiUsageBudget:
    """Persist a conservative daily call/token ceiling before provider calls."""

    def __init__(self, path: Path, *, call_limit: int, token_limit: int,
                 visitor_call_limit: int | None = None, visitor_token_limit: int | None = None):
        self.path = path
        self.call_limit = max(0, call_limit)
        self.token_limit = max(0, token_limit)
        self.visitor_call_limit = max(0, visitor_call_limit if visitor_call_limit is not None else call_limit)
        self.visitor_token_limit = max(0, visitor_token_limit if visitor_token_limit is not None else token_limit)
        self._lock = asyncio.Lock()

    @staticmethod
    def _day() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("day") == self._day():
                value.setdefault("visitors", {})
                return value
        except (OSError, ValueError, TypeError):
            pass
        return {"day": self._day(), "calls": 0, "tokens": 0, "visitors": {}}

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    # Storage hooks; a database-backed budget overrides these two methods.
    async def _load(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._read)

    async def _save(self, value: dict[str, Any]) -> None:
        await asyncio.to_thread(self._write, value)

    async def reserve(self, prompt: str, max_output_tokens: int) -> UsageReservation:
        # Conservative text estimate. Reserving before the call prevents two
        # concurrent requests from both spending the same remaining budget.
        estimated = max(1, (len(prompt) + 1) // 2) + max(1, max_output_tokens)
        visitor_id = current_visitor_id.get()
        async with self._lock:
            value = await self._load()
            visitors = value.setdefault("visitors", {})
            visitor = visitors.setdefault(visitor_id, {"calls": 0, "tokens": 0})
            if self.call_limit == 0 or value["calls"] >= self.call_limit:
                raise PreviewLimitError("Gemini 每日呼叫上限已達，本次未送出")
            if self.token_limit == 0 or value["tokens"] + estimated > self.token_limit:
                raise PreviewLimitError("Gemini 每日 token 預算不足，本次未送出")
            if self.visitor_call_limit == 0 or visitor["calls"] >= self.visitor_call_limit:
                raise PreviewLimitError("PINWISE 設定的本工作階段 Gemini 每日呼叫上限已達；本次未送出，限制於下一個 UTC 日重置")
            if self.visitor_token_limit == 0 or visitor["tokens"] + estimated > self.visitor_token_limit:
                raise PreviewLimitError("PINWISE 設定的本工作階段 Gemini 每日 token 預算不足；本次未送出，限制於下一個 UTC 日重置")
            value["calls"] += 1
            value["tokens"] += estimated
            visitor["calls"] += 1
            visitor["tokens"] += estimated
            await self._save(value)
        return UsageReservation(self, estimated, visitor_id)

    async def _finish(self, reserved: int, actual: int | None, visitor_id: str) -> None:
        if actual is None:
            return
        async with self._lock:
            value = await self._load()
            value["tokens"] = max(0, int(value.get("tokens", 0)) - reserved + actual)
            visitor = value.setdefault("visitors", {}).setdefault(visitor_id, {"calls": 0, "tokens": 0})
            visitor["tokens"] = max(0, int(visitor.get("tokens", 0)) - reserved + actual)
            await self._save(value)
