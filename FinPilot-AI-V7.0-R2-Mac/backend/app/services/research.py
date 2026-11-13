from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable
from uuid import uuid4

from ..core.models import ResearchRequest, ResearchResponse, utc_now
from ..core.provenance import require_live_data
from ..providers.finmind import FinMindProvider
from ..providers.gemini import GeminiProvider
from ..providers.investor_relations import InvestorRelationsProvider
from ..providers.mops import MOPSProvider
from ..providers.news import NewsProvider
from ..providers.tpex import TPExProvider
from ..providers.twse import TWSEProvider
from .analytics import completeness, price_metrics
from .market import MarketService
from .input_understanding import parse_period, requested_count, strip_count


PROMPT_VERSION = "finpilot-research-v4-fundamentals"
EventCallback = Callable[..., Awaitable[None]]
Checkpoint = Callable[[], Awaitable[None]]


def compact_prompt_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep full evidence in the report; send bounded, non-repeated facts to Gemini."""
    result = []
    for item in evidence:
        row = {key: value for key, value in item.items() if key != "data"}
        # Quantitative history is already represented by deterministic metrics.
        # Per-row metadata repeats the same endpoint and does not add model facts.
        rows = item.get("data") or []
        selected = rows[-2:] if "歷史日行情" in item.get("source", "") else rows[:5]
        row["data"] = [{key: value for key, value in record.items() if key != "metadata"}
                       if isinstance(record, dict) else record for record in selected]
        row["prompt_sample_count"] = len(selected)
        result.append(row)
    return result

URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d[\d,]*(?:\.\d+)?")
def research_date_range(horizon: str | None, query: str, *, today: date | None = None) -> tuple[date, date, str, bool]:
    """Resolve a historical window without mistaking a calendar year for a duration."""
    period, _ = parse_period(f"{horizon or ''} {query or ''}", today=today)
    return date.fromisoformat(period["start"]), date.fromisoformat(period["end"]), period["label"], period["defaulted"]


def _canonical_number(value: str) -> str | None:
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None
    normalized = format(number.normalize(), "f")
    return "0" if normalized in {"-0", "+0"} else normalized


def _number_tokens(value: Any) -> set[str]:
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    return {token for raw in NUMBER_PATTERN.findall(serialized) if (token := _canonical_number(raw)) is not None}


METRIC_CLAIMS = {
    "period_return_pct": re.compile(r"(?:期間)?報酬(?:率)?[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*(%|％)?"),
    "annualized_volatility_pct": re.compile(r"(?:年化)?波動(?:率|度)?[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*(%|％)?"),
    "max_drawdown_pct": re.compile(r"最大回撤[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*(%|％)?"),
    "latest_close": re.compile(r"(?:期末|最新)?收盤(?:價)?[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*(元)?"),
}


def _metric_claim_problems(text: str, metrics: dict[str, Any], symbols: list[str], evidence: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    sentences = re.split(r"[;；。！？\n]", text)
    for sentence in sentences:
        mentioned = [symbol for symbol in symbols if re.search(rf"(?<!\d){re.escape(symbol)}(?!\d)", sentence)]
        target = mentioned[0] if len(mentioned) == 1 else (symbols[0] if len(symbols) == 1 else None)
        for metric, pattern in METRIC_CLAIMS.items():
            for match in pattern.finditer(sentence):
                token = _canonical_number(match.group(1))
                expected = _canonical_number(str((metrics.get(target) or {}).get(metric))) if target else None
                unit = match.group(2)
                expected_unit = "元" if metric == "latest_close" else "%"
                if target is None:
                    problems.append(f"指標 {metric} 未綁定標的")
                elif expected is None or token != expected:
                    problems.append(f"{target} 的 {metric}={match.group(1)} 與程式計算不符")
                elif not any(item.get("source") == f"{target} 歷史日行情" and not item.get("missing") for item in evidence):
                    problems.append(f"{target} 的 {metric} 沒有可用歷史日行情來源")
                if unit is None:
                    problems.append(f"{target or '未知標的'} 的 {metric} 缺少單位 {expected_unit}")
                period = metrics.get("query_period") or {}
                if years := re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", sentence):
                    start_year = int(str(period.get("period_start") or "0000")[:4])
                    end_year = int(str(period.get("period_end") or "0000")[:4])
                    if any(not (start_year <= int(year) <= end_year) for year in years):
                        problems.append(f"{target or '未知標的'} 的 {metric} 期間與查詢區間不符")
    return problems


# Numbers spelled in Chinese (e.g. 百分之十一點一) cannot be matched against evidence,
# so they would bypass the numeric check; such sentences are treated as unverifiable.
CHINESE_NUMBER_PATTERN = re.compile(
    r"百分之[零〇一二兩三四五六七八九十百千點]+|[零〇一二兩三四五六七八九十百千]+點[零〇一二三四五六七八九]+"
)


def _unsupported_model_claims(text: str, allowed_numbers: set[str], metrics: dict[str, Any] | None = None,
                              symbols: list[str] | None = None, evidence: list[dict[str, Any]] | None = None) -> list[str]:
    problems = [f"網址 {url}" for url in URL_PATTERN.findall(text)]
    problems.extend(f"中文數字 {value}（無法與證據核對）" for value in CHINESE_NUMBER_PATTERN.findall(text))
    for raw in NUMBER_PATTERN.findall(text):
        token = _canonical_number(raw)
        if token is not None and token not in allowed_numbers:
            problems.append(f"數字 {raw}")
    if metrics is not None and symbols:
        problems.extend(_metric_claim_problems(text, metrics, symbols, evidence or []))
    return list(dict.fromkeys(problems))


SENTENCE_PATTERN = re.compile(r"[^。！？；;\n]+[。！？；;]?")


def validated_sentences(text: Any, allowed_numbers: set[str], metrics: dict[str, Any] | None = None,
                        symbols: list[str] | None = None, evidence: list[dict[str, Any]] | None = None
                        ) -> tuple[str | None, list[str], list[str]]:
    """Keep the sentences whose numbers and URLs are backed by evidence.

    Returns (kept text or None, rejected sentences, problems).  Only the
    unsupported sentences are removed, so one bad number no longer discards a
    whole paragraph of otherwise verified analysis.
    """
    kept, rejected, problems = [], [], []
    for sentence in SENTENCE_PATTERN.findall(str(text or "").strip()):
        if not sentence.strip():
            continue
        found = _unsupported_model_claims(sentence, allowed_numbers, metrics, symbols, evidence)
        if found:
            rejected.append(sentence.strip())
            problems.extend(found)
        else:
            kept.append(sentence)
    result = "".join(kept).strip()
    return (result or None), rejected, problems


FUNDAMENTAL_FIELDS = (
    "valuation_date", "pe_ratio", "dividend_yield_pct", "pb_ratio", "revenue_month", "revenue_yoy_pct",
    "revenue_mom_pct", "revenue_ytd_yoy_pct", "eps_period", "eps_ytd", "operating_margin_pct",
)


def fundamental_metrics(snapshot) -> dict[str, Any]:
    """Official fundamentals as metric fields; dates become ISO strings, missing values are omitted."""
    values = snapshot.model_dump(mode="json") if hasattr(snapshot, "model_dump") else dict(snapshot)
    return {key: values[key] for key in FUNDAMENTAL_FIELDS if values.get(key) is not None}


def _deterministic_summary(symbols: list[str], metrics: dict[str, Any], horizon_label: str) -> str:
    rows = []
    for symbol in symbols:
        item = metrics.get(symbol) or {}
        period = " 至 ".join(value for value in (item.get("period_start"), item.get("period_end")) if value)
        facts = []
        if item.get("period_return_pct") is not None:
            facts.append(f"期間報酬 {item['period_return_pct']}%")
        if item.get("annualized_volatility_pct") is not None:
            facts.append(f"年化波動 {item['annualized_volatility_pct']}%")
        if item.get("max_drawdown_pct") is not None:
            facts.append(f"最大回撤 {item['max_drawdown_pct']}%")
        if item.get("latest_close") is not None:
            facts.append(f"期末收盤 {item['latest_close']} 元")
        if item.get("revenue_yoy_pct") is not None:
            facts.append(f"{item.get('revenue_month', '最新')} 月營收年增 {item['revenue_yoy_pct']}%")
        if item.get("eps_ytd") is not None:
            facts.append(f"{item.get('eps_period', '累計')} EPS {item['eps_ytd']} 元")
        if item.get("pe_ratio") is not None:
            facts.append(f"本益比 {item['pe_ratio']} 倍")
        if item.get("dividend_yield_pct") is not None:
            facts.append(f"殖利率 {item['dividend_yield_pct']}%")
        rows.append(f"{symbol} 在{period or horizon_label}的程式計算結果為：{'、'.join(facts) if facts else '歷史日價不足，未計算期間指標'}")
    return "；".join(rows) + "。以上數值來自保存的日價資料與程式計算；質化判斷仍須對照來源及資料缺漏。"


class ResearchExecutionError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ResearchService:
    def __init__(
        self, *, twse: TWSEProvider, tpex: TPExProvider, mops: MOPSProvider,
        finmind: FinMindProvider, news: NewsProvider,
        ir: InvestorRelationsProvider, gemini: GeminiProvider,
        market: MarketService | None = None, fundamentals=None,
    ):
        self.fundamentals = fundamentals
        self.twse = twse
        self.tpex = tpex
        self.mops = mops
        self.finmind = finmind
        self.news = news
        self.ir = ir
        self.gemini = gemini
        self.market = market or MarketService(twse=twse, tpex=tpex, mops=mops, finmind=finmind)

    @staticmethod
    def _evidence(label: str, value: Any, error: str | None = None) -> dict[str, Any]:
        if value is None or value == []:
            return {
                "source": label, "title": f"{label} 無可用資料", "url": None,
                "fetched_at": utc_now().isoformat(), "period_start": None, "period_end": None,
                "missing": True, "missing_reason": error or "目前期間沒有資料", "stale": False,
                "data": None, "data_status": "missing", "provider": None, "subjects": [label.split()[0]],
                "evidence_id": label, "latest_data_at": None, "record_count": 0,
            }
        sample = value[-30:] if isinstance(value, list) else [value]
        # Period datasets are ordered oldest -> newest.  Use the newest row for
        # freshness/fetch metadata while preserving the sampled period below.
        newest = sample[-1]
        metadata = newest.metadata if hasattr(newest, "metadata") else None
        dates = []
        for row in value if isinstance(value, list) else [value]:
            stamp = (getattr(row, "trade_date", None) or getattr(row, "published_at", None)
                     or getattr(row, "announced_at", None) or getattr(getattr(row, "metadata", None), "period_end", None))
            if stamp:
                dates.append(stamp.isoformat()[:10])
        from ..core.provenance import contains_fixture
        data_status = "fixture" if contains_fixture(value) else getattr(metadata, "data_status", "unverified")
        return {
            "evidence_id": label, "provider": metadata.source if metadata else None,
            "subjects": sorted({str(row.symbol) for row in sample if getattr(row, "symbol", None)}),
            "data_status": data_status, "latest_data_at": max(dates, default=None),
            "record_count": len(value) if isinstance(value, list) else 1,
            "source": label,
            "title": metadata.raw_source if metadata else label,
            "url": metadata.source_url if metadata else None,
            "fetched_at": (metadata.fetched_at if metadata else utc_now()).isoformat(),
            "period_start": min(dates) if dates else None,
            "period_end": max(dates) if dates else None,
            "missing": False, "missing_reason": None,
            "stale": bool(metadata.stale) if metadata else False,
            "data": [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in sample],
        }

    async def run(
        self,
        request: ResearchRequest,
        *,
        emit: EventCallback | None = None,
        checkpoint: Checkpoint | None = None,
    ) -> ResearchResponse:
        started = time.perf_counter()
        trace: list[dict[str, Any]] = []
        sequence = 0
        start, end, horizon_label, horizon_defaulted = research_date_range(request.horizon, request.query)

        async def event(
            phase: str, agent: str, action: str, detail: str, source: str,
            status: str, progress: int, *, duration_ms: int | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            nonlocal sequence
            sequence += 1
            row = {
                "id": f"event_{sequence}_{uuid4().hex[:6]}", "sequence": sequence,
                "phase": phase, "agent": agent, "action": action, "detail": detail,
                "source": source, "status": status, "progress": progress,
                "at": utc_now().isoformat(), "duration_ms": duration_ms,
                "attempt": 1, "metadata": metadata or {}, "demo": False,
            }
            trace.append(row)
            if emit:
                await emit(**row)

        async def boundary() -> None:
            if checkpoint:
                await checkpoint()

        async def tool(
            label: str, operation: Awaitable[Any], progress: int,
            *, phase: str = "data", source: str | None = None,
        ) -> tuple[Any, str | None]:
            try:
                await boundary()
            except BaseException:
                close = getattr(operation, "close", None)
                if close:
                    close()
                raise
            source_name = source or label
            await event(phase, "Data Agent", f"取得 {label}", "正在呼叫外部資料來源", source_name, "started", progress,
                        metadata={"control_boundary": False, "retry_policy": "僅網路錯誤、429 與 5xx 有限重試"})
            call_started = time.perf_counter()
            try:
                result = await operation
                if not getattr(self.gemini, "is_fixture", False):
                    require_live_data(result)
                duration = round((time.perf_counter() - call_started) * 1000)
                count = len(result) if isinstance(result, list) else int(result is not None)
                await event(phase, "Data Agent", f"取得 {label}", f"取得 {count} 筆正規化資料", source_name,
                            "completed", min(99, progress + 2), duration_ms=duration,
                            metadata={"record_count": count, "control_boundary": True})
                await boundary()
                return result, None
            except Exception as exc:
                duration = round((time.perf_counter() - call_started) * 1000)
                await event(phase, "Data Agent", f"取得 {label}", str(exc), source_name, "failed",
                            min(99, progress + 2), duration_ms=duration,
                            metadata={"control_boundary": True, "fallback": "保留缺漏並繼續可用來源"})
                await boundary()
                return None, str(exc)

        await event("understanding", "Research Agent", "理解問題與條件", request.query, "使用者輸入", "completed", 6,
                    metadata={"requested_horizon": request.horizon, "applied_horizon": horizon_label,
                              "period_start": start.isoformat(), "period_end": end.isoformat(),
                              "horizon_defaulted": horizon_defaulted, "risk_preference": request.risk_preference,
                              "research_type": request.research_type, "research_topic": request.research_topic})
        await boundary()
        industry_scope: dict[str, Any] | None = None
        # 使用者指定檔數（「研究三檔半導體」）時照辦，最多 5 檔；沒指定維持 5 檔。
        wanted = requested_count(request.query) or 5
        try:
            if request.research_type == "industry_supply_chain" and not request.symbols:
                industry_scope = await self.market.resolve_industry_scope(
                    strip_count(request.research_topic or request.query), limit=wanted,
                )
                symbols = list(industry_scope.get("symbols") or [])
            else:
                symbols = await self.market.resolve_symbols(request.query, request.symbols, limit=wanted)
        except Exception as exc:
            raise ResearchExecutionError("planning_failed", f"無法建立候選工具範圍：{exc}", retryable=True) from exc
        # 使用者在確認視窗移除的標的，即使問題文字寫了代號也不再納入。
        excluded = {str(value).strip().upper() for value in (request.preferences.get("excludedSymbols") or [])}
        if excluded:
            symbols = [symbol for symbol in symbols if symbol.upper() not in excluded]
        if not symbols:
            if request.research_type == "industry_supply_chain":
                raise ResearchExecutionError(
                    "unsupported_industry_scope",
                    "已辨識為產業研究，但現有官方分類不足以建立可核實的公司範圍；本次未以不相關個股或名稱模糊比對替代。",
                )
            raise ResearchExecutionError("unknown_symbol", "找不到可由官方市場資料核對的標的，請加入股票代號或更明確的產業條件")
        planning_detail = (
            f"依可追查的產業範圍規則建立「{request.research_topic or request.query}」研究，依序核對 {len(symbols)} 家候選企業：{'、'.join(symbols)}"
            if industry_scope else f"依序核對 {len(symbols)} 檔標的：{'、'.join(symbols)}"
        )
        await event("planning", "Planning Agent", "規劃研究任務", planning_detail,
                    "研究規劃器", "completed", 14,
                    metadata={"symbols": symbols, "research_type": request.research_type,
                              "industry_scope": industry_scope or {}})
        tools = ["TWSE", "TPEx", "FinMind", "MOPS", "Investor Relations", "TWSE News", "Gemini"]
        if self.fundamentals is not None:
            tools.insert(4, "官方估值／月營收／EPS")
        await event("tools", "Tool Agent", "選擇資料工具",
                    "日行情使用 TWSE／TPEx；歷史行情使用 FinMind；公司與重大訊息使用 MOPS 衍生 OpenAPI；"
                    + ("估值、月營收與 EPS 使用 TWSE／TPEx 官方 OpenAPI；" if self.fundamentals is not None else "")
                    + "分析使用 Gemini",
                    "工具註冊表", "completed", 20, metadata={"tools": tools})

        evidence: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}
        found_symbols: list[str] = []
        step = max(2, 34 // max(1, len(symbols)))
        progress = 22
        for symbol in symbols:
            quote, quote_error = await tool(f"{symbol} TWSE／TPEx 日行情", self._market_quote(symbol), progress, source="TWSE／TPEx")
            company, company_error = await tool(f"{symbol} 公司基本資料", self.mops.company(symbol), progress + 2, source="MOPS")
            history, history_error = await tool(f"{symbol} 歷史日行情", self.finmind.history(symbol, start, end), progress + 4, source="FinMind")
            disclosures, disclosure_error = await tool(f"{symbol} 重大訊息", self.mops.disclosures(symbol, limit=20), progress + 6, source="MOPS")
            conferences, conference_error = await tool(f"{symbol} 法說會公告", self.ir.conferences(symbol, limit=20), progress + 8, source="MOPS 法說會公告")
            if quote or company or history:
                found_symbols.append(symbol)
            evidence.extend([
                self._evidence(f"{symbol} 市場日行情", quote, quote_error),
                self._evidence(f"{symbol} 公司基本資料", company, company_error),
                self._evidence(f"{symbol} 歷史日行情", history, history_error),
                self._evidence(f"{symbol} 重大訊息", disclosures, disclosure_error),
                self._evidence(f"{symbol} 法說會", conferences, conference_error),
            ])
            metrics[symbol] = price_metrics(history or [])
            if not history and quote:
                metrics[symbol]["fallback"] = "歷史行情缺漏；只保留交易所最新日資料，不計算期間指標"
            if self.fundamentals is not None:
                snapshot, snapshot_error = await tool(f"{symbol} 估值與財務", self.fundamentals.snapshot(symbol),
                                                      progress + 9, source="TWSE／TPEx／MOPS")
                if snapshot is None and not snapshot_error:
                    snapshot_error = "官方估值與財務資料未涵蓋此代號（ETF 不適用本益比、月營收與 EPS）"
                evidence.append(self._evidence(f"{symbol} 估值與財務", snapshot, snapshot_error))
                if snapshot is not None:
                    metrics[symbol].update(fundamental_metrics(snapshot))
            progress = min(56, progress + step)

        if not found_symbols:
            raise ResearchExecutionError("unknown_symbol", f"官方資料來源找不到指定標的：{'、'.join(symbols)}")

        news, news_error = await tool("TWSE 官方新聞", self.news.items(limit=20), 58, source="TWSE 官方新聞")
        evidence.append(self._evidence("TWSE 官方新聞", news, news_error))
        await event("verification", "Evidence Agent", "核對資料與調整後續步驟",
                    "已排除找不到的標的；來源失敗保留缺漏，歷史行情失敗時不計算期間指標",
                    "正規化資料集", "completed", 66,
                    metadata={"requested_symbols": symbols, "verified_symbols": found_symbols,
                              "missing_sources": [item["source"] for item in evidence if item["missing"]]})
        metrics["coverage"] = completeness(evidence)
        metrics["query_period"] = {
            "requested_horizon": request.horizon,
            "applied_horizon": horizon_label,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "defaulted": horizon_defaulted,
        }
        if industry_scope:
            metrics["industry_scope"] = industry_scope
        await event("metrics", "Calculation Agent", "計算量化指標",
                    "以日收盤資料計算期間報酬、年化波動、最大回撤、區間高低與平均成交量；缺值不補造",
                    "PINWISE deterministic analytics", "completed", 74,
                    metadata={"formula_version": "daily-price-metrics-v1", "symbols": found_symbols})
        await boundary()

        if not getattr(self.gemini, "available", bool(self.gemini.settings.gemini_api_key)):
            raise ResearchExecutionError("missing_api_key", "缺少 GEMINI_API_KEY；資料已取得，但 Gemini 分析未執行")
        source_payload = {
            "question": request.query, "horizon": request.horizon,
            "risk_preference": request.risk_preference, "preferences": request.preferences,
            "research_type": request.research_type, "research_topic": request.research_topic,
            "industry_scope": industry_scope,
            "requested_symbols": symbols, "verified_symbols": found_symbols,
            "calculated_metrics": metrics, "evidence": compact_prompt_evidence(evidence),
        }
        prompt = (
            f"prompt_version={PROMPT_VERSION}\n"
            "請依下列 JSON 產出繁體中文研究報告，讀者可能是第一次投資的新手。\n"
            "summary：先用 2–4 句白話直接回答 question 本身（例如產業發展就談營收、獲利與估值透露的趨勢），"
            "再說明依據；不要只逐檔列出報酬、波動等數字。若 preferences.explanationStyle 為「清楚易懂」，"
            "第一次出現的專有名詞（本益比、殖利率、年增率、EPS、年化波動、最大回撤）用一句話說明意義。\n"
            "所有數值只能原樣引用 calculated_metrics 或 evidence，一律使用與資料相同的阿拉伯數字（例如 54.65%），"
            "不得改寫成中文數字、換算單位、四捨五入或推算新數字；"
            "不得把 missing=true 的項目當證據；所有網址只由系統 evidence 呈現，文字欄位不得輸出網址；"
            "候選代號只能從 verified_symbols 選擇；不得使用「買進」「賣出」等指令式建議。\n"
            "若 research_type 為 etf，標的是 ETF：不得用公司營收、EPS、本益比的角度分析，"
            "不得推測成份股、費用率、配息或追蹤誤差；資料沒有的項目要列入 limitations。\n"
            "若 preferences.researchFocus 有值，summary 要先回答該面向，risks 也優先列與該面向相關的風險；"
            "該面向資料不足時要明白說明，不得補造。\n"
            "risks 與 invalidation_conditions 各至少 3 點；limitations 必須列出資料缺口。\n"
            "watch_items：列出 3–6 個之後可用官方資料持續追蹤的觀察條件（例如下個月營收年增率是否維持、"
            "殖利率或本益比變化、重大訊息），symbol 填對應代號（全市場條件可留空），why 說明為何值得觀察。\n"
            + json.dumps(source_payload, ensure_ascii=False, default=str)
        )
        await event("analysis", "Gemini Agent", "Gemini 分析", "模型正在依已核對資料與程式計算指標產生結構化結果",
                    "Gemini API", "started", 82, metadata={"model": self.gemini.settings.gemini_model, "prompt_version": PROMPT_VERSION})
        generation_started = time.perf_counter()
        try:
            generated = await self.gemini.generate_research(prompt)
        except asyncio.TimeoutError as exc:
            raise ResearchExecutionError("timeout", "Gemini 分析逾時，任務已中止", retryable=True) from exc
        except Exception as exc:
            message = str(exc)
            if "每日" in message or "預算" in message or "上限" in message:
                code = "preview_limit"
            else:
                code = "quota_exceeded" if "429" in message or "quota" in message.lower() else "gemini_error"
            raise ResearchExecutionError(code, f"Gemini 分析失敗：{message}", retryable=code in {"quota_exceeded", "gemini_error"}) from exc
        generation_ms = round((time.perf_counter() - generation_started) * 1000)
        usage = generated.pop("_usage", {}) if isinstance(generated, dict) else {}
        await event("analysis", "Gemini Agent", "Gemini 分析", "已完成結構化分析",
                    "Gemini API", "completed", 90, duration_ms=generation_ms,
                    metadata={"model": self.gemini.settings.gemini_model, "usage": usage})
        await boundary()

        allowed = set(found_symbols)
        candidates = list(dict.fromkeys(str(item) for item in generated.get("candidates", []) if str(item) in allowed))
        # User-entered numbers are not evidence.  Only normalized source data,
        # deterministic metrics and verified symbols can authorize a number.
        allowed_numbers = _number_tokens({"metrics": metrics, "evidence": evidence, "verified_symbols": found_symbols})
        rejected_claims: list[str] = []
        rejected_sentences: list[str] = []

        def validated_text(value: Any) -> str | None:
            text, rejected, problems = validated_sentences(value, allowed_numbers, metrics, found_symbols, evidence)
            rejected_sentences.extend(rejected)
            rejected_claims.extend(problems)
            return text

        model_summary = validated_text(generated.get("summary"))
        summary = model_summary or _deterministic_summary(found_symbols, metrics, horizon_label)
        risks = [text for item in generated.get("risks", []) if (text := validated_text(item))][:10]
        invalidation = [text for item in generated.get("invalidation_conditions", []) if (text := validated_text(item))][:10]
        limitations = [text for item in generated.get("limitations", []) if (text := validated_text(item))][:10]
        limitations.extend(
            f"{item['source']}：{item['missing_reason']}" for item in evidence if item["missing"]
            if f"{item['source']}：{item['missing_reason']}" not in limitations
        )
        if industry_scope:
            limitations.extend(str(item) for item in industry_scope.get("limitations") or [] if str(item) not in limitations)
        limitations.extend(f"{item['source']}：隔離或未驗證資料，不計入真實來源覆蓋率"
                           for item in evidence if not item["missing"] and item["data_status"] not in {"real", "cache"})
        if self.fundamentals is not None and any(
                item["source"].endswith("估值與財務") and not item["missing"] for item in evidence):
            limitations.append("財務資料為官方本益比／殖利率／股價淨值比、最新月營收與當年度累計 EPS；尚未取得完整財報細項、法說內容與細分供應鏈產品證據。")
        else:
            limitations.append("目前財務資料僅有公司基本資料與每日公告；尚未取得營收、EPS、財報、估值與細分供應鏈產品證據，不據此推定投資結論。")
        if any(item.get("stale") for item in evidence):
            limitations.append("部分來源資料日期較舊，請依各筆交易日／公告日核對；日資料不代表即時行情。")
        watch_items = []
        for raw in generated.get("watch_items") or []:
            if not isinstance(raw, dict) or len(watch_items) >= 6:
                continue
            symbol = str(raw.get("symbol") or "").strip()
            item_text, why_text = validated_text(raw.get("item")), validated_text(raw.get("why"))
            if item_text and why_text and (not symbol or symbol in allowed):
                watch_items.append({"symbol": symbol or None, "item": item_text, "why": why_text})
        if not candidates:
            candidates = found_symbols[:3]
        if not risks:
            risks = ["目前證據不足，需等待更多可追溯資料後重新評估"]
        if rejected_sentences:
            limitations.append(
                f"模型輸出有 {len(rejected_sentences)} 句含無法與輸入證據對應的數字或網址，這些句子已從報告文字排除，其餘經逐句檢核的分析保留；來源只採後端保存的 evidence 紀錄。"
            )
        metrics["output_validation"] = {
            "model_summary_accepted": model_summary is not None,
            "rejected_claim_count": len(rejected_claims),
            "rejected_sentence_count": len(rejected_sentences),
            "rejected_sentences": [sentence[:200] for sentence in rejected_sentences[:10]],
            "validation_granularity": "sentence",
            "evidence_records": len(evidence),
            "model_urls_used_as_evidence": 0,
            "numeric_binding": "symbol + metric + unit + query_period + normalized_history_source",
        }
        await event("validation", "Validation Agent", "輸出檢核",
                    f"已限制候選代號、逐句核對模型數字與網址；移除 {len(rejected_sentences)} 句無法對應證據的內容，其餘保留",
                    "PINWISE output validator", "completed", 96,
                    metadata={"candidate_allowlist": sorted(allowed), "missing_count": metrics["coverage"]["missing_sources"],
                              "rejected_claim_count": len(rejected_claims), "rejected_sentence_count": len(rejected_sentences),
                              "model_urls_used_as_evidence": 0})
        await boundary()

        duration_ms = round((time.perf_counter() - started) * 1000)
        response = ResearchResponse(
            query=request.query, summary=summary,
            risks=risks, candidates=candidates, evidence=evidence, trace=trace,
            metrics=metrics, invalidation_conditions=invalidation or risks,
            data_mode="fixture" if getattr(self.gemini, "is_fixture", False) else "live",
            verification_status="limited" if metrics["coverage"]["available_sources"] < metrics["coverage"]["total_sources"] else "sourced",
            limitations=list(dict.fromkeys(limitations)), prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms, usage=usage, model=self.gemini.settings.gemini_model,
            watch_items=watch_items,
        )
        await event("persistence", "Report Agent", "保存報告及證據",
                    "報告、輸入條件、模型、提示版本、工具事件、資料快照、耗時與可取得用量已完成封裝",
                    "研究任務儲存", "completed", 100,
                    metadata={"duration_ms": duration_ms, "evidence_count": len(evidence)})
        response.trace = trace
        return response

    async def _market_quote(self, symbol: str):
        results = await asyncio.gather(self.twse.quote(symbol), self.tpex.quote(symbol), return_exceptions=True)
        for result in results:
            if result is not None and not isinstance(result, Exception):
                return result
        errors = [result for result in results if isinstance(result, Exception)]
        if len(errors) == len(results):
            raise errors[0]
        return None
