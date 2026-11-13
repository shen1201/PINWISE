from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


Market = Literal["TWSE", "TPEX", "EMERGING", "UNKNOWN"]
HealthStatus = Literal["healthy", "degraded", "stale", "pending", "fixture", "disabled", "error"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceMetadata(BaseModel):
    source: str
    source_url: str
    fetched_at: datetime = Field(default_factory=utc_now)
    raw_source: str
    period_start: date | None = None
    period_end: date | None = None
    missing: bool = False
    missing_reason: str | None = None
    stale: bool = False
    data_status: Literal["real", "cache", "fixture", "missing", "unverified"] = "unverified"


class MarketQuote(BaseModel):
    symbol: str
    name: str | None = None
    market: Market
    trade_date: date | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    change: float | None = None
    volume_shares: int | None = None
    trade_value_twd: int | None = None
    transactions: int | None = None
    metadata: SourceMetadata


class PricePoint(BaseModel):
    symbol: str
    market: Market = "UNKNOWN"
    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    change: float | None = None
    volume_shares: int | None = None
    trade_value_twd: int | None = None
    transactions: int | None = None
    metadata: SourceMetadata


class CompanyProfile(BaseModel):
    symbol: str
    name: str | None = None
    short_name: str | None = None
    market: Market
    industry_code: str | None = None
    listing_date: date | None = None
    website: str | None = None
    paid_in_capital_twd: float | None = None
    issued_shares: int | None = None
    metadata: SourceMetadata


class DisclosureEvent(BaseModel):
    symbol: str
    company_name: str | None = None
    market: Market
    published_at: datetime | None = None
    event_date: date | None = None
    title: str
    description: str | None = None
    article: str | None = None
    metadata: SourceMetadata


class NewsItem(BaseModel):
    title: str
    url: str
    published_at: datetime | None = None
    source: str
    symbol: str | None = None
    summary: str | None = None
    metadata: SourceMetadata


class InvestorConference(BaseModel):
    symbol: str
    company_name: str | None = None
    market: Market
    announced_at: datetime | None = None
    event_date: date | None = None
    title: str
    details: str | None = None
    metadata: SourceMetadata


class HealthResult(BaseModel):
    source: str
    status: HealthStatus
    checked_at: datetime = Field(default_factory=utc_now)
    latency_ms: int | None = None
    record_count: int | None = None
    latest_data_at: datetime | date | None = None
    message: str
    endpoint: str | None = None
    required_settings: list[str] = Field(default_factory=list)
    http_status: int | None = None


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    symbols: list[str] = Field(default_factory=list, max_length=8)
    research_type: Literal[
        "single_company", "etf", "multi_target_comparison", "industry_supply_chain",
        "market_trend", "stock_screen", "knowledge", "unknown",
    ] = "unknown"
    research_topic: str | None = Field(default=None, max_length=120)
    horizon: str | None = Field(default=None, max_length=80)
    risk_preference: str | None = Field(default=None, max_length=80)
    preferences: dict[str, Any] = Field(default_factory=dict)


class InputUnderstandingRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    context: Literal["home", "research", "assistant"] = "research"
    default_history_months: int = Field(default=6, ge=1, le=120)


class InputCandidate(BaseModel):
    symbol: str
    name: str
    short_name: str | None = None
    market: Market
    matched_text: str
    typed_text: str | None = None  # 同音或近似比對時，使用者實際輸入的那幾個字
    match_kind: Literal["symbol", "official_name", "short_name", "alias", "phonetic", "approximate"]
    confidence: float = Field(ge=0, le=1)


class InputHypothesis(BaseModel):
    type: Literal["price_target", "price_scenario"]
    value: float
    unit: Literal["TWD"] = "TWD"
    raw_text: str = Field(max_length=120)
    source: Literal["user"] = "user"
    conditional: bool = True
    symbol: str | None = Field(default=None, max_length=16)


class InputConstraint(BaseModel):
    type: Literal["budget", "risk_preference", "research_preference"]
    value: str | float
    unit: str | None = Field(default=None, max_length=16)
    raw_text: str = Field(max_length=160)
    source: Literal["user"] = "user"
    retention: Literal["conversation"] = "conversation"


class InputUnderstandingResponse(BaseModel):
    raw_input: str
    normalized_input: str
    context: Literal["home", "research", "assistant"]
    intent: Literal[
        "investment_decision", "target_price_scenario", "valuation", "risk_analysis",
        "compare", "rephrase", "full_research", "research", "screen", "explain", "track", "unknown",
    ]
    target_status: Literal["recognized", "ambiguous", "needs_confirmation", "not_required", "source_error"]
    candidates: list[InputCandidate] = Field(default_factory=list)
    selected_symbol: str | None = None
    resolved_symbols: list[str] = Field(default_factory=list, max_length=3)
    assumptions: list[str] = Field(default_factory=list, max_length=6)
    research_type: Literal[
        "single_company", "etf", "multi_target_comparison", "industry_supply_chain",
        "market_trend", "stock_screen", "knowledge", "unknown",
    ] = "unknown"
    research_topic: str | None = Field(default=None, max_length=120)
    historical_period: dict[str, Any]
    outlook_period: dict[str, Any] | None = None
    constraints: list[str] = Field(default_factory=list)
    structured_constraints: list[InputConstraint] = Field(default_factory=list)
    hypotheses: list[InputHypothesis] = Field(default_factory=list)
    requires_market_data: bool = False
    classification_signals: list[str] = Field(default_factory=list)
    corrections: list[dict[str, str]] = Field(default_factory=list)
    message: str
    source_status: Literal["official", "partial", "error"] = "official"
    source_names: list[str] = Field(default_factory=list)


class AssistantHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=6000)


