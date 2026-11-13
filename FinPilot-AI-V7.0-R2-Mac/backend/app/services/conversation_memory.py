from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..core.normalization import normalized_symbol


CONTEXT_FOLLOWUP_INTENTS = {
    "investment_decision", "target_price_scenario", "valuation", "risk_analysis",
    "price", "history", "research", "company", "disclosure",
}
CONTEXT_CUE = re.compile(r"那|它|該公司|這檔|前者|後者|如果|假設|若|改成|再|繼續|同樣|呢[?？]?")
# 問題的主角是使用者自己（偏好、適合我），不是上一題的股票；除非明確說「這檔／它」。
PERSONAL_SUBJECT = re.compile(r"偏好|個人化|風險承受|我適合|適合我|我的(?:條件|設定|狀況)")
EXPLICIT_REFERENCE = re.compile(r"它|該公司|這檔|這支|這家|前者|後者")


@dataclass
class ConversationResolution:
    symbols: list[str]
    active_symbols: list[str]
    comparison_symbols: list[str]
    used_memory: bool = False
    switched_target: bool = False
    clarification: str | None = None


def _unique_symbols(values: list[str | None]) -> list[str]:
    return list(dict.fromkeys(code for value in values if (code := normalized_symbol(value or ""))))[:3]


def memory_active_symbols(memory) -> list[str]:
    active = _unique_symbols(list(memory.active_symbols))
    if active:
        return active
    confirmed = normalized_symbol(memory.confirmed_symbol or "")
    if confirmed:
        return [confirmed]
    return _unique_symbols(list(memory.recent_symbols[:1]))


def _explicit_comparison_symbols(candidates) -> list[str]:
    """Drop a shorter official alias when it is embedded in a longer exact mention."""
    explicit = [
        item for item in candidates
        if not any(
            item.matched_text != other.matched_text
            and item.matched_text in other.matched_text
            for other in candidates
        )
    ]
    return _unique_symbols([item.symbol for item in explicit])


def resolve_conversation(message: str, understood, memory, intent: str) -> ConversationResolution:
    active = memory_active_symbols(memory)
    comparison = _unique_symbols(list(memory.comparison_symbols))
    switched = any(signal in understood.classification_signals for signal in {
        "explicit_target_switch", "replace_previous_selection", "explicit_topic_switch",
    })

    if understood.research_type in {"industry_supply_chain", "market_trend"}:
        previous_topic = str((memory.structured_summary or {}).get("research_topic") or "")
        topic_changed = bool(understood.research_topic and understood.research_topic != previous_topic)
        return ConversationResolution(
            symbols=[], active_symbols=[], comparison_symbols=[],
            switched_target=bool(switched or active or comparison or (previous_topic and topic_changed)),
            used_memory=bool(previous_topic and not topic_changed),
        )

    if understood.resolved_symbols:
        explicit = _unique_symbols(list(understood.resolved_symbols))
    elif understood.selected_symbol:
        explicit = _unique_symbols([understood.selected_symbol])
    elif understood.target_status == "ambiguous" and intent == "compare":
        explicit = _explicit_comparison_symbols(understood.candidates)
    else:
        explicit = []

    if switched and explicit:
        comparison_after_switch = explicit if intent == "compare" and len(explicit) > 1 else []
        return ConversationResolution(
            symbols=explicit, active_symbols=explicit,
            comparison_symbols=comparison_after_switch, switched_target=True,
        )

    if intent == "rephrase":
        subjects = comparison or active
        return ConversationResolution(
            symbols=subjects, active_symbols=active, comparison_symbols=comparison,
            used_memory=bool(subjects),
        )

    if intent == "compare":
        should_extend = bool(comparison or active) and (
            len(explicit) < 2 or bool(re.search(r"那|再|還有|跟|和|與", message))
        )
        base = comparison or active if should_extend else []
        subjects = _unique_symbols(base + explicit)
        if len(subjects) < 2:
            return ConversationResolution(
                symbols=subjects, active_symbols=active, comparison_symbols=comparison,
                used_memory=bool(base), clarification="比較需要至少兩個明確標的，請再指定另一家公司或代號。",
            )
        return ConversationResolution(
            symbols=subjects, active_symbols=subjects, comparison_symbols=subjects,
            used_memory=bool(base),
        )

    if explicit:
        same_subject = explicit == active and not comparison
        changed_subject = bool(active or comparison) and explicit != (comparison or active)
        return ConversationResolution(
            symbols=explicit, active_symbols=explicit, comparison_symbols=[],
            used_memory=same_subject, switched_target=changed_subject,
        )

    if PERSONAL_SUBJECT.search(message) and not EXPLICIT_REFERENCE.search(message):
        return ConversationResolution(
            symbols=[], active_symbols=[], comparison_symbols=[], switched_target=bool(active or comparison),
        )

    follows_context = intent in CONTEXT_FOLLOWUP_INTENTS or bool(CONTEXT_CUE.search(message)) or not understood.historical_period.get("defaulted", True)
    if follows_context:
        subjects = comparison or active
        if len(subjects) == 1:
            return ConversationResolution(
                symbols=subjects, active_symbols=subjects, comparison_symbols=[], used_memory=True,
            )
        if len(subjects) > 1:
            return ConversationResolution(
                symbols=[], active_symbols=active, comparison_symbols=comparison, used_memory=True,
                clarification="目前同時討論多個標的，請指定這一題是要問哪一檔。",
            )

    return ConversationResolution(symbols=[], active_symbols=active, comparison_symbols=comparison)


