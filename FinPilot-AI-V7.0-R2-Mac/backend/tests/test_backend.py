from __future__ import annotations

import asyncio

import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ["FINPILOT_SKIP_DOTENV"] = "1"
os.environ["FINPILOT_STARTUP_SOURCE_CHECK"] = "false"

import httpx
from fastapi.testclient import TestClient

from backend.app.core.config import load_settings
from backend.app.core.http_client import ResilientHttpClient, UpstreamError
from backend.app.main import app, settings, upstream_error_handler
from backend.app.core.models import CompanyProfile, HealthResult, InputUnderstandingRequest, MarketQuote, SourceMetadata
from backend.app.core.normalization import clean_text, parse_number, parse_roc_date
from backend.app.providers.tpex import TPExProvider
from backend.app.providers.twse import TWSEProvider
from backend.app.services.market import MarketService, explicit_symbols_from_query
from backend.app.services.input_understanding import InputUnderstandingService
from backend.run import browser_url, main as run_main


class FakeHttp:
    def __init__(self, values):
        self.values = values

    async def get_json(self, _source, url, **_kwargs):
        return self.values[url]

    def provenance(self, _url, _params=None):
        return {"data_status": "fixture"}


def metadata(source="test"):
    return SourceMetadata(source=source, source_url="https://example.test/source", raw_source="test fixture")


class FakeUniverseExchange:
    def __init__(self, quotes):
        self.rows = quotes

    async def quotes(self):
        return self.rows

    async def companies(self):
        return []


class FakeCompanyExchange:
    def __init__(self, companies=None, error=None, quotes=None):
        self.rows = companies or []
        self.error = error
        self.quote_rows = quotes or []

    async def companies(self):
        if self.error:
            raise self.error
        return self.rows

    async def quotes(self):
        return self.quote_rows


def company(symbol, name, short_name, market="TWSE"):
    return CompanyProfile(symbol=symbol, name=name, short_name=short_name, market=market, metadata=metadata(f"{market} companies"))


class SequenceHttpClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    async def get(self, *_args, **_kwargs):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def aclose(self):
        return None


