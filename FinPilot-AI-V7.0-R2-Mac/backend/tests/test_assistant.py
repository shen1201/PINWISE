from __future__ import annotations

import asyncio
import json
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

os.environ["FINPILOT_SKIP_DOTENV"] = "1"
os.environ["FINPILOT_STARTUP_SOURCE_CHECK"] = "false"

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.models import AssistantRequest, CompanyProfile, MarketQuote, PricePoint, SourceMetadata
from backend.app.services.assistant import AssistantService
from backend.app.services.input_understanding import InputUnderstandingService


def metadata(*, stale=False):
    return SourceMetadata(source="fixture", source_url="https://example.test", raw_source="isolated fixture", stale=stale)


class FakeCompanies:
    def __init__(self, rows, quotes=None):
        self.rows = rows
        self.quote_rows = quotes or []

    async def companies(self):
        return self.rows

    async def quotes(self):
        return self.quote_rows


class FakeMarket:
    def __init__(self, fail=False, stale=False):
        self.calls = []
        self.scopes = []
        self.fail = fail
        self.stale = stale

    async def snapshot(self, symbol, *, scope="full"):
        self.calls.append(symbol)
        self.scopes.append(scope)
        if self.fail:
            raise RuntimeError("source unavailable")
        names = {"2330": "台積電", "2454": "聯發科", "6488": "環球晶", "5483": "中美晶", "2327": "國巨"}
        price = 100.0 if symbol == "2330" else 80.0
        source = metadata(stale=self.stale).model_dump(mode="json")
        capabilities = ["market_snapshot"]
        if scope in {"market", "full"}:
            capabilities.append("price_history")
        if scope == "full":
            capabilities.extend(["company_profile", "material_events"])
        return {
            "symbol": symbol, "name": names.get(symbol, symbol), "market": "TWSE",
            "found": True, "data_frequency": "daily", "as_of": "2026-10-08",
            "quote": {"symbol": symbol, "close": price, "trade_date": "2026-10-08", "metadata": source},
            "company": {"symbol": symbol, "name": names.get(symbol, symbol), "metadata": source},
            "metrics": {"period_return_pct": 5.0, "annualized_volatility_pct": 20.0},
            "history": [], "events": [], "errors": [],
            "scope": scope, "capabilities": capabilities,
        }


