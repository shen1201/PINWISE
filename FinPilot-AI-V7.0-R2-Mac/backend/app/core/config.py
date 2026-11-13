from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _csv(name: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip().rstrip("/") for value in os.getenv(name, "").split(",") if value.strip()))


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    log_level: str
    request_timeout_seconds: float
    retry_attempts: int
    cache_ttl_seconds: int
    stale_hours: int
    gemini_api_key: str | None
    gemini_model: str
    assistant_max_input_chars: int
    assistant_max_output_tokens: int
    assistant_max_history_messages: int
    assistant_max_tool_calls: int
    assistant_stream_timeout_seconds: int
    research_max_output_tokens: int
    gemini_enabled: bool
    preview_fixture_mode: bool
    preview_auth_required: bool
    preview_token: str | None
    demo_access_enabled: bool
    demo_session_secret: str | None
    demo_session_ttl_seconds: int
    demo_session_issue_limit_per_minute: int
    cors_origins: tuple[str, ...]
    rate_limit_per_minute: int
    system_rate_limit_per_minute: int
    assistant_max_concurrent: int
    assistant_max_concurrent_per_visitor: int
    research_max_concurrent: int
    research_max_concurrent_per_visitor: int
    daily_gemini_call_limit: int
    daily_gemini_token_limit: int
    visitor_daily_gemini_call_limit: int
    visitor_daily_gemini_token_limit: int
    data_dir: Path
    twse_base_url: str
    tpex_base_url: str
    twse_news_rss_url: str
    finmind_base_url: str
    finmind_token: str | None
    shioaji_enabled: bool
    shioaji_api_key: str | None
    shioaji_secret_key: str | None
    shioaji_simulation: bool
    demo_invite_token: str | None = None
    demo_expires_at: int = 0
    database_url: str | None = None
    startup_source_check: bool = True

    @property
    def missing_optional_settings(self) -> list[str]:
        missing: list[str] = []
        if self.gemini_enabled and not self.preview_fixture_mode and not self.gemini_api_key:
            missing.append("GEMINI_API_KEY（AI 助手與研究功能）")
        if not self.finmind_token:
            missing.append("FINMIND_TOKEN（選填；未填使用匿名免費額度）")
        if self.shioaji_enabled:
            if not self.shioaji_api_key:
                missing.append("SHIOAJI_API_KEY")
            if not self.shioaji_secret_key:
                missing.append("SHIOAJI_SECRET_KEY")
        return missing


