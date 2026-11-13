from __future__ import annotations

import os
import unittest

os.environ["FINPILOT_SKIP_DOTENV"] = "1"

from backend.app.services.assistant_claims import validate_assistant_answer


SOURCE = {
    "source": "fixture",
    "source_url": "https://evidence.example/2330",
    "raw_source": "isolated fixture",
    "fetched_at": "2026-10-09T00:00:00Z",
}


def snapshot(*, status="completed"):
    if status != "completed":
        return {
            "tool": "market_snapshot", "symbol": "2330", "status": status,
            "error_code": "unavailable", "error": "資料來源目前無法取得",
        }
    return {
        "tool": "market_snapshot", "symbol": "2330", "status": "completed",
        "data": {
            "symbol": "2330", "name": "台積電", "market": "TWSE", "as_of": "2026-10-08",
            "quote": {
                "symbol": "2330", "close": 100.0, "open": 98.0, "high": 102.0,
                "low": 97.0, "change": 2.0, "volume": 1200000,
                "trade_date": "2026-10-08", "metadata": SOURCE,
            },
            "company": {"symbol": "2330", "name": "台積電", "metadata": SOURCE},
            "metrics": {}, "events": [], "errors": [],
        },
    }


def history():
    return {
        "tool": "price_history", "symbol": "2330", "status": "completed",
        "data": {
            "symbol": "2330",
            "period": {"label": "近 6 個月", "start": "2026-04-09", "end": "2026-10-09"},
            "metrics": {
                "period_return_pct": 8.5, "annualized_volatility_pct": 20.0,
                "max_drawdown_pct": -12.0, "period_start": "2026-04-09",
                "period_end": "2026-10-08", "latest_close": 100.0,
            },
            "points": [],
        },
    }


def failed_company():
    return {
        "tool": "company_profile", "symbol": "2330", "status": "failed",
        "error_code": "upstream_error", "error": "資料來源暫時錯誤（HTTP 503）",
    }


def context():
    return {"historical_observation_period": {"label": "近 6 個月"}}


def validate(text, *, tools=None, hypotheses=None, previous=None):
    return validate_assistant_answer(
        text,
        tools=tools or [snapshot(), history()],
        hypotheses=hypotheses or [],
        research_context=context(),
        fallback="程式整理的已驗證摘要。",
        previous_answer=previous,
    )


