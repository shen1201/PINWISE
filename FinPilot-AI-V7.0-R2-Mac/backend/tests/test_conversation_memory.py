from __future__ import annotations

import json
import os
import unittest

os.environ["FINPILOT_SKIP_DOTENV"] = "1"

from backend.app.core.models import AssistantRequest
from backend.tests.test_assistant import FakeGemini, FakeMarket, collect, make_service


def event_data(events, event_type: str):
    return next(event["data"] for event in events if event["type"] == event_type)


def event_memory(events):
    return next(event["memory"] for event in reversed(events) if event["type"] in {"done", "memory"})


class ConversationMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def turn(self, service, message: str, memory=None, *, conversation_id="p1", history=None):
        payload = {"conversation_id": conversation_id, "message": message, "history": history or []}
        if memory is not None:
            payload["memory"] = memory
        events = await collect(service, AssistantRequest(**payload))
        return events, event_memory(events) if any(
            event["type"] in {"done", "memory"} for event in events
        ) else memory

    async def test_question_about_my_preferences_does_not_reuse_previous_stock(self):
        service = make_service(market=FakeMarket())
        _, memory = await self.turn(service, "環球晶現在值得買嗎？")
        self.assertEqual(memory["active_symbols"], ["6488"])
        second, _ = await self.turn(service, "分析我的個人化偏好，我可以持有哪些標的？", memory)
        self.assertNotIn("clarification", [event["type"] for event in second])
        self.assertEqual(event_data(second, "tool_plan")["calls"], [])

    async def test_follow_up_announcement_question_keeps_previous_stock(self):
        # 先問台積電股價，再問「最近有新的公告嗎？」要接著查台積電，不反問標的。
        service = make_service(market=FakeMarket())
        _, memory = await self.turn(service, "台積電現在股價多少？")
        self.assertEqual(memory["active_symbols"], ["2330"])
        for follow_up in ("最近有新的公告嗎？", "那它有法說會嗎？", "波動大嗎"):
            with self.subTest(follow_up=follow_up):
                events, _ = await self.turn(service, follow_up, memory)
                self.assertNotIn("clarification", [event["type"] for event in events])
                self.assertIn("2330", [call.get("symbol") for call in event_data(events, "tool_plan")["calls"]])

    async def test_required_four_turn_research_context(self):
        market = FakeMarket()
        service = make_service(market=market)

        first, memory = await self.turn(service, "環球晶現在值得買嗎？")
        self.assertEqual(event_data(first, "understanding")["intent"], "investment_decision")
        self.assertEqual(memory["active_symbols"], ["6488"])
        self.assertEqual(memory["comparison_symbols"], [])
        self.assertEqual([call["name"] for call in event_data(first, "tool_plan")["calls"]],
                         ["market_snapshot"])
        self.assertEqual(event_data(first, "tool_plan")["calls"][0]["scope"], "full")

        second, memory = await self.turn(service, "如果跌到 900 元呢？", memory)
        self.assertEqual(event_data(second, "understanding")["intent"], "target_price_scenario")
        self.assertEqual(memory["active_symbols"], ["6488"])
        self.assertEqual(memory["hypotheses"], [{
            "type": "price_scenario", "value": 900.0, "unit": "TWD",
            "raw_text": "如果跌到 900 元", "source": "user", "conditional": True,
            "symbol": "6488",
        }])
        self.assertEqual([call["name"] for call in event_data(second, "tool_plan")["calls"]],
                         ["market_snapshot"])
        self.assertEqual(event_data(second, "tool_plan")["calls"][0]["scope"], "full")

        third, memory = await self.turn(service, "那跟中美晶相比呢？", memory)
        self.assertEqual(event_data(third, "understanding")["intent"], "compare")
        self.assertEqual(memory["active_symbols"], ["6488", "5483"])
        self.assertEqual(memory["comparison_symbols"], ["6488", "5483"])
        self.assertEqual(
            [(call["name"], call["symbol"]) for call in event_data(third, "tool_plan")["calls"]],
            [("market_snapshot", "6488"), ("market_snapshot", "5483")],
        )
        self.assertEqual(memory["hypotheses"][0]["symbol"], "6488")

        calls_before_rephrase = list(market.calls)
        fourth, memory = await self.turn(service, "講白話一點。", memory)
        plan = event_data(fourth, "tool_plan")
        self.assertEqual(plan["intent"], "rephrase")
        self.assertEqual(plan["calls"], [])
        self.assertEqual(plan["market_data_action"], "no_market_lookup")
        self.assertTrue(plan["reused_conversation_facts"])
        self.assertEqual(market.calls, calls_before_rephrase)
        self.assertEqual(memory["comparison_symbols"], ["6488", "5483"])

    async def test_price_hypothesis_update_period_change_and_explicit_target_switch(self):
        market = FakeMarket()
        service = make_service(market=market)
        _, memory = await self.turn(service, "環球晶現在值得買嗎？")
        _, memory = await self.turn(service, "如果跌到 900 元呢？", memory)
        _, memory = await self.turn(service, "改成 850 元呢？", memory)
        self.assertEqual(len(memory["hypotheses"]), 1)
        self.assertEqual(memory["hypotheses"][0]["value"], 850.0)
        self.assertEqual(memory["hypotheses"][0]["symbol"], "6488")

        period_events, memory = await self.turn(service, "改看近一年", memory)
        self.assertEqual(event_data(period_events, "tool_plan")["intent"], "history")
        self.assertEqual([call["name"] for call in event_data(period_events, "tool_plan")["calls"]],
                         ["price_history"])
        self.assertFalse(memory["historical_period"]["defaulted"])
        self.assertEqual(memory["historical_period"]["label"], "近 1 年")

        switch_events, memory = await self.turn(service, "先不要看環球晶，改研究台積電。", memory)
        self.assertEqual(memory["active_symbols"], ["2330"])
        self.assertEqual(memory["comparison_symbols"], [])
        self.assertEqual(memory["hypotheses"], [])
        self.assertEqual(event_data(switch_events, "tool_plan")["intent"], "research")
        self.assertEqual([(call["name"], call["symbol"]) for call in event_data(switch_events, "tool_plan")["calls"]],
                         [("price_history", "2330")])

    async def test_three_stock_and_etf_comparisons_keep_all_explicit_subjects(self):
        service = make_service()
        _, memory = await self.turn(service, "比較環球晶與中美晶")
        events, memory = await self.turn(service, "再跟國巨比", memory)
        self.assertEqual(memory["comparison_symbols"], ["6488", "5483", "2327"])
        self.assertEqual([call["symbol"] for call in event_data(events, "tool_plan")["calls"]],
                         ["6488", "5483", "2327"])

        etf_events, etf_memory = await self.turn(
            make_service(), "我有五萬元，想比較 0050 和 006208。", conversation_id="etf"
        )
        self.assertEqual(etf_memory["comparison_symbols"], ["0050", "006208"])
        self.assertEqual(etf_memory["constraints"], [{
            "type": "budget", "value": 50000.0, "unit": "TWD", "raw_text": "我有五萬元",
            "source": "user", "retention": "conversation",
        }])
        self.assertNotIn("50000", [call["symbol"] for call in event_data(etf_events, "tool_plan")["calls"]])

    async def test_missing_context_session_isolation_and_legacy_memory_migration(self):
        service = make_service()
        missing = await collect(service, AssistantRequest(
            conversation_id="empty", message="如果跌到 900 元呢？"
        ))
        self.assertEqual(missing[-1]["type"], "clarification")
        self.assertFalse(any(event["type"] == "tool" for event in missing))

        _, session_one_memory = await self.turn(service, "環球晶現在值得買嗎？", conversation_id="one")
        isolated = await collect(service, AssistantRequest(
            conversation_id="two", message="那它風險呢？"
        ))
        self.assertEqual(isolated[-1]["type"], "clarification")

        legacy = {"confirmed_symbol": "6488", "recent_symbols": ["6488"], "last_intent": "price"}
        legacy_events, migrated = await self.turn(
            service, "那它風險呢？", legacy, conversation_id="legacy"
        )
        self.assertEqual(migrated["version"], 2)
        self.assertEqual(migrated["active_symbols"], ["6488"])
        self.assertEqual(event_data(legacy_events, "tool_plan")["intent"], "risk_analysis")
        self.assertEqual(session_one_memory["active_symbols"], ["6488"])

    async def test_current_price_requeries_provider_even_when_old_memory_exists(self):
        market = FakeMarket()
        service = make_service(market=market)
        _, memory = await self.turn(service, "環球晶現在值得買嗎？")
        memory["expires_at"] = "2020-01-01T00:00:00+00:00"
        prior_calls = len(market.calls)

        events, refreshed = await self.turn(service, "目前股價呢？", memory)
        self.assertEqual(len(market.calls), prior_calls + 1)
        self.assertEqual(market.calls[-1], "6488")
        self.assertEqual(event_data(events, "tool_plan")["market_data_action"],
                         "provider_query_or_valid_cache")
        self.assertNotEqual(refreshed["expires_at"], "2020-01-01T00:00:00+00:00")
        self.assertEqual(refreshed["last_verified_claims"][0]["symbol"], "6488")

    async def test_direct_new_symbol_clears_old_symbol_hypotheses_and_claims(self):
        service = make_service()
        _, memory = await self.turn(service, "環球晶如果跌到 900 元呢？")
        self.assertEqual(memory["hypotheses"][0]["symbol"], "6488")

        _, memory = await self.turn(service, "台積電目前股價多少？", memory)
        self.assertEqual(memory["active_symbols"], ["2330"])
        self.assertEqual(memory["comparison_symbols"], [])
        self.assertEqual(memory["hypotheses"], [])
        self.assertTrue(memory["last_verified_claims"])
        self.assertTrue(all(claim["symbol"] == "2330" for claim in memory["last_verified_claims"]))

    async def test_explicit_industry_topic_switch_clears_old_stock_and_hypothesis(self):
        service = make_service()
        _, memory = await self.turn(service, "環球晶如果跌到 900 元呢？")
        events, memory = await self.turn(service, "先不要看環球晶，換成台灣被動元件產業。", memory)
        understood = event_data(events, "understanding")
        self.assertEqual(understood["research_type"], "industry_supply_chain")
        self.assertIn("explicit_topic_switch", understood["classification_signals"])
        self.assertEqual(memory["active_symbols"], [])
        self.assertEqual(memory["comparison_symbols"], [])
        self.assertEqual(memory["hypotheses"], [])
        self.assertIn("台灣被動元件", memory["structured_summary"]["research_topic"])

    async def test_memory_event_survives_stream_interruption_and_allows_next_question(self):
        market = FakeMarket()
        interrupted_service = make_service(market=market, gemini=FakeGemini(mode="interrupted"))
        interrupted = await collect(interrupted_service, AssistantRequest(
            conversation_id="stopped", message="台積電目前股價多少？"
        ))
        self.assertTrue(any(event["type"] == "memory" for event in interrupted))
        self.assertEqual(interrupted[-1]["type"], "error")
        memory = next(event["memory"] for event in interrupted if event["type"] == "memory")

        resumed_service = make_service(market=market)
        events, resumed = await self.turn(
            resumed_service, "那它風險呢？", memory, conversation_id="stopped"
        )
        self.assertEqual(resumed["active_symbols"], ["2330"])
        self.assertEqual(event_data(events, "tool_plan")["intent"], "risk_analysis")

    async def test_gemini_receives_bounded_structured_state_not_private_holdings(self):
        gemini = FakeGemini()
        service = make_service(gemini=gemini)
        _, memory = await self.turn(service, "我有五萬元，想比較 0050 和 006208。")
        await self.turn(service, "那近期風險呢？", memory)
        payload = json.loads(gemini.prompts[-1].split("\n", 1)[1])
        state = payload["research_context"]["conversation_state"]
        self.assertEqual(state["comparison_symbols"], ["0050", "006208"])
        self.assertLessEqual(len(payload["conversation_memory"]["last_verified_claims"]), 12)
        self.assertLessEqual(len(payload["conversation_memory"]["hypotheses"]), 6)
        self.assertFalse(payload["research_context"]["data_policy"]["private_holdings_or_broker_data_used"])
        self.assertEqual(payload["research_context"]["user_constraints"][0]["retention"], "conversation")


if __name__ == "__main__":
    unittest.main()


class HomophoneTargetTests(unittest.TestCase):
    def test_typo_needs_same_sound_and_a_shared_character(self):
        from datetime import date
        from backend.app.core.models import CompanyProfile, SourceMetadata
        from backend.app.services.input_understanding import _homophone_targets

        meta = SourceMetadata(source="fixture", source_url="https://fixture.example", raw_source="fixture", fetched_at="2026-11-10T00:00:00Z")
        profiles = [CompanyProfile(symbol=code, short_name=name, market="TWSE", metadata=meta)
                    for code, name in [("1815", "富喬"), ("6922", "宸曜"), ("2330", "台積電")]]
        self.assertEqual([c.symbol for c in _homophone_targets("復喬", profiles, set())], ["1815"])
        self.assertEqual([c.symbol for c in _homophone_targets("台機電", profiles, set())], ["2330"])
        self.assertEqual(_homophone_targets("磣要", profiles, set()), [])  # 同音但沒有共同字