def _validated_origins(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        parsed = urlparse(value)
        if value == "*" or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
            continue
        result.append(value)
    return tuple(result)


def load_settings(*, read_dotenv: bool = True, env_file: Path | None = None) -> Settings:
    # 測試可設 FINPILOT_SKIP_DOTENV=1，避免觸碰使用者的真實設定檔。
    if read_dotenv and not _bool("FINPILOT_SKIP_DOTENV"):
        load_dotenv(env_file or ENV_FILE, override=False)
    return Settings(
        host=os.getenv("FINPILOT_HOST", "127.0.0.1"),
        port=_int("FINPILOT_PORT", _int("PORT", 8080)),
        log_level=os.getenv("FINPILOT_LOG_LEVEL", "info"),
        request_timeout_seconds=max(1.0, _float("FINPILOT_REQUEST_TIMEOUT_SECONDS", 12)),
        retry_attempts=max(0, min(5, _int("FINPILOT_RETRY_ATTEMPTS", 2))),
        cache_ttl_seconds=max(1, _int("FINPILOT_CACHE_TTL_SECONDS", 300)),
        stale_hours=max(1, _int("FINPILOT_PUBLIC_DATA_STALE_HOURS", 72)),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        assistant_max_input_chars=max(100, min(4000, _int("FINPILOT_ASSISTANT_MAX_INPUT_CHARS", 1200))),
        assistant_max_output_tokens=max(128, min(4096, _int("FINPILOT_ASSISTANT_MAX_OUTPUT_TOKENS", 1024))),
        assistant_max_history_messages=max(0, min(20, _int("FINPILOT_ASSISTANT_MAX_HISTORY_MESSAGES", 8))),
        assistant_max_tool_calls=max(0, min(5, _int("FINPILOT_ASSISTANT_MAX_TOOL_CALLS", 3))),
        assistant_stream_timeout_seconds=max(20, min(300, _int("FINPILOT_ASSISTANT_STREAM_TIMEOUT_SECONDS", 90))),
        research_max_output_tokens=max(256, min(4096, _int("FINPILOT_RESEARCH_MAX_OUTPUT_TOKENS", 2048))),
        gemini_enabled=_bool("FINPILOT_GEMINI_ENABLED", True),
        preview_fixture_mode=_bool("FINPILOT_PREVIEW_FIXTURE_MODE", False),
        preview_auth_required=_bool("FINPILOT_PREVIEW_AUTH_REQUIRED", False),
        preview_token=os.getenv("FINPILOT_PREVIEW_TOKEN") or None,
        demo_access_enabled=_bool("FINPILOT_DEMO_ACCESS_ENABLED", False),
        demo_session_secret=os.getenv("FINPILOT_DEMO_SESSION_SECRET") or None,
        demo_session_ttl_seconds=max(900, min(86400, _int("FINPILOT_DEMO_SESSION_TTL_SECONDS", 14400))),
        demo_session_issue_limit_per_minute=max(1, min(60, _int("FINPILOT_DEMO_SESSION_ISSUE_LIMIT_PER_MINUTE", 8))),
        cors_origins=_validated_origins(_csv("FINPILOT_CORS_ORIGINS")),
        rate_limit_per_minute=max(5, min(600, _int("FINPILOT_RATE_LIMIT_PER_MINUTE", 60))),
        system_rate_limit_per_minute=max(10, min(5000, _int("FINPILOT_SYSTEM_RATE_LIMIT_PER_MINUTE", 240))),
        assistant_max_concurrent=max(1, min(20, _int("FINPILOT_ASSISTANT_MAX_CONCURRENT", 2))),
        assistant_max_concurrent_per_visitor=max(1, min(5, _int("FINPILOT_ASSISTANT_MAX_CONCURRENT_PER_VISITOR", 1))),
        research_max_concurrent=max(1, min(10, _int("FINPILOT_RESEARCH_MAX_CONCURRENT", 1))),
        research_max_concurrent_per_visitor=max(1, min(3, _int("FINPILOT_RESEARCH_MAX_CONCURRENT_PER_VISITOR", 1))),
        daily_gemini_call_limit=max(0, min(10000, _int("FINPILOT_DAILY_GEMINI_CALL_LIMIT", 20))),
        daily_gemini_token_limit=max(0, min(100_000_000, _int("FINPILOT_DAILY_GEMINI_TOKEN_LIMIT", 250000))),
        # Local use follows the normal daily ceiling by default. Public demo
        # deployments keep their stricter explicit values in render.yaml.
        visitor_daily_gemini_call_limit=max(0, min(1000, _int("FINPILOT_VISITOR_DAILY_GEMINI_CALL_LIMIT", 20))),
        visitor_daily_gemini_token_limit=max(0, min(10_000_000, _int("FINPILOT_VISITOR_DAILY_GEMINI_TOKEN_LIMIT", 250000))),
        data_dir=Path(os.getenv("FINPILOT_DATA_DIR", str(PROJECT_ROOT / "backend" / "data"))).expanduser(),
        twse_base_url=os.getenv("TWSE_OPENAPI_BASE_URL", "https://openapi.twse.com.tw/v1").rstrip("/"),
        tpex_base_url=os.getenv("TPEX_OPENAPI_BASE_URL", "https://www.tpex.org.tw/openapi/v1").rstrip("/"),
        twse_news_rss_url=os.getenv("TWSE_NEWS_RSS_URL", "https://www.twse.com.tw/rwd/zh/news/feed?type=rss"),
        finmind_base_url=os.getenv("FINMIND_BASE_URL", "https://api.finmindtrade.com/api/v4").rstrip("/"),
        finmind_token=os.getenv("FINMIND_TOKEN") or None,
        shioaji_enabled=_bool("SHIOAJI_ENABLED"),
        shioaji_api_key=os.getenv("SHIOAJI_API_KEY") or None,
        shioaji_secret_key=os.getenv("SHIOAJI_SECRET_KEY") or None,
        shioaji_simulation=_bool("SHIOAJI_SIMULATION", True),
        demo_invite_token=os.getenv("FINPILOT_DEMO_INVITE_TOKEN") or None,
        demo_expires_at=max(0, _int("FINPILOT_DEMO_EXPIRES_AT", 0)),
        database_url=os.getenv("DATABASE_URL") or None,
        startup_source_check=_bool("FINPILOT_STARTUP_SOURCE_CHECK", True),
    )
