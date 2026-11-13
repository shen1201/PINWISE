from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import PurePosixPath
from time import perf_counter
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles

from .storage.auth import AccountError, AccountRepository, AccountSessionMiddleware, LoginRateLimiter
from .core.config import PROJECT_ROOT, load_settings
from .storage.database import Database, database_summary
from .core.http_client import ResilientHttpClient, UpstreamError
from .core.models import AIPickerRequest, AssistantRequest, HealthResult, InputUnderstandingRequest, InputUnderstandingResponse, PickerRequest, ResearchJob, ResearchRequest, StockSnapshotRequest
from .core.normalization import normalized_symbol
from .providers.esg import EsgProvider
from .providers.etf_holdings import EtfHoldingsService
from .providers.finmind import FinMindProvider
from .providers.fundamentals import FundamentalsProvider
from .providers.gemini import GeminiProvider
from .providers.investor_relations import InvestorRelationsProvider
from .providers.mops import MOPSProvider
from .providers.news import NewsProvider
from .providers.shioaji import ShioajiProvider
from .providers.tpex import TPExProvider
from .providers.twse import TWSEProvider
from .providers.preview import PreviewExchangeProvider, PreviewFinMindProvider, PreviewGeminiProvider, PreviewIRProvider, PreviewNewsProvider
from .security.preview_security import ConcurrencyLimiter, DemoSessionError, DemoSessionManager, GeminiUsageBudget, PreviewAccessMiddleware, PreviewLimitError, validate_preview_settings, visitor_id_from_scope
from .storage.repositories import PostgresJobStore, PostgresUsageBudget, WorkspaceRepository
from .services.research import ResearchService
from .services.market import MarketService
from .services.input_understanding import InputUnderstandingService
from .services.assistant import AssistantService
from .services.feedback import FeedbackEntry, FeedbackStore
from .services.research_jobs import ResearchCapacityError, ResearchJobManager
from .services.ai_picker import AIPickerService


settings = load_settings()
validate_preview_settings(settings)
http = ResilientHttpClient(settings.request_timeout_seconds, settings.retry_attempts, settings.cache_ttl_seconds)
# PostgreSQL is optional: without DATABASE_URL (or in fixture mode) the original JSON files are used.
database = Database(settings.database_url) if settings.database_url and not settings.preview_fixture_mode else None
workspace = WorkspaceRepository(database) if database else None
accounts = AccountRepository(database) if database else None
login_limiter = LoginRateLimiter()
budget_limits = dict(
    call_limit=settings.daily_gemini_call_limit,
    token_limit=settings.daily_gemini_token_limit,
    visitor_call_limit=settings.visitor_daily_gemini_call_limit,
    visitor_token_limit=settings.visitor_daily_gemini_token_limit,
)
usage_budget = (
    PostgresUsageBudget(database, **budget_limits) if database
    else GeminiUsageBudget(settings.data_dir / "preview_usage_budget.json", **budget_limits)
)
demo_sessions = DemoSessionManager(
    settings.demo_session_secret or "",
    ttl_seconds=settings.demo_session_ttl_seconds,
    issue_limit_per_minute=settings.demo_session_issue_limit_per_minute,
    allowed_origins=settings.cors_origins,
    invite_token=settings.demo_invite_token, expires_at=settings.demo_expires_at,
) if settings.demo_access_enabled else None
if settings.preview_fixture_mode:
    twse = PreviewExchangeProvider("TWSE")
    tpex = PreviewExchangeProvider("TPEX")
    mops = MOPSProvider(settings, http, twse, tpex)
    finmind = PreviewFinMindProvider()
    news = PreviewNewsProvider(twse)
    investor_relations = PreviewIRProvider()
    gemini = PreviewGeminiProvider(settings)
else:
    twse = TWSEProvider(settings, http)
    tpex = TPExProvider(settings, http)
    mops = MOPSProvider(settings, http, twse, tpex)
    finmind = FinMindProvider(settings, http)
    news = NewsProvider(settings, http, twse)
    investor_relations = InvestorRelationsProvider(settings, mops)
    gemini = GeminiProvider(settings, http, budget=usage_budget)
shioaji = ShioajiProvider(settings)
# ETF 成份股：隔離模式不連外。
etf_holdings_service = None if settings.preview_fixture_mode else EtfHoldingsService(http, twse.fund_list, settings)
# Official valuation / monthly revenue / EPS; fixture mode never contacts real sources.
fundamentals = None if settings.preview_fixture_mode else FundamentalsProvider(settings, http)
esg_provider = None if settings.preview_fixture_mode else EsgProvider(settings, http)
market = MarketService(twse=twse, tpex=tpex, mops=mops, finmind=finmind)
ai_picker = AIPickerService(market=market, fundamentals=fundamentals, gemini=gemini, finmind=finmind)
input_understanding = InputUnderstandingService(twse=twse, tpex=tpex)
assistant = AssistantService(
    settings=gemini.settings, understanding=input_understanding, market=market,
    finmind=finmind, mops=mops, gemini=gemini, ir=investor_relations, news=news,
)
research = ResearchService(twse=twse, tpex=tpex, mops=mops, finmind=finmind, news=news, ir=investor_relations, gemini=gemini, market=market, fundamentals=fundamentals)
assistant_capacity = ConcurrencyLimiter(
    settings.assistant_max_concurrent, "助手",
    per_visitor_limit=settings.assistant_max_concurrent_per_visitor,
)
research_capacity = ConcurrencyLimiter(
    settings.research_max_concurrent, "研究",
    per_visitor_limit=settings.research_max_concurrent_per_visitor,
)
feedback_store = FeedbackStore(settings.data_dir / "feedback" / "feedback.jsonl")
research_jobs = ResearchJobManager(
    research,
    settings.data_dir / ("fixture_research_jobs" if settings.preview_fixture_mode else "research_jobs"),
    max_active=settings.research_max_concurrent,
    capacity=research_capacity,
    store=PostgresJobStore(database) if database else None,
)
WORKSPACE_MAX_BYTES = 4_000_000


