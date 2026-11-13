from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.app.core.models import CompanyProfile, MarketQuote, PickerRequest, PricePoint, ResearchRequest, ResearchResponse, SourceMetadata
from backend.app.services.analytics import price_metrics
from backend.app.services.market import MarketService
from backend.app.services.research import ResearchExecutionError, ResearchService, research_date_range
from backend.app.services.research_jobs import ResearchJobManager
from backend.app.providers.gemini import GeminiProvider


def metadata(source="test"):
    return SourceMetadata(source=source, source_url="https://example.test/source", raw_source="test fixture")


class FakeExchange:
    def __init__(self, quote=None):
        self.value = quote

    async def quote(self, _symbol):
        return self.value


class FakeMops:
    async def company(self, _symbol):
        return None

    async def disclosures(self, _symbol=None, limit=20):
        return []


class FakeFinMind:
    def __init__(self, history=None, error=None):
        self.rows = history or []
        self.error = error
        self.calls = []

    async def history(self, *args):
        self.calls.append(args)
        if self.error:
            raise self.error
        return self.rows


class FakeNews:
    async def items(self, limit=20):
        return []


class FakeIR:
    async def conferences(self, _symbol=None, limit=20):
        return []


class FakeMarket:
    def __init__(self, symbols, industry_symbols=None):
        self.symbols = symbols
        self.industry_symbols = list(symbols if industry_symbols is None else industry_symbols)
        self.industry_calls = []

    async def resolve_symbols(self, *_args, **_kwargs):
        return self.symbols

    async def resolve_industry_scope(self, topic, limit=5):
        self.industry_calls.append((topic, limit))
        return {
            "topic": topic, "symbols": self.industry_symbols[:limit], "industry_codes": ["28"],
            "selection_basis": "official_exchange_industry_code_then_daily_trade_value",
            "limitations": ["交易所產業分類較廣，仍需核對產品關聯。"],
        }


class FakeUniverseExchange:
    def __init__(self, quotes):
        self.rows = quotes

    async def quotes(self):
        return self.rows

    async def companies(self):
        return []


class FakePickerFinMind:
    async def history(self, symbol, *_args):
        closes = [100, 100.1, 100.2, 100.3] if symbol == "1111" else [100, 160, 80, 170]
        return [
            PricePoint(
                symbol=symbol,
                market="TWSE",
                trade_date=date(2026, 10, index + 1),
                close=close,
                volume_shares=1000,
                metadata=metadata("FinMind"),
            )
            for index, close in enumerate(closes)
        ]


class FakeGemini:
    def __init__(self, mode="ok", key="test-key"):
        self.mode = mode
        self.settings = SimpleNamespace(gemini_api_key=key, gemini_model="test-model")
        self.prompts = []

    async def generate_research(self, _prompt):
        self.prompts.append(_prompt)
        if self.mode == "quota":
            raise RuntimeError("429 quota exceeded")
        if self.mode == "timeout":
            raise asyncio.TimeoutError()
        if self.mode == "hallucinated_claims":
            return {
                "summary": "2330 預估上漲99.99%，來源 https://invented.example/report",
                "risks": ["2330 的期間報酬為 11.11%", "2454 預估成長 88%"],
                "candidates": ["2330", "9999"],
                "evidence_notes": ["https://invented.example/report"],
                "invalidation_conditions": ["跌幅達 77%"],
                "limitations": ["仍需核對資料"],
                "_usage": {"total_token_count": 42},
            }
        if self.mode == "swapped_metrics":
            return {
                "summary": "2330 的期間報酬 11.11%，年化波動 11.11%。",
                "risks": ["風險一"], "candidates": ["2330"], "evidence_notes": [],
                "invalidation_conditions": ["條件一"], "limitations": [], "_usage": {},
            }
        return {
            "summary": "依可用資料完成測試摘要。",
            "risks": ["風險一", "風險二", "風險三"],
            "candidates": ["2330", "9999"],
            "evidence_notes": ["測試"],
            "invalidation_conditions": ["條件一", "條件二", "條件三"],
            "limitations": ["測試來源有限"],
            "_usage": {"total_token_count": 42},
        }


