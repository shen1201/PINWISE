from __future__ import annotations

import os
import unittest
from datetime import date
from types import SimpleNamespace

os.environ["FINPILOT_SKIP_DOTENV"] = "1"

from backend.app.core.models import AIPickerRequest, CompanyProfile, FundamentalSnapshot, MarketQuote, PricePoint, SourceMetadata
from backend.app.providers.fundamentals import FundamentalsProvider
from backend.app.services.ai_picker import AIPickerService
from backend.app.services.research import _number_tokens, validated_sentences


def meta(source="test"):
    return SourceMetadata(source=source, source_url="https://example.test/source", raw_source="test fixture", data_status="real")


def quote(symbol, name, value, market="TWSE", close=100.0):
    return MarketQuote(symbol=symbol, name=name, market=market, trade_date=date(2026, 10, 14), close=close,
                       trade_value_twd=value, volume_shares=1000, metadata=meta())


def profile(symbol, code):
    return CompanyProfile(symbol=symbol, name=symbol, short_name=symbol, market="TWSE", industry_code=code, metadata=meta())


def snapshot(symbol, industry, **values):
    return FundamentalSnapshot(symbol=symbol, market="TWSE", industry_name=industry, valuation_date=date(2026, 10, 13),
                               metadata=meta(), **values)


class FakeMarket:
    async def universe(self):
        quotes = [
            quote("2330", "台積電", 50_000_000_000), quote("2454", "聯發科", 20_000_000_000),
            quote("2881", "富邦金", 3_000_000_000), quote("9999", "冷門股", 1_000_000),
            quote("5314", "世紀", 900_000_000), quote("0050", "元大台灣50", 40_000_000_000),
            quote("00631L", "元大台灣50正2", 30_000_000_000), quote("0056", "元大高股息", 10_000_000_000),
        ]
        profiles = {"2330": profile("2330", "24"), "2454": profile("2454", "24"), "2881": profile("2881", "17"),
                    "9999": profile("9999", "17"), "5314": profile("5314", "31")}
        return quotes, profiles


class FakeFundamentals:
    async def snapshots(self):
        return {
            "2330": snapshot("2330", "半導體業", pe_ratio=28.86, dividend_yield_pct=0.88, revenue_yoy_pct=54.65, eps_ytd=49.33),
            "2454": snapshot("2454", "半導體業", pe_ratio=14.2, dividend_yield_pct=4.5, revenue_yoy_pct=12.0, eps_ytd=30.1),
            "2881": snapshot("2881", "金融保險業", pe_ratio=9.5, dividend_yield_pct=6.1, revenue_yoy_pct=3.0, eps_ytd=6.2),
            "9999": snapshot("9999", "金融保險業", pe_ratio=5.0, dividend_yield_pct=9.0, eps_ytd=1.0),
            "5314": snapshot("5314", "其他電子業", dividend_yield_pct=119.77),
        }


class FakeFinMind:
    def __init__(self, volatility_by_symbol):
        self.volatility = volatility_by_symbol

    async def history(self, symbol, start, end):
        swing = self.volatility.get(symbol, 0.01)
        return [PricePoint(symbol=symbol, trade_date=date(2026, 9, day), close=100 * (1 + swing * (day % 2)),
                           metadata=meta("FinMind")) for day in range(1, 25)]


def service(volatility=None, gemini=None):
    return AIPickerService(market=FakeMarket(), fundamentals=FakeFundamentals(),
                           gemini=gemini or SimpleNamespace(available=False), finmind=FakeFinMind(volatility or {}))


class SentenceValidationTests(unittest.TestCase):
    def test_only_unsupported_sentences_are_removed(self):
        allowed = _number_tokens({"pe": 28.86, "yoy": 54.65})
        text, rejected, problems = validated_sentences("台積電本益比 28.86 倍。營收年增 54.65%。目標價 9999 元。", allowed)
        self.assertEqual(text, "台積電本益比 28.86 倍。營收年增 54.65%。")
        self.assertEqual(rejected, ["目標價 9999 元。"])
        self.assertTrue(problems)

    def test_all_rejected_returns_none(self):
        self.assertIsNone(validated_sentences("報酬 77%。", set())[0])