class FrontendStaticFiles(StaticFiles):
    """Serve only browser assets; never expose settings, backend code or reports."""

    _root_files = {"", ".", "index.html", "runtime-config.js"}
    _asset_directories = {"assets", "js", "css"}

    async def get_response(self, path: str, scope):
        parts = PurePosixPath(path.replace("\\", "/")).parts
        allowed = path in self._root_files or (parts and parts[0] in self._asset_directories)
        if not allowed or any(part.startswith(".") for part in parts):
            raise HTTPException(status_code=404, detail="Not found")
        return await super().get_response(path, scope)


@asynccontextmanager
async def lifespan(_: FastAPI):
    missing = settings.missing_optional_settings
    if missing:
        print("PINWISE 選配設定尚未提供：" + "、".join(missing))
    if getattr(settings, "preview_fixture_mode", False):
        print("PINWISE 隔離預覽模式：外部資料來源與真實 Gemini 均不會被呼叫。")
    else:
        print("PINWISE 公開資料來源將在健康檢查或查詢時進行真實連線。")
    if database:
        try:
            await asyncio.to_thread(database.open)
        except Exception as exc:
            # Fail fast: silently falling back to JSON would split data between two stores.
            raise RuntimeError(f"無法連線 PostgreSQL（請檢查 DATABASE_URL 與資料庫服務）：{type(exc).__name__}") from None
        print("PINWISE 資料庫：PostgreSQL 已連線，資料表已就緒。")
    else:
        print("PINWISE 資料庫：未設定 DATABASE_URL，使用本機 JSON 檔案。")
    # Health checks read metadata only (no Gemini generation), so the source
    # cards show real status right after startup instead of "not checked".
    startup_check = None
    if getattr(settings, "startup_source_check", False) and not getattr(settings, "preview_fixture_mode", False):
        startup_check = asyncio.create_task(_startup_source_check())
    yield
    if startup_check:
        startup_check.cancel()
        await asyncio.gather(startup_check, return_exceptions=True)
    await http.close()
    if database:
        await asyncio.to_thread(database.close)


app = FastAPI(
    title="PINWISE R2 API",
    version="1.0.0",
    description="PINWISE R2 的本機資料與 AI 後端；敏感設定不會回傳給瀏覽器。",
    lifespan=lifespan,
    docs_url=None if settings.demo_access_enabled or settings.preview_auth_required else "/docs",
    redoc_url=None if settings.demo_access_enabled or settings.preview_auth_required else "/redoc",
    openapi_url=None if settings.demo_access_enabled or settings.preview_auth_required else "/openapi.json",
)

# Added first so it runs inside PreviewAccessMiddleware and can replace the
# guest/demo visitor id with the signed-in account's owner id.
app.add_middleware(AccountSessionMiddleware, accounts=accounts)
# CORS is deliberately an allowlist. PreviewAccessMiddleware protects every
# API/docs route; /healthz alone remains public for the platform health probe.
app.add_middleware(
    PreviewAccessMiddleware,
    required=settings.preview_auth_required,
    token=settings.preview_token,
    rate_limit_per_minute=settings.rate_limit_per_minute,
    system_rate_limit_per_minute=settings.system_rate_limit_per_minute,
    session_manager=demo_sessions,
)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-FinPilot-Preview-Token", "X-FinPilot-Invite", "X-FinPilot-Session", "ngrok-skip-browser-warning"],
        expose_headers=["Retry-After"],
    )