class AssistantMemory(BaseModel):
    version: int = Field(default=2, ge=1, le=10)
    confirmed_symbol: str | None = Field(default=None, max_length=16)
    recent_symbols: list[str] = Field(default_factory=list, max_length=3)
    active_symbols: list[str] = Field(default_factory=list, max_length=3)
    comparison_symbols: list[str] = Field(default_factory=list, max_length=3)
    last_intent: str | None = Field(default=None, max_length=40)
    hypotheses: list[InputHypothesis] = Field(default_factory=list, max_length=6)
    constraints: list[InputConstraint] = Field(default_factory=list, max_length=8)
    historical_period: dict[str, Any] | None = None
    last_tool_results: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    last_verified_claims: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    last_answer_reference: str | None = Field(default=None, max_length=2400)
    as_of: str | None = Field(default=None, max_length=40)
    expires_at: str | None = Field(default=None, max_length=40)
    updated_at: str | None = Field(default=None, max_length=40)
    structured_summary: dict[str, Any] = Field(default_factory=dict)


class AssistantRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=4000)
    history: list[AssistantHistoryMessage] = Field(default_factory=list, max_length=20)
    memory: AssistantMemory = Field(default_factory=AssistantMemory)
    preferences: dict[str, Any] = Field(default_factory=dict)


class FundamentalSnapshot(BaseModel):
    """Official valuation, monthly revenue and cumulative earnings; missing values stay None."""
    symbol: str
    name: str | None = None
    market: Market
    industry_name: str | None = None
    valuation_date: date | None = None
    pe_ratio: float | None = None
    dividend_yield_pct: float | None = None
    pb_ratio: float | None = None
    revenue_month: str | None = None
    revenue_thousand_twd: float | None = None
    revenue_mom_pct: float | None = None
    revenue_yoy_pct: float | None = None
    revenue_ytd_yoy_pct: float | None = None
    eps_period: str | None = None
    eps_ytd: float | None = None
    operating_margin_pct: float | None = None
    metadata: SourceMetadata
    sources: list[str] = Field(default_factory=list)


class AIPickerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=8, ge=1, le=20)
    preferences: dict[str, Any] = Field(default_factory=dict)
    explain: bool = True


class PickerRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    product_type: Literal["all", "stock", "etf"] = "all"
    market: Literal["all", "TWSE", "TPEX"] = "all"
    industry: str | None = Field(default=None, max_length=80)
    period: str | None = Field(default=None, max_length=40)
    risk: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=12, ge=1, le=50)


class StockSnapshotRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=20)


ResearchJobStatus = Literal[
    "queued", "running", "pause_requested", "paused", "cancel_requested",
    "cancelled", "completed", "failed",
]


class ResearchEvent(BaseModel):
    id: str
    sequence: int
    phase: str
    agent: str
    action: str
    detail: str
    source: str
    status: Literal["started", "completed", "failed", "skipped", "retrying", "cancelled", "paused"]
    progress: int = Field(ge=0, le=100)
    at: datetime = Field(default_factory=utc_now)
    duration_ms: int | None = None
    attempt: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchResponse(BaseModel):
    query: str
    data_mode: Literal["live", "fixture", "unverified"] = "unverified"
    verification_status: Literal["limited", "sourced", "unverified"] = "unverified"
    status: Literal["completed"] = "completed"
    summary: str
    risks: list[str]
    candidates: list[str]
    evidence: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    metrics: dict[str, Any] = Field(default_factory=dict)
    invalidation_conditions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    prompt_version: str = "finpilot-research-v3"
    duration_ms: int | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=utc_now)
    model: str
    watch_items: list[dict[str, Any]] = Field(default_factory=list)


class ResearchJob(BaseModel):
    id: str
    fingerprint: str
    status: ResearchJobStatus = "queued"
    progress: int = 0
    current_phase: str = "understanding"
    current_operation: str | None = None
    request: ResearchRequest
    prompt_version: str = "finpilot-research-v3"
    model: str
    events: list[ResearchEvent] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    result: ResearchResponse | None = None
    error: dict[str, Any] | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    duration_ms: int | None = None
    deduplicated: bool = False
