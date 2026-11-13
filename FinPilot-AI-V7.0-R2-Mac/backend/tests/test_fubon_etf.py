import unittest

from backend.app.providers.fubon_etf import FubonEtfProvider, parse_holdings, supported_symbols


def page(symbol="006208", rows=None, total="66.0000", date_text="資料日期：2026/11/09"):
    rows = rows if rows is not None else [
        ("2454", "聯發科", "6,759,042", "25,177,431,450", "6.0000"),
        ("2330", "台積電", "112,594,064", "251,647,733,040", "60.0000"),
    ]
    body = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td><td>{e}</td></tr>" for a, b, c, d, e in rows)
    return f"""<a href="Fund/Download.aspx?stkId={symbol}">檔案下載</a><a href="Assets.aspx?stkId=006208">x</a>
    <p>{date_text}</p>
    <table><tr><td>期貨代碼</td><td>期貨名稱</td><td>口數</td><td>金額</td><td>權重(%)</td></tr>
    <tr><td>WTX</td><td>期貨</td><td>1</td><td>1</td><td>0.2741</td></tr></table>
    <table><tr><td>股票代碼</td><td>股票名稱</td><td>股數</td><td>金額</td><td>權重(%)</td></tr>{body}
    <tr><td>股票合計</td><td></td><td></td><td>1</td><td>{total}</td></tr></table>"""


class Http:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    async def get_text(self, _source, _url, params=None, **_kwargs):
        key = (params or {}).get("stkId")
        self.calls.append(key)
        return self.pages[key]


class ParseTests(unittest.TestCase):
    def test_parses_stock_table_only_and_sorts_by_weight(self):
        result = parse_holdings(page(), "006208")
        self.assertEqual(result["as_of"], "2026-11-09")
        self.assertEqual([row["code"] for row in result["holdings"]], ["2330", "2454"])
        self.assertEqual(result["holdings"][0]["shares"], 112594064)
        self.assertEqual(result["stock_weight_total"], 66.0)

    def test_rejects_page_of_another_fund(self):
        # 未知代號時網站會回傳別檔基金
        self.assertIsNone(parse_holdings(page(symbol="00717"), "0050"))

    def test_rejects_when_weights_do_not_match_stated_total(self):
        self.assertIsNone(parse_holdings(page(total="90.0000"), "006208"))

    def test_rejects_missing_date_or_stock_table(self):
        self.assertIsNone(parse_holdings(page(date_text=""), "006208"))
        self.assertIsNone(parse_holdings('<a href="Download.aspx?stkId=00694B"></a><table><tr><td>債券代碼</td></tr></table>資料日期：2026/11/09', "00694B"))

    def test_supported_symbols(self):
        self.assertEqual(supported_symbols(page()), {"006208"})


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_never_requests_symbols_outside_official_list(self):
        http = Http({None: page()})
        provider = FubonEtfProvider(None, http)
        self.assertIsNone(await provider.holdings("0050"))
        self.assertIsNone(await provider.holdings("../evil"))
        self.assertEqual(http.calls, [None])

    async def test_returns_source_for_supported_symbol(self):
        http = Http({None: page(), "006208": page()})
        result = await FubonEtfProvider(None, http).holdings("006208")
        self.assertEqual((result["symbol"], result["issuer"]), ("006208", "富邦投信"))
        self.assertTrue(result["source_url"].endswith("stkId=006208"))


if __name__ == "__main__":
    unittest.main()