class NormalizationTests(unittest.TestCase):
    def test_zero_is_not_missing(self):
        self.assertEqual(parse_number("0"), 0.0)
        self.assertIsNone(parse_number("--"))
        self.assertIsNone(clean_text("－"))

    def test_roc_and_iso_dates(self):
        self.assertEqual(parse_roc_date("1151007"), date(2026, 10, 7))
        self.assertEqual(parse_roc_date("2026-10-07"), date(2026, 10, 7))


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_twse_quote_maps_units_and_market(self):
        settings = load_settings(read_dotenv=False)
        url = f"{settings.twse_base_url}/exchangeReport/STOCK_DAY_ALL"
        provider = TWSEProvider(settings, FakeHttp({url: [{
            "Date": "1151007", "Code": "2330", "Name": "台積電", "TradeVolume": "1,000",
            "TradeValue": "2500000", "OpeningPrice": "2500", "HighestPrice": "2510",
            "LowestPrice": "2490", "ClosingPrice": "2505", "Change": "+5", "Transaction": "100",
        }]}))
        quote = await provider.quote("2330")
        self.assertEqual(quote.market, "TWSE")
        self.assertEqual(quote.volume_shares, 1000)
        self.assertEqual(quote.close, 2505)

    async def test_market_summary_maps_official_daily_fields(self):
        from backend.app.main import _market_series
        settings = load_settings(read_dotenv=False)
        twse_url = f"{settings.twse_base_url}/exchangeReport/FMTQIK"
        tpex_url = f"{settings.tpex_base_url}/tpex_daily_trading_index"
        twse_rows = await TWSEProvider(settings, FakeHttp({twse_url: [
            {"Date": "1151105", "TradeValue": "1000", "TAIEX": "41574.72", "Change": "100"},
            {"Date": "1151106", "TradeValue": "1321071858650", "TAIEX": "39701.64", "Change": "-1873.08"},
        ]})).market_summary()
        tpex_rows = await TPExProvider(settings, FakeHttp({tpex_url: [
            {"Date": "1151106", "TradeAmount": "163831232335", "TPExIndex": "304.02", "Change": "-17.45"},
        ]})).market_summary()
        twse = _market_series(twse_rows)
        self.assertEqual((str(twse["date"]), twse["index"], twse["trade_value_twd"]), ("2026-11-06", 39701.64, 1321071858650))
        self.assertEqual(twse["change_pct"], -4.51)
        self.assertEqual([point["index"] for point in twse["history"]], [41574.72, 39701.64])
        self.assertEqual(_market_series(tpex_rows)["change_pct"], -5.43)
        # 來源失敗或沒有資料時不回傳預設值
        self.assertIsNone(_market_series(RuntimeError("down")))
        self.assertIsNone(_market_series([]))

    async def test_sector_ranking_excludes_aggregates_and_sorts(self):
        from backend.app.main import _sector_ranking
        settings = load_settings(read_dotenv=False)
        url = f"{settings.twse_base_url}/exchangeReport/MI_INDEX"
        rows = await TWSEProvider(settings, FakeHttp({url: [
            {"日期": "1151106", "指數": "寶島股價指數", "收盤指數": "43675.60", "漲跌百分比": "-4.56"},
            {"日期": "1151106", "指數": "電子工業類指數", "收盤指數": "2429.32", "漲跌百分比": "-4.93"},
            {"日期": "1151106", "指數": "半導體類指數", "收盤指數": "1328.81", "漲跌百分比": "-4.71"},
            {"日期": "1151106", "指數": "資訊服務類指數", "收盤指數": "300.00", "漲跌百分比": "3.37"},
            {"日期": "1151106", "指數": "其他類指數", "收盤指數": "--", "漲跌百分比": ""},
        ]})).sector_indexes()
        ranked = _sector_ranking(rows)
        self.assertEqual([row["name"] for row in ranked], ["資訊服務", "半導體"])
        self.assertEqual(str(ranked[0]["date"]), "2026-11-06")
        self.assertEqual(_sector_ranking(RuntimeError("down")), [])

    async def test_top_volume_applies_official_direction(self):
        settings = load_settings(read_dotenv=False)
        url = f"{settings.twse_base_url}/exchangeReport/MI_INDEX20"
        rows = await TWSEProvider(settings, FakeHttp({url: [
            {"Date": "20261106", "Rank": "1", "Code": "00685L", "Name": "群益臺灣加權正2", "TradeVolume": "1566489625", "ClosingPrice": "8.56", "Dir": "-", "Change": "0.94"},
            {"Date": "20261106", "Rank": "2", "Code": "2330", "Name": "台積電", "TradeVolume": "1000", "ClosingPrice": "110", "Dir": "+", "Change": "10"},
            {"Date": "20261106", "Rank": "3", "Code": "9999", "Name": "方向不明", "TradeVolume": "1000", "ClosingPrice": "10", "Dir": "X", "Change": "1"},
        ]})).top_volume()
        self.assertEqual(str(rows[0]["date"]), "2026-11-06")
        self.assertEqual((rows[0]["volume"], rows[0]["change_pct"]), (1566489625, -9.89))
        self.assertEqual(rows[1]["change_pct"], 10.0)
        self.assertIsNone(rows[2]["change_pct"])

    async def test_index_history_sorts_and_rejects_other_ids(self):
        from backend.app.providers.finmind import FinMindProvider
        class Http:
            async def get_json(self, *_args, **_kwargs):
                return {"status": 200, "data": [
                    {"date": "2026-11-06", "stock_id": "TAIEX", "close": 39701.64},
                    {"date": "2026-11-05", "stock_id": "TAIEX", "close": 41574.72},
                    {"date": "2026-11-04", "stock_id": "2330", "close": 1.0},
                    {"date": "2026-11-03", "stock_id": "TAIEX", "close": 0},
                ]}
        rows = await FinMindProvider(load_settings(read_dotenv=False), Http()).index_history("TAIEX", date(2026, 11, 1), date(2026, 11, 7))
        self.assertEqual([(row["date"], row["index"]) for row in rows], [("2026-11-05", 41574.72), ("2026-11-06", 39701.64)])

    def test_merge_news_dedupes_and_sorts_newest_first(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from backend.app.main import _merge_news
        def item(title, day, hour=0):
            when = datetime(2026, 11, day, hour, tzinfo=timezone.utc)
            return SimpleNamespace(title=title, published_at=when, model_dump=lambda mode: {"title": title, "published_at": when.isoformat()})
        merged = _merge_news([item("新", 9, 6), item("同一則", 6)], RuntimeError("down"), [item("同一則", 5), item("舊", 4)])
        self.assertEqual([row["title"] for row in merged], ["新", "同一則", "舊"])
        self.assertEqual(merged[0]["published_at"], "2026-11-09T14:00:00+08:00")

    def test_newer_quote_uses_history_only_when_it_is_newer(self):
        from types import SimpleNamespace
        from backend.app.services.market import MarketService
        class Quote(SimpleNamespace):
            def model_copy(self, update):
                return Quote(**{**self.__dict__, **update})
        def point(day, close):
            return SimpleNamespace(trade_date=date(2026, 11, day), open=close, high=close, low=close, close=close, change=None,
                                   volume_shares=1, trade_value_twd=2, transactions=3, metadata="finmind")
        quote = Quote(trade_date=date(2026, 11, 6), close=100.0, change=1.0, metadata="official")
        updated = MarketService.newer_quote(quote, [point(6, 100.0), point(9, 104.5)])
        self.assertEqual((updated.trade_date, updated.close, updated.change, updated.metadata), (date(2026, 11, 9), 104.5, 4.5, "finmind"))
        self.assertIs(MarketService.newer_quote(quote, [point(5, 90.0), point(6, 99.0)]), quote)
        self.assertIsNone(MarketService.newer_quote(None, [point(9, 1.0)]))

    def test_merge_newer_only_appends_dates_official_lacks(self):
        from backend.app.main import _market_series, _merge_newer
        official = [{"date": date(2026, 11, 6), "index": 39701.64, "change": -1873.08, "trade_value_twd": 1}]
        extra = [
            {"date": "2026-11-06", "index": 1.0, "change": 0.0, "trade_value_twd": 9},
            {"date": "2026-11-09", "index": 41661.7, "change": 1960.06, "trade_value_twd": 2},
        ]
        merged = _merge_newer(official, extra)
        self.assertEqual([row["index"] for row in merged], [39701.64, 41661.7])
        series = _market_series(merged)
        self.assertEqual((str(series["date"]), series["source"]), ("2026-11-09", "FinMind"))
        self.assertEqual(_market_series(official)["source"], "官方開放資料")
        # 任一來源失敗時用另一邊，不回傳預設值
        self.assertEqual(_merge_newer(official, RuntimeError("down")), official)
        self.assertEqual(_market_series(_merge_newer(RuntimeError("down"), extra))["index"], 41661.7)


    async def test_tpex_missing_price_stays_none(self):
        settings = load_settings(read_dotenv=False)
        url = f"{settings.tpex_base_url}/tpex_mainboard_quotes"
        provider = TPExProvider(settings, FakeHttp({url: [{
            "Date": "1151007", "SecuritiesCompanyCode": "6488", "CompanyName": "環球晶",
            "Close": "--", "Change": "0", "Open": "--", "High": "--", "Low": "--",
            "TradingShares": "0", "TransactionAmount": "0", "TransactionNumber": "0",
        }]}))
        quote = await provider.quote("6488")
        self.assertIsNone(quote.close)
        self.assertEqual(quote.change, 0)
        self.assertEqual(quote.volume_shares, 0)


class HttpRetryTests(unittest.IsolatedAsyncioTestCase):
    async def _failed_request(self, outcomes):
        client = ResilientHttpClient(timeout_seconds=1, retries=1, cache_ttl_seconds=0)
        await client._client.aclose()
        client._client = SequenceHttpClient(outcomes)
        with patch("backend.app.core.http_client.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(UpstreamError) as caught:
                await client.request("fixture", "https://example.test/data", min_interval=0)
        return caught.exception

    async def test_retry_preserves_429_and_5xx_status(self):
        request = httpx.Request("GET", "https://example.test/data")
        for status_code in (429, 500, 503):
            with self.subTest(status_code=status_code):
                responses = [
                    httpx.Response(status_code, headers={"Retry-After": "0"}, request=request),
                    httpx.Response(status_code, headers={"Retry-After": "0"}, request=request),
                ]
                error = await self._failed_request(responses)
                self.assertEqual(error.status_code, status_code)
                self.assertIn(str(status_code), str(error))
                api_response = await upstream_error_handler(None, error)
                self.assertEqual(api_response.status_code, status_code)
                self.assertEqual(json.loads(api_response.body)["upstream_status"], status_code)

    async def test_retry_keeps_timeout_distinct_from_http_failure(self):
        request = httpx.Request("GET", "https://example.test/data")
        error = await self._failed_request([
            httpx.ReadTimeout("timed out", request=request),
            httpx.ReadTimeout("timed out", request=request),
        ])
        self.assertIsNone(error.status_code)
        self.assertEqual(str(error), "連線逾時")
        api_response = await upstream_error_handler(None, error)
        self.assertEqual(api_response.status_code, 504)


class PickerApiTests(unittest.TestCase):
    def test_stock_code_extraction_ignores_dates_but_keeps_bare_code(self):
        self.assertEqual(explicit_symbols_from_query("研究 2330，驗證日期 2026-10-08"), ["2330"])
        self.assertEqual(explicit_symbols_from_query("研究 2330 在 2026 年的表現"), ["2330"])
        self.assertEqual(explicit_symbols_from_query("研究股票 2026"), ["2026"])

    def test_unknown_or_unrecognized_query_returns_no_unrelated_stocks(self):
        quotes = [
            MarketQuote(symbol="2330", name="台積電", market="TWSE", trade_date=date(2026, 10, 7), close=100, trade_value_twd=2000, metadata=metadata("TWSE")),
            MarketQuote(symbol="2454", name="聯發科", market="TWSE", trade_date=date(2026, 10, 7), close=80, trade_value_twd=1000, metadata=metadata("TWSE")),
        ]
        service = MarketService(
            twse=FakeUniverseExchange(quotes),
            tpex=FakeUniverseExchange([]),
            mops=object(),
            finmind=object(),
        )
        with patch("backend.app.main.market", service), TestClient(app) as client:
            cases = (
                ("請推薦不存在公司標的", {}),
                ("推薦 9999 公司標的", {}),
                ("推薦股票標的", {"product_type": "stock"}),
                ("不存在公司推薦標的", {"risk": "low"}),
                ("", {"industry": "不存在產業"}),
            )
            for query, conditions in cases:
                with self.subTest(query=query, conditions=conditions):
                    response = client.post("/api/stocks/select", json={"query": query, "limit": 8, **conditions})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["items"], [])

            recognized = client.post("/api/stocks/select", json={"query": "推薦台積電公司", "limit": 8})
            self.assertEqual(recognized.status_code, 200)
            self.assertEqual([item["symbol"] for item in recognized.json()["items"]], ["2330"])


class InputUnderstandingApiTests(unittest.TestCase):
    def setUp(self):
        listed = [
            company("2330", "台灣積體電路製造股份有限公司", "台積電"),
            company("2454", "聯發科技股份有限公司", "聯發科"),
            company("1459", "聯發紡織纖維股份有限公司", "聯發"),
            company("2327", "國巨股份有限公司", "國巨"),
        ]
        otc = [
            company("3374", "精材科技股份有限公司", "精材", "TPEX"),
            company("3535", "晶彩科技股份有限公司", "晶彩科", "TPEX"),
            company("5425", "台灣半導體股份有限公司", "台半", "TPEX"),
            company("6488", "環球晶圓股份有限公司", "環球晶", "TPEX"),
        ]
        etf_quotes = [
            MarketQuote(symbol="0050", name="元大台灣50", market="TWSE", trade_date=date(2026, 10, 8), close=60, metadata=metadata("TWSE quote")),
            MarketQuote(symbol="0056", name="元大高股息", market="TWSE", trade_date=date(2026, 10, 8), close=38, metadata=metadata("TWSE quote")),
            MarketQuote(symbol="00878", name="國泰永續高股息", market="TWSE", trade_date=date(2026, 10, 8), close=22, metadata=metadata("TWSE quote")),
            MarketQuote(symbol="00919", name="群益台灣精選高息", market="TWSE", trade_date=date(2026, 10, 8), close=24, metadata=metadata("TWSE quote")),
            MarketQuote(symbol="006208", name="富邦台50", market="TWSE", trade_date=date(2026, 10, 8), close=120, metadata=metadata("TWSE quote")),
            MarketQuote(symbol="00713", name="元大台灣高息低波", market="TWSE", trade_date=date(2026, 10, 8), close=52, metadata=metadata("TWSE quote")),
            MarketQuote(symbol="00891", name="中信關鍵半導體", market="TWSE", trade_date=date(2026, 10, 8), close=18, metadata=metadata("TWSE quote")),
            MarketQuote(symbol="00927", name="群益半導體收益", market="TWSE", trade_date=date(2026, 10, 8), close=20, metadata=metadata("TWSE quote")),
            MarketQuote(symbol="0052", name="富邦科技", market="TWSE", trade_date=date(2026, 10, 8), close=145, metadata=metadata("TWSE quote")),
        ]
        self.service = InputUnderstandingService(twse=FakeCompanyExchange(listed, quotes=etf_quotes), tpex=FakeCompanyExchange(otc))

    def test_company_subject_with_theme_words_is_single_company(self):
        # 公司簡稱開頭、只是提到產業：研究那家公司；問供應鏈有哪些公司仍是主題研究。
        run = lambda text: asyncio.run(self.service.understand(InputUnderstandingRequest(text=text, context="home")))
        single = run("台積電在 AI 伺服器的成長與風險")
        self.assertEqual(single.target_status, "recognized")
        self.assertEqual(single.selected_symbol, "2330")
        self.assertEqual(single.research_type, "single_company")
        chain = run("台積電供應鏈有哪些公司")
        self.assertEqual(chain.target_status, "not_required")
        self.assertEqual(chain.research_type, "industry_supply_chain")

    def test_direct_api_understands_exact_typo_ambiguous_periods_and_unknown(self):
        with patch("backend.app.main.input_understanding", self.service), TestClient(app) as client:
            cases = (
                ("幫我研究精材最近的表現", "recognized", "3374", "預設近 6 個月"),
                ("台機電最近三個月怎樣", "recognized", "2330", "近 3 個月"),
                ("精彩最近的表現", "ambiguous", None, "預設近 6 個月"),
                ("研究台積電近十二個月", "recognized", "2330", "近 1 年"),
                ("研究台積電在2026年的表現", "recognized", "2330", "2026 年"),
                ("聯發科呢？", "recognized", "2454", "預設近 6 個月"),
                ("請用簡單方式解釋 ROE 是什麼，並舉一個生活化例子。", "not_required", None, "預設近 6 個月"),
                ("請查看 台 積 電，近半年波動如何？", "recognized", "2330", "近 6 個月"),
                ("研究火星電力股份有限公司", "needs_confirmation", None, "預設近 6 個月"),
            )
            for text, status, symbol, period in cases:
                with self.subTest(text=text):
                    response = client.post("/api/input/understand", json={"text": text, "context": "research"})
                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual(body["raw_input"], text)
                    self.assertEqual(body["target_status"], status)
                    self.assertEqual(body["selected_symbol"], symbol)
                    self.assertEqual(body["historical_period"]["label"], period)

    def test_everyday_words_are_not_fuzzy_matched_to_stocks(self):
        # 測試 曾因拼音包含而對到 漢民測試系統；你好 曾以近似拼音對到 今皓／均豪。
        service = InputUnderstandingService(
            twse=FakeCompanyExchange([
                company("2330", "台灣積體電路製造股份有限公司", "台積電"),
                company("3011", "今皓實業股份有限公司", "今皓"),
            ]),
            tpex=FakeCompanyExchange([
                company("7856", "漢民測試系統股份有限公司", "漢測", "TPEX"),
                company("5443", "均豪精密工業股份有限公司", "均豪", "TPEX"),
                company("3374", "精材科技股份有限公司", "精材", "TPEX"),
                company("3535", "晶彩科技股份有限公司", "晶彩科", "TPEX"),
            ]),
        )
        # 直接呼叫服務，不經 HTTP，避免整批測試超過 API 每分鐘請求上限。
        cases = (
            ("測試", "assistant", "not_required", None),
            ("你好", "assistant", "not_required", None),
            ("我在測試api而已", "assistant", "not_required", None),
            # 真正的錯字修正與多候選仍保留
            ("台機電最近三個月怎樣", "assistant", "recognized", "2330"),
            ("精彩最近的表現", "assistant", "ambiguous", None),
            ("漢測", "assistant", "recognized", "7856"),
            # 正式研究找不到標的時仍要求確認
            ("研究火星電力股份有限公司", "research", "needs_confirmation", None),
        )
        for text, context, status, symbol in cases:
            with self.subTest(text=text, context=context):
                result = asyncio.run(service.understand(InputUnderstandingRequest(text=text, context=context)))
                self.assertEqual(result.target_status, status)
                self.assertEqual(result.selected_symbol, symbol)

    def test_homophone_of_longer_name_is_detected(self):
        from types import SimpleNamespace
        from backend.app.services.input_understanding import _homophone_of_longer_name
        profiles = [SimpleNamespace(symbol="2454", name="聯發科技股份有限公司", short_name="聯發科", english_name=None)]
        found = _homophone_of_longer_name("聯發客的風險", "聯發", profiles, "1459")
        self.assertEqual((found[0].symbol, found[1], found[2]), ("2454", "聯發科", "聯發客"))
        self.assertIsNone(_homophone_of_longer_name("聯發的風險", "聯發", profiles, "1459"))
        self.assertIsNone(_homophone_of_longer_name("聯發科的風險", "聯發", profiles, "1459"))

    def test_typed_part_finds_the_misspelled_name(self):
        from backend.app.services.input_understanding import _typed_part
        self.assertEqual(_typed_part("國劇投資", "國巨"), "國劇")

    def test_generic_word_is_not_treated_as_a_company_name(self):
        from backend.app.services.input_understanding import _target_fragment
        # 「值得」與個股「直得」同音，不能留在比對標的的文字裡。
        self.assertNotIn("值得", _target_fragment("有哪些值得比較的公司"))

    def test_official_list_failure_preserves_input_as_source_error(self):
        service = InputUnderstandingService(
            twse=FakeCompanyExchange(error=RuntimeError("TWSE unavailable")),
            tpex=FakeCompanyExchange(error=RuntimeError("TPEx unavailable")),
        )
        with patch("backend.app.main.input_understanding", service), TestClient(app) as client:
            response = client.post("/api/input/understand", json={"text": "研究未知公司"})
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["target_status"], "source_error")
            self.assertEqual(result["raw_input"], "研究未知公司")
            self.assertEqual(result["candidates"], [])
            knowledge = client.post("/api/input/understand", json={
                "text": "ETF 跟個股有什麼差別？", "context": "assistant",
            }).json()
            self.assertEqual(knowledge["intent"], "explain")
            self.assertEqual(knowledge["target_status"], "not_required")
            self.assertFalse(knowledge["requires_market_data"])

    def test_p0_investment_intents_and_price_hypothesis_are_structured(self):
        with patch("backend.app.main.input_understanding", self.service), TestClient(app) as client:
            cases = (
                ("環球晶現在值得買嗎？", "investment_decision", "6488"),
                ("國巨未來有機會漲回 1200 元嗎？", "target_price_scenario", "2327"),
                ("台積電目前合理價是多少？", "valuation", "2330"),
                ("環球晶近期有什麼利多和利空？", "risk_analysis", "6488"),
                ("講白話一點。", "rephrase", None),
                ("請建立台積電完整研究", "full_research", "2330"),
            )
            for text, intent, symbol in cases:
                with self.subTest(text=text):
                    body = client.post("/api/input/understand", json={"text": text, "context": "assistant"}).json()
                    self.assertEqual(body["intent"], intent)
                    self.assertEqual(body["selected_symbol"], symbol)
            target = client.post("/api/input/understand", json={
                "text": "國巨未來有機會漲回 1200 元嗎？", "context": "assistant",
            }).json()
            self.assertEqual(target["hypotheses"], [{
                "type": "price_target", "value": 1200.0, "unit": "TWD",
                "raw_text": "有機會漲回 1200 元", "source": "user", "conditional": True,
                "symbol": None,
            }])
            self.assertTrue(target["requires_market_data"])

    def test_theme_knowledge_and_vague_etf_requests_do_not_become_wrong_stock(self):
        with patch("backend.app.main.input_understanding", self.service), TestClient(app) as client:
            industry = client.post("/api/input/understand", json={
                "text": "台灣半導體產業有哪些值得研究的公司？", "context": "research",
            }).json()
            self.assertEqual(industry["target_status"], "not_required")
            self.assertIsNone(industry["selected_symbol"])
            self.assertIn("industry_or_theme_query", industry["classification_signals"])

            knowledge = client.post("/api/input/understand", json={
                "text": "ETF 跟個股差在哪？", "context": "assistant",
            }).json()
            self.assertEqual(knowledge["intent"], "explain")
            self.assertEqual(knowledge["target_status"], "not_required")
            self.assertFalse(knowledge["requires_market_data"])

            vague = client.post("/api/input/understand", json={
                "text": "分析3檔ETF", "context": "research",
            }).json()
            self.assertEqual(vague["target_status"], "recognized")
            self.assertIsNone(vague["selected_symbol"])
            self.assertEqual(vague["resolved_symbols"], ["0050", "0056", "00878"])
            self.assertIn("可修改的比較起點", vague["message"])
            self.assertIn("transparent_system_assumption", vague["classification_signals"])

    def test_natural_questions_use_direct_answers_defaults_or_only_necessary_clarification(self):
        with patch("backend.app.main.input_understanding", self.service), TestClient(app) as client:
            cases = (
                ("ETF 跟個股有什麼差別？", "explain", "not_required", [], "general_knowledge_question"),
                ("幫我分析三檔 ETF。", "compare", "recognized", ["0050", "0056", "00878"], "representative_etf_defaults"),
                ("分析台灣半導體產業。", "research", "not_required", [], "industry_or_theme_query"),
                ("分析台半 5425。", "research", "recognized", [], None),
                ("比較 0050、0056、00878。", "compare", "recognized", ["0050", "0056", "00878"], "explicit_multi_target"),
                ("最近有哪些值得關注的股票？", "screen", "not_required", [], "broad_market_discovery"),
                ("我想分析目前持有的股票。", "research", "needs_confirmation", [], "personal_portfolio_symbols_missing"),
                # 問「適合持有哪種」是問類型，要用偏好回答，不是要讀持股。
                ("分析我的個人化偏好推薦我可以持有哪種類型股票", "screen", "not_required", [], None),
                # 「我有 1000 塊」是預算不是目標價；新手怎麼買不需要先指定標的。
                ("我是投資新手，我有1000塊怎麼買", "unknown", "not_required", [], None),
                ("不是這三檔，換成其他 ETF。", "compare", "recognized", ["006208", "00713", "00919"], "replace_previous_selection"),
                ("分析三檔高股息 ETF，但沒有即時行情可用。", "compare", "recognized", ["0056", "00878", "00919"], "representative_etf_defaults"),
                ("精彩最近的表現", "research", "ambiguous", [], None),
            )
            for text, intent, status, resolved, signal in cases:
                with self.subTest(text=text):
                    body = client.post("/api/input/understand", json={"text": text, "context": "assistant"}).json()
                    self.assertEqual(body["intent"], intent)
                    self.assertEqual(body["target_status"], status)
                    self.assertEqual(body["resolved_symbols"], resolved)
                    self.assertNotEqual(body["intent"], "full_research")
                    if signal:
                        self.assertIn(signal, body["classification_signals"])
            exact = client.post("/api/input/understand", json={
                "text": "分析台半 5425。", "context": "assistant",
            }).json()
            self.assertEqual(exact["selected_symbol"], "5425")

    def test_industry_and_supply_chain_queries_never_enter_company_fuzzy_matching(self):
        cases = (
            "研究台灣被動元件的機會與主要風險",
            "分析台灣半導體產業",
            "分析 PCB 產業未來需求",
            "研究台灣 IC 載板產業",
            "分析 AI 伺服器散熱供應鏈",
            "分析矽光子技術相關產業",
            "研究記憶體產業景氣循環",
            "想了解國內光通訊供應鏈的需求與風險",
        )
        with patch("backend.app.main.input_understanding", self.service), TestClient(app) as client:
            for text in cases:
                with self.subTest(text=text):
                    body = client.post("/api/input/understand", json={"text": text, "context": "research"}).json()
                    self.assertEqual(body["research_type"], "industry_supply_chain")
                    self.assertEqual(body["target_status"], "not_required")
                    self.assertEqual(body["candidates"], [])
                    self.assertEqual(body["resolved_symbols"], [])
                    self.assertIsNone(body["selected_symbol"])
                    self.assertIn("industry_or_theme_query", body["classification_signals"])
                    self.assertNotIn("fuzzy", json.dumps(body, ensure_ascii=False))

            for text, symbol in (("分析台半 5425", "5425"), ("分析國巨 2327", "2327")):
                with self.subTest(text=text):
                    body = client.post("/api/input/understand", json={"text": text, "context": "research"}).json()
                    self.assertEqual(body["research_type"], "single_company")
                    self.assertEqual(body["selected_symbol"], symbol)

            comparison = client.post("/api/input/understand", json={
                "text": "比較台灣被動元件相關公司", "context": "research",
            }).json()
            self.assertEqual(comparison["research_type"], "industry_supply_chain")
            self.assertEqual(comparison["target_status"], "not_required")
            self.assertEqual(comparison["candidates"], [])

    def test_explicit_etf_codes_fall_back_to_official_quote_list(self):
        quotes = [
            MarketQuote(symbol="0050", name="元大台灣50", market="TWSE", trade_date=date(2026, 10, 8), close=60, metadata=metadata("TWSE quote")),
            MarketQuote(symbol="006208", name="富邦台50", market="TWSE", trade_date=date(2026, 10, 8), close=120, metadata=metadata("TWSE quote")),
        ]
        service = InputUnderstandingService(
            twse=FakeCompanyExchange([], quotes=quotes), tpex=FakeCompanyExchange([]),
        )
        with patch("backend.app.main.input_understanding", service), TestClient(app) as client:
            body = client.post("/api/input/understand", json={
                "text": "0050 跟 006208 哪個比較適合長期持有？", "context": "assistant",
            }).json()
            self.assertEqual(body["intent"], "compare")
            self.assertEqual(body["target_status"], "recognized")
            self.assertEqual({item["symbol"] for item in body["candidates"]}, {"0050", "006208"})
            self.assertEqual(body["resolved_symbols"], ["0050", "006208"])

    def test_duplicate_numeric_code_requires_confirmation_and_future_is_separate(self):
        duplicate = InputUnderstandingService(
            twse=FakeCompanyExchange([company("7777", "甲公司", "甲", "TWSE")]),
            tpex=FakeCompanyExchange([company("7777", "乙公司", "乙", "TPEX")]),
        )
        with patch("backend.app.main.input_understanding", duplicate), TestClient(app) as client:
            ambiguous = client.post("/api/input/understand", json={"text": "研究 7777 最近表現"}).json()
            self.assertEqual(ambiguous["target_status"], "ambiguous")
            self.assertIsNone(ambiguous["selected_symbol"])
            self.assertEqual(len(ambiguous["candidates"]), 2)

        with patch("backend.app.main.input_understanding", self.service), TestClient(app) as client:
            future = client.post("/api/input/understand", json={"text": "展望台積電未來一年，但歷史先看半年"}).json()
            self.assertEqual(future["target_status"], "recognized")
            self.assertEqual(future["historical_period"]["label"], "近 6 個月")
            self.assertEqual(future["outlook_period"]["kind"], "future_outlook")