def effective_period(understood, memory, resolution: ConversationResolution) -> dict[str, Any]:
    current = dict(understood.historical_period)
    if resolution.switched_target:
        return current
    if not current.get("defaulted", True):
        return current
    if resolution.used_memory and memory.historical_period:
        return dict(memory.historical_period)
    return current


def verified_claims(tools: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    claims: list[dict[str, Any]] = []
    dates: list[str] = []
    metric_units = {
        "period_return_pct": "%", "annualized_volatility_pct": "%", "max_drawdown_pct": "%",
        "latest_close": "TWD", "first_close": "TWD",
    }
    for result in tools:
        if result.get("status") != "completed":
            continue
        tool, symbol = result.get("tool"), result.get("symbol")
        data = result.get("data") or {}
        if tool == "market_snapshot":
            quote = data.get("quote") or {}
            as_of = quote.get("trade_date") or data.get("as_of")
            if as_of:
                dates.append(str(as_of))
            if quote.get("close") is not None:
                claims.append({
                    "symbol": symbol, "claim": "daily_close", "value": quote.get("close"), "unit": "TWD",
                    "as_of": as_of, "source": ((quote.get("metadata") or {}).get("source")), "verified": True,
                })
            metrics = data.get("metrics") or {}
        elif tool == "price_history":
            period = data.get("period") or {}
            as_of = period.get("end")
            if as_of:
                dates.append(str(as_of))
            metrics = data.get("metrics") or {}
        else:
            metrics = {}
        for key, unit in metric_units.items():
            if metrics.get(key) is not None:
                claims.append({
                    "symbol": symbol, "claim": key, "value": metrics[key], "unit": unit,
                    "as_of": as_of, "source": tool, "verified": True,
                })
    return claims[:12], max(dates) if dates else None


def build_memory(*, existing, resolution: ConversationResolution, understood, intent: str,
                 period: dict[str, Any], tools: list[dict[str, Any]], ttl_seconds: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    old = existing.model_dump(mode="json")
    active = resolution.active_symbols
    comparison = resolution.comparison_symbols

    hypotheses = [] if resolution.switched_target else [item.model_dump(mode="json") for item in existing.hypotheses]
    hypothesis_symbol = resolution.symbols[0] if len(resolution.symbols) == 1 else None
    for item in understood.hypotheses:
        value = item.model_copy(update={"symbol": hypothesis_symbol}).model_dump(mode="json")
        hypotheses = [old_item for old_item in hypotheses if not (
            old_item.get("type") == value["type"] and old_item.get("symbol") == value.get("symbol")
        )]
        hypotheses.append(value)
    hypotheses = hypotheses[-6:]

    constraints = [item.model_dump(mode="json") for item in existing.constraints]
    for item in understood.structured_constraints:
        value = item.model_dump(mode="json")
        constraints = [old_item for old_item in constraints if old_item.get("type") != value["type"]]
        constraints.append(value)
    constraints = constraints[-8:]

    new_claims, as_of = verified_claims(tools)
    claims = new_claims if resolution.switched_target else (new_claims or list(existing.last_verified_claims))
    has_verified_market_data = bool(new_claims)
    expires_at = (
        (now + timedelta(seconds=max(60, ttl_seconds))).isoformat()
        if has_verified_market_data else (None if resolution.switched_target else old.get("expires_at"))
    )
    effective_as_of = as_of if has_verified_market_data else (None if resolution.switched_target else old.get("as_of"))
    recent = _unique_symbols(active + list(existing.recent_symbols))
    summary = {
        "active_symbols": active,
        "comparison_symbols": comparison,
        "last_intent": intent,
        "hypotheses": [{"type": item.get("type"), "value": item.get("value"), "unit": item.get("unit"), "symbol": item.get("symbol")} for item in hypotheses],
        "constraints": [{"type": item.get("type"), "value": item.get("value"), "unit": item.get("unit")} for item in constraints],
        "historical_period": period,
        "verified_claim_count": len(claims),
        "market_data_fresh": bool(expires_at and expires_at > now.isoformat()),
        "research_type": understood.research_type,
        "research_topic": understood.research_topic or (
            None if resolution.switched_target else (old.get("structured_summary") or {}).get("research_topic")
        ),
    }
    return {
        "version": 2,
        "confirmed_symbol": active[0] if len(active) == 1 else None,
        "recent_symbols": recent,
        "active_symbols": active,
        "comparison_symbols": comparison,
        "last_intent": intent,
        "hypotheses": hypotheses,
        "constraints": constraints,
        "historical_period": period,
        "last_tool_results": [{"tool": row["tool"], "symbol": row.get("symbol"), "status": row["status"]} for row in tools][:3],
        "last_verified_claims": claims,
        "last_answer_reference": old.get("last_answer_reference"),
        "as_of": effective_as_of,
        "expires_at": expires_at,
        "updated_at": now.isoformat(),
        "structured_summary": summary,
    }


def with_answer_reference(memory: dict[str, Any], answer: str) -> dict[str, Any]:
    updated = dict(memory)
    updated["last_answer_reference"] = answer[-2400:] if answer else updated.get("last_answer_reference")
    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
    return updated