class FundamentalsParsingTests(unittest.IsolatedAsyncioTestCase):
    async def test_six_official_datasets_merge_by_symbol(self):
        rows = {
            "exchangeReport/BWIBBU_ALL": [{"Date": "1151013", "Code": "2330", "Name": "台積電", "PEratio": "28.86",
                                           "DividendYield": "0.88", "PBratio": "10.04"}],
            "opendata/t187ap05_L": [{"資料年月": "11509", "公司代號": "2330", "公司名稱": "台積電", "產業別": "半導體業",
                                     "營業收入-當月營收": "511857399", "營業收入-上月比較增減(%)": "-0.57",
                                     "營業收入-去年同月增減(%)": "54.6512", "累計營業收入-前期比較增減(%)": "41.11"}],
            "opendata/t187ap14_L": [{"年度": "115", "季別": "2", "公司代號": "2330", "產業別": "半導體業",
                                     "基本每股盈餘(元)": "49.33", "營業收入": "1000", "營業利益": "593"}],
            "tpex_mainboard_peratio_analysis": [{"Date": "1151014", "SecuritiesCompanyCode": "6488", "CompanyName": "環球晶",
                                                 "PriceEarningRatio": "0", "YieldRatio": "0.75", "PriceBookRatio": "5.04"}],
            "mopsfin_t187ap05_O": [],
        }

        class FakeHttp:
            async def get_json(self, source, url, **kwargs):
                key = next((path for path in rows if url.endswith(path)), None)
                if key is None:
                    raise RuntimeError("upstream down")
                return rows[key]

            def provenance(self, url):
                return {"data_status": "real"}

        settings = SimpleNamespace(twse_base_url="https://twse.test", tpex_base_url="https://tpex.test", stale_hours=72)
        provider = FundamentalsProvider(settings, FakeHttp())
        snapshots = await provider.snapshots()
        tsmc = snapshots["2330"]
        self.assertEqual((tsmc.pe_ratio, tsmc.dividend_yield_pct, tsmc.pb_ratio), (28.86, 0.88, 10.04))
        self.assertEqual((tsmc.revenue_month, tsmc.revenue_yoy_pct, tsmc.eps_ytd), ("2026-09", 54.65, 49.33))
        self.assertEqual((tsmc.eps_period, tsmc.operating_margin_pct), ("2026 年第 2 季累計", 59.3))
        self.assertIsNone(snapshots["6488"].pe_ratio, "交易所以 0 表示不適用，不可當成本益比 0")
        self.assertIn("TPEX earnings", provider.errors, "單一資料集失敗應記錄但不影響其他資料")