class StartupConfigurationTests(unittest.TestCase):
    def test_local_defaults_allow_a_complete_research_while_render_keeps_demo_caps(self):
        with patch.dict(os.environ, {"FINPILOT_SKIP_DOTENV": "1"}, clear=True):
            settings = load_settings(read_dotenv=False)
        self.assertEqual(settings.visitor_daily_gemini_call_limit, 20)
        self.assertEqual(settings.visitor_daily_gemini_token_limit, 250000)
        render = (Path(__file__).resolve().parents[2] / "render.yaml").read_text(encoding="utf-8")
        self.assertRegex(render, r"FINPILOT_VISITOR_DAILY_GEMINI_CALL_LIMIT\s*\n\s*value:\s*\"6\"")
        self.assertRegex(render, r"FINPILOT_VISITOR_DAILY_GEMINI_TOKEN_LIMIT\s*\n\s*value:\s*\"60000\"")

    def test_dotenv_port_and_environment_override_use_same_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("FINPILOT_HOST=0.0.0.0\nFINPILOT_PORT=9123\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(env_file=env_file)
                self.assertEqual(settings.port, 9123)
                self.assertEqual(browser_url(settings), "http://127.0.0.1:9123")
            with patch.dict(os.environ, {"FINPILOT_PORT": "9234"}, clear=True):
                settings = load_settings(env_file=env_file)
                self.assertEqual(settings.port, 9234)
                self.assertEqual(browser_url(settings), "http://127.0.0.1:9234")

    def test_port_fallback_and_print_url(self):
        with patch.dict(os.environ, {"FINPILOT_SKIP_DOTENV": "1", "PORT": "9345"}, clear=True):
            settings = load_settings()
            self.assertEqual(settings.port, 9345)
            with patch("builtins.print") as output:
                run_main(["--print-url"])
            output.assert_called_once_with("http://127.0.0.1:9345")

    def test_start_command_installs_lock_and_uses_python_resolved_url(self):
        script = (Path(__file__).resolve().parents[2] / "start.command").read_text(encoding="utf-8")
        self.assertIn('FINPILOT_REQUIREMENTS="backend/requirements.lock"', script)
        self.assertIn('-m backend.run --print-url', script)
        self.assertNotIn("pip install -r backend/requirements.txt", script)


class StaticSecurityTests(unittest.TestCase):
    def test_static_server_never_exposes_secrets_or_backend(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/.env").status_code, 404)
            self.assertEqual(client.get("/backend/.env.example").status_code, 404)
            response = client.get("/api/health")
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["secrets_exposed"])

    def test_source_status_reports_configuration_without_external_requests(self):
        from backend.app import main as api
        with patch.dict(api.source_health_results, {}, clear=True), \
             patch.dict(api.http._observations, {}, clear=True), \
             patch.object(api.gemini, "last_connection", None), \
             patch("backend.app.main.twse.health", new=AsyncMock(side_effect=AssertionError("must not probe"))), TestClient(app) as client:
            response = client.get("/api/sources/status")
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual({row["source"] for row in rows}, {
            "Gemini", "FinMind", "TWSE", "TPEx", "MOPS", "官方新聞", "公司法說會", "官方估值與財務", "Shioaji",
        })
        self.assertTrue(all(row["connection_status"] in {"not_checked", "disabled", "fixture"} for row in rows))
        self.assertTrue(all("purpose" in row and "requires_api_key" in row for row in rows))
        self.assertFalse(any("api_key" in row or "token" in row for row in rows))

    def test_single_source_health_check_only_calls_requested_provider(self):
        result = HealthResult(source="TWSE", status="healthy", message="fixture")
        with patch("backend.app.main.settings", replace(settings, preview_fixture_mode=True)), \
             patch("backend.app.main.twse.health", new=AsyncMock(return_value=result)) as twse_health, \
             patch("backend.app.main.tpex.health", new=AsyncMock(side_effect=AssertionError("must not probe"))), \
             TestClient(app) as client:
            response = client.get("/api/sources/health", params={"source": "TWSE"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["source"], "TWSE")
        self.assertEqual(response.json()[0]["status"], "fixture")
        twse_health.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