def research_service(*, symbols=("2330",), gemini_mode="ok", key="test-key", history_error=None):
    quote = MarketQuote(symbol="2330", name="台積電", market="TWSE", trade_date=date(2026, 10, 7), close=100, metadata=metadata("TWSE"))
    history = [
        PricePoint(symbol="2330", market="TWSE", trade_date=date(2026, 10, 1), close=90, volume_shares=1000, metadata=metadata("FinMind")),
        PricePoint(symbol="2330", market="TWSE", trade_date=date(2026, 10, 7), close=100, volume_shares=2000, metadata=metadata("FinMind")),
    ]
    twse = FakeExchange(quote)
    tpex = FakeExchange(None)
    mops = FakeMops()
    finmind = FakeFinMind(history, history_error)
    return ResearchService(
        twse=twse, tpex=tpex, mops=mops, finmind=finmind,
        news=FakeNews(), ir=FakeIR(), gemini=FakeGemini(gemini_mode, key),
        market=FakeMarket(list(symbols)),
    )


class AnalyticsTests(unittest.TestCase):
    def test_price_metrics_flag_split_without_changing_values(self):
        prices = [(1, 300), (2, 310), (3, 10), (4, 11)]
        rows = [PricePoint(symbol="00685L", trade_date=date(2026, 1, day), close=close, volume_shares=1, metadata=metadata()) for day, close in prices]
        result = price_metrics(rows)
        self.assertEqual(result["suspected_split_dates"], ["2026-01-03"])
        self.assertEqual(result["period_low"], 10)
        limit_moves = [PricePoint(symbol="2330", trade_date=date(2026, 1, day), close=close, volume_shares=1, metadata=metadata()) for day, close in [(1, 100), (2, 90), (3, 99)]]
        self.assertEqual(price_metrics(limit_moves)["suspected_split_dates"], [])

    def test_price_metrics_are_calculated_not_generated(self):
        rows = [
            PricePoint(symbol="2330", trade_date=date(2026, 1, 1), close=100, volume_shares=0, metadata=metadata()),
            PricePoint(symbol="2330", trade_date=date(2026, 1, 2), close=90, volume_shares=100, metadata=metadata()),
            PricePoint(symbol="2330", trade_date=date(2026, 1, 3), close=110, volume_shares=200, metadata=metadata()),
        ]
        result = price_metrics(rows)
        self.assertEqual(result["period_return_pct"], 10.0)
        self.assertEqual(result["max_drawdown_pct"], -10.0)
        self.assertEqual(result["average_volume_shares"], 100)


class MarketServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_risk_filter_uses_calculated_volatility(self):
        quotes = [
            MarketQuote(symbol="1111", name="低波動", market="TWSE", trade_date=date(2026, 10, 7), close=100.3, trade_value_twd=2000, metadata=metadata("TWSE")),
            MarketQuote(symbol="2222", name="高波動", market="TWSE", trade_date=date(2026, 10, 7), close=170, trade_value_twd=3000, metadata=metadata("TWSE")),
        ]
        service = MarketService(
            twse=FakeUniverseExchange(quotes),
            tpex=FakeUniverseExchange([]),
            mops=FakeMops(),
            finmind=FakePickerFinMind(),
        )
        result = await service.select(PickerRequest(query="台股", risk="low", period="3m", limit=10))
        self.assertEqual([item["symbol"] for item in result], ["1111"])
        self.assertLess(result[0]["metrics"]["annualized_volatility_pct"], 25)
        self.assertIn("年化波動度", result[0]["risk_method"])
        funnel: dict = {}
        none = await service.select(PickerRequest(query="台股", risk="medium", period="3m", limit=10), funnel)
        # 篩選過程：先符合 2 檔，波動檢查 2 檔，中等 0 檔；各等級的檔數用來建議改選哪一級。
        self.assertEqual(none, [])
        self.assertEqual((funnel["matched"], funnel["risk_checked"], funnel["risk_matched"]), (2, 2, 0))
        self.assertEqual(funnel["risk_level_counts"], {"low": 1, "medium": 0, "high": 1})
        self.assertEqual(funnel["returned"], 0)
        high = await service.select(PickerRequest(query="台股", risk="high", period="3m", limit=10))
        self.assertEqual([item["symbol"] for item in high], ["2222"])
        self.assertGreaterEqual(high[0]["metrics"]["annualized_volatility_pct"], 45)

    async def test_industry_query_excludes_unrelated_etfs(self):
        # 回報案例：「生技醫療產業有哪些值得研究的公司？」＋波動偏高，結果混入成交金額大的正二與主動 ETF。
        day = date(2026, 10, 7)
        quotes = [
            MarketQuote(symbol="00631L", name="元大台灣50正2", market="TWSE", trade_date=day, close=28.9, trade_value_twd=9000, metadata=metadata("TWSE")),
            MarketQuote(symbol="00981A", name="主動統一台股增長", market="TWSE", trade_date=day, close=23, trade_value_twd=8000, metadata=metadata("TWSE")),
            MarketQuote(symbol="00965", name="元大全球生技ETF", market="TWSE", trade_date=day, close=15, trade_value_twd=50, metadata=metadata("TWSE")),
            MarketQuote(symbol="2222", name="高波動生醫", market="TWSE", trade_date=day, close=170, trade_value_twd=3000, metadata=metadata("TWSE")),
        ]
        profile = CompanyProfile(symbol="2222", short_name="高波動生醫", market="TWSE", industry_code="22", metadata=metadata("TWSE"))

        class Companies(FakeUniverseExchange):
            async def companies(self):
                return [profile]

        service = MarketService(twse=Companies(quotes), tpex=FakeUniverseExchange([]), mops=FakeMops(), finmind=FakePickerFinMind())
        company = await service.select(PickerRequest(query="生技醫療產業有哪些值得研究的公司？", risk="high", limit=10))
        self.assertEqual([item["symbol"] for item in company], ["2222"])
        self.assertIn("生技", company[0]["selection_reason"])
        self.assertIn("年化波動", company[0]["selection_reason"])
        # 沒說「公司」時，只留名稱帶主題的 ETF。
        themed = await service.select(PickerRequest(query="生技醫療", limit=10))
        self.assertEqual([item["symbol"] for item in themed], ["2222", "00965"])


