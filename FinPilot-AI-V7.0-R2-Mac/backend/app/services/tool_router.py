from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_TOOLS = {
    "market_snapshot", "price_history", "company_profile", "material_events",
    "investor_conferences",
}


@dataclass(frozen=True)
class ToolCall:
    name: str
    symbol: str
    reason: str
    scope: str | None = None

    def as_dict(self) -> dict[str, str]:
        result = {"name": self.name, "symbol": self.symbol, "reason": self.reason}
        if self.scope:
            result["scope"] = self.scope
        return result


@dataclass
class ToolPlan:
    intent: str
    required_data: list[str] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    omitted_calls: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "required_data": self.required_data,
            "calls": [call.as_dict() for call in self.calls],
            "missing_capabilities": self.missing_capabilities,
            "omitted_calls": self.omitted_calls,
        }


class ToolRouter:
    """Build a deterministic, bounded plan from an already understood request."""

    def __init__(self, *, max_calls: int):
        self.max_calls = max(0, max_calls)

    def plan(self, *, intent: str, symbols: list[str], period: dict[str, Any], message: str = "") -> ToolPlan:
        plan = ToolPlan(intent=intent)
        if not symbols or intent in {"unknown", "general", "explain", "rephrase", "full_research"}:
            return plan

        calls: list[ToolCall] = []
        explicit_period = not period.get("defaulted", True)
        asks_conference = "法說" in message or "法人說明會" in message

        if intent == "price":
            plan.required_data = ["最近官方日行情與交易日期"]
            calls = [ToolCall("market_snapshot", symbol, "只取得最近日行情與日期", "quote") for symbol in symbols]
        elif intent in {"history", "research"}:
            plan.required_data = ["指定期間歷史日價", "程式計算的報酬與波動指標"]
            calls = [ToolCall("price_history", symbol, "依使用者期間計算歷史表現") for symbol in symbols]
        elif intent == "company":
            plan.required_data = ["官方公司基本資料"]
            calls = [ToolCall("company_profile", symbol, "取得官方公司資料") for symbol in symbols]
        elif intent == "disclosure":
            if asks_conference:
                plan.required_data = ["MOPS 每日重大訊息中的法說會公告"]
                calls = [ToolCall("investor_conferences", symbol, "取得近期法說會公告") for symbol in symbols]
            else:
                plan.required_data = ["重大訊息與公告"]
                calls = [ToolCall("material_events", symbol, "取得近期重大訊息") for symbol in symbols]
        elif intent == "compare":
            plan.required_data = ["各標的同口徑日行情", "歷史風險與報酬指標", "公司與事件摘要"]
            calls = [ToolCall("market_snapshot", symbol, "以相同日行情與歷史指標口徑比較標的", "market") for symbol in symbols]
            if explicit_period:
                extra = [ToolCall("price_history", symbol, "以指定期間比較歷史表現") for symbol in symbols]
                if len(calls) + len(extra) <= self.max_calls:
                    calls.extend(extra)
                else:
                    plan.missing_capabilities.append("工具呼叫上限不足以替所有比較標的追加指定期間日價；保留同口徑市場快照")
            if any(symbol.startswith("00") for symbol in symbols):
                plan.missing_capabilities.append("ETF 長期適配仍缺成分、經理費、保管費、配息來源與追蹤誤差資料")
            else:
                plan.missing_capabilities.append("基本面比較仍缺同期營收、EPS、估值、毛利率與 ROE")
        elif intent == "investment_decision":
            plan.required_data = ["最近官方日行情", "歷史風險與報酬", "公司基本資料", "近期重大事件"]
            for symbol in symbols:
                calls.append(ToolCall("market_snapshot", symbol, "一次取得行情、歷史指標、公司與事件摘要", "full"))
            plan.missing_capabilities.extend([
                "尚無同期營收、EPS、本益比、毛利率與 ROE 的可核實助手工具；不能據此給出精確估值",
                "尚無外資、投信、自營商與融資融券等籌碼工具",
            ])
        elif intent == "target_price_scenario":
            plan.required_data = ["最近官方日行情", "歷史價格範圍與波動", "影響情境的重大事件"]
            for symbol in symbols:
                calls.append(ToolCall("market_snapshot", symbol, "取得現況、近六個月歷史指標與重大事件", "full"))
                if explicit_period:
                    calls.append(ToolCall("price_history", symbol, "依使用者指定期間評估價格情境"))
            plan.missing_capabilities.append("缺少可核實的 EPS、估值倍數與獲利預測，不把使用者目標價當成合理價")
        elif intent == "valuation":
            plan.required_data = ["最近官方日行情", "官方公司資料", "估值所需財務指標"]
            for symbol in symbols:
                calls.append(ToolCall("market_snapshot", symbol, "取得現價、歷史區間、公司資料與事件", "full"))
            plan.missing_capabilities.append("目前沒有同期 EPS、本益比、股價淨值比、毛利率與 ROE；不得聲稱已算出唯一合理價")
        elif intent == "risk_analysis":
            plan.required_data = ["最近官方日行情", "歷史波動與回撤", "重大事件"]
            for symbol in symbols:
                calls.append(ToolCall("market_snapshot", symbol, "取得行情、近六個月風險指標與重大事件", "full"))
                if explicit_period:
                    calls.append(ToolCall("price_history", symbol, "依指定期間核對波動與回撤"))
            plan.missing_capabilities.append("籌碼與完整產業新聞尚未納入一般助手；事件判斷只採已取得的官方公告")

        unique: list[ToolCall] = []
        seen: set[tuple[str, str]] = set()
        for call in calls:
            key = (call.name, call.symbol)
            if call.name not in ALLOWED_TOOLS or key in seen:
                continue
            seen.add(key)
            unique.append(call)
        plan.omitted_calls = max(0, len(unique) - self.max_calls)
        plan.calls = unique[:self.max_calls]
        if plan.omitted_calls:
            plan.missing_capabilities.append(f"受工具呼叫上限限制，省略 {plan.omitted_calls} 個低優先查詢")
        return plan
