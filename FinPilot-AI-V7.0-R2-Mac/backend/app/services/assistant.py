from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator

from ..core.models import AssistantRequest, InputUnderstandingRequest
from ..core.normalization import normalized_symbol
from .analytics import price_metrics
from .conversation_memory import (
    build_memory, effective_period, resolve_conversation, with_answer_reference,
)
from .input_understanding import InputUnderstandingService, parse_period
from .assistant_claims import validate_assistant_answer
from .tool_router import ALLOWED_TOOLS, ToolPlan, ToolRouter
from .input_understanding import PREFERENCE_REQUEST_PATTERN
from ..security.preview_security import PreviewLimitError


PRONOUN_PATTERN = re.compile(r"那(?:它|他|家|檔|個)?|它|該公司|這檔|前者|後者")
RESEARCH_PATTERN = re.compile(r"完整研究|深入研究|建立研究|開始研究|跑一份研究")
PRICE_PATTERN = re.compile(r"股價|價格|收盤|多少錢|多少元|行情")
HISTORY_PATTERN = re.compile(r"歷史|報酬|波動|走勢|表現|回撤|風險")
COMPANY_PATTERN = re.compile(r"公司資料|基本資料|做什麼|產業|資本額|上市|上櫃")
# 公司或基金的重大事件：只用官方公告回答，模型不能憑印象說有或沒有。
# 問「這則公告代表什麼／要注意什麼」是要解釋，不是問有沒有：交給 AI 依查到的公告說明。
EVENT_EXPLAIN_PATTERN = re.compile(r"代表|意思|意義|影響|注意|為什麼|怎麼看|解釋|說明|好還是壞|利多|利空|好事|壞事|該怎麼")
EVENT_PATTERN = re.compile(r"反分割|分割|受益人會議|清算|下市|下櫃|併購|合併(?!營收|報表|財報)|減資")
DISCLOSURE_PATTERN = re.compile(r"公告|重大訊息|重訊|法說")
COMPARE_PATTERN = re.compile(r"比較|相比|對比|差異|哪(?:一|個|檔)|兩檔|兩家|(?:和|跟|與).{0,20}比")
REPHRASE_PATTERN = re.compile(r"換個說法|再解釋|重新解釋|重新說明|用白話|講白話|白話一點|簡單一點|換一個例子")
ASSISTANT_PROMPT_VERSION = "finpilot-assistant-natural-v4"