class AssistantClaimValidationTests(unittest.TestCase):
    def test_correct_price_and_valid_analysis_are_kept(self):
        result = validate("2330 台積電在 2026 年 10 月 8 日收盤價為 100 元。需求改善可能形成支撐。")
        self.assertEqual(result.status, "verified")
        self.assertIn("收盤價為 100 元", result.text)
        self.assertIn("可能形成支撐", result.text)

    def test_removed_sentence_never_leaves_stray_markup_or_empty_heading(self):
        text = (
            "**2330 台積電收盤價為 999 元。需求改善可能形成支撐。**\n\n"
            "*   **優點**\n    *   需求改善可能形成支撐。\n"
            "*   **適合誰**\n    *   2330 收盤價為 888 元。\n"
        )
        result = validate(text)
        self.assertEqual(result.status, "claims_filtered")
        self.assertNotIn("999", result.text)
        self.assertNotIn("適合誰", result.text)
        for line in result.text.splitlines():
            self.assertNotEqual(line.strip(), "**")
            self.assertEqual(line.count("**") % 2, 0, line)

    def test_list_tool_data_and_converted_units_do_not_break_validation(self):
        # 公告工具回傳清單（以前會讓回答中斷）；股→張、元→億的換算是同一個數字。
        events = {"tool": "material_events", "symbol": "2330", "status": "completed",
                  "data": [{"title": "董事會決議", "published_at": "2026-11-10T08:00:00Z", "metadata": SOURCE}]}
        result = validate("2330 有一則董事會決議公告。", tools=[snapshot(), events])
        self.assertIn(result.status, {"verified", "claims_filtered"})
        thresholds = validate("2330 的年化波動超過 1%，風險仍需留意。")
        self.assertNotIn("unsupported_number", str(thresholds.claim_summary))

    def test_two_company_sentence_binds_each_number_to_nearest_company(self):
        def snap(code, name, close):
            return {"tool": "market_snapshot", "symbol": code, "status": "completed", "data": {
                "symbol": code, "name": name, "as_of": "2026-11-10",
                "quote": {"symbol": code, "close": close, "trade_date": "2026-11-10", "metadata": SOURCE}}}
        tools = [snap("1815", "富喬", 128.0), snap("6488", "環球晶", 612.0)]
        good = validate("富喬收盤價為 128 元，環球晶收盤價為 612 元。\n\n* **環球晶**\n  * 收盤價為 612 元。", tools=tools)
        self.assertEqual(good.status, "verified")
        swapped = validate("富喬收盤價為 612 元，環球晶收盤價為 128 元。風險仍需留意。", tools=tools)
        self.assertNotIn("612", swapped.text)

    def test_wrong_price_removes_only_affected_claim(self):
        result = validate("2330 台積電收盤價為 999 元。需求改善可能形成支撐。")
        self.assertEqual(result.status, "claims_filtered")
        self.assertNotIn("999", result.text)
        self.assertIn("可能形成支撐", result.text)
        self.assertIn("1 項數字或日期未通過資料核對", result.notes[0])
        self.assertNotIn("未通過", result.text)

    def test_correct_number_bound_to_wrong_stock_is_rejected(self):
        result = validate("2454 聯發科收盤價為 100 元。台積電的需求展望仍可討論。")
        self.assertEqual(result.status, "claims_filtered")
        self.assertNotIn("2454", result.text)
        self.assertNotIn("聯發科收盤價", result.text)
        self.assertIn("台積電的需求展望", result.text)
        codes = result.claim_summary["claims"][0]["reason_codes"]
        self.assertIn("symbol_mismatch", codes)

        name_only = validate("聯發科收盤價為 100 元。台積電的需求展望仍可討論。")
        self.assertEqual(name_only.status, "claims_filtered")
        self.assertNotIn("聯發科收盤價", name_only.text)
        self.assertIn("company_name_mismatch", name_only.claim_summary["claims"][0]["reason_codes"])

    def test_wrong_date_or_unit_is_rejected(self):
        # 10/09 exists as fetch time / history query end, but is not the quote's trade date.
        wrong_date = validate("2330 台積電在 2026 年 10 月 9 日收盤價為 100 元。")
        self.assertEqual(wrong_date.status, "replaced_with_verified_facts")
        self.assertIn("date_mismatch", wrong_date.claim_summary["claims"][0]["reason_codes"])
        wrong_unit = validate("2330 台積電在 2026 年 10 月 8 日收盤價為 100 美元。")
        self.assertEqual(wrong_unit.status, "replaced_with_verified_facts")
        self.assertIn("unit_mismatch", wrong_unit.claim_summary["claims"][0]["reason_codes"])

    def test_user_hypothesis_is_not_market_evidence(self):
        hypotheses = [{
            "type": "price_scenario", "value": 900.0, "unit": "TWD", "source": "user",
            "conditional": True, "symbol": "2330", "raw_text": "如果跌到 900 元",
        }]
        accepted = validate("900 元是使用者提出的假設價格，不是已確認行情。", hypotheses=hypotheses)
        self.assertEqual(accepted.status, "verified")
        misuse = validate("2330 台積電目前股價為 900 元。", hypotheses=hypotheses)
        self.assertEqual(misuse.status, "replaced_with_verified_facts")
        self.assertNotIn("目前股價為 900", misuse.text)
        self.assertIn("hypothesis_as_market_fact", misuse.claim_summary["claims"][0]["reason_codes"])

    def test_partial_source_failure_only_removes_dependent_company_claim(self):
        result = validate(
            "2330 台積電公司資料顯示資本額為 999 元。2330 台積電收盤價為 100 元。",
            tools=[snapshot(), failed_company()],
        )
        self.assertEqual(result.status, "claims_filtered")
        self.assertNotIn("資本額為 999", result.text)
        self.assertIn("收盤價為 100 元", result.text)
        self.assertIn("required_source_missing", result.claim_summary["claims"][0]["reason_codes"])

    def test_unverified_url_is_removed_but_known_source_can_remain(self):
        result = validate(
            "可參考 https://invented.example/report 。官方來源為 https://evidence.example/2330 。"
        )
        self.assertEqual(result.status, "claims_filtered")
        self.assertNotIn("invented.example", result.text)
        self.assertIn("https://evidence.example/2330", result.text)

    def test_incomplete_plain_analysis_is_preserved(self):
        result = validate("台積電需求若改善，營運可能受益")
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.text, "台積電需求若改善，營運可能受益")

    def test_wrong_period_is_rejected(self):
        result = validate("2330 台積電近 1 年報酬率為 8.5%。")
        self.assertEqual(result.status, "replaced_with_verified_facts")
        self.assertIn("period_mismatch", result.claim_summary["claims"][0]["reason_codes"])

    def test_dependent_conclusion_is_removed_with_bad_premise(self):
        result = validate("2330 台積電收盤價為 999 元。因此已突破壓力，建議追價。另需留意景氣風險。")
        self.assertEqual(result.status, "claims_filtered")
        self.assertNotIn("999", result.text)
        self.assertNotIn("建議追價", result.text)
        self.assertIn("另需留意景氣風險", result.text)
        self.assertEqual(result.claim_summary["dependent_rejected"], 1)

    def test_rejected_audit_does_not_echo_bad_value_or_url(self):
        result = validate("2330 台積電收盤價為 999 元，來源 https://invented.example 。")
        audit = str(result.claim_summary)
        self.assertNotIn("999", audit)
        self.assertNotIn("invented.example", audit)
        self.assertTrue(result.claim_summary["claims"][0]["reason_codes"])

    def test_multiple_bad_claims_use_one_notice_and_keep_valid_analysis(self):
        result = validate(
            "2330 台積電收盤價為 999 元。2330 台積電年化波動為 88%。"
            "需求若改善，營運可能受益；但仍需留意景氣循環。"
        )
        self.assertEqual(result.status, "claims_filtered")
        self.assertNotIn("999", result.text)
        self.assertNotIn("88", result.text)
        self.assertIn("需求若改善", result.text)
        # 核對結果不再寫進回答本文，改成一則給介面顯示的說明。
        self.assertNotIn("資料檢核", result.text)
        self.assertEqual(len(result.notes), 1)
        self.assertIn("2 項", result.notes[0])
        self.assertNotIn("【未驗證", result.text)

    def test_lead_in_sentence_is_removed_with_its_rejected_content(self):
        result = validate(
            "台積電的整體表現偏弱。\n依據 2026 年 10 月 08 日的交易日資料：\n"
            "2330 台積電收盤價為 999 元。\n\n需求若改善，營運可能受益。"
        )
        self.assertEqual(result.status, "claims_filtered")
        self.assertNotIn("交易日資料：", result.text)
        self.assertIn("需求若改善", result.text)

    def test_note_about_removed_numbers_is_removed(self):
        result = validate(
            "2330 台積電收盤價為 999 元。\n\n（註：以上數據為特定歷史區間之計算結果）\n\n需求若改善，營運可能受益。"
        )
        self.assertNotIn("以上數據", result.text)
        self.assertIn("需求若改善", result.text)

    def test_table_without_remaining_rows_is_removed(self):
        result = validate(
            "兩者差異在波動。\n\n| 指標 | 2330 |\n|---|---:|\n| 收盤價 | 999 元 |\n\n需求若改善，營運可能受益。"
        )
        self.assertNotIn("| 指標", result.text)
        self.assertIn("需求若改善", result.text)

    def test_stale_history_rows_do_not_mark_current_quote_stale(self):
        stale = dict(SOURCE, stale=True)
        item = snapshot()
        item["data"]["history"] = [{"trade_date": "2026-09-01", "close": 90.0, "metadata": stale}]
        result = validate("2330 台積電收盤價為 100 元。", tools=[item, history()])
        self.assertEqual(result.status, "verified")

    def test_history_only_supports_close_and_period_extremes(self):
        # 只有歷史日價時，收盤價、期間高低點與交易日可由歷史資料支持。
        item = history()
        item["data"]["metrics"].update({"period_high": 120.0, "period_low": 90.0})
        result = validate(
            "在 2026-10-08 收盤價為 100 元，期間最高曾達 120 TWD，顯示股價波動明顯。",
            tools=[item],
        )
        self.assertEqual(result.status, "verified")
        # 查詢區間的結束日（10/09）不是交易日，仍不接受。
        wrong = validate("2330 台積電在 2026 年 10 月 9 日收盤價為 100 元。", tools=[item])
        self.assertNotEqual(wrong.status, "verified")

    def test_heading_with_all_content_removed_is_dropped(self):
        result = validate("需求若改善，營運可能受益。\n\n**優點**\n2330 台積電收盤價為 999 元。\n\n**適合誰**\n長期投資人。")
        self.assertNotIn("優點", result.text)
        self.assertIn("適合誰", result.text)

    def test_real_answers_that_were_wrongly_rejected(self):
        # 中美晶實際回答中曾被誤刪的句子：正數搭配「下跌」、句首一般詞被當公司名、平均成交量。
        item = {
            "tool": "price_history", "symbol": "5483", "status": "completed",
            "data": {
                "symbol": "5483",
                "period": {"label": "近 6 個月", "start": "2026-05-07", "end": "2026-11-07"},
                "metrics": {
                    "period_start": "2026-05-07", "period_end": "2026-11-06",
                    "period_return_pct": -4.93, "annualized_volatility_pct": 77.37,
                    "max_drawdown_pct": -48.02, "average_volume_shares": 23414917,
                    "period_high": 278.0, "period_low": 135.0, "latest_close": 144.5,
                },
                "points": [],
            },
        }
        for sentence in (
            "中美晶（5483）截至 2026 年 11 月 6 日的收盤價為 144.5 新台幣，期間小幅下跌 4.93%。",
            "最大回檔幅度達到 48.02%，年化波動率則約為 77.37%，顯示這段期間股價波動相當劇烈。",
            "*   近期收盤價已接近波段相對低位，需留意下檔支撐力道。",
            "*   年化波動率與最大回檔幅度偏高，顯示短線價格變化劇烈。",
            "平均每日成交量約為 23,414,917 股。",
        ):
            with self.subTest(sentence=sentence):
                result = validate(sentence, tools=[item])
                self.assertEqual(result.status, "verified", result.claim_summary["claims"])
        # 方向寫反（「上漲」配上負值的絕對值）仍要擋下。
        wrong = validate("中美晶期間上漲 4.93%。", tools=[item])
        self.assertNotEqual(wrong.status, "verified")

    def test_orphan_headings_do_not_prevent_safe_fallback(self):
        result = validate("## 最新行情\n2330 台積電收盤價為 999 元。\n## 技術面\n因此建議追價。")
        self.assertEqual(result.status, "replaced_with_verified_facts")
        self.assertEqual(result.text, "程式整理的已驗證摘要。")
        self.assertNotIn("999", result.text)


if __name__ == "__main__":
    unittest.main()