class ApiNoStoreMiddleware:
    """API 回應一律不讓瀏覽器快取：資料依時間與訪客而變，暫時失敗的結果也不該被瀏覽器記住重複使用。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                if not any(name.lower() == b"cache-control" for name, _ in headers):
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)


app.add_middleware(ApiNoStoreMiddleware)


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_, exc: UpstreamError):
    status = 504 if "逾時" in str(exc) else 502
    if exc.status_code in {401, 403}:
        status = exc.status_code
    if exc.status_code == 429:
        status = 429
    if exc.status_code is not None and 500 <= exc.status_code <= 599:
        status = exc.status_code
    return JSONResponse(
        status_code=status,
        content={"detail": str(exc), "source": exc.source, "upstream_status": exc.status_code},
    )


@app.get("/healthz", include_in_schema=False)
async def platform_health():
    return {"status": "ok"}


@app.post("/api/demo/session", include_in_schema=False)
async def create_demo_session(request: Request):
    if not demo_sessions:
        raise HTTPException(404, "訪客展示模式未啟用")
    # Proxy headers are interpreted only by a separately configured trusted
    # proxy layer, never by arbitrary user-supplied headers here.
    client_key = request.client.host if request.client else "unknown"
    try:
        payload = await demo_sessions.issue(client_key, request.headers.get("origin"), request.headers.get("x-finpilot-invite"))
    except DemoSessionError as exc:
        status_code = 429 if exc.code == "demo_session_rate_limited" else 403
        raise HTTPException(status_code, str(exc), headers={"Cache-Control": "no-store"}) from exc
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/health")
async def application_health():
    return {
        "service": "PINWISE R2 API",
        "status": "healthy",
        "missing_optional_settings": settings.missing_optional_settings,
        "secrets_exposed": False,
        "preview_fixture_mode": getattr(settings, "preview_fixture_mode", False),
        "preview_auth_required": getattr(settings, "preview_auth_required", False),
        "demo_access_enabled": settings.demo_access_enabled,
        "gemini_mode": "fixture" if getattr(gemini, "is_fixture", False) else ("enabled" if getattr(gemini, "available", False) else "disabled"),
        "data_mode": "fixture" if settings.preview_fixture_mode else "live",
        "gemini_model": settings.gemini_model,
        "gemini_last_call": getattr(gemini, "last_call", None),
        "storage": "postgresql" if database else "json_files",
    }


@app.get("/runtime-config.js", include_in_schema=False)
async def runtime_config():
    import json
    payload = {"apiBaseUrl": "", "previewMode": settings.preview_fixture_mode,
        "dataMode": "fixture" if settings.preview_fixture_mode else "live",
        "demoMode": settings.demo_access_enabled,
        "accessMode": "demo-session" if settings.demo_access_enabled else "shared-token" if settings.preview_auth_required else "local",
        "requirePreviewToken": settings.preview_auth_required,
        "inviteRequired": bool(settings.demo_invite_token),
        "assistantTimeoutMs": 105000}
    return Response("window.FINPILOT_CONFIG = Object.freeze(" + json.dumps(payload) + ");",
                    media_type="application/javascript", headers={"Cache-Control": "no-store"})


source_health_results: dict[str, HealthResult] = {}


async def _health_call(source: str, operation) -> HealthResult:
    started = perf_counter()
    try:
        result = await operation
        observation = http.source_observation(source)
        if observation and result.http_status is None:
            result.http_status = observation["http_status"]
        source_health_results[source] = result
        return result
    except UpstreamError as exc:
        if exc.status_code in {401, 403}:
            status = "pending"
            message = f"權限不足或驗證失敗：{exc}"
        elif exc.status_code == 429:
            status = "degraded"
            message = f"已達限流：{exc}"
        else:
            status = "error"
            message = str(exc)
        result = HealthResult(source=source, status=status, latency_ms=round((perf_counter() - started) * 1000), message=message, http_status=exc.status_code)
        source_health_results[source] = result
        return result
    except asyncio.TimeoutError:
        result = HealthResult(source=source, status="error", latency_ms=round((perf_counter() - started) * 1000), message="健康檢查逾時")
        source_health_results[source] = result
        return result
    except Exception as exc:
        result = HealthResult(source=source, status="error", latency_ms=round((perf_counter() - started) * 1000), message="健康檢查失敗：回傳格式不符或服務錯誤")
        source_health_results[source] = result
        return result


def _gemini_available() -> bool:
    return bool(
        getattr(settings, "preview_fixture_mode", False)
        or (getattr(settings, "gemini_enabled", True) and getattr(settings, "gemini_api_key", None))
    )


def _source_configuration_status() -> list[dict[str, object]]:
    fixture = bool(getattr(settings, "preview_fixture_mode", False))
    gemini_enabled = bool(getattr(settings, "gemini_enabled", True))
    gemini_configured = bool(getattr(settings, "gemini_api_key", None))
    shioaji_enabled = bool(getattr(settings, "shioaji_enabled", False))
    shioaji_configured = bool(getattr(settings, "shioaji_api_key", None) and getattr(settings, "shioaji_secret_key", None))
    rows = [
        {"source": "Gemini", "purpose": "AI 助手與完整研究分析", "requires_api_key": True,
         "configuration_status": "fixture" if fixture else ("disabled" if not gemini_enabled else "configured" if gemini_configured else "missing"),
         "connection_status": "fixture" if fixture else "not_checked", "required_settings": ["GEMINI_API_KEY"]},
        {"source": "FinMind", "purpose": "歷史日價與市場資料補強", "requires_api_key": False, "api_key_optional": True,
         "configuration_status": "configured" if getattr(settings, "finmind_token", None) else "optional_anonymous",
         "connection_status": "not_checked", "required_settings": ["FINMIND_TOKEN（選填）"]},
        {"source": "TWSE", "purpose": "上市公司、日成交與官方公開資料", "requires_api_key": False,
         "configuration_status": "built_in", "connection_status": "not_checked", "required_settings": []},
        {"source": "TPEx", "purpose": "上櫃公司、日成交與官方公開資料", "requires_api_key": False,
         "configuration_status": "built_in", "connection_status": "not_checked", "required_settings": []},
        {"source": "MOPS", "purpose": "公司基本資料與每日重大訊息", "requires_api_key": False,
         "configuration_status": "built_in", "connection_status": "not_checked", "required_settings": []},
        {"source": "官方新聞", "purpose": "TWSE 官方新聞 RSS 與原文連結", "requires_api_key": False,
         "configuration_status": "built_in", "connection_status": "not_checked", "required_settings": []},
        {"source": "公司法說會", "purpose": "MOPS 每日重訊中的法說公告", "requires_api_key": False,
         "configuration_status": "built_in", "connection_status": "not_checked", "required_settings": []},
        {"source": "官方估值與財務", "purpose": "本益比、殖利率、股價淨值比、月營收與累計 EPS（TWSE／TPEx／MOPS）",
         "requires_api_key": False, "configuration_status": "built_in", "connection_status": "not_checked",
         "required_settings": []},
        {"source": "Shioaji", "purpose": "選配的唯讀行情來源", "requires_api_key": True, "optional": True,
         "configuration_status": "configured" if shioaji_enabled and shioaji_configured else "missing" if shioaji_enabled else "disabled",
         "connection_status": "not_checked" if shioaji_enabled else "disabled",
         "required_settings": ["SHIOAJI_ENABLED=true", "SHIOAJI_API_KEY", "SHIOAJI_SECRET_KEY"]},
    ]
    for row in rows:
        row.update({"checked_at": None, "latest_data_at": None})
        status = str(row["configuration_status"])
        row["message"] = {
            "fixture": "隔離測試模式；不會呼叫真實外部服務",
            "configured": "已設定，尚未執行連線檢查",
            "optional_anonymous": "未設選填 Token；可使用匿名免費額度，尚未檢查",
            "built_in": "不需要 API Key；尚未執行連線檢查",
            "missing": "尚未完成必要設定",
            "disabled": "目前由後端設定關閉",
        }.get(status, "尚未檢查")
        if fixture and row["source"] != "Shioaji":
            row.update(configuration_status="fixture", connection_status="fixture", message="隔離測試模式；不會呼叫真實外部服務")
        elif not fixture:
            result = (getattr(gemini, "last_connection", None) or source_health_results.get("Gemini")) if row["source"] == "Gemini" else source_health_results.get(str(row["source"]))
            if result:
                row.update(result.model_dump(mode="json"))
                row["connection_status"] = result.status
            if row["source"] in {"TWSE", "TPEx", "FinMind"}:
                observation = http.source_observation(str(row["source"]))
                if observation and (not result or observation["data_status"] == "missing" and observation["checked_at"] > result.checked_at):
                    row.update(checked_at=observation["checked_at"].isoformat(), http_status=observation["http_status"],
                        connection_status="error" if observation["data_status"] == "missing" else "not_checked",
                        message="最近請求失敗；不可沿用先前健康狀態" if observation["data_status"] == "missing" else "已收到 HTTP 回應；尚未完成此來源的資料結構健康檢查")
    return rows


@app.get("/api/sources/status")
async def source_configuration_status():
    """Return configuration metadata without contacting any external service."""
    return _source_configuration_status()


def _health_operations():
    operations = {
        "TWSE": twse.health, "TPEx": tpex.health, "MOPS": mops.health,
        "FinMind": finmind.health, "官方新聞": news.health,
        "公司法說會": investor_relations.health, "Gemini": gemini.health,
        "Shioaji": shioaji.health,
    }
    if fundamentals is not None:
        operations["官方估值與財務"] = fundamentals.health
    return operations


async def _startup_source_check() -> None:
    results = await asyncio.gather(*[_health_call(name, operation()) for name, operation in _health_operations().items()])
    available = [result.source for result in results if result.status in {"healthy", "degraded"}]
    print(f"PINWISE 資料來源啟動檢查：{len(available)}/{len(results)} 可用（{'、'.join(available) or '無'}）")


@app.get("/api/sources/health", response_model=list[HealthResult])
async def source_health(source: str | None = None):
    operations = _health_operations()
    if source is not None:
        operation = operations.get(source)
        if operation is None:
            raise HTTPException(400, "不支援的資料來源")
        result = await _health_call(source, operation())
        if getattr(settings, "preview_fixture_mode", False):
            result = result.model_copy(update={"status": "fixture"})
        return [result]
    results = await asyncio.gather(*[_health_call(name, operation()) for name, operation in operations.items()])
    if getattr(settings, "preview_fixture_mode", False):
        return [result.model_copy(update={"status": "fixture"}) for result in results]
    return results


_MARKET_REFRESH_COOLDOWN_SECONDS = 60
_market_refresh_at = -float(_MARKET_REFRESH_COOLDOWN_SECONDS)


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _merge_newer(official: Any, extra: Any) -> Any:
    """官方開放資料較慢時，用 FinMind 補上官方還沒有的較新交易日；官方已有的日期仍以官方為準。"""
    extra_rows = [] if isinstance(extra, Exception) or not extra else [
        {**row, "date": _as_date(row["date"]), "source": "FinMind"} for row in extra
    ]
    if isinstance(official, Exception) or not official:
        return extra_rows[-5:] or official
    latest = max(_as_date(row["date"]) for row in official)
    return [*official, *(row for row in extra_rows if row["date"] > latest)]


def _merge_news(*sources: Any) -> list[dict[str, Any]]:
    """合併開放資料與官方 RSS 的新聞，相同標題只留一則，新的在前。"""
    from datetime import datetime, timezone
    taipei = timezone(timedelta(hours=8))
    items: dict[str, Any] = {}
    for source in sources:
        if isinstance(source, Exception):
            continue
        for item in source:
            items.setdefault(item.title.strip(), item)
    def when(item: Any) -> datetime:
        return item.published_at or datetime.min.replace(tzinfo=timezone.utc)
    return [
        {**item.model_dump(mode="json"), "published_at": item.published_at.astimezone(taipei).isoformat() if item.published_at else None}
        for item in sorted(items.values(), key=when, reverse=True)
    ]


def _market_series(rows: Any) -> dict[str, Any] | None:
    """整理單一市場的日資料；取不到或沒有數字時回傳 None，不以預設值代替。"""
    if isinstance(rows, Exception) or not rows:
        return None
    ordered = sorted((row for row in rows if row.get("date") and row.get("index") is not None), key=lambda row: row["date"])
    if not ordered:
        return None
    latest = ordered[-1]
    previous = latest["index"] - latest["change"] if latest.get("change") is not None else None
    return {
        **latest,
        "source": latest.get("source") or "官方開放資料",
        "change_pct": round(latest["change"] / previous * 100, 2) if previous else None,
        "history": [{"date": row["date"], "index": row["index"]} for row in ordered[-5:]],
    }


def _sector_ranking(rows: Any) -> list[dict[str, Any]]:
    """類股依漲跌幅由高到低；沒有漲跌幅的類股不列入。"""
    if isinstance(rows, Exception) or not rows:
        return []
    return sorted((row for row in rows if row.get("change_pct") is not None), key=lambda row: row["change_pct"], reverse=True)


@app.get("/api/market/overview")
async def market_overview(refresh: bool = Query(False)):
    """大盤、類股、成交量排行收盤資料與證交所新聞。指數取官方與 FinMind 中日期較新者，盤中不會即時更新。"""
    global _market_refresh_at
    async def unavailable():
        raise RuntimeError("隔離預覽模式不提供大盤資料")

    # 使用者按更新時略過快取；同一分鐘內只重抓一次，避免連按造成來源負擔。
    if refresh and hasattr(http, "forget") and perf_counter() - _market_refresh_at >= _MARKET_REFRESH_COOLDOWN_SECONDS:
        _market_refresh_at = perf_counter()
        http.forget("FMTQIK", "tpex_daily_trading_index", "MI_INDEX", "newsList", "news/feed", "TAIEX", "TPEx")

    today = date.today()
    window_start = today - timedelta(days=62)
    twse_rows, tpex_rows, sector_rows, volume_rows, news_rows, taiex_rows, tpex_extra, rss_rows = await asyncio.gather(
        twse.market_summary() if hasattr(twse, "market_summary") else unavailable(),
        tpex.market_summary() if hasattr(tpex, "market_summary") else unavailable(),
        twse.sector_indexes() if hasattr(twse, "sector_indexes") else unavailable(),
        twse.top_volume() if hasattr(twse, "top_volume") else unavailable(),
        news.items(limit=30),
        finmind.index_history("TAIEX", window_start, today) if hasattr(finmind, "index_history") else unavailable(),
        finmind.index_history("TPEx", window_start, today) if hasattr(finmind, "index_history") else unavailable(),
        news.rss_items(limit=30),
        return_exceptions=True,
    )
    twse_rows, tpex_rows = _merge_newer(twse_rows, taiex_rows), _merge_newer(tpex_rows, tpex_extra)
    labels = (
        ("TWSE 大盤資料", twse_rows), ("TPEx 大盤資料", tpex_rows), ("類股指數", sector_rows),
        ("成交量排行", volume_rows), *([("市場新聞", news_rows)] if isinstance(rss_rows, Exception) else []),
    )
    return {
        "twse": _market_series(twse_rows),
        "tpex": _market_series(tpex_rows),
        "sectors": _sector_ranking(sector_rows),
        "top_volume": [] if isinstance(volume_rows, Exception) else volume_rows,
        "news": _merge_news(rss_rows, news_rows)[:30],
        "errors": [label for label, value in labels if isinstance(value, Exception)],
        "data_frequency": "daily",
        "notice": "官方盤後日資料，不是即時行情。",
    }


@app.get("/api/market/index-history")
async def market_index_history():
    """加權指數近兩個月日收盤，供市場總覽切換 15 日與一個月走勢；取不到時回傳空清單，不以預設值代替。"""
    if not hasattr(finmind, "index_history"):
        return {"points": [], "source": None, "error": "隔離預覽模式不提供指數歷史"}
    today = date.today()
    try:
        rows = await finmind.index_history("TAIEX", today - timedelta(days=62), today)
        points = [{"date": row["date"], "index": row["index"]} for row in rows]
    except Exception:
        return {"points": [], "source": None, "error": "FinMind 指數歷史暫時無法取得"}
    return {"points": points, "source": "FinMind", "error": None}


@app.get("/api/market/quote/{symbol}")
async def market_quote(symbol: str):
    code = normalized_symbol(symbol)
    if not code:
        raise HTTPException(422, "股票代號不可為空")
    results = await asyncio.gather(twse.quote(code), tpex.quote(code), return_exceptions=True)
    result = next((item for item in results if item is not None and not isinstance(item, Exception)), None)
    errors = [item for item in results if isinstance(item, Exception)]
    if not result and len(errors) == len(results):
        raise errors[0]
    if not result:
        raise HTTPException(404, "TWSE／TPEx 當日資料中找不到此代號")
    return result


@app.get("/api/esg")
async def esg_summaries(symbols: str = ""):
    """多檔的揭露完整度摘要（公司自行申報），最多 30 檔。來源失敗時回傳空清單與 available=false。"""
    codes = list(dict.fromkeys(code for code in (normalized_symbol(raw) for raw in symbols.split(",")[:30]) if code))
    if esg_provider is None:
        return {"available": False, "items": []}
    try:
        return {"available": True, "items": await esg_provider.summaries(codes)}
    except Exception:
        return {"available": False, "items": []}


@app.get("/api/esg/{symbol}")
async def esg_company(symbol: str):
    """單一公司的 ESG 揭露。reason：not_listed 沒有申報資料（例如 ETF）、source_failed 來源暫時失敗。"""
    code = normalized_symbol(symbol)
    if esg_provider is None or not code:
        return {"available": False, "symbol": code, "reason": "source_failed"}
    try:
        data = await esg_provider.company(code)
    except Exception:
        return {"available": False, "symbol": code, "reason": "source_failed"}
    return {"available": True, **data} if data else {"available": False, "symbol": code, "reason": "not_listed"}


@app.get("/api/etf/{symbol}/holdings")
async def etf_holdings(symbol: str):
    """ETF 成份股（投信公開揭露）。沒有資料或來源失敗時回傳 available=false，前端不顯示成份股。"""
    code = normalized_symbol(symbol)
    data = None
    if etf_holdings_service is not None and code:
        try:
            data = await etf_holdings_service.holdings(code)
        except Exception:
            data = None
    return {"available": True, **data} if data else {"available": False, "symbol": code}


@app.get("/api/stocks/{symbol}/overview")
async def stock_overview(symbol: str, months: int = Query(6, ge=1, le=24)):
    """Latest daily quote, daily candles for a K-line chart and official fundamentals in one call."""
    from datetime import timedelta
    from .services.analytics import price_metrics
    from .services.research import fundamental_metrics

    code = normalized_symbol(symbol)
    if not code:
        raise HTTPException(422, "股票代號不可為空")
    end = date.today()
    start = end - timedelta(days=31 * months)

    async def no_fundamentals():
        return None

    quotes, history, snapshot = await asyncio.gather(
        asyncio.gather(twse.quote(code), tpex.quote(code), return_exceptions=True),
        finmind.history(code, start, end),
        fundamentals.snapshot(code) if fundamentals is not None else no_fundamentals(),
        return_exceptions=True,
    )
    errors = []
    quote = None
    if not isinstance(quotes, Exception):
        quote = next((item for item in quotes if item is not None and not isinstance(item, Exception)), None)
        if quote is None and all(isinstance(item, Exception) for item in quotes):
            errors.append({"source": "TWSE／TPEx", "message": "日行情暫時無法取得"})
    if isinstance(history, Exception):
        errors.append({"source": "FinMind", "message": "歷史日價暫時無法取得"})
        history = []
    if isinstance(snapshot, Exception):
        errors.append({"source": "官方估值與財務", "message": "估值與財務資料暫時無法取得"})
        snapshot = None
    if quote is None and not history:
        raise HTTPException(404, "官方資料中找不到此代號，或來源暫時無法取得")
    candles = [{"date": row.trade_date.isoformat(), "open": row.open, "high": row.high, "low": row.low,
                "close": row.close, "volume": row.volume_shares}
               for row in history if row.close is not None]
    # Show the most recent trading day available from either official source.
    latest = None
    if quote and quote.close is not None and quote.trade_date:
        latest = {"date": quote.trade_date.isoformat(), "close": quote.close, "change": quote.change,
                  "source": "TWSE" if quote.market == "TWSE" else "TPEx"}
    if candles and (latest is None or candles[-1]["date"] > latest["date"]):
        previous = candles[-2]["close"] if len(candles) > 1 else None
        latest = {"date": candles[-1]["date"], "close": candles[-1]["close"],
                  "change": round(candles[-1]["close"] - previous, 2) if previous is not None else None,
                  "source": "FinMind"}
    if latest and latest.get("change") is not None and latest["close"] - latest["change"]:
        latest["change_pct"] = round(latest["change"] / (latest["close"] - latest["change"]) * 100, 2)
    return {
        "symbol": code, "name": (quote.name if quote else None) or (snapshot.name if snapshot else None),
        "latest": latest,
        "quote": quote.model_dump(mode="json") if quote else None,
        "candles": candles, "metrics": price_metrics(history),
        "fundamentals": fundamental_metrics(snapshot) if snapshot else {},
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "errors": errors,
        "notice": "價格為官方最近交易日收盤，不是即時報價；K 線為 FinMind 公開的每日開高低收。",
    }


@app.get("/api/market/history/{symbol}")
async def market_history(symbol: str, start_date: date, end_date: date):
    code = normalized_symbol(symbol)
    if start_date > end_date:
        raise HTTPException(422, "start_date 不可晚於 end_date")
    if (end_date - start_date).days > 3650:
        raise HTTPException(422, "單次查詢期間不可超過 10 年")
    return await finmind.history(code, start_date, end_date)


@app.post("/api/stocks/select")
async def select_stocks(payload: PickerRequest):
    funnel: dict = {}
    items = await market.select(payload, funnel)
    return {
        "items": items,
        "funnel": funnel,
        "data_frequency": "daily",
        "notice": "排序使用交易所最近可得日資料，不是即時行情，也不是買進建議。",
    }


@app.post("/api/stocks/ai-select")
async def ai_select_stocks(payload: AIPickerRequest):
    """Natural-language picker: AI interprets and explains; filtering and ranking use official data only."""
    return await ai_picker.select(payload)


@app.post("/api/input/understand", response_model=InputUnderstandingResponse)
async def understand_input(payload: InputUnderstandingRequest):
    """Deterministic, allow-listed interpretation; it never executes model-generated code or URLs."""
    return await input_understanding.understand(payload)


@app.post("/api/assistant/stream")
async def assistant_stream(payload: AssistantRequest, request: Request):
    if not _gemini_available():
        raise HTTPException(503, "缺少 GEMINI_API_KEY；助手不會改用示範回答")
    try:
        visitor_id = visitor_id_from_scope(request.scope)
        await assistant_capacity.acquire(visitor_id)
    except PreviewLimitError as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "5"}) from exc

    async def events():
        import json
        try:
            async for event in assistant.stream(payload):
                yield "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"
        except PreviewLimitError as exc:
            limited = {"type": "error", "code": "demo_budget_exhausted", "message": str(exc)}
            yield "data: " + json.dumps(limited, ensure_ascii=False) + "\n\n"
        except Exception:
            # Do not expose secrets or raw provider payloads after headers were sent.
            fallback = {"type": "error", "code": "stream_interrupted",
                        "message": "助手串流中斷，本次已停止，沒有改用示範回答。"}
            yield "data: " + json.dumps(fallback, ensure_ascii=False) + "\n\n"
        finally:
            await assistant_capacity.release(visitor_id)

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
    })


@app.post("/api/stocks/snapshots")
async def stock_snapshots(payload: StockSnapshotRequest):
    return {
        "items": await market.snapshots(payload.symbols),
        "data_frequency": "daily",
    }


@app.get("/api/companies/{symbol}")
async def company_profile(symbol: str):
    result = await mops.company(normalized_symbol(symbol))
    if not result:
        raise HTTPException(404, "MOPS 官方公開資料中找不到此公司代號")
    return result


@app.get("/api/mops/material-events")
async def material_events(symbol: str | None = None, limit: int = Query(100, ge=1, le=500)):
    return await mops.disclosures(normalized_symbol(symbol) if symbol else None, limit=limit)


@app.get("/api/news")
async def official_news(limit: int = Query(50, ge=1, le=200)):
    return await news.items(limit=limit)


@app.get("/api/news/rss")
async def official_news_rss(limit: int = Query(20, ge=1, le=100)):
    return await news.rss_items(limit=limit)


@app.get("/api/ir/conferences")
async def ir_conferences(symbol: str | None = None, limit: int = Query(100, ge=1, le=200)):
    return await investor_relations.conferences(normalized_symbol(symbol) if symbol else None, limit=limit)


@app.post("/api/research")
async def run_research(payload: ResearchRequest, request: Request):
    if not _gemini_available():
        raise HTTPException(503, "缺少 GEMINI_API_KEY；公開資料查詢仍可使用，但 AI 研究尚未啟用")
    acquired = False
    try:
        visitor_id = visitor_id_from_scope(request.scope)
        await research_capacity.acquire(visitor_id)
        acquired = True
        return await research.run(payload)
    except PreviewLimitError as exc:
        retry_after = "3600" if "每日" in str(exc) or "token" in str(exc) else "5"
        raise HTTPException(429, str(exc), headers={"Retry-After": retry_after}) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    finally:
        if acquired:
            await research_capacity.release(visitor_id)


@app.post("/api/research/jobs", response_model=ResearchJob, status_code=status.HTTP_202_ACCEPTED)
async def create_research_job(payload: ResearchRequest, request: Request):
    if not _gemini_available():
        raise HTTPException(503, "缺少 GEMINI_API_KEY；研究任務未建立")
    try:
        return await research_jobs.create(payload, visitor_id_from_scope(request.scope))
    except ResearchCapacityError as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "5"}) from exc


@app.get("/api/research/jobs/{job_id}", response_model=ResearchJob)
async def get_research_job(job_id: str, request: Request):
    job = await research_jobs.get(job_id, visitor_id_from_scope(request.scope))
    if not job:
        raise HTTPException(404, "找不到研究任務")
    return job


@app.post("/api/research/jobs/{job_id}/pause", response_model=ResearchJob)
async def pause_research_job(job_id: str, request: Request):
    job = await research_jobs.pause(job_id, visitor_id_from_scope(request.scope))
    if not job:
        raise HTTPException(404, "找不到研究任務")
    return job


@app.post("/api/research/jobs/{job_id}/resume", response_model=ResearchJob)
async def resume_research_job(job_id: str, request: Request):
    job = await research_jobs.resume(job_id, visitor_id_from_scope(request.scope))
    if not job:
        raise HTTPException(404, "找不到研究任務")
    return job


@app.delete("/api/research/jobs/{job_id}/record", status_code=204)
async def delete_research_record(job_id: str, request: Request):
    if not await research_jobs.purge(job_id, visitor_id_from_scope(request.scope)):
        raise HTTPException(404, "找不到研究任務")
    return Response(status_code=204)


@app.post("/api/feedback", status_code=204)
async def submit_feedback(entry: FeedbackEntry, request: Request):
    await feedback_store.add(entry, visitor_id_from_scope(request.scope))
    return Response(status_code=204)


@app.delete("/api/research/jobs/{job_id}", response_model=ResearchJob)
async def cancel_research_job(job_id: str, request: Request):
    job = await research_jobs.cancel(job_id, visitor_id_from_scope(request.scope))
    if not job:
        raise HTTPException(404, "找不到研究任務")
    return job


async def _json_body(request: Request, key: str, expected: type):
    body = await request.body()
    if len(body) > WORKSPACE_MAX_BYTES:
        raise HTTPException(413, "工作區資料過大，未儲存")
    try:
        import json
        value = json.loads(body or b"{}").get(key)
    except (ValueError, AttributeError):
        raise HTTPException(422, "工作區資料格式錯誤") from None
    if not isinstance(value, expected):
        raise HTTPException(422, "工作區資料格式錯誤")
    return value


@app.get("/api/workspace")
async def get_workspace(request: Request):
    """Return the visitor's saved workspace; enabled=false means the browser keeps local storage only."""
    if not workspace:
        return {"enabled": False}
    return {"enabled": True, **await workspace.load(visitor_id_from_scope(request.scope))}


