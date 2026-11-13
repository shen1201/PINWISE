import io
import unittest
import zipfile
from types import SimpleNamespace

from backend.app.providers.etf_holdings import (
    CathayEtfProvider, EtfHoldingsService, FuhuaEtfProvider, parse_fuhua, parse_mega, parse_nomura, parse_sinopac, parse_taishin, parse_yuanta, read_xlsx_rows,
)


def yuanta(symbol="0050", stock=60.0):
    return ('<p>基金權重-股票</p><span>交易日期: 2026/11/09</span><script>window.__NUXT__=(function(a,b,c,d,e){return {weightData:{PCF:{fundid:e,fundname:"",markcd:a,nav:1}},FundWeights:{Summary:'
            '{code:e,name:"",stkvalues:' + str(stock) + ',futvalues:1,fundsize:100},StockWeights:[{code:b,ym:"",name:c,ename:d,weights:58,qty:10},'
            '{code:"2454",ym:"",name:"聯發]科",ename:d,weights:2,qty:5}],FutureWeights:[]}}}("0050","2330","台積電","TSMC","1066"));</script>')


def xlsx(title="復華台灣未來50（證劵代碼：00991A）"):
    strings = [title, "日期: 2026/11/09", "證券代號", "證券名稱", "股數", "金額", "權重(%)", "2330", "台灣積體", "4,200,000", "9,387,000,000", "15.833%"]
    cells = lambda ids: "".join(f'<x:c t="s"><x:v>{i}</x:v></x:c>' for i in ids)
    sheet = "".join(f"<x:row>{cells(ids)}</x:row>" for ids in ([0], [1], [2, 3, 4, 5, 6], [7, 8, 9, 10, 11]))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/sharedStrings.xml", "".join(f"<x:si><x:t>{s}</x:t></x:si>" for s in strings))
        book.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


class ParserTests(unittest.TestCase):
    def test_yuanta_resolves_embedded_values(self):
        day, rows = parse_yuanta(yuanta(), "0050")
        self.assertEqual(day, "2026-11-09")
        self.assertEqual([(r["code"], r["name"], r["weight"]) for r in rows], [("2330", "台積電", 58.0), ("2454", "聯發]科", 2.0)])

    def test_yuanta_rejects_other_fund_or_mismatched_total(self):
        self.assertIsNone(parse_yuanta(yuanta(), "0056"))
        self.assertIsNone(parse_yuanta(yuanta(stock=90.0), "0050"))

    def test_fuhua_excel(self):
        self.assertEqual(len(read_xlsx_rows(xlsx())), 4)
        day, rows = parse_fuhua(xlsx(), "00991A")
        self.assertEqual((day, rows[0]["code"], rows[0]["weight"]), ("2026-11-09", "2330", 15.833))
        self.assertIsNone(parse_fuhua(xlsx(), "00992A"))

    def test_nomura_checks_fund_and_columns(self):
        payload = {"Entries": {"FundID": "00935", "Data": {"FundAsset": {"NavDate": "2026/11/09"}, "Table": [
            {"TableTitle": "股票", "Columns": [{"Name": "股票代號"}, {"Name": "股票名稱"}, {"Name": "股數"}, {"Name": "權重(%)"}],
             "Rows": [["2330", "台灣積體電路製造", "7282000", "34.06"]]}]}}}
        day, rows = parse_nomura(payload, "00935")
        self.assertEqual((day, rows[0]["weight"]), ("2026-11-09", 34.06))
        self.assertIsNone(parse_nomura(payload, "00980A"))

    def test_taishin_identity_comes_from_heading_not_dropdown(self):
        page = ('<li title="00703">(00703) 台新MSCI中國</li><span>查詢日期</span><span>台新永續高息基金 (00936)</span>'
                '<table><tr><td>2026/11/9每基數申購總價金差額(元)</td></tr></table>'
                '<table><tr><th>代號</th><th>名稱</th><th>股數</th><th>持股權重</th></tr>'
                '<tr><td>5876 TT</td><td>上海商銀</td><td>4,364,290</td><td>6.0925%</td></tr></table>')
        day, rows = parse_taishin(page, "00936")
        self.assertEqual((day, rows[0]["code"], rows[0]["weight"]), ("2026-11-09", "5876", 6.0925))
        self.assertIsNone(parse_taishin(page, "00703"))

    def test_sinopac_needs_matching_fund_heading(self):
        page = ('<div>永豐台灣ESG（證劵代碼：00888）2026/11/10</div><div>資料日期：2026/11/09</div>'
                '<table><tr><th>證券代碼</th><th>證券名稱</th><th>股數</th><th>佔基金淨資產之權重(%)</th></tr>'
                '<tr><td>2330</td><td>台積電</td><td>3,001,773</td><td>31.19</td></tr></table>')
        day, rows = parse_sinopac(page, "00888")
        self.assertEqual((day, rows[0]["shares"], rows[0]["weight"]), ("2026-11-09", 3001773, 31.19))
        self.assertIsNone(parse_sinopac(page, "00410A"))

    def test_mega_uses_stock_tab_and_bloomberg_identity(self):
        page = ('<div class="etfin5-title">彭博代碼</div> <div class="etfin5-info"> 00911 TT Equity </div>資料來源：兆豐投信，2026/11/06'
                '<div id="fund_tab_2" data-tab="2" class="fund-name">股票</div><!-- pc --><div id="fund_content_list_2">'
                '<div>股票代號</div><div>持股權重</div><div class="fund-content">AMD_US</div><div class="fund-content">超微 </div>'
                '<div class="fund-content txt-right">1,000</div><div class="fund-content txt-right">9.50 %</div></div><!-- mobile -->')
        day, rows = parse_mega(page, "00911")
        self.assertEqual((day, rows[0]["code"], rows[0]["name"], rows[0]["weight"]), ("2026-11-06", "AMD_US", "超微", 9.5))
        self.assertIsNone(parse_mega(page, "00690"))