class FakeFinMind:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def history(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if self.error:
            raise self.error
        return [
            PricePoint(symbol=symbol, trade_date=date(2026, 10, 1), close=75, metadata=metadata()),
            PricePoint(symbol=symbol, trade_date=date(2026, 10, 8), close=80, metadata=metadata()),
        ]


class FakeMops:
    def __init__(self, company_error=None, disclosure_error=None):
        self.company_error = company_error
        self.disclosure_error = disclosure_error
        self.company_calls = []
        self.disclosure_calls = []

    async def company(self, symbol):
        self.company_calls.append(symbol)
        if self.company_error:
            raise self.company_error
        return {"symbol": symbol, "name": "fixture", "metadata": metadata().model_dump(mode="json")}

    async def disclosures(self, symbol, **_kwargs):
        self.disclosure_calls.append(symbol)
        if self.disclosure_error:
            raise self.disclosure_error
        return []


class FakeIR:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.calls = []

    async def conferences(self, symbol, **_kwargs):
        self.calls.append(symbol)
        if self.error:
            raise self.error
        return self.rows


class FakeGemini:
    def __init__(self, mode="ok", text=None):
        self.mode = mode
        self.text = text
        self.calls = 0
        self.prompts = []

    async def stream_assistant(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        if self.mode == "quota":
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
        if self.mode == "timeout":
            raise asyncio.TimeoutError()
        if self.mode == "interrupted":
            yield {"text": "部分回答"}
            raise RuntimeError("connection reset")
        if self.text is not None:
            yield {"text": self.text}
        else:
            yield {"text": "依官方日資料，"}
            yield {"text": "已標示交易日。"}
        yield {"usage": {"total_token_count": 12}}


def settings(**overrides):
    values = dict(
        gemini_model="test-model", assistant_max_input_chars=1200,
        assistant_max_output_tokens=256, assistant_max_history_messages=4,
        assistant_max_tool_calls=3, request_timeout_seconds=1,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def make_service(*, gemini=None, market=None, finmind=None, mops=None, ir=None, max_history=4):
    profiles = [
        CompanyProfile(symbol="2330", name="台灣積體電路製造股份有限公司", short_name="台積電", market="TWSE", metadata=metadata()),
        CompanyProfile(symbol="2454", name="聯發科技股份有限公司", short_name="聯發科", market="TWSE", metadata=metadata()),
        CompanyProfile(symbol="1459", name="聯發紡織纖維股份有限公司", short_name="聯發", market="TWSE", metadata=metadata()),
        CompanyProfile(symbol="6488", name="環球晶圓股份有限公司", short_name="環球晶", market="TPEX", metadata=metadata()),
        CompanyProfile(symbol="5483", name="中美矽晶製品股份有限公司", short_name="中美晶", market="TPEX", metadata=metadata()),
        CompanyProfile(symbol="2327", name="國巨股份有限公司", short_name="國巨", market="TWSE", metadata=metadata()),
        CompanyProfile(symbol="0050", name="元大台灣卓越50證券投資信託基金", short_name="元大台灣50", market="TWSE", metadata=metadata()),
        CompanyProfile(symbol="006208", name="富邦台灣采吉50證券投資信託基金", short_name="富邦台50", market="TWSE", metadata=metadata()),
    ]
    etf_quotes = [
        MarketQuote(symbol=symbol, name=name, market="TWSE", trade_date=date(2026, 10, 8), close=close, metadata=metadata())
        for symbol, name, close in (
            ("0050", "元大台灣50", 60), ("0056", "元大高股息", 38),
            ("00878", "國泰永續高股息", 22), ("006208", "富邦台50", 120),
            ("00713", "元大台灣高息低波", 52), ("00919", "群益台灣精選高息", 24),
            ("00891", "中信關鍵半導體", 18), ("00927", "群益半導體收益", 20),
            ("0052", "富邦科技", 145),
        )
    ]
    understanding = InputUnderstandingService(twse=FakeCompanies(profiles, quotes=etf_quotes), tpex=FakeCompanies([]))
    return AssistantService(
        settings=settings(assistant_max_history_messages=max_history), understanding=understanding,
        market=market or FakeMarket(), finmind=finmind or FakeFinMind(), mops=mops or FakeMops(),
        gemini=gemini or FakeGemini(), ir=ir or FakeIR(),
    )


async def collect(service, request):
    return [event async for event in service.stream(request)]


class AssistantServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_natural_chat_defaults_do_not_create_full_research_or_force_clarification(self):
        market, gemini = FakeMarket(), FakeGemini()
        service = make_service(market=market, gemini=gemini)

        knowledge = await collect(service, AssistantRequest(
            conversation_id="natural-knowledge", message="ETF 跟個股有什麼差別？",
        ))
        self.assertFalse(any(event["type"] in {"clarification", "research_handoff", "tool"} for event in knowledge))

        etf = await collect(service, AssistantRequest(
            conversation_id="natural-etf", message="幫我分析三檔 ETF。",
        ))
        understood = next(event["data"] for event in etf if event["type"] == "understanding")
        plan = next(event["data"] for event in etf if event["type"] == "tool_plan")
        self.assertEqual(understood["resolved_symbols"], ["0050", "0056", "00878"])
        self.assertEqual([call["symbol"] for call in plan["calls"]], ["0050", "0056", "00878"])
        self.assertFalse(any(event["type"] in {"clarification", "research_handoff"} for event in etf))

        screen = await collect(service, AssistantRequest(
            conversation_id="natural-screen", message="最近有哪些值得關注的股票？",
        ))
        self.assertFalse(any(event["type"] in {"clarification", "research_handoff", "tool"} for event in screen))

        portfolio = await collect(service, AssistantRequest(
            conversation_id="natural-portfolio", message="我想分析目前持有的股票。",
        ))
        self.assertEqual(portfolio[-1]["type"], "clarification")
        self.assertIn("無法讀取你的私人持股", portfolio[-1]["message"])

    async def test_event_question_is_answered_from_records_without_model(self):
        class NoCallGemini(FakeGemini):
            async def stream_assistant(self, _prompt):
                raise AssertionError("事件題不應呼叫模型")
                yield {}

        service = make_service(gemini=NoCallGemini())
        etf = await collect(service, AssistantRequest(conversation_id="event-etf", message="0050 最近要分割嗎"))
        etf_text = "".join(event.get("text", "") for event in etf if event["type"] == "delta")
        self.assertIn("無法確認", etf_text)
        self.assertIn("投信", etf_text)
        self.assertNotIn("目前沒有", etf_text)
        company = await collect(service, AssistantRequest(conversation_id="event-co", message="2330 最近要減資嗎"))
        self.assertIn("不代表沒有", "".join(event.get("text", "") for event in company if event["type"] == "delta"))

    async def test_industry_topic_is_not_clarified_or_sent_to_stock_tools(self):
        gemini, market = FakeGemini(text="可先從需求、景氣循環與競爭格局理解。"), FakeMarket()
        events = await collect(make_service(gemini=gemini, market=market), AssistantRequest(
            conversation_id="industry-chat", message="分析台灣被動元件產業的機會與風險",
        ))
        understood = next(event["data"] for event in events if event["type"] == "understanding")
        plan = next(event["data"] for event in events if event["type"] == "tool_plan")
        self.assertEqual(understood["research_type"], "industry_supply_chain")
        self.assertEqual(understood["target_status"], "not_required")
        self.assertEqual(understood["candidates"], [])
        self.assertEqual(plan["calls"], [])
        self.assertEqual(market.calls, [])
        self.assertFalse(any(event["type"] == "clarification" for event in events))
        payload = json.loads(gemini.prompts[0].split("\n", 1)[1])
        profile = payload["research_context"]["response_profile"]
        self.assertEqual(profile["style"], "natural_conversation")
        self.assertTrue(payload["instructions"]["do_not_force_fixed_report_headings"])

    async def test_industry_full_research_handoff_keeps_type_and_topic(self):
        gemini = FakeGemini()
        events = await collect(make_service(gemini=gemini), AssistantRequest(
            conversation_id="industry-handoff", message="請建立台灣被動元件產業完整研究",
        ))
        handoff = next(event for event in events if event["type"] == "research_handoff")
        self.assertEqual(handoff["research_type"], "industry_supply_chain")
        self.assertIn("台灣被動元件", handoff["research_topic"])
        self.assertEqual(handoff["symbols"], [])
        self.assertEqual(gemini.calls, 0)

    async def test_etf_followup_replaces_defaults_instead_of_extending_old_selection(self):
        service = make_service()
        first = await collect(service, AssistantRequest(
            conversation_id="etf-correction", message="幫我分析三檔 ETF。",
        ))
        memory = next(event["memory"] for event in first if event["type"] == "done")
        self.assertEqual(memory["comparison_symbols"], ["0050", "0056", "00878"])
        second = await collect(service, AssistantRequest(
            conversation_id="etf-correction", message="不是這三檔，換成其他 ETF。", memory=memory,
        ))
        next_memory = next(event["memory"] for event in second if event["type"] == "done")
        self.assertEqual(next_memory["comparison_symbols"], ["006208", "00713", "00919"])
        plan = next(event["data"] for event in second if event["type"] == "tool_plan")
        self.assertEqual([call["symbol"] for call in plan["calls"]], ["006208", "00713", "00919"])
    async def test_investment_decision_builds_public_tool_plan_and_research_context(self):
        gemini, market, mops = FakeGemini(), FakeMarket(), FakeMops()
        events = await collect(make_service(gemini=gemini, market=market, mops=mops), AssistantRequest(
            conversation_id="decision", message="環球晶現在值得買嗎？"
        ))
        understanding = next(event["data"] for event in events if event["type"] == "understanding")
        plan = next(event["data"] for event in events if event["type"] == "tool_plan")
        self.assertEqual(understanding["intent"], "investment_decision")
        self.assertTrue(understanding["requires_market_data"])
        self.assertEqual([call["name"] for call in plan["calls"]], ["market_snapshot"])
        self.assertEqual(plan["calls"][0]["scope"], "full")
        self.assertEqual(market.calls, ["6488"])
        self.assertEqual(market.scopes, ["full"])
        self.assertEqual(mops.company_calls, [])
        self.assertEqual(mops.disclosure_calls, [])
        payload = json.loads(gemini.prompts[0].split("\n", 1)[1])
        context = payload["research_context"]
        self.assertEqual(context["intent"], "investment_decision")
        self.assertEqual(context["research_targets"], ["6488"])
        self.assertTrue(context["verified_market_information"])
        self.assertTrue(context["source_records"])
        self.assertFalse(context["data_policy"]["private_holdings_or_broker_data_used"])

    async def test_target_price_is_user_hypothesis_not_verified_quote(self):
        gemini = FakeGemini(text="1200 元是使用者提出的目標情境，不是已確認現價。")
        finmind, mops = FakeFinMind(), FakeMops()
        events = await collect(make_service(gemini=gemini, finmind=finmind, mops=mops), AssistantRequest(
            conversation_id="target", message="國巨未來有機會漲回 1200 元嗎？"
        ))
        understanding = next(event["data"] for event in events if event["type"] == "understanding")
        self.assertEqual(understanding["intent"], "target_price_scenario")
        self.assertEqual(understanding["hypotheses"][0]["value"], 1200.0)
        plan = next(event["data"] for event in events if event["type"] == "tool_plan")
        self.assertEqual([call["name"] for call in plan["calls"]], ["market_snapshot"])
        self.assertEqual(plan["calls"][0]["scope"], "full")
        payload = json.loads(gemini.prompts[0].split("\n", 1)[1])
        hypothesis = payload["research_context"]["user_hypotheses"][0]
        self.assertEqual(hypothesis["source"], "user")
        self.assertEqual(hypothesis["type"], "price_target")
        self.assertNotEqual(payload["research_context"]["verified_market_information"][0]["quote"]["close"], 1200)
        calculation = payload["research_context"]["deterministic_calculations"][0]
        self.assertEqual(calculation["target_source"], "user_hypothesis")
        self.assertEqual(calculation["required_change_pct"], 1400.0)
        self.assertTrue(payload["research_context"]["missing_or_unavailable"])
        answer = "".join(event.get("text", "") for event in events if event["type"] == "delta")
        self.assertIn(gemini.text, answer)
        self.assertIn("需變動 1400%", answer)
        self.assertIn("不代表合理價或預測", answer)
        # 資料限制改由介面顯示在回答下方，不寫進回答本文。
        self.assertNotIn("資料限制", answer)
        notes = next(event for event in events if event["type"] == "done")["notes"]
        self.assertTrue(any(note.startswith("目前無法取得") for note in notes))
        self.assertEqual(next(event for event in events if event["type"] == "done")["verification"], "verified")

    async def test_target_hypothesis_cannot_be_relabelled_as_current_price(self):
        gemini = FakeGemini(text="目前股價為 1200 元。")
        events = await collect(make_service(gemini=gemini), AssistantRequest(
            conversation_id="target-misuse", message="國巨未來有機會漲回 1200 元嗎？"
        ))
        answer = "".join(event.get("text", "") for event in events if event["type"] == "delta")
        self.assertNotIn("目前股價為 1200", answer)
        self.assertIn("收盤價 80.0 元", answer)
        self.assertEqual(next(event for event in events if event["type"] == "done")["verification"],
                         "replaced_with_verified_facts")

    async def test_price_and_knowledge_questions_use_minimum_tools(self):
        market, price_gemini = FakeMarket(), FakeGemini()
        price_events = await collect(make_service(market=market, gemini=price_gemini), AssistantRequest(
            conversation_id="minimum-price", message="台積電目前股價多少？"
        ))
        price_plan = next(event["data"] for event in price_events if event["type"] == "tool_plan")
        self.assertEqual([call["name"] for call in price_plan["calls"]], ["market_snapshot"])
        self.assertEqual(market.calls, ["2330"])
        self.assertEqual(market.scopes, ["quote"])

        knowledge_gemini = FakeGemini()
        knowledge_events = await collect(make_service(gemini=knowledge_gemini), AssistantRequest(
            conversation_id="minimum-knowledge", message="什麼是本益比？"
        ))
        knowledge_plan = next(event["data"] for event in knowledge_events if event["type"] == "tool_plan")
        self.assertEqual(knowledge_plan["calls"], [])
        self.assertFalse(any(event["type"] == "tool" for event in knowledge_events))
        self.assertEqual(knowledge_gemini.calls, 1)

    async def test_partial_tool_failures_are_preserved_without_discarding_successes(self):
        gemini = FakeGemini()
        events = await collect(make_service(gemini=gemini, finmind=FakeFinMind(error=RuntimeError("503 upstream"))), AssistantRequest(
            conversation_id="partial", message="環球晶近一年風險如何？"
        ))
        tools = [event for event in events if event["type"] == "tool"]
        self.assertEqual([event["status"] for event in tools], ["completed", "failed"])
        self.assertEqual(tools[1]["error_code"], "upstream_error")
        self.assertEqual(gemini.calls, 1)
        context = json.loads(gemini.prompts[0].split("\n", 1)[1])["research_context"]
        self.assertTrue(context["verified_market_information"])
        self.assertTrue(any(item.get("error_code") == "upstream_error" for item in context["missing_or_unavailable"]))

    async def test_tool_429_and_timeout_remain_distinct_with_partial_data(self):
        gemini = FakeGemini()
        rate_events = await collect(make_service(
            gemini=gemini, finmind=FakeFinMind(error=RuntimeError("429 rate limited")),
        ), AssistantRequest(conversation_id="tool-rate", message="國巨近一年如果漲到 1200 元呢？"))
        rate_error = next(event for event in rate_events if event["type"] == "tool" and event["status"] == "failed")
        self.assertEqual((rate_error["name"], rate_error["error_code"]), ("price_history", "rate_limited"))
        timeout_events = await collect(make_service(
            gemini=gemini, mops=FakeMops(disclosure_error=asyncio.TimeoutError()),
        ), AssistantRequest(conversation_id="tool-timeout", message="國巨有什麼重大訊息？"))
        timeout_error = next(event for event in timeout_events if event["type"] == "tool" and event["status"] == "failed")
        self.assertEqual((timeout_error["name"], timeout_error["error_code"]), ("material_events", "timeout"))
        self.assertEqual(gemini.calls, 1)

    async def test_etf_long_term_comparison_uses_symmetric_snapshots(self):
        market = FakeMarket()
        events = await collect(make_service(market=market), AssistantRequest(
            conversation_id="etf-compare", message="0050 跟 006208 哪個比較適合長期持有？"
        ))
        plan = next(event["data"] for event in events if event["type"] == "tool_plan")
        self.assertEqual(plan["intent"], "compare")
        self.assertEqual([(call["name"], call["symbol"]) for call in plan["calls"]],
                         [("market_snapshot", "0050"), ("market_snapshot", "006208")])
        self.assertEqual(market.calls, ["0050", "006208"])

    async def test_price_followup_switches_symbol_and_refreshes_daily_tool(self):
        market, gemini = FakeMarket(), FakeGemini()
        service = make_service(market=market, gemini=gemini)
        first = await collect(service, AssistantRequest(conversation_id="a", message="台積電目前股價多少？"))
        memory = next(event["memory"] for event in first if event["type"] == "done")
        self.assertEqual(memory["confirmed_symbol"], "2330")
        self.assertEqual(memory["last_intent"], "price")
        second = await collect(service, AssistantRequest(
            conversation_id="a", message="聯發科呢？", memory=memory,
            history=[{"role": "user", "text": "台積電目前股價多少？"}, {"role": "assistant", "text": "前一則回答"}],
        ))
        second_memory = next(event["memory"] for event in second if event["type"] == "done")
        self.assertEqual(second_memory["confirmed_symbol"], "2454")
        self.assertEqual(market.calls, ["2330", "2454"])
        self.assertEqual(gemini.calls, 2)

    async def test_pronoun_uses_only_same_conversation_memory(self):
        market = FakeMarket()
        service = make_service(market=market)
        with_memory = await collect(service, AssistantRequest(
            conversation_id="one", message="那它風險呢？",
            memory={"confirmed_symbol": "2330", "recent_symbols": ["2330"], "last_intent": "price"},
        ))
        self.assertTrue(any(event["type"] == "tool" for event in with_memory))
        isolated = await collect(service, AssistantRequest(conversation_id="two", message="那它風險呢？"))
        self.assertEqual([event["type"] for event in isolated][-1], "clarification")
        self.assertEqual(market.calls, ["2330"])

    async def test_history_is_bounded_and_is_not_used_as_market_tool_result(self):
        gemini = FakeGemini()
        service = make_service(gemini=gemini, max_history=2)
        history = [{"role": "user" if index % 2 == 0 else "assistant", "text": f"old-{index}"} for index in range(8)]
        await collect(service, AssistantRequest(conversation_id="bounded", message="ROE 是什麼？", history=history))
        prompt = gemini.prompts[0]
        self.assertIn("old-7", prompt)
        self.assertIn("old-6", prompt)
        self.assertNotIn("old-5", prompt)
        self.assertIn('"tool_results": []', prompt)

    async def test_general_knowledge_does_not_fuzzy_match_a_company(self):
        gemini = FakeGemini()
        events = await collect(make_service(gemini=gemini), AssistantRequest(
            conversation_id="knowledge",
            message="請用簡單方式解釋 ROE 是什麼，並舉一個生活化例子。",
        ))
        self.assertFalse(any(event["type"] == "clarification" for event in events))
        self.assertTrue(any(event["type"] == "done" for event in events))
        self.assertEqual(gemini.calls, 1)

    async def test_tool_answer_is_verified_before_any_delta_is_released(self):
        gemini = FakeGemini(text="2330 台積電收盤 999 元，來源 https://invented.example")
        events = await collect(make_service(gemini=gemini), AssistantRequest(
            conversation_id="verification", message="台積電目前股價多少？"
        ))
        answer = "".join(event.get("text", "") for event in events if event["type"] == "delta")
        self.assertNotIn("999", answer)
        self.assertNotIn("invented.example", answer)
        self.assertIn("收盤價 100.0 元", answer)
        done = next(event for event in events if event["type"] == "done")
        self.assertEqual(done["verification"], "replaced_with_verified_facts")

    async def test_claim_level_filter_keeps_independent_analysis_without_leaking_bad_claim(self):
        gemini = FakeGemini(text="2330 台積電收盤價為 999 元。需求改善可能形成支撐。")
        events = await collect(make_service(gemini=gemini), AssistantRequest(
            conversation_id="claim-level", message="台積電目前股價多少？"
        ))
        answer = "".join(event.get("text", "") for event in events if event["type"] == "delta")
        self.assertNotIn("999", answer)
        self.assertIn("需求改善可能形成支撐", answer)
        verification_index = next(index for index, event in enumerate(events) if event["type"] == "verification" and event["status"] != "checking")
        delta_index = next(index for index, event in enumerate(events) if event["type"] == "delta")
        self.assertLess(verification_index, delta_index)
        verification = events[verification_index]
        self.assertEqual(verification["status"], "claims_filtered")
        self.assertEqual(verification["claim_summary"]["rejected"], 1)
        self.assertNotIn("999", json.dumps(verification, ensure_ascii=False))
        self.assertEqual(next(event for event in events if event["type"] == "done")["verification"], "claims_filtered")

    async def test_bad_premise_also_removes_its_downstream_conclusion(self):
        gemini = FakeGemini(text="2330 台積電收盤價為 999 元。因此已突破壓力，建議追價。仍應留意景氣風險。")
        events = await collect(make_service(gemini=gemini), AssistantRequest(
            conversation_id="dependent-claim", message="台積電目前股價多少？"
        ))
        answer = "".join(event.get("text", "") for event in events if event["type"] == "delta")
        self.assertNotIn("999", answer)
        self.assertNotIn("建議追價", answer)
        self.assertIn("仍應留意景氣風險", answer)
        done = next(event for event in events if event["type"] == "done")
        self.assertEqual(done["claim_summary"]["dependent_rejected"], 1)

    async def test_interrupted_tool_answer_never_releases_unverified_buffer(self):
        events = await collect(make_service(gemini=FakeGemini("interrupted")), AssistantRequest(
            conversation_id="buffer-interrupted", message="台積電目前股價多少？"
        ))
        self.assertFalse(any(event["type"] == "delta" for event in events))
        error = next(event for event in events if event["type"] == "error")
        self.assertEqual(error["code"], "stream_interrupted")

    async def test_verified_tool_answer_keeps_matching_numbers_dates_and_varied_wording(self):
        answers = (
            "2330 台積電在 2026 年 10 月 8 日的收盤價是 100 元。",
            "截至 2026/10/8，2330 台積電官方日資料顯示收盤 100 元。",
        )
        for index, answer in enumerate(answers):
            with self.subTest(answer=answer):
                events = await collect(make_service(gemini=FakeGemini(text=answer)), AssistantRequest(
                    conversation_id=f"wording-{index}", message="台積電目前股價多少？"
                ))
                text = "".join(event.get("text", "") for event in events if event["type"] == "delta")
                self.assertEqual(text, answer)
                self.assertEqual(next(event for event in events if event["type"] == "done")["verification"], "verified")

    async def test_two_stock_comparison_uses_only_explicit_longest_names(self):
        market = FakeMarket()
        events = await collect(make_service(market=market), AssistantRequest(
            conversation_id="compare", message="比較台積電和聯發科股價"
        ))
        self.assertEqual(market.calls, ["2330", "2454"])
        done = next(event for event in events if event["type"] == "done")
        self.assertEqual(done["tool_count"], 2)
        self.assertFalse(any(event["type"] == "clarification" for event in events))

    async def test_source_failure_names_missing_data_without_calling_model(self):
        gemini = FakeGemini()
        events = await collect(make_service(gemini=gemini, market=FakeMarket(fail=True)), AssistantRequest(
            conversation_id="source-failure", message="台積電目前股價多少？"
        ))
        text = "".join(event.get("text", "") for event in events if event["type"] == "delta")
        self.assertIn("資料來源目前無法取得", text)
        self.assertIn("無法提供或比較相關數字", text)
        self.assertEqual(gemini.calls, 0)
        self.assertEqual(next(event for event in events if event["type"] == "done")["verification"], "source_missing")

    async def test_quota_timeout_and_interruption_do_not_retry_or_fallback(self):
        for mode, code in (("quota", "quota_exceeded"), ("timeout", "timeout"), ("interrupted", "stream_interrupted")):
            with self.subTest(mode=mode):
                gemini = FakeGemini(mode)
                events = await collect(make_service(gemini=gemini), AssistantRequest(conversation_id=mode, message="ROE 是什麼？"))
                error = next(event for event in events if event["type"] == "error")
                self.assertEqual(error["code"], code)
                self.assertEqual(gemini.calls, 1)
                self.assertNotIn("示範回答", "".join(event.get("text", "") for event in events))

    async def test_explicit_full_research_hands_off_without_assistant_model_call(self):
        gemini = FakeGemini()
        events = await collect(make_service(gemini=gemini), AssistantRequest(
            conversation_id="research", message="請幫我建立台積電完整研究"
        ))
        handoff = next(event for event in events if event["type"] == "research_handoff")
        self.assertEqual(handoff["symbols"], ["2330"])
        self.assertEqual(gemini.calls, 0)


class FakeStreamingService:
    async def stream(self, _payload):
        yield {"type": "delta", "text": "測試"}
        yield {"type": "done", "memory": {}, "usage": {}, "model": "test", "tool_count": 0}


class AssistantApiTests(unittest.TestCase):
    def test_sse_api_routes_investment_decision_through_real_p0_service(self):
        enabled = SimpleNamespace(gemini_api_key="fixture-key", missing_optional_settings=[])
        service = make_service(gemini=FakeGemini())
        with patch("backend.app.main.settings", enabled), patch("backend.app.main.assistant", service), TestClient(app) as client:
            response = client.post("/api/assistant/stream", json={
                "conversation_id": "api-p0", "message": "環球晶現在值得買嗎？",
            })
            self.assertEqual(response.status_code, 200)
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            understanding = next(event["data"] for event in events if event["type"] == "understanding")
            plan = next(event["data"] for event in events if event["type"] == "tool_plan")
            self.assertEqual(understanding["intent"], "investment_decision")
            self.assertEqual([call["name"] for call in plan["calls"]], ["market_snapshot"])
            self.assertEqual(plan["calls"][0]["scope"], "full")
            self.assertTrue(any(event["type"] == "done" for event in events))

    def test_sse_endpoint_and_missing_key(self):
        enabled = SimpleNamespace(gemini_api_key="fixture-key", missing_optional_settings=[])
        with patch("backend.app.main.settings", enabled), patch("backend.app.main.assistant", FakeStreamingService()), TestClient(app) as client:
            response = client.post("/api/assistant/stream", json={"conversation_id": "api-test", "message": "hello"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
            self.assertIn('"type": "delta"', response.text)
            self.assertIn('"type": "done"', response.text)
        with patch("backend.app.main.settings", SimpleNamespace(gemini_api_key=None, missing_optional_settings=[])), TestClient(app) as client:
            response = client.post("/api/assistant/stream", json={"conversation_id": "api-test", "message": "hello"})
            self.assertEqual(response.status_code, 503)
            self.assertIn("GEMINI_API_KEY", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()


class VerifiedFallbackTextTests(unittest.TestCase):
    def test_history_fallback_uses_readable_labels(self):
        from backend.app.services.assistant import AssistantService
        text = AssistantService._verified_tool_answer([{
            "tool": "price_history", "symbol": "5483", "status": "completed",
            "data": {"metrics": {
                "observations": 125, "period_start": "2026-05-07", "period_end": "2026-11-06",
                "period_return_pct": -4.93, "average_volume_shares": 23414917, "latest_close": 144.5,
            }},
        }], "general")
        self.assertIn("區間報酬 -4.93%", text)
        self.assertIn("平均每日成交量 23,414,917 股", text)
        self.assertNotIn("_", text)
        self.assertNotIn("observations", text)


class EventQuestionRoutingTests(unittest.TestCase):
    def test_explain_question_goes_to_ai_but_yes_no_uses_shortcut(self):
        from backend.app.services.assistant import EVENT_EXPLAIN_PATTERN, EVENT_PATTERN
        explain = "2330 台積電 發布公告「董事會決議辦理限制員工權利新股收回註銷減資事宜」，這類公告通常代表什麼？投資人要注意哪些事？"
        self.assertTrue(EVENT_PATTERN.search(explain) and EVENT_EXPLAIN_PATTERN.search(explain))
        self.assertFalse(EVENT_EXPLAIN_PATTERN.search("台積電最近有減資嗎？"))