class RequestedCountTests(unittest.TestCase):
    def test_count_is_parsed_and_stripped_from_topic(self):
        from backend.app.services.input_understanding import requested_count, strip_count, _research_topic
        self.assertEqual(requested_count("分析三檔半導體產業"), 3)
        self.assertEqual(requested_count("研究 2 家 AI 伺服器公司"), 2)
        self.assertEqual(requested_count("比較兩支電動車股"), 2)
        self.assertEqual(requested_count("找十檔高股息"), 5)  # 上限 5
        self.assertIsNone(requested_count("研究台積電近 6 個月"))
        self.assertEqual(strip_count("三檔半導體產業"), "半導體產業")
        self.assertEqual(_research_topic("分析三檔半導體產業"), "半導體產業")


class ResearchServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_requested_horizon_resolves_to_actual_query_window(self):
        today = date(2026, 10, 8)
        self.assertEqual(research_date_range("近 3 個月", "", today=today), (date(2026, 7, 8), today, "近 3 個月", False))
        self.assertEqual(research_date_range("3–6 個月", "", today=today), (date(2026, 4, 8), today, "近 6 個月", False))
        self.assertEqual(research_date_range(None, "研究 2330", today=today), (date(2026, 4, 8), today, "預設近 6 個月", True))
        self.assertEqual(research_date_range(None, "研究台積電近十二個月", today=today), (date(2025, 10, 8), today, "近 1 年", False))
        self.assertEqual(research_date_range(None, "研究台積電在2026年的表現", today=today), (date(2026, 1, 1), today, "2026 年", False))

    async def test_requested_horizon_is_used_for_finmind_history(self):
        service = research_service()
        result = await service.run(ResearchRequest(query="研究 2330 台積電近三個月", horizon="近 3 個月"))
        _, requested_start, requested_end = service.finmind.calls[0]
        self.assertEqual((requested_start, requested_end), research_date_range("近 3 個月", "研究 2330 台積電近三個月")[:2])
        self.assertEqual(result.metrics["query_period"]["applied_horizon"], "近 3 個月")
        self.assertFalse(result.metrics["query_period"]["defaulted"])

    async def test_requested_count_limits_industry_scope(self):
        service = research_service()
        service.market = FakeMarket(["2330"], industry_symbols=["2330", "2454", "3443", "2408", "3711"])
        await service.run(ResearchRequest(query="分析三檔半導體產業", research_type="industry_supply_chain",
                                          research_topic="三檔半導體產業"))
        self.assertEqual(service.market.industry_calls[0], ("半導體產業", 3))

    async def test_normal_research_filters_candidates_and_keeps_usage(self):
        result = await research_service().run(ResearchRequest(query="研究 2330 台積電"))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.candidates, ["2330"])
        self.assertEqual(result.metrics["2330"]["period_return_pct"], 11.11)
        self.assertEqual(result.usage["total_token_count"], 42)
        self.assertTrue(any(event["phase"] == "validation" for event in result.trace))

    async def test_confirmed_scope_excludes_symbols_and_sends_focus(self):
        service = research_service(symbols=("2330", "2454"))
        result = await service.run(ResearchRequest(
            query="比較 2330 和 2454 的風險", symbols=["2330", "2454"],
            preferences={"excludedSymbols": ["2454"], "researchFocus": "財報與基本面"},
        ))
        self.assertEqual(result.candidates, ["2330"])
        self.assertNotIn("2454", result.metrics)
        self.assertIn("preferences.researchFocus", service.gemini.prompts[0])
        self.assertIn("財報與基本面", service.gemini.prompts[0])

    async def test_etf_research_runs_and_tells_model_not_to_guess_holdings(self):
        service = research_service()
        result = await service.run(ResearchRequest(query="研究 2330 的風險", symbols=["2330"], research_type="etf"))
        self.assertEqual(result.status, "completed")
        self.assertIn("不得推測成份股", service.gemini.prompts[0])

    async def test_unknown_symbol_stops_before_gemini(self):
        with self.assertRaisesRegex(ResearchExecutionError, "找不到") as caught:
            await research_service(symbols=()).run(ResearchRequest(query="研究不存在標的"))
        self.assertEqual(caught.exception.code, "unknown_symbol")

    async def test_industry_research_uses_official_scope_not_company_fuzzy_search(self):
        service = research_service()
        result = await service.run(ResearchRequest(
            query="研究台灣被動元件的機會與主要風險",
            research_type="industry_supply_chain", research_topic="台灣被動元件",
        ))
        self.assertEqual(service.market.industry_calls, [("台灣被動元件", 5)])
        self.assertEqual(result.candidates, ["2330"])
        self.assertEqual(result.metrics["industry_scope"]["selection_basis"],
                         "official_exchange_industry_code_then_daily_trade_value")
        self.assertIn('"research_type": "industry_supply_chain"', service.gemini.prompts[0])
        self.assertIn("交易所產業分類較廣", " ".join(result.limitations))

    async def test_unsupported_industry_scope_stops_without_gemini(self):
        service = research_service()
        service.market.industry_symbols = []
        with self.assertRaises(ResearchExecutionError) as caught:
            await service.run(ResearchRequest(
                query="研究尚無官方分類的新興主題",
                research_type="industry_supply_chain", research_topic="尚無官方分類的新興主題",
            ))
        self.assertEqual(caught.exception.code, "unsupported_industry_scope")
        self.assertEqual(service.gemini.prompts, [])

    async def test_missing_key_is_explicit(self):
        with self.assertRaises(ResearchExecutionError) as caught:
            await research_service(key=None).run(ResearchRequest(query="研究 2330 台積電"))
        self.assertEqual(caught.exception.code, "missing_api_key")

    async def test_missing_history_uses_quote_without_inventing_metrics(self):
        service = research_service(history_error=RuntimeError("history unavailable"))
        result = await service.run(ResearchRequest(query="研究 2330 台積電"))
        self.assertIsNone(result.metrics["2330"]["period_return_pct"])
        self.assertTrue(any(item["missing"] and "歷史日行情" in item["source"] for item in result.evidence))

    async def test_quota_and_timeout_have_distinct_errors(self):
        for mode, code in (("quota", "quota_exceeded"), ("timeout", "timeout")):
            with self.subTest(mode=mode), self.assertRaises(ResearchExecutionError) as caught:
                await research_service(gemini_mode=mode).run(ResearchRequest(query="研究 2330 台積電"))
            self.assertEqual(caught.exception.code, code)

    async def test_unverified_model_numbers_and_urls_are_not_reported_as_evidence(self):
        result = await research_service(gemini_mode="hallucinated_claims").run(
            ResearchRequest(query="研究 2330 台積電")
        )
        self.assertEqual(result.candidates, ["2330"])
        self.assertNotIn("99.99", result.summary)
        self.assertNotIn("invented.example", result.summary)
        self.assertFalse(any("2454" in risk or "88%" in risk for risk in result.risks))
        self.assertGreater(result.metrics["output_validation"]["rejected_claim_count"], 0)
        self.assertEqual(result.metrics["output_validation"]["model_urls_used_as_evidence"], 0)
        self.assertTrue(any("已從報告文字排除" in item for item in result.limitations))

    async def test_metric_number_must_match_symbol_metric_unit_and_period(self):
        result = await research_service(gemini_mode="swapped_metrics").run(ResearchRequest(query="研究 2330 台積電"))
        # 11.11 is a valid return value, but reusing it as volatility must reject
        # the entire model summary instead of merely checking number membership.
        self.assertFalse(result.metrics["output_validation"]["model_summary_accepted"])
        self.assertIn("期間報酬", result.summary)
        self.assertGreater(result.metrics["output_validation"]["rejected_claim_count"], 0)


class GeminiProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_research_disables_sdk_retries(self):
        settings = SimpleNamespace(
            gemini_api_key="test-key",
            gemini_model="test-model",
            request_timeout_seconds=12,
        )
        response = SimpleNamespace(
            text='{"summary":"ok","risks":[],"candidates":[],"evidence_notes":[],"invalidation_conditions":[],"limitations":[]}',
            usage_metadata=None,
        )
        client = Mock()
        client.models.generate_content.return_value = response
        with patch("backend.app.providers.gemini.genai.Client", return_value=client) as client_factory:
            result = await GeminiProvider(settings, Mock()).generate_research("test prompt")

        self.assertEqual(result["summary"], "ok")
        http_options = client_factory.call_args.kwargs["http_options"]
        self.assertEqual(http_options.retry_options.attempts, 1)
        self.assertEqual(http_options.timeout, 60000)

    async def test_busy_server_is_retried_once_but_quota_is_not(self):
        settings = SimpleNamespace(gemini_api_key="test-key", gemini_model="test-model", request_timeout_seconds=12)
        ok = SimpleNamespace(text='{"summary":"ok","risks":[],"candidates":[],"evidence_notes":[],"invalidation_conditions":[],"limitations":[]}', usage_metadata=None)

        def error(code):
            exc = RuntimeError("gemini error")
            exc.code = code
            return exc

        busy = Mock()
        busy.models.generate_content.side_effect = [error(503), ok]
        with patch("backend.app.providers.gemini.genai.Client", return_value=busy), \
                patch("backend.app.providers.gemini.RETRY_DELAY_SECONDS", 0):
            result = await GeminiProvider(settings, Mock()).generate_research("p")
        self.assertEqual(result["summary"], "ok")
        self.assertEqual(busy.models.generate_content.call_count, 2)

        quota = Mock()
        quota.models.generate_content.side_effect = [error(429), ok]
        with patch("backend.app.providers.gemini.genai.Client", return_value=quota), \
                patch("backend.app.providers.gemini.RETRY_DELAY_SECONDS", 0):
            with self.assertRaises(RuntimeError):
                await GeminiProvider(settings, Mock()).generate_research("p")
        self.assertEqual(quota.models.generate_content.call_count, 1)