class AIPickerTests(unittest.IsolatedAsyncioTestCase):
    async def test_etf_query_filters_product_type_and_flags_leveraged_etf(self):
        result = await service().select(AIPickerRequest(query="etf推薦", limit=5, explain=False))
        symbols = [item["symbol"] for item in result["items"]]
        self.assertEqual(symbols, ["0050", "00631L", "0056"])
        leveraged = next(item for item in result["items"] if item["symbol"] == "00631L")
        self.assertTrue(any("槓桿" in reason for reason in leveraged["reasons"]))
        self.assertIn("ETF", [term["term"] for term in result["glossary"]])

    async def test_high_yield_excludes_illiquid_and_outlier_and_explains_with_real_values(self):
        result = await service().select(AIPickerRequest(query="幫我找殖利率高的股票", limit=5, explain=False))
        symbols = [item["symbol"] for item in result["items"]]
        self.assertEqual(symbols, ["2881", "2454"], "依殖利率排序；排除成交清淡的 9999 與 119.77% 異常值")
        self.assertTrue(any("殖利率 6.1%" in reason for reason in result["items"][0]["reasons"]))
        self.assertTrue(any("異常值" in stage["label"] for stage in result["funnel"]))

    async def test_industry_and_valuation_conditions_combine(self):
        result = await service().select(AIPickerRequest(query="本益比低的半導體股", limit=5, explain=False))
        self.assertEqual(result["plan"]["industries"], ["半導體業"])
        self.assertEqual([item["symbol"] for item in result["items"]], ["2454"])

    async def test_passive_components_use_reviewed_list_not_broad_industry(self):
        # 「被動元件」曾被對到整個電子零組件業（含台達電等）；應只用人工核對名單（國巨、華新科）。
        class PassiveMarket(FakeMarket):
            async def universe(self):
                quotes = [quote("2308", "台達電", 9_000_000_000), quote("2327", "國巨", 5_000_000_000),
                          quote("2492", "華新科", 1_000_000_000), quote("3037", "欣興", 8_000_000_000)]
                return quotes, {symbol: profile(symbol, "28") for symbol in ("2308", "2327", "2492", "3037")}

        picker = AIPickerService(market=PassiveMarket(), fundamentals=FakeFundamentals(),
                                 gemini=SimpleNamespace(available=False), finmind=FakeFinMind({}))
        result = await picker.select(AIPickerRequest(query="我想找被動元件", limit=5, explain=False))
        self.assertEqual(sorted(item["symbol"] for item in result["items"]), ["2327", "2492"])
        self.assertEqual(result["plan"]["industries"], [])

    async def test_unknown_terms_are_reported_not_silently_used(self):
        result = await service().select(AIPickerRequest(query="外資買超的元宇宙股", limit=5, explain=False))
        self.assertTrue(any("找不到" in note for note in result["plan"]["unsupported"]))

    async def test_volatility_relaxes_with_explicit_note_instead_of_empty(self):
        volatile = {symbol: 0.05 for symbol in ("2330", "2454", "2881", "0050", "00631L", "0056", "5314", "9999")}
        result = await service(volatility=volatile).select(AIPickerRequest(query="穩定的大型股", limit=3, explain=False))
        self.assertTrue(result["items"])
        self.assertIn("改列出波動最接近條件", result["plan"]["relaxed"])
        self.assertTrue(any("放寬後列入" in reason for reason in result["items"][0]["reasons"]))

    async def test_model_plan_is_validated_and_explanations_are_checked(self):
        class FakeGemini:
            available, is_fixture = True, False

            async def generate_json(self, prompt, *, operation, **kwargs):
                if operation == "picker_plan":
                    return {"product_type": "stock", "market": "all", "industries": ["半導體", "AI 概念"],
                            "name_keywords": [], "volatility": "any", "sort_by": "pe_ratio", "max_pe_ratio": 9999,
                            "interpretation": "找本益比較低的半導體股", "unsupported": []}
                return {"overall": "以本益比由低到高排序。保證會漲 50%。",
                        "items": [{"symbol": "2454", "explanation": "本益比 14.2 倍，低於條件。"},
                                  {"symbol": "0000", "explanation": "不在清單"}]}

        result = await service(gemini=FakeGemini()).select(AIPickerRequest(query="便宜的半導體", limit=5))
        self.assertEqual(result["plan"]["source"], "gemini")
        self.assertEqual(result["plan"]["max_pe_ratio"], 200, "模型給的數值須限制在合理範圍")
        self.assertTrue(any("AI 概念" in note for note in result["plan"]["unsupported"]))
        self.assertEqual(result["overall_explanation"], "以本益比由低到高排序。", "無法對應資料的句子被移除")
        explained = {item["symbol"]: item["explanation"] for item in result["items"]}
        self.assertEqual(explained["2454"], "本益比 14.2 倍，低於條件。")


if __name__ == "__main__":
    unittest.main()