@app.put("/api/workspace/state")
async def save_workspace_state(request: Request):
    if not workspace:
        return {"enabled": False}
    await workspace.save_state(visitor_id_from_scope(request.scope), await _json_body(request, "state", dict))
    return {"enabled": True, "saved": True}


@app.put("/api/workspace/conversations")
async def save_workspace_conversations(request: Request):
    if not workspace:
        return {"enabled": False}
    await workspace.save_conversations(visitor_id_from_scope(request.scope), await _json_body(request, "conversations", list))
    return {"enabled": True, "saved": True}


async def _credentials(request: Request) -> tuple[str, str]:
    if not accounts:
        raise HTTPException(503, "帳號功能需要設定 PostgreSQL（DATABASE_URL）")
    client = request.client.host if request.client else "unknown"
    if not await login_limiter.allow(client):
        raise HTTPException(429, "嘗試次數過多，請一分鐘後再試", headers={"Retry-After": "60"})
    username = await _json_body(request, "username", str)
    password = await _json_body(request, "password", str)
    return username, password


def _session_response(user: dict, token: str) -> JSONResponse:
    return JSONResponse({"user": user, "token": token}, headers={"Cache-Control": "no-store"})


@app.get("/api/auth/me")
async def account_me(request: Request):
    return {"enabled": bool(accounts), "user": request.scope.get("finpilot.user")}


