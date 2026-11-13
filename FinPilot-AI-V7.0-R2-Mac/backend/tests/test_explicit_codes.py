import unittest

from backend.app.services.input_understanding import _explicit_codes, _intent
from backend.app.services.market import explicit_symbols_from_query


class ExplicitCodeTests(unittest.TestCase):
    def test_letter_suffixed_etf_codes(self):
        self.assertEqual(_explicit_codes("請比較 0050、00981A 的報酬"), ["0050", "00981A"])
        self.assertEqual(_explicit_codes("00631l 和 00679b"), ["00631L", "00679B"])
        self.assertEqual(_explicit_codes("00981Ａ"), ["00981A"])

    def test_market_search_keeps_letter_suffix(self):
        self.assertEqual(explicit_symbols_from_query("00981a"), ["00981A"])
        self.assertEqual(explicit_symbols_from_query("研究 2330，驗證日期 2026-10-08"), ["2330"])

    def test_plain_codes_and_prices_unchanged(self):
        self.assertEqual(_explicit_codes("2330tsmc 目標 1200元"), ["2330"])
        self.assertEqual(_explicit_codes("2026年 看 2454"), ["2454"])

    def test_amounts_in_wan_are_not_stock_codes(self):
        self.assertEqual(_explicit_codes("20 年後想存到 1000 萬，每月投入 10000 元"), [])

    def test_savings_plan_is_knowledge_not_target_price(self):
        intent, signals = _intent("我想存到 1000 萬，每月投入 10000 元，計畫合理嗎", [])
        self.assertEqual((intent, signals), ("explain", ["personal_finance_planning"]))
        self.assertNotEqual(_intent("每月投入 5000 買 0050 好嗎", [])[1], ["personal_finance_planning"])