class ResearchFundamentalsTests(unittest.IsolatedAsyncioTestCase):
    async def test_fundamentals_feed_metrics_and_watch_items_are_validated(self):
        from backend.app.core.models import ResearchRequest
        from backend.tests.test_research_workflow import research_service

        class Fundamentals:
            async def snapshot(self, symbol):
                return snapshot(symbol, "半導體業", pe_ratio=28.86, revenue_month="2026-09", revenue_yoy_pct=54.65,
                                eps_period="2026 年第 2 季累計", eps_ytd=49.33)

        service = research_service()
        service.fundamentals = Fundamentals()

        async def generate(prompt):
            service.gemini.prompts.append(prompt)
            return {"summary": "台積電 2026-09 月營收年增 54.65%，成長動能明確。外資目標價 2500 元。",
                    "risks": ["本益比 28.86 倍，評價不低"], "candidates": ["2330"], "evidence_notes": [],
                    "invalidation_conditions": ["月營收年增率轉負"], "limitations": [],
                    "watch_items": [{"symbol": "2330", "item": "下個月營收年增率是否維持兩位數", "why": "目前年增 54.65%"},
                                    {"symbol": "2330", "item": "法人目標價", "why": "目標價 2500 元"},
                                    {"symbol": "9999", "item": "不在研究範圍", "why": "不應保留"}],
                    "_usage": {}}

        service.gemini.generate_research = generate
        result = await service.run(ResearchRequest(query="研究 2330 台積電"))
        self.assertEqual(result.metrics["2330"]["revenue_yoy_pct"], 54.65)
        self.assertEqual(result.summary, "台積電 2026-09 月營收年增 54.65%，成長動能明確。", "只移除無證據的句子")
        self.assertEqual(result.watch_items, [{"symbol": "2330", "item": "下個月營收年增率是否維持兩位數", "why": "目前年增 54.65%"}])
        self.assertTrue(any(item["source"] == "2330 估值與財務" and not item["missing"] for item in result.evidence))
        self.assertEqual(result.metrics["output_validation"]["rejected_sentence_count"], 2)
        self.assertIn("watch_items", service.gemini.prompts[0])


class ChineseNumberTests(unittest.TestCase):
    def test_numbers_written_in_chinese_cannot_bypass_the_check(self):
        allowed = _number_tokens({"yield": 11.1})
        text, rejected, _ = validated_sentences("殖利率 11.1%。殖利率達百分之九十。股價漲了三十點五倍。只是一點點。", allowed)
        self.assertEqual(text, "殖利率 11.1%。只是一點點。")
        self.assertEqual(len(rejected), 2)


class StockOverviewEndpointTests(unittest.IsolatedAsyncioTestCase):
    # Calls the endpoint function directly so the shared per-visitor rate limiter is not consumed.
    async def test_latest_price_uses_newest_source_and_candles_are_returned(self):
        from unittest.mock import AsyncMock, patch
        from fastapi import HTTPException
        from backend.app import main as api

        history = [PricePoint(symbol="2330", trade_date=date(2026, 10, day), open=100, high=105, low=95,
                              close=close, volume_shares=1000, metadata=meta("FinMind"))
                   for day, close in ((13, 100.0), (14, 102.0))]
        official = quote("2330", "台積電", 1, close=100.0).model_copy(update={"trade_date": date(2026, 10, 13)})
        no_fundamentals = SimpleNamespace(snapshot=AsyncMock(return_value=None))
        with patch.object(api.twse, "quote", AsyncMock(return_value=official)), \
             patch.object(api.tpex, "quote", AsyncMock(return_value=None)), \
             patch.object(api.finmind, "history", AsyncMock(return_value=history)), \
             patch.object(api, "fundamentals", no_fundamentals):
            data = await api.stock_overview("2330", months=6)
        self.assertEqual(data["latest"], {"date": "2026-10-14", "close": 102.0, "change": 2.0,
                                          "source": "FinMind", "change_pct": 2.0})
        self.assertEqual(len(data["candles"]), 2)
        self.assertEqual(data["fundamentals"], {})
        with patch.object(api.twse, "quote", AsyncMock(return_value=None)), \
             patch.object(api.tpex, "quote", AsyncMock(return_value=None)), \
             patch.object(api.finmind, "history", AsyncMock(return_value=[])), \
             patch.object(api, "fundamentals", no_fundamentals):
            with self.assertRaises(HTTPException) as missing:
                await api.stock_overview("0000", months=6)
        self.assertEqual(missing.exception.status_code, 404)