class Http:
    def __init__(self):
        self.calls = []

    async def get_json(self, _source, url, params=None, **_):
        self.calls.append(url.rsplit("/", 1)[1])
        if url.endswith("GetETFList"):
            return {"success": True, "result": [{"stockCode": "00878", "fundCode": "CN"}]}
        if url.endswith("GetETFAssets"):
            return {"success": True, "result": {"preDate": "2026/11/09"}}
        assert params == {"fundCode": "CN", "SearchDate": "2026/11/09"}
        return {"success": True, "result": [{"stockCode": "2891", "stockName": "中信金", "volumn": "968,404,000", "weights": "11.41"}]}


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_cathay_maps_symbol_and_uses_latest_date(self):
        result = await CathayEtfProvider(Http()).holdings("00878")
        self.assertEqual((result["as_of"], result["holdings"][0]["code"], result["holdings"][0]["shares"]), ("2026-11-09", "2891", 968404000))

    async def test_cathay_unknown_symbol_stops_after_list(self):
        http = Http()
        self.assertIsNone(await CathayEtfProvider(http).holdings("0050"))
        self.assertEqual(http.calls, ["GetETFList"])

    async def test_service_routes_by_official_fund_name(self):
        async def funds():
            return [{"code": "00878", "name": "國泰永續高股息ETF"}, {"code": "00713", "name": "統一台灣高息"}]
        service = EtfHoldingsService(Http(), funds, SimpleNamespace())
        self.assertEqual((await service.holdings("00878"))["issuer"], "國泰投信")
        self.assertIsNone(await service.holdings("00713"))
        self.assertIsNone(await service.holdings("2330"))

    async def test_service_skips_leveraged_and_shares_foreign_currency_class(self):
        async def funds():
            return [{"code": "00878", "name": "國泰永續高股息ETF"}, {"code": "00631L", "name": "元大台灣50正2"}]
        service = EtfHoldingsService(Http(), funds, SimpleNamespace())
        self.assertIsNone(await service.holdings("00631L"))
        self.assertEqual((await service.holdings("00878K"))["symbol"], "00878K")

    async def test_service_tries_each_issuer_for_funds_missing_from_list(self):
        async def funds():
            return []
        self.assertEqual((await EtfHoldingsService(Http(), funds, SimpleNamespace()).holdings("00878"))["issuer"], "國泰投信")

    async def test_service_survives_fund_list_failure(self):
        async def funds():
            raise ValueError("上游回傳不是有效 JSON")
        self.assertEqual((await EtfHoldingsService(Http(), funds, SimpleNamespace()).holdings("00878"))["issuer"], "國泰投信")
