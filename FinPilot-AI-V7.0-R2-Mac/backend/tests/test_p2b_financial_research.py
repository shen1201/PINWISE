from __future__ import annotations

import os
import unittest
from datetime import date

os.environ["FINPILOT_SKIP_DOTENV"] = "1"

from backend.app.core.models import AssistantRequest, MarketQuote, PricePoint, SourceMetadata
from backend.app.services.market import MarketService
from backend.app.services.tool_router import ToolRouter
from backend.tests.test_assistant import FakeGemini, FakeIR, FakeMarket, collect, make_service


def metadata(*, stale=False):
    return SourceMetadata(
        source="fixture", source_url="https://example.test/source",
        raw_source="fixed public fixture", stale=stale,
    )


class FakeExchange:
    def __init__(self, quote=None):
        self.value = quote
        self.quote_calls = []

    async def quote(self, symbol):
        self.quote_calls.append(symbol)
        return self.value


class CountingFinMind:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def history(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if self.error:
            raise self.error
        return [
            PricePoint(symbol=symbol, trade_date=date(2026, 4, 9), close=90, metadata=metadata()),
            PricePoint(symbol=symbol, trade_date=date(2026, 10, 8), close=100, metadata=metadata()),
        ]


class CountingMops:
    def __init__(self):
        self.company_calls = []
        self.disclosure_calls = []

    async def company(self, symbol):
        self.company_calls.append(symbol)
        return None

    async def disclosures(self, symbol, **_kwargs):
        self.disclosure_calls.append(symbol)
        return []


class ToolPlanningTests(unittest.TestCase):
    def test_question_types_use_bounded_non_duplicate_plans(self):
        router = ToolRouter(max_calls=3)
        default_period = {"label": "預設近 6 個月", "defaulted": True}
        explicit_period = {"label": "近 1 年", "defaulted": False}

        price = router.plan(intent="price", symbols=["2330"], period=default_period, message="目前股價多少")
        self.assertEqual([(call.name, call.scope) for call in price.calls], [("market_snapshot", "quote")])

        decision = router.plan(intent="investment_decision", symbols=["6488"], period=default_period, message="值得買嗎")
        self.assertEqual([(call.name, call.scope) for call in decision.calls], [("market_snapshot", "full")])
        self.assertTrue(any("EPS" in gap for gap in decision.missing_capabilities))

        target_default = router.plan(intent="target_price_scenario", symbols=["2327"], period=default_period, message="漲回 1200 元嗎")
        self.assertEqual([call.name for call in target_default.calls], ["market_snapshot"])
        target_explicit = router.plan(intent="target_price_scenario", symbols=["2327"], period=explicit_period, message="近一年漲回 1200 元嗎")
        self.assertEqual([call.name for call in target_explicit.calls], ["market_snapshot", "price_history"])

        compare = router.plan(intent="compare", symbols=["0050", "006208"], period=default_period, message="哪個適合長期持有")
        self.assertEqual([(call.name, call.scope) for call in compare.calls], [
            ("market_snapshot", "market"), ("market_snapshot", "market"),
        ])
        self.assertTrue(any("追蹤誤差" in gap for gap in compare.missing_capabilities))

    def test_explicit_conference_question_uses_existing_ir_provider(self):
        router = ToolRouter(max_calls=3)
        plan = router.plan(
            intent="disclosure", symbols=["2330"], period={"defaulted": True},
            message="台積電近期有法說會嗎？",
        )
        self.assertEqual([call.name for call in plan.calls], ["investor_conferences"])


class ScopedSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_simple_quote_only_adds_bounded_price_lookup(self):
        quote = MarketQuote(
            symbol="2330", name="台積電", market="TWSE", trade_date=date(2026, 10, 8),
            close=100, metadata=metadata(),
        )
        twse, tpex = FakeExchange(quote), FakeExchange(None)
        finmind, mops = CountingFinMind(), CountingMops()
        service = MarketService(twse=twse, tpex=tpex, finmind=finmind, mops=mops)

        result = await service.snapshot("2330", scope="quote")
        self.assertEqual(result["capabilities"], ["market_snapshot"])
        self.assertEqual(result["quote"]["close"], 100.0)
        # 只問股價時，為了取得最新收盤，最多多查一次兩週內的日價；公告與公司資料仍不查。
        self.assertEqual(len(finmind.calls), 1)
        self.assertLessEqual((finmind.calls[0][2] - finmind.calls[0][1]).days, 14)
        self.assertEqual(mops.company_calls, [])
        self.assertEqual(mops.disclosure_calls, [])

    async def test_simple_quote_keeps_official_quote_when_history_fails(self):
        quote = MarketQuote(
            symbol="2330", name="台積電", market="TWSE", trade_date=date(2026, 10, 8),
            close=100, metadata=metadata(),
        )
        service = MarketService(twse=FakeExchange(quote), tpex=FakeExchange(None),
                                finmind=CountingFinMind(error=RuntimeError("down")), mops=CountingMops())
        result = await service.snapshot("2330", scope="quote")
        self.assertEqual((result["quote"]["close"], result["quote"]["trade_date"]), (100.0, "2026-10-08"))

    async def test_market_scope_degrades_when_history_fails_but_keeps_quote(self):
        quote = MarketQuote(
            symbol="2330", name="台積電", market="TWSE", trade_date=date(2026, 10, 8),
            close=100, metadata=metadata(),
        )
        service = MarketService(
            twse=FakeExchange(quote), tpex=FakeExchange(None),
            finmind=CountingFinMind(error=RuntimeError("429 rate limited")), mops=CountingMops(),
        )
        result = await service.snapshot("2330", scope="market")
        self.assertTrue(result["found"])
        self.assertEqual(result["capabilities"], ["market_snapshot"])
        self.assertEqual(result["errors"][0]["capability"], "price_history")


class AssistantResearchQualityTests(unittest.IsolatedAsyncioTestCase):
    async def test_target_scenario_has_calculation_conditions_and_explicit_gaps(self):
        gemini = FakeGemini(text=(
            "1200 元是使用者目標情境。從目前收盤價 80 元到目標 1200 元，"
            "程式計算需要上漲 1400%。這需要獲利改善支持，也要留意需求反轉風險。"
        ))
        events = await collect(make_service(gemini=gemini), AssistantRequest(
            conversation_id="p2b-target", message="國巨未來有機會漲回 1200 元嗎？",
        ))
        answer = "".join(event.get("text", "") for event in events if event["type"] == "delta")
        self.assertIn("使用者目標情境", answer)
        self.assertIn("1400%", answer)
        self.assertIn("獲利改善", answer)
        # 資料限制改由介面顯示在回答下方，不寫進回答本文。
        self.assertNotIn("資料限制", answer)
        notes = next(event for event in events if event["type"] == "done")["notes"]
        self.assertTrue(any(note.startswith("目前無法取得") for note in notes))
        self.assertNotIn("1200 元是合理價", answer)
        done = next(event for event in events if event["type"] == "done")
        self.assertEqual(done["verification"], "verified")

    async def test_etf_comparison_discloses_unsupported_fee_and_component_fields(self):
        gemini = FakeGemini(text="兩檔目前只能依相同口徑日行情比較；長期選擇仍要看成本與追蹤品質。")
        events = await collect(make_service(gemini=gemini), AssistantRequest(
            conversation_id="p2b-etf", message="0050 跟 006208 哪個適合長期持有？",
        ))
        answer = "".join(event.get("text", "") for event in events if event["type"] == "delta")
        # 能力缺口改由介面顯示在回答下方；比較數字由後端產生表格。
        notes = " ".join(next(event for event in events if event["type"] == "done")["notes"])
        self.assertIn("ETF 長期適配仍缺成分", notes)
        self.assertIn("追蹤誤差", notes)
        self.assertIn("| 0050 | 80（10/08） |", answer)
        self.assertIn("| 006208 | 80（10/08） |", answer)
        payload = gemini.prompts[0]
        self.assertIn('"dates_aligned": true', payload)
        self.assertIn('"depth": "comparative"', payload)

    async def test_explicit_conference_question_calls_ir_only(self):
        ir = FakeIR(rows=[])
        events = await collect(make_service(ir=ir), AssistantRequest(
            conversation_id="p2b-ir", message="台積電近期有法說會公告嗎？",
        ))
        plan = next(event["data"] for event in events if event["type"] == "tool_plan")
        self.assertEqual([call["name"] for call in plan["calls"]], ["investor_conferences"])
        self.assertEqual(ir.calls, ["2330"])

    async def test_stale_quote_requires_date_or_stale_disclosure(self):
        events = await collect(make_service(
            market=FakeMarket(stale=True), gemini=FakeGemini(text="台積電收盤價為 100 元。"),
        ), AssistantRequest(conversation_id="p2b-stale", message="台積電目前股價多少？"))
        done = next(event for event in events if event["type"] == "done")
        reasons = done["claim_summary"]["claims"][0]["reason_codes"]
        self.assertIn("stale_evidence_not_disclosed", reasons)
        answer = "".join(event.get("text", "") for event in events if event["type"] == "delta")
        self.assertIn("2026-10-08", answer)
        self.assertIn("可能過期", answer)


if __name__ == "__main__":
    unittest.main()