class SlowFakeService:
    def __init__(self):
        self.gemini = SimpleNamespace(settings=SimpleNamespace(gemini_model="fake-model"))

    async def run(self, request, *, emit, checkpoint):
        await emit(id="source", sequence=1, phase="data", agent="Data Agent", action="測試呼叫", detail="執行中", source="fixture", status="started", progress=20, at="2026-10-08T00:00:00Z", duration_ms=None, attempt=1, metadata={}, demo=False)
        await asyncio.sleep(0.05)
        await checkpoint()
        await emit(id="done", sequence=2, phase="persistence", agent="Report Agent", action="保存", detail="完成", source="fixture", status="completed", progress=100, at="2026-10-08T00:00:01Z", duration_ms=1, attempt=1, metadata={}, demo=False)
        return ResearchResponse(query=request.query, summary="done", risks=["risk"], candidates=[], evidence=[], trace=[], model="fake-model")


class ResearchJobManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = ResearchJobManager(SlowFakeService(), Path(self.temp.name))

    async def asyncTearDown(self):
        tasks = list(self.manager.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.temp.cleanup()

    async def wait_terminal(self, job_id):
        for _ in range(100):
            job = await self.manager.get(job_id)
            if job.status in {"completed", "failed", "cancelled"}:
                return job
            await asyncio.sleep(0.01)
        self.fail("job did not finish")

    async def test_duplicate_submission_reuses_active_job(self):
        request = ResearchRequest(query="研究 2330")
        first = await self.manager.create(request)
        second = await self.manager.create(request)
        self.assertEqual(first.id, second.id)
        self.assertTrue(second.deduplicated)

    async def test_cancel_stops_at_boundary(self):
        job = await self.manager.create(ResearchRequest(query="研究 2330"))
        cancelled = await self.manager.cancel(job.id)
        # A very fast task may reach the safe boundary while cancel() is
        # persisting the request, so either truthful transitional state is OK.
        self.assertIn(cancelled.status, {"cancel_requested", "cancelled"})
        final = await self.wait_terminal(job.id)
        self.assertEqual(final.status, "cancelled")
        self.assertTrue(any(event.status == "cancelled" for event in final.events))

    async def test_pause_and_resume_at_boundary(self):
        job = await self.manager.create(ResearchRequest(query="研究 2330 暫停繼續"))
        paused_request = await self.manager.pause(job.id)
        self.assertIn(paused_request.status, {"pause_requested", "paused"})
        for _ in range(100):
            paused = await self.manager.get(job.id)
            if paused.status == "paused":
                break
            await asyncio.sleep(0.01)
        else:
            self.fail("job did not pause at a safe boundary")
        resumed = await self.manager.resume(job.id)
        self.assertEqual(resumed.status, "running")
        final = await self.wait_terminal(job.id)
        self.assertEqual(final.status, "completed")
        self.assertTrue(any(event.action == "研究繼續" for event in final.events))

    async def test_completed_job_can_be_reopened_from_disk(self):
        job = await self.manager.create(ResearchRequest(query="研究 2330"))
        final = await self.wait_terminal(job.id)
        reopened = ResearchJobManager(SlowFakeService(), Path(self.temp.name))
        loaded = await reopened.get(final.id)
        self.assertEqual(loaded.status, "completed")
        self.assertEqual(loaded.result.summary, "done")

    async def test_interrupted_job_is_marked_failed_after_restart(self):
        job = await self.manager.create(ResearchRequest(query="研究 2330 重啟"))
        task = self.manager.tasks[job.id]
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        reopened = ResearchJobManager(SlowFakeService(), Path(self.temp.name))
        loaded = await reopened.get(job.id)
        self.assertEqual(loaded.status, "failed")
        self.assertEqual(loaded.error["code"], "server_restarted")


if __name__ == "__main__":
    unittest.main()


class TwseCompaniesFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_broken_company_list_falls_back_to_snapshot_then_quotes(self):
        from backend.app.providers.twse import TWSEProvider

        row = {"公司代號": "2330", "公司名稱": "台灣積體電路製造股份有限公司", "公司簡稱": "台積電", "產業別": "24", "出表日期": "1151110"}
        quote_row = {"Code": "1101", "Name": "台泥", "Date": "1151110", "ClosingPrice": "30"}
        with tempfile.TemporaryDirectory() as folder:
            settings = SimpleNamespace(twse_base_url="https://twse.example", data_dir=Path(folder), stale_hours=48)
            http = Mock()
            http.provenance.return_value = {"fetched_at": "2026-11-10T00:00:00Z"}
            provider = TWSEProvider(settings, http)

            async def good(path):
                return [row] if "t187ap03_L" in path else [quote_row]

            async def broken(path):
                if "t187ap03_L" in path:
                    raise ValueError("上游回傳不是有效 JSON")
                return [quote_row]

            provider._rows = good
            self.assertEqual([c.short_name for c in await provider.companies()], ["台積電"])
            provider._rows = broken
            cached = await provider.companies()
            self.assertEqual([(c.short_name, c.industry_code, c.metadata.stale) for c in cached], [("台積電", "24", True)])
            (Path(folder) / "cache" / "twse_companies.json").unlink()
            self.assertEqual([c.short_name for c in await provider.companies()], ["台泥"])
