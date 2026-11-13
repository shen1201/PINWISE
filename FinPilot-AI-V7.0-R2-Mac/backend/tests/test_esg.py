import unittest
from types import SimpleNamespace

from backend.app.providers.esg import EsgProvider, format_value


def base(code="2330"):
    return {"出表日期": "1151110", "報告年度": "114", "公司代號": code, "公司名稱": "台積電"}


class FakeHttp:
    def __init__(self, tables, fail=()):
        self.tables, self.fail, self.calls = tables, fail, 0

    async def get_json(self, _source, url, **_):
        self.calls += 1
        number = int(url.rsplit("_", 1)[1])
        if url.split("/")[-1] in self.fail:
            raise RuntimeError("down")
        return self.tables.get(number, []) if "_L_" in url else []


def provider(tables, fail=()):
    return EsgProvider(SimpleNamespace(twse_base_url="https://t", tpex_base_url="https://o"), FakeHttp(tables, fail))


GREENHOUSE = {**base(), "範疇一排放量(噸CO2e)": "2196516.0000", "範疇一取得驗證": "是", "範疇二排放量(噸CO2e)": "N/A", "範疇二取得驗證": "否", "範疇三排放量(噸CO2e)": "", "範疇三取得驗證": "否"}


class EsgTests(unittest.IsolatedAsyncioTestCase):
    def test_format_keeps_value_and_treats_placeholders_as_blank(self):
        self.assertEqual(format_value("2196516.0000"), "2,196,516")
        self.assertEqual(format_value("20.1000%"), "20.1%")
        self.assertEqual(format_value("0"), "0")
        self.assertIsNone(format_value("N/A"))
        self.assertIsNone(format_value(" "))
        self.assertEqual(format_value("ISO 50001"), "ISO 50001")

    async def test_counts_disclosure_and_verification(self):
        tables = {1: [GREENHOUSE], 2: [{**base(), "使用率(再生能源/總能源)": "N/A", "取得驗證": "N/A"}], 7: [{**base(), "公司年度召開法說會次數(次)": "5"}]}
        data = await provider(tables).company("2330")
        topics = {topic["key"]: topic for topic in data["topics"]}
        self.assertEqual(data["disclosed_count"], 2)
        self.assertEqual(data["topic_count"], 9)
        self.assertEqual(data["verified_count"], 1)
        self.assertEqual(data["verifiable_count"], 2)
        self.assertEqual(topics["greenhouse"]["highlights"][0]["value"], "2,196,516")
        self.assertIsNone(topics["greenhouse"]["highlights"][1]["value"])
        self.assertFalse(topics["energy"]["disclosed"])
        self.assertFalse(topics["water"]["disclosed"])
        self.assertEqual(data["as_of"], "2026-11-10")
        self.assertEqual(topics["greenhouse"]["verification"], "1／3 個範疇有驗證")
        self.assertIsNone(topics["energy"]["verification"])

    async def test_unknown_company_returns_none(self):
        self.assertIsNone(await provider({1: [GREENHOUSE]}).company("0050"))

    async def test_summaries_skip_unknown_and_omit_topics(self):
        rows = await provider({1: [GREENHOUSE]}).summaries(["2330", "9999"])
        self.assertEqual([row["symbol"] for row in rows], ["2330"])
        self.assertNotIn("topics", rows[0])

    async def test_partial_failure_is_not_cached(self):
        esg = provider({1: [GREENHOUSE]}, fail={"t187ap46_L_2"})
        await esg.company("2330")
        first = esg.http.calls
        await esg.company("2330")
        self.assertGreater(esg.http.calls, first)

    async def test_full_success_is_cached(self):
        esg = provider({1: [GREENHOUSE]})
        await esg.company("2330")
        first = esg.http.calls
        await esg.company("2330")
        self.assertEqual(esg.http.calls, first)

    async def test_all_sources_down_raises(self):
        names = {f"t187ap46_{m}_{n}" for m in "LO" for n in (1, 2, 3, 4, 5, 6, 7, 9, 21)}
        with self.assertRaises(RuntimeError):
            await provider({}, fail=names).company("2330")