@app.post("/api/auth/register")
async def account_register(request: Request):
    username, password = await _credentials(request)
    try:
        user = await accounts.register(username, password)
    except AccountError as exc:
        raise HTTPException(409 if exc.code == "username_taken" else 422, str(exc)) from None
    return _session_response(user, await accounts.create_session(user["id"]))


@app.post("/api/auth/login")
async def account_login(request: Request):
    username, password = await _credentials(request)
    user = await accounts.authenticate(username, password)
    if user is None:
        raise HTTPException(401, "帳號或密碼不正確")
    return _session_response(user, await accounts.create_session(user["id"]))


@app.post("/api/auth/logout")
async def account_logout(request: Request):
    token = request.scope.get("finpilot.session_token")
    if accounts and token:
        await accounts.delete_session(token)
    return {"logged_out": True}


@app.get("/api/database/status")
async def database_status():
    if not database:
        return {"storage": "json_files", "enabled": False}
    return {"storage": "postgresql", "enabled": True, **await database.run(database_summary)}


# API 路由必須先註冊；最後才掛載原有前端，確保同源部署且不暴露 .env。
# 有打包好的 Vue 前端（frontend-vue/dist，執行 npm run build 產生）就由後端一起提供，
# 一個網址即可使用整個網站，方便以通道或雲端對外展示；沒有打包時維持原本的根目錄。
VUE_DIST = PROJECT_ROOT / "frontend-vue" / "dist"
FRONTEND_DIR = VUE_DIST if (VUE_DIST / "index.html").is_file() else PROJECT_ROOT
app.mount("/", FrontendStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
