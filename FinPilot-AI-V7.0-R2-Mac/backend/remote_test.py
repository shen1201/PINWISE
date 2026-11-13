"""Prepare a short-lived loopback origin for an authenticated HTTPS tunnel.

No tunnel is created here. Supply the approved HTTPS origin of a named tunnel
that supports SSE. This process never exposes project files outside the static
asset allowlist and uses a new, empty visitor data directory on every launch.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import tempfile
import time
from urllib.parse import urlparse

import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--hours", type=float, default=2)
    parser.add_argument("--gemini-calls", type=int, choices=range(0, 7), default=2)
    args = parser.parse_args()
    origin = urlparse(args.origin)
    if origin.scheme != "https" or not origin.hostname or origin.path not in {"", "/"} or origin.hostname.endswith(".invalid") or origin.username or origin.query:
        parser.error("--origin 必須是已核准且支援 SSE 的 HTTPS 網域")
    if not 0.25 <= args.hours <= 4:
        parser.error("測試入口期限限 15 分鐘至 4 小時")
    invite = secrets.token_urlsafe(24)
    duration = int(args.hours * 3600)
    values = {
        "FINPILOT_HOST": "127.0.0.1", "FINPILOT_PORT": str(args.port),
        "FINPILOT_PREVIEW_FIXTURE_MODE": "false", "FINPILOT_PREVIEW_AUTH_REQUIRED": "false",
        "FINPILOT_DEMO_ACCESS_ENABLED": "true", "FINPILOT_DEMO_SESSION_SECRET": secrets.token_urlsafe(48),
        "FINPILOT_DEMO_INVITE_TOKEN": invite, "FINPILOT_DEMO_EXPIRES_AT": str(int(time.time()) + duration),
        "FINPILOT_CORS_ORIGINS": args.origin.rstrip("/"), "FINPILOT_DEMO_SESSION_TTL_SECONDS": "1800",
        "FINPILOT_DATA_DIR": tempfile.mkdtemp(prefix="finpilot-p3-visitors-"),
        "FINPILOT_RATE_LIMIT_PER_MINUTE": "80", "FINPILOT_SYSTEM_RATE_LIMIT_PER_MINUTE": "160",
        "FINPILOT_DAILY_GEMINI_CALL_LIMIT": str(args.gemini_calls),
        "FINPILOT_VISITOR_DAILY_GEMINI_CALL_LIMIT": str(args.gemini_calls),
        "FINPILOT_DAILY_GEMINI_TOKEN_LIMIT": "100000", "FINPILOT_VISITOR_DAILY_GEMINI_TOKEN_LIMIT": "100000",
        "FINPILOT_ASSISTANT_MAX_CONCURRENT": "1", "FINPILOT_RESEARCH_MAX_CONCURRENT": "1",
        "FINPILOT_REQUEST_TIMEOUT_SECONDS": "10", "FINPILOT_RETRY_ATTEMPTS": "0",
        "SHIOAJI_ENABLED": "false", "FINPILOT_LOG_LEVEL": "warning",
    }
    os.environ.update(values)
    print(f"準備中的測試 origin：{args.origin}；有效 {args.hours} 小時；Gemini 最多 {args.gemini_calls} 次")
    print(f"測試邀請碼（不是 API Key，僅分享給驗收者）：{invite}")
    print("停止：此終端 Ctrl+C，並停止對應 tunnel；到期後伺服器自動停止。")

    async def serve():
        server = uvicorn.Server(uvicorn.Config("backend.app.main:app", host="127.0.0.1", port=args.port, log_level="warning", access_log=False, proxy_headers=False))
        async def expire():
            await asyncio.sleep(duration)
            server.should_exit = True
        expiry = asyncio.create_task(expire())
        try:
            await server.serve()
        finally:
            expiry.cancel()
    asyncio.run(serve())


if __name__ == "__main__":
    main()