class AssistantService:
    """Bounded conversational orchestration over an explicit tool allowlist."""

    allowed_tools = ALLOWED_TOOLS

    def __init__(self, *, settings, understanding: InputUnderstandingService, market, finmind, mops, gemini, ir=None, news=None):
        self.settings = settings
        self.understanding = understanding
        self.market = market
        self.finmind = finmind
        self.mops = mops
        self.gemini = gemini
        self.ir = ir
        self.news = news

    async def _event_answer(self, symbol: str, name: str, event: str) -> tuple[str, int]:
        """查官方新聞與重大訊息回答事件題；查不到時只說無法確認，不說沒有。"""
        found: list[tuple[str, str]] = []
        label = f"{symbol} {name}".strip()
        def matches(title: str, by_subject: bool) -> bool:
            return bool(EVENT_PATTERN.search(title)) and (not by_subject or symbol in title or bool(name and name in title))
        if self.news is not None:
            try:
                for item in await self.news.items(limit=200):
                    if matches(item.title, True):
                        found.append((str(item.published_at or "")[:10], item.title))
            except Exception:
                pass
        is_etf = symbol.startswith("00")
        if not is_etf:
            try:
                for item in await self.mops.disclosures(symbol, limit=10):
                    title = str(getattr(item, "title", "") or "")
                    if matches(title, False):
                        day = getattr(item, "published_at", None) or getattr(item, "event_date", None) or ""
                        found.append((str(day)[:10], " ".join(re.sub(r"\s*\n\s*", "", title).split())))
            except Exception:
                pass
        if found:
            rows = "\n".join(f"- {day}　{title}".strip() for day, title in found[:5])
            return f"**我在官方資料中找到 {len(found[:5])} 則與 {label} {event}有關的公告。**\n\n{rows}\n\n細節請以公告原文為準。", len(found[:5])
        if is_etf:
            return (f"**我目前無法確認 {label} 是否有{event}相關安排。**\n\n"
                    "ETF 的受益人會議、分割等事項由投信公告，我接的官方資料沒有涵蓋這類公告，所以查不到不代表沒有。"
                    "建議直接查該檔 ETF 的投信官網，或公開資訊觀測站的基金公告。"), 0
        return (f"**我在目前的資料中沒有看到 {label} {event}相關公告，但這不代表沒有。**\n\n"
                "我接的重大訊息只涵蓋最近可得的每日公告，較早的內容查不到。"
                "建議到公開資訊觀測站查詢完整公告。"), 0

    def _bounded_history(self, request: AssistantRequest) -> list[dict[str, str]]:
        rows = request.history[-self.settings.assistant_max_history_messages:]
        budget = 9000
        result: list[dict[str, str]] = []
        for row in reversed(rows):
            text = row.text[:2000]
            if budget - len(text) < 0:
                break
            result.append({"role": row.role, "text": text})
            budget -= len(text)
        return list(reversed(result))

    @staticmethod
    def _safe_memory(request: AssistantRequest) -> tuple[str | None, list[str]]:
        confirmed = normalized_symbol(request.memory.confirmed_symbol or "") or None
        recent = list(dict.fromkeys(
            normalized_symbol(value) for value in request.memory.recent_symbols
            if normalized_symbol(value)
        ))[:3]
        return confirmed, recent

    @staticmethod
    def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": snapshot.get("symbol"), "name": snapshot.get("name"), "market": snapshot.get("market"),
            "found": snapshot.get("found"), "data_frequency": snapshot.get("data_frequency"), "as_of": snapshot.get("as_of"),
            "quote": snapshot.get("quote"), "company": snapshot.get("company"), "metrics": snapshot.get("metrics"),
            "history": (snapshot.get("history") or [])[-8:], "events": (snapshot.get("events") or [])[:5],
            "errors": snapshot.get("errors") or [],
            "scope": snapshot.get("scope"), "capabilities": snapshot.get("capabilities") or [],
        }

    @staticmethod
    def _assistant_intent(message: str, fallback: str | None = None, understood_intent: str | None = None) -> str:
        if understood_intent in {
            "investment_decision", "target_price_scenario", "valuation", "risk_analysis",
            "compare", "rephrase", "full_research", "research", "screen", "explain",
        }:
            return understood_intent
        if RESEARCH_PATTERN.search(message):
            return "full_research"
        if COMPARE_PATTERN.search(message):
            return "compare"
        if PRICE_PATTERN.search(message):
            return "price"
        if DISCLOSURE_PATTERN.search(message):
            return "disclosure"
        if COMPANY_PATTERN.search(message):
            return "company"
        if HISTORY_PATTERN.search(message):
            return "history"
        if re.search(r"呢[?？]?$", message.strip()) or PRONOUN_PATTERN.search(message):
            return fallback or "general"
        return "general"

    @staticmethod
    def _safe_tool_error(exc: Exception) -> tuple[str, str]:
        value = str(exc)
        lowered = value.lower()
        if "429" in value or "rate" in lowered or "quota" in lowered:
            return "rate_limited", "資料來源達到速率限制（HTTP 429）"
        if isinstance(exc, asyncio.TimeoutError) or "timeout" in lowered or "逾時" in value:
            return "timeout", "資料來源回應逾時"
        status = re.search(r"\b(5\d\d)\b", value)
        if status:
            return "upstream_error", f"資料來源暫時錯誤（HTTP {status.group(1)}）"
        return "unavailable", "資料來源目前無法取得"

    async def _tool_results(self, plan: ToolPlan, period: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for call in plan.calls:
            name, symbol = call.name, call.symbol
            if name not in self.allowed_tools:
                continue
            try:
                if name == "market_snapshot":
                    operation = self.market.snapshot(symbol, scope=call.scope or "full")
                elif name == "company_profile":
                    operation = self.mops.company(symbol)
                elif name == "material_events":
                    operation = self.mops.disclosures(symbol, limit=10)
                elif name == "investor_conferences":
                    if self.ir is None:
                        raise RuntimeError("法說會資料工具未設定")
                    operation = self.ir.conferences(symbol, limit=10)
                else:
                    from datetime import date
                    operation = self.finmind.history(
                        symbol, date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
                    )
                value = await operation
                if not getattr(self.gemini, "is_fixture", False):
                    from ..core.provenance import require_live_data
                    require_live_data(value)
                if name == "market_snapshot":
                    data = self._compact_snapshot(value)
                elif name == "price_history":
                    data = {"symbol": symbol, "period": period, "metrics": price_metrics(value),
                            "points": [item.model_dump(mode="json") for item in value[-12:]]}
                elif isinstance(value, list):
                    data = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value[:10]]
                else:
                    data = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
                results.append({"tool": name, "symbol": symbol, "status": "completed", "reason": call.reason, "data": data})
            except Exception as exc:
                code, error = self._safe_tool_error(exc)
                results.append({"tool": name, "symbol": symbol, "status": "failed", "reason": call.reason,
                                "error_code": code, "error": error})
        return results

    @staticmethod
    def _source_records(value: Any, *, tool: str, symbol: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        def visit(node: Any, historical: bool = False):
            if len(records) >= 12:
                return
            if isinstance(node, list):
                for item in node:
                    visit(item, historical)
                return
            if not isinstance(node, dict):
                return
            metadata = node.get("metadata")
            if isinstance(metadata, dict) and metadata.get("source"):
                record = {
                    "tool": tool, "symbol": symbol, "source": metadata.get("source"),
                    "source_url": metadata.get("source_url"), "fetched_at": metadata.get("fetched_at"),
                    "period_start": metadata.get("period_start"), "period_end": metadata.get("period_end"),
                    # 歷史日價本來就是過去的資料，不代表目前行情過期。
                    "stale": bool(metadata.get("stale")) and not historical, "missing": bool(metadata.get("missing")),
                    "missing_reason": metadata.get("missing_reason"),
                    "data_at": node.get("trade_date") or node.get("event_date") or node.get("published_at"),
                }
                if record not in records:
                    records.append(record)
            for key, child in node.items():
                if isinstance(child, (dict, list)):
                    visit(child, historical or key in {"history", "points", "recent_points"})

        visit(value)
        return records

    @staticmethod
    def _response_profile(intent: str, symbols: list[str]) -> dict[str, Any]:
        profiles = {
            "price": {
                "depth": "concise", "cover_naturally": ["直接數字", "資料日期與來源", "非即時提醒"],
                "avoid": ["無關公司介紹", "未要求的完整研究"],
            },
            "investment_decision": {
                "depth": "decision_support",
                "cover_naturally": ["先回答適合與否取決於哪些條件", "支持因素", "反方風險", "觀察條件", "必要的資料限制"],
                "avoid": ["保證買賣結論", "用缺漏財務欄位估算合理價"],
            },
            "compare": {
                "depth": "comparative",
                "cover_naturally": ["比較結論", "同日期同單位指標", "各自優劣", "適用情境", "必要的資料限制"],
                "avoid": ["不同期間直接比較", "缺 ETF 費用資料時宣稱成本較低"],
            },
            "target_price_scenario": {
                "depth": "scenario",
                "cover_naturally": ["目標價是使用者假設", "程式計算差距", "必要支持條件", "反方風險", "失效條件", "必要的資料限制"],
                "avoid": ["把目標價稱為合理價", "沒有 EPS 或估值倍數卻給精確預測"],
            },
            "valuation": {
                "depth": "bounded_valuation",
                "cover_naturally": ["現有資料可支持範圍", "歷史價格與風險", "估值缺口", "需要補充的財務資料"],
                "avoid": ["製造唯一合理價"],
            },
            "risk_analysis": {
                "depth": "risk", "cover_naturally": ["主要風險", "支持與反方因素", "事件證據", "失效條件", "必要的資料限制"],
                "avoid": ["把沒有公告支持的傳聞寫成事實"],
            },
        }
        return profiles.get(intent, {
            "depth": "focused", "cover_naturally": ["直接回答", "必要的可確認證據與限制"], "avoid": ["無關背景"],
        }) | {
            "target_count": len(symbols),
            "style": "natural_conversation",
            "lead_with_answer": True,
            "headings": "only_when_the_answer_is_complex",
            "do_not_force_labels": ["已確認市場事實", "風險", "資料缺口"],
        }

    @staticmethod
    def _deterministic_calculations(intent: str, tools: list[dict[str, Any]], hypotheses: list[Any], symbols: list[str]) -> list[dict[str, Any]]:
        snapshots: dict[str, dict[str, Any]] = {}
        for result in tools:
            if result.get("status") == "completed" and result.get("tool") == "market_snapshot":
                snapshots[str(result.get("symbol"))] = result.get("data") or {}
        calculations: list[dict[str, Any]] = []
        if intent == "target_price_scenario":
            for raw in hypotheses:
                item = raw if isinstance(raw, dict) else raw.model_dump(mode="json")
                symbol = str(item.get("symbol") or (symbols[0] if len(symbols) == 1 else ""))
                quote = (snapshots.get(symbol) or {}).get("quote") or {}
                close, target = quote.get("close"), item.get("value")
                if close in (None, 0) or target is None:
                    continue
                close_value, target_value = float(close), float(target)
                calculations.append({
                    "type": "target_price_gap", "symbol": symbol,
                    "current_close": close_value, "target_price": target_value, "currency": "TWD",
                    "absolute_gap": round(target_value - close_value, 2),
                    "required_change_pct": round((target_value / close_value - 1) * 100, 2),
                    "trade_date": quote.get("trade_date") or (snapshots.get(symbol) or {}).get("as_of"),
                    "target_source": "user_hypothesis", "calculation_source": "PINWISE deterministic calculation",
                })
        if intent == "compare" and snapshots:
            dates = {
                symbol: ((data.get("quote") or {}).get("trade_date") or data.get("as_of"))
                for symbol, data in snapshots.items()
            }
            available_dates = {value for value in dates.values() if value}
            calculations.append({
                "type": "comparison_basis", "symbols": list(snapshots), "data_dates": dates,
                "dates_aligned": len(available_dates) <= 1, "currency": "TWD", "frequency": "daily",
                "comparable_metrics": ["close", "period_return_pct", "annualized_volatility_pct", "max_drawdown_pct"],
            })
        return calculations

    @staticmethod
    def _trusted_context_notes(answer: str, context: dict[str, Any]) -> tuple[str, list[str], list[str]]:
        """Append backend calculations to the answer; return data notes separately for the UI.

        Only the target-price calculation is answer content.  Data limits, gaps
        and freshness are shown by the interface below the answer, so they are
        returned as ``data_notes`` instead of being written into the text.
        """
        notes: list[str] = []
        data_notes: list[str] = []
        note_types: list[str] = []
        for calculation in context.get("deterministic_calculations") or []:
            if calculation.get("type") == "target_price_gap":
                required = calculation.get("required_change_pct")
                if required is not None and f"{required:g}" not in answer:
                    notes.append(
                        "情境差距（程式計算）："
                        f"以 {calculation.get('trade_date') or '未標示日期'} 收盤 {calculation['current_close']:g} 元，"
                        f"到使用者目標 {calculation['target_price']:g} 元需變動 {required:g}%。"
                        "這只是數學情境，不代表合理價或預測。"
                    )
                    note_types.append("target_price_gap")
            elif calculation.get("type") == "comparison_basis" and not calculation.get("dates_aligned", True):
                data_notes.append("各標的資料日期不同，價格與短期變化不是完全同日比較")
                note_types.append("comparison_date_mismatch")
        gaps = [
            str(item.get("capability")) for item in context.get("missing_or_unavailable") or []
            if isinstance(item, dict) and item.get("capability")
        ]
        if gaps:
            data_notes.append("目前無法取得：" + "、".join(dict.fromkeys(gaps)))
            note_types.append("capability_gaps")
        tool_labels = {
            "market_snapshot": "最近日行情", "price_history": "歷史日價",
            "company_profile": "公司基本資料", "material_events": "重大訊息",
            "investor_conferences": "法說會公告",
        }
        failed_items = []
        for item in context.get("missing_or_unavailable") or []:
            if not isinstance(item, dict) or not item.get("tool"):
                continue
            label = tool_labels.get(str(item.get("tool")), str(item.get("tool")))
            failed_items.append(f"{item.get('symbol') or '標的'}的{label}未取得")
        if failed_items:
            data_notes.append("；".join(dict.fromkeys(failed_items)) + "，回答只使用成功取得的資料")
            note_types.append("failed_sources")
        if (context.get("data_quality") or {}).get("stale_source_count", 0):
            data_notes.append("部分資料可能不是最新，請以標示的資料日期解讀")
            note_types.append("stale_sources")
        dates = sorted({
            str((item.get("quote") or {}).get("trade_date"))
            for item in context.get("verified_market_information") or []
            if isinstance(item, dict) and (item.get("quote") or {}).get("trade_date")
        })
        if dates:
            data_notes.insert(0, f"行情為 {'、'.join(dates)} 收盤日資料，非即時價")
        if not notes:
            return answer, note_types, data_notes
        return answer.rstrip() + "\n\n" + "\n\n".join(notes), note_types, data_notes

    @staticmethod
    def _comparison_table(tools: list[dict[str, Any]]) -> str:
        """Comparison numbers rendered by the backend from verified tool data.

        Gemini is told not to write its own per-symbol number table, so the
        comparison keeps its figures instead of losing them in claim checks.
        """
        rows: list[str] = []
        periods: set[tuple[str, str]] = set()

        def pct(value: Any) -> str:
            return f"{value:+.2f}%" if isinstance(value, (int, float)) else "—"

        for result in tools:
            if result.get("status") != "completed" or result.get("tool") != "market_snapshot":
                continue
            data = result.get("data") or {}
            quote = data.get("quote") or {}
            metrics = data.get("metrics") or {}
            close, trade_date = quote.get("close"), str(quote.get("trade_date") or "")
            close_text = f"{close:,.2f}".rstrip("0").rstrip(".") if isinstance(close, (int, float)) else "—"
            if trade_date:
                close_text += f"（{trade_date[5:].replace('-', '/')}）"
            vol = metrics.get("annualized_volatility_pct")
            name = data.get("name") if data.get("name") and data.get("name") != result.get("symbol") else ""
            label = f"{result.get('symbol')} {name}".strip()
            rows.append(
                f"| {label} | {close_text} | "
                f"{pct(metrics.get('period_return_pct'))} | "
                f"{f'{vol:.2f}%' if isinstance(vol, (int, float)) else '—'} | "
                f"{pct(metrics.get('max_drawdown_pct'))} |"
            )
            if metrics.get("period_start") and metrics.get("period_end"):
                periods.add((str(metrics["period_start"]), str(metrics["period_end"])))
        if len(rows) < 2:
            return ""
        period_text = (f"，{next(iter(periods))[0]} ～ {next(iter(periods))[1]}" if len(periods) == 1
                       else "，各標的期間不同" if periods else "")
        return "\n".join([
            f"**數字比較**（程式依官方日資料計算{period_text}）",
            "",
            "| 標的 | 收盤（日期） | 區間報酬 | 年化波動 | 最大回撤 |",
            "|---|---:|---:|---:|---:|",
            *rows,
        ])

    def _research_context(self, *, message: str, intent: str, symbols: list[str], understood,
                          period: dict[str, Any], plan: ToolPlan, tools: list[dict[str, Any]],
                          conversation_memory: dict[str, Any]) -> dict[str, Any]:
        verified: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        for result in tools:
            if result.get("status") != "completed":
                missing.append({
                    "tool": result.get("tool"), "symbol": result.get("symbol"),
                    "reason": result.get("error"), "error_code": result.get("error_code"),
                })
                continue
            data = result.get("data") or {}
            tool = result.get("tool")
            symbol = result.get("symbol")
            if tool == "market_snapshot":
                verified.append({
                    "tool": tool, "symbol": symbol, "name": data.get("name"), "market": data.get("market"),
                    "as_of": data.get("as_of"), "data_frequency": data.get("data_frequency"),
                    "quote": data.get("quote"), "calculated_metrics": data.get("metrics"),
                    "company": data.get("company"), "recent_events": data.get("events"),
                })
                for error in data.get("errors") or []:
                    missing.append({"tool": tool, "symbol": symbol, "reason": error})
            elif tool == "price_history":
                verified.append({
                    "tool": tool, "symbol": symbol, "period": data.get("period"),
                    "calculated_metrics": data.get("metrics"), "recent_points": data.get("points"),
                })
            elif tool == "company_profile":
                verified.append({"tool": tool, "symbol": symbol, "company": data})
            else:
                verified.append({"tool": tool, "symbol": symbol, "events": data})
            sources.extend(self._source_records(data, tool=tool, symbol=symbol))
        missing.extend({"capability": value} for value in plan.missing_capabilities)
        calculations = self._deterministic_calculations(
            intent, tools, conversation_memory.get("hypotheses") or [], symbols,
        )
        stale_sources = [
            {"tool": item.get("tool"), "symbol": item.get("symbol"), "source": item.get("source"), "data_at": item.get("data_at")}
            for item in sources if item.get("stale")
        ]
        return {
            "current_question": message,
            "intent": intent,
            "research_targets": symbols,
            "historical_observation_period": period,
            "future_outlook_period": understood.outlook_period,
            "user_constraints": conversation_memory.get("constraints") or [],
            "user_hypotheses": conversation_memory.get("hypotheses") or [],
            "conversation_state": conversation_memory.get("structured_summary") or {},
            "verified_market_information": verified,
            "source_records": sources,
            "missing_or_unavailable": missing,
            "deterministic_calculations": calculations,
            "data_quality": {
                "source_record_count": len(sources), "stale_source_count": len(stale_sources),
                "stale_sources": stale_sources, "missing_item_count": len(missing),
            },
            "response_profile": self._response_profile(intent, symbols),
            "unverified_content": [
                "使用者提出的價格只是假設，不是行情或已確認事實",
                "模型分析與情境推論不得改寫成已發生事實",
            ],
            "tool_plan": plan.as_dict(),
            "data_policy": {
                "daily_quotes_are_not_realtime": True,
                "only_tool_results_are_market_evidence": True,
                "private_holdings_or_broker_data_used": False,
            },
        }

    @staticmethod
    def _verified_tool_answer(tools: list[dict[str, Any]], intent: str) -> str:
        paragraphs: list[str] = []
        for result in tools:
            symbol = result.get("symbol") or "該標的"
            if result.get("status") != "completed":
                paragraphs.append(f"{symbol}：{result.get('error') or '資料來源目前無法取得'}；因此無法提供或比較相關數字。")
                continue
            data = result.get("data") or {}
            if result.get("tool") == "market_snapshot":
                quote = data.get("quote") or {}
                name = data.get("name") or symbol
                trade_date = quote.get("trade_date") or data.get("as_of")
                close = quote.get("close")
                if close is None:
                    paragraphs.append(f"{symbol} {name}：最近官方日行情缺少收盤價，不能提供價格數字。")
                    continue
                details = [f"收盤價 {close} 元"]
                for label, key, suffix in (("開盤", "open", " 元"), ("最高", "high", " 元"), ("最低", "low", " 元"),
                                           ("漲跌", "change", " 元"), ("成交量", "volume", " 股")):
                    if quote.get(key) is not None:
                        details.append(f"{label} {quote[key]}{suffix}")
                stale = bool((quote.get("metadata") or {}).get("stale"))
                stale_note = "資料來源已標示可能過期；" if stale else ""
                paragraphs.append(f"{symbol} {name} 在 {trade_date or '未標示日期'} 的官方日資料為：{'、'.join(details)}。{stale_note}這不是即時報價。")
            elif result.get("tool") == "price_history":
                # 以中文標籤呈現，不直接輸出程式欄位名稱（底線會被 Markdown 當成斜體）。
                metrics = data.get("metrics") or {}
                labels = (
                    ("latest_close", "最新收盤價", " 元"), ("period_return_pct", "區間報酬", "%"),
                    ("annualized_volatility_pct", "年化波動", "%"), ("max_drawdown_pct", "最大回撤", "%"),
                    ("period_high", "期間最高收盤", " 元"), ("period_low", "期間最低收盤", " 元"),
                    ("average_volume_shares", "平均每日成交量", " 股"),
                )
                facts = [
                    f"{label} {metrics[key]:,}{unit}" if isinstance(metrics.get(key), int) else f"{label} {metrics[key]}{unit}"
                    for key, label, unit in labels if metrics.get(key) is not None
                ]
                period = (f"{metrics['period_start']} 至 {metrics['period_end']}"
                          if metrics.get("period_start") and metrics.get("period_end") else "所選期間")
                paragraphs.append(
                    f"{symbol} 在 {period} 的日資料計算結果：{'、'.join(facts)}。" if facts
                    else f"{symbol} 的歷史日價資料點不足，沒有可報告的指標。"
                )
            elif result.get("tool") == "company_profile":
                paragraphs.append(f"{symbol} 的公司資料已取得；回答只採用後端提供的公司欄位，缺漏欄位不推測。")
            elif result.get("tool") == "investor_conferences":
                count = len(data) if isinstance(data, list) else 0
                paragraphs.append(f"{symbol} 取得 {count} 筆 MOPS 每日重大訊息中的法說會公告；這不代表完整歷史法說資料庫。")
            else:
                count = len(data) if isinstance(data, list) else 0
                paragraphs.append(f"{symbol} 取得 {count} 筆公告；沒有資料時不推測公告內容。")
        suffix = "比較只涵蓋上述相同日期口徑的可用日資料。" if intent == "compare" else ""
        return "\n\n".join(paragraphs + ([suffix] if suffix else []))

    @staticmethod
    def _error_event(exc: Exception) -> dict[str, Any]:
        message = str(exc)
        lower = message.lower()
        if isinstance(exc, PreviewLimitError):
            code, user_message = "preview_limit", f"{message}。本次未送出或已停止。"
        elif "429" in message or "quota" in lower or "resource_exhausted" in lower:
            code, user_message = "quota_exceeded", "Gemini 額度或速率限制已達上限，本次已停止，沒有自動重試。"
        elif isinstance(exc, asyncio.TimeoutError) or "timeout" in lower or "逾時" in message:
            code, user_message = "timeout", "Gemini 回答逾時，本次已停止，沒有改用示範回答。"
        else:
            code, user_message = "stream_interrupted", "Gemini 串流中斷，已保留收到的文字，沒有改用示範回答。"
        return {"type": "error", "code": code, "message": user_message}

    async def stream(self, request: AssistantRequest) -> AsyncIterator[dict[str, Any]]:
        message = request.message.strip()
        if len(message) > self.settings.assistant_max_input_chars:
            yield {"type": "error", "code": "input_too_long",
                   "message": f"輸入超過 {self.settings.assistant_max_input_chars} 字上限，請精簡後再送出。"}
            return
        yield {"type": "start", "model": self.settings.gemini_model, "conversation_id": request.conversation_id}
        understood = await self.understanding.understand(InputUnderstandingRequest(text=message, context="assistant"))
        yield {"type": "understanding", "data": understood.model_dump(mode="json")}
        intent = self._assistant_intent(message, request.memory.last_intent, understood.intent)
        if intent == "general" and not understood.historical_period.get("defaulted", True):
            intent = "history"
        resolution = resolve_conversation(message, understood, request.memory, intent)
        symbols = resolution.symbols
        if resolution.clarification:
            yield {"type": "clarification", "message": resolution.clarification, "candidates": []}
            return
        if understood.target_status == "ambiguous" and not symbols:
            yield {"type": "clarification", "message": understood.message,
                   "candidates": [item.model_dump(mode="json") for item in understood.candidates]}
            return
        # 「我適合買什麼」「依我的偏好」沒有指定標的，是要用個人化偏好回答類型，不必先問代號。
        preference_question = bool(PREFERENCE_REQUEST_PATTERN.search(message)) and understood.target_status == "needs_confirmation" \
            and "personal_portfolio_symbols_missing" not in understood.classification_signals
        if understood.target_status in {"needs_confirmation", "source_error"} and not symbols and intent != "rephrase" and not preference_question:
            yield {"type": "clarification", "message": understood.message, "candidates": []}
            return
        if intent == "rephrase" and not request.memory.last_answer_reference and not any(
            row.role == "assistant" for row in request.history
        ):
            yield {"type": "clarification", "message": "目前沒有可重新解釋的上一則回答，請先提出研究問題。", "candidates": []}
            return
        period = effective_period(understood, request.memory, resolution)
        if understood.intent == "full_research" or RESEARCH_PATTERN.search(message):
            yield {"type": "research_handoff", "query": message, "symbols": symbols,
                   "horizon": period.get("label"), "research_type": understood.research_type,
                   "research_topic": understood.research_topic,
                   "understanding": understood.model_dump(mode="json")}
            return

        event_match = EVENT_PATTERN.search(message)
        if event_match and len(symbols) == 1 and not EVENT_EXPLAIN_PATTERN.search(message):
            subject_name = next((item.name for item in understood.candidates if item.symbol == symbols[0]), "").rstrip("*")
            answer, count = await self._event_answer(symbols[0], subject_name, event_match.group(0))
            next_memory = with_answer_reference(build_memory(
                existing=request.memory, resolution=resolution, understood=understood, intent=intent, period=period,
                tools=[], ttl_seconds=getattr(self.settings, "cache_ttl_seconds", 300),
            ), answer)
            yield {"type": "delta", "text": answer}
            yield {"type": "done", "memory": next_memory, "usage": {}, "model": None, "tool_count": count,
                   "verification": "not_required" if count else "source_missing"}
            return

        plan = ToolRouter(max_calls=self.settings.assistant_max_tool_calls).plan(
            intent=intent, symbols=symbols, period=period, message=message,
        )
        plan_payload = plan.as_dict()
        plan_payload.update({
            "market_data_action": "provider_query_or_valid_cache" if plan.calls else "no_market_lookup",
            "reused_conversation_facts": intent == "rephrase",
        })
        yield {"type": "tool_plan", "data": plan_payload}
        tools = await self._tool_results(plan, period)
        for result in tools:
            yield {"type": "tool", "name": result["tool"], "symbol": result.get("symbol"),
                   "status": result["status"], "error_code": result.get("error_code"), "message": result.get("error")}
        next_memory = build_memory(
            existing=request.memory, resolution=resolution, understood=understood, intent=intent,
            period=period, tools=tools, ttl_seconds=getattr(self.settings, "cache_ttl_seconds", 300),
        )
        yield {"type": "memory", "memory": next_memory}
        prompt_payload = {
            "prompt_version": ASSISTANT_PROMPT_VERSION,
            "current_message": message,
            "conversation_history": self._bounded_history(request),
            "conversation_memory": next_memory,
            "understanding": understood.model_dump(mode="json"),
            "tool_results": tools,
            "research_context": self._research_context(
                message=message, intent=intent, symbols=symbols, understood=understood, period=period,
                plan=plan, tools=tools, conversation_memory=next_memory,
            ),
            "user_preferences": request.preferences,
            "instructions": {
                "current_request_overrides_preferences": True,
                "rephrase_without_repeating_previous_wording": intent == "rephrase",
                "tool_results_are_the_only_market_evidence": True,
                "mention_daily_date_for_price": True,
                "answer_the_question_before_background": True,
                "distinguish_verified_facts_user_hypotheses_calculations_and_analysis": True,
                "claim_categories": [
                    "verified_market_fact", "deterministic_calculation", "user_hypothesis",
                    "model_inference", "missing_data",
                ],
                "unsupported_claim_must_not_support_downstream_conclusion": True,
                "source_urls_must_come_from_source_records": True,
                "follow_response_profile_and_answer_depth": True,
                "explain_why_with_supporting_and_opposing_conditions": intent in {
                    "investment_decision", "target_price_scenario", "valuation", "risk_analysis", "compare",
                },
                "do_not_fill_missing_capabilities_with_estimates": True,
                "transparent_system_defaults_are_not_user_choices": True,
                "ordinary_chat_must_not_claim_a_full_research_job_ran": True,
                "use_natural_paragraphs_for_ordinary_chat": True,
                "do_not_force_fixed_report_headings": True,
                "use_lists_or_tables_only_when_they_improve_clarity": True,
                "start_with_one_bold_sentence_conclusion": True,
                "use_plain_labels_like_優點_要注意的地方_適合誰_instead_of_report_jargon": True,
                "indent_sub_items_under_their_parent_item": True,
                "system_renders_number_comparison_table_do_not_write_your_own": intent == "compare",
                "do_not_repeat_the_comparison_table_numbers_in_prose": intent == "compare",
                "do_not_append_source_freshness_or_verification_disclaimers_ui_shows_them": True,
                # 使用者常打錯字或選錯同音字（「磣要的標的」＝「怎樣的標的」）：依原意理解，不要糾正對方。
                "current_message_may_contain_typos_or_wrong_homophones_interpret_the_intended_meaning": True,
                "if_unsure_of_a_typo_state_your_interpretation_in_one_short_clause": True,
                # 沒有指名標的的追問（最近有公告嗎、波動大嗎）延續上一題的標的。
                "follow_up_without_a_named_stock_refers_to_conversation_memory_active_symbols": True,
                # 使用者問某則公告代表什麼時：先用白話說這類公告一般是什麼意思（一般知識可以說），
                # 再依 tool_results 裡這則公告的實際內容說明，最後列投資人可以注意的地方；不要只重複標題。
                "when_asked_what_an_announcement_means": (
                    "第一句用白話說明這類公告的意思；接著說明對股東可能的影響與不代表什麼；"
                    "再列 2～3 個可以注意或後續追蹤的地方。公司特定的數字與日期只能引用 tool_results 的公告；"
                    "解釋公告類型的一般意義屬於一般知識，可以說明。"
                ),
                # 使用者問「依我的偏好／適合我的」時，要真的用已保存的偏好回答，並說出用了哪些。
                "personalization": {
                    "user_preferences_available": bool(request.preferences),
                    "when_user_asks_based_on_their_preferences_or_what_suits_them": (
                        "先用一句話列出你採用的偏好（例如：清楚易懂、觀察長期、可接受明顯波動、重視股息收入、預估投入 1～10 萬），"
                        "再依這些偏好說明適合研究的標的「類型」與理由（例如市值型或高股息 ETF、大型權值股、成長型個股），"
                        "並各寫一個要注意的風險；不要自創或推薦特定股票代號，除非 tool_results 有資料。"
                    ),
                    "if_user_preferences_empty": "說明還沒有設定個人化偏好，可以到「設定 → 個人化偏好」填寫，並先給一般性的類型說明。",
                    "budget_is_only_a_range_never_suggest_how_many_shares_or_lots_to_buy": True,
                    "never_say_you_cannot_read_preferences_when_user_preferences_is_provided": True,
                    "user_preferences_are_settings_not_holdings_you_still_cannot_see_holdings": True,
                },
            },
        }
        prompt = "依下列受限 JSON 回答當前使用者：\n" + json.dumps(prompt_payload, ensure_ascii=False, default=str)
        if tools and not any(row["status"] == "completed" for row in tools):
            yield {"type": "verification", "status": "source_missing",
                   "message": "需要的資料來源都未成功；只說明缺漏，不產生行情數字。"}
            safe_answer = self._verified_tool_answer(tools, intent)
            next_memory = with_answer_reference(next_memory, safe_answer)
            yield {"type": "delta", "text": safe_answer}
            yield {"type": "done", "memory": next_memory, "usage": {}, "model": None,
                   "tool_count": len(tools), "verification": "source_missing"}
            return

        usage: dict[str, Any] = {}
        emitted = False
        buffered: list[str] = []
        collected: list[str] = []
        verify_before_release = bool(tools) or intent == "rephrase"
        try:
            async with asyncio.timeout(getattr(self.settings, "assistant_stream_timeout_seconds", max(20, self.settings.request_timeout_seconds * 4))):
                async for chunk in self.gemini.stream_assistant(prompt):
                    if chunk.get("text"):
                        emitted = True
                        collected.append(chunk["text"])
                        if verify_before_release:
                            buffered.append(chunk["text"])
                        else:
                            yield {"type": "delta", "text": chunk["text"]}
                    if chunk.get("usage"):
                        usage = chunk["usage"]
        except Exception as exc:
            yield self._error_event(exc)
            return
        if not emitted:
            yield {"type": "error", "code": "empty_response", "message": "Gemini 沒有回傳可顯示文字，本次已停止。"}
            return
        verification = "not_required"
        claim_summary: dict[str, Any] = {}
        answer_notes: list[str] = []
        final_answer = "".join(collected)
        if verify_before_release:
            yield {"type": "verification", "status": "checking",
                   "message": "正在核對回答中的數字、日期與網址…"}
            generated = "".join(buffered)
            research_context = prompt_payload["research_context"]
            validated = validate_assistant_answer(
                generated,
                tools=tools,
                hypotheses=next_memory.get("hypotheses") or [],
                research_context=research_context,
                fallback=self._verified_tool_answer(tools, intent),
                previous_answer=request.memory.last_answer_reference if intent == "rephrase" else None,
            )
            generated = validated.text
            verification = validated.status
            claim_summary = validated.claim_summary
            generated, system_notes, data_notes = self._trusted_context_notes(generated, research_context)
            answer_notes = data_notes + validated.notes
            claim_summary["system_notes_added"] = system_notes
            table = self._comparison_table(tools) if intent == "compare" else ""
            if table:
                # 放在第一段（結論）之後；表格在核對後才加入，數字來自已驗證的工具資料。
                head, sep, rest = generated.partition("\n\n")
                generated = f"{head}\n\n{table}\n\n{rest}".rstrip() if sep else f"{head}\n\n{table}"
            if verification == "verified":
                verification_message = "逐項證據核對完成。"
            elif verification == "claims_filtered":
                verification_message = "部分主張未通過證據核對；只處理受影響內容，其他分析已保留。"
            else:
                verification_message = "回答中的市場主張未通過證據核對，已改用後端可確認的內容。"
            yield {"type": "verification", "status": verification,
                   "message": verification_message,
                   "claim_summary": validated.claim_summary,
                   "notes": answer_notes}
            yield {"type": "delta", "text": generated}
            final_answer = generated
        next_memory = with_answer_reference(next_memory, final_answer)
        yield {"type": "done", "memory": next_memory, "usage": usage,
               "model": getattr(getattr(self.gemini, "settings", None), "gemini_model", self.settings.gemini_model),
               "tool_count": len(tools), "verification": verification, "claim_summary": claim_summary,
               "notes": answer_notes}
