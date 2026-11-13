from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any
from urllib.parse import quote

from ..core.http_client import ResilientHttpClient
from .fubon_etf import CACHE_SECONDS, MIN_INTERVAL_SECONDS, SYMBOL_PATTERN, FubonEtfProvider, _number, _TableParser

# 各投信公開揭露的 ETF 持股。每家只連固定網域；代號不符、數字對不起來時一律回傳 None，不猜測。
MAX_WEIGHT_TOTAL = 105.0
YUANTA_TOLERANCE = 1.5
MAX_XLSX_BYTES = 5_000_000


def _finish(symbol: str, issuer: str, source_url: str, as_of: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    holdings = [row for row in rows if row["code"] and row["weight"] is not None]
    total = round(sum(row["weight"] for row in holdings), 4)
    if not holdings or not 0 < total <= MAX_WEIGHT_TOTAL:
        return None
    holdings.sort(key=lambda row: row["weight"], reverse=True)
    return {"symbol": symbol, "issuer": issuer, "source_url": source_url, "as_of": as_of,
            "holdings": holdings, "stock_weight_total": total}


# ── 元大：持股在頁面內嵌的 Nuxt 資料，值以函式參數表示，需要還原 ─────────────
_TOKEN = r'(?:"(?:[^"\\]|\\.)*"|[^,{}\[\]]+)'
_ROW = re.compile(rf"\{{code:({_TOKEN}),ym:{_TOKEN},name:({_TOKEN}),ename:{_TOKEN},weights:({_TOKEN}),qty:({_TOKEN})\}}")


def _split_args(text: str) -> list[str]:
    parts, start, index, depth, in_string = [], 0, 0, 0, False
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
        index += 1
    parts.append(text[start:])
    return parts


def _literal(token: str, names: dict[str, Any] | None = None) -> Any:
    token = token.strip()
    if token.startswith('"'):
        return json.loads(token)
    if token in {"null", "void 0"}:
        return None
    if token in {"true", "false"}:
        return token == "true"
    number = _number(token)
    if number is not None:
        return number
    return (names or {}).get(token)


def _array_after(text: str, key: str) -> str | None:
    start = text.find(key)
    if start < 0:
        return None
    index, depth, in_string = start + len(key) - 1, 0, False
    for position in range(index, len(text)):
        char = text[position]
        if in_string:
            if char == '"' and text[position - 1] != "\\":
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[index + 1:position]
    return None


def parse_yuanta(page: str, symbol: str) -> tuple[str, list[dict[str, Any]]] | None:
    begin = page.find("window.__NUXT__=(function(")
    if begin < 0:
        return None
    script = page[begin:page.find("</script>", begin)]
    head = re.match(r"window\.__NUXT__=\(function\(([^)]*)\)\{", script)
    tail = script.rfind("}(")
    close = script.rfind("))")
    if not head or tail < 0 or close < tail:
        return None
    params = head.group(1).split(",")
    args = _split_args(script[tail + 2:close])
    if len(params) != len(args):
        return None
    names = {name: _literal(value) for name, value in zip(params, args)}
    summary = re.search(rf"FundWeights:\{{Summary:\{{code:({_TOKEN}),.*?stkvalues:({_TOKEN}),.*?fundsize:({_TOKEN})\}}", script)
    identity = re.search(rf"weightData:\{{PCF:\{{fundid:({_TOKEN}),.*?markcd:({_TOKEN}),", script)
    # 持股表只帶投信內部編號，要透過同一份資料的 PCF 對到股票代號。
    if not summary or not identity or _literal(identity.group(2), names) != symbol or _literal(identity.group(1), names) != _literal(summary.group(1), names):
        return None
    body = _array_after(script, "StockWeights:[")
    if not body:
        return None
    rows = [{"code": str(_literal(code, names) or ""), "name": str(_literal(name, names) or ""),
             "shares": _literal(qty, names), "amount": None, "weight": _literal(weight, names)}
            for code, name, weight, qty in _ROW.findall(body)]
    stocks, size = _literal(summary.group(2), names), _literal(summary.group(3), names)
    if not rows or not stocks or not size:
        return None
    if abs(sum(row["weight"] or 0 for row in rows) - stocks / size * 100) > YUANTA_TOLERANCE:
        return None
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page[:begin]))
    date_match = re.search(r"基金權重-股票 交易日期: (\d{4})/(\d{2})/(\d{2})", text)
    if not date_match:
        return None
    return "-".join(date_match.groups()), rows


class YuantaEtfProvider:
    name = "元大投信"

    def __init__(self, http: ResilientHttpClient):
        self.http = http

    async def holdings(self, symbol: str) -> dict[str, Any] | None:
        url = f"https://www.yuantaetfs.com/product/detail/{quote(symbol)}/ratio"
        parsed = parse_yuanta(await self.http.get_text(self.name, url, cache_ttl=CACHE_SECONDS, min_interval=MIN_INTERVAL_SECONDS), symbol)
        return _finish(symbol, self.name, url, parsed[0], parsed[1]) if parsed else None


# ── 國泰：官網前端使用的公開 JSON 查詢 ──────────────────────────────
class CathayEtfProvider:
    name = "國泰投信"
    BASE = "https://cwapi.cathaysite.com.tw/api/ETF"

    def __init__(self, http: ResilientHttpClient):
        self.http = http

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        payload = await self.http.get_json(self.name, f"{self.BASE}/{path}", params=params, cache_ttl=CACHE_SECONDS,
                                           min_interval=MIN_INTERVAL_SECONDS, headers={"Accept": "application/json"})
        return payload.get("result") if isinstance(payload, dict) and payload.get("success") else None

    async def holdings(self, symbol: str) -> dict[str, Any] | None:
        funds = await self._get("GetETFList", {"CurrentPage": 1, "PerPageCount": 200}) or []
        fund = next((row.get("fundCode") for row in funds if row.get("stockCode") == symbol), None)
        if not fund:
            return None
        assets = await self._get("GetETFAssets", {"fundCode": fund})
        day = (assets or {}).get("preDate")
        if not day or not re.fullmatch(r"\d{4}/\d{2}/\d{2}", day):
            return None
        rows = await self._get("GetETFDetailStockList", {"fundCode": fund, "SearchDate": day})
        if not rows:
            return None
        parsed = [{"code": str(row.get("stockCode") or "").strip(), "name": str(row.get("stockName") or "").strip(),
                   "shares": _number(str(row.get("volumn") or "")), "amount": None,
                   "weight": _number(str(row.get("weights") or ""))} for row in rows]
        return _finish(symbol, self.name, f"https://www.cathaysite.com.tw/ETF/detail/{fund}", day.replace("/", "-"), parsed)


# ── 復華：官網提供的持股 Excel ──────────────────────────────────────
def read_xlsx_rows(data: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        if sum(item.file_size for item in book.infolist()) > MAX_XLSX_BYTES:
            raise ValueError("Excel 檔案過大")
        strings = [re.sub(r"<[^>]+>", "", item) for item in re.findall(r"<(?:x:)?si>(.*?)</(?:x:)?si>", book.read("xl/sharedStrings.xml").decode("utf8"), re.S)]
        sheet = book.read("xl/worksheets/sheet1.xml").decode("utf8")
    rows = []
    for row in re.findall(r"<(?:x:)?row\b[^>]*>(.*?)</(?:x:)?row>", sheet, re.S):
        cells = []
        for attrs, value in re.findall(r"<(?:x:)?c\b([^>]*?)>\s*<(?:x:)?v>([^<]*)</(?:x:)?v>", row):
            cells.append(strings[int(value)] if 't="s"' in attrs else value)
        rows.append(cells)
    return rows


def parse_fuhua(data: bytes, symbol: str) -> tuple[str, list[dict[str, Any]]] | None:
    rows = read_xlsx_rows(data)
    if len(rows) < 3 or f"：{symbol}" not in (rows[0][0] if rows[0] else ""):
        return None
    date_match = re.search(r"(\d{4})/(\d{2})/(\d{2})", rows[1][0] if rows[1] else "")
    header = next((index for index, row in enumerate(rows) if row[:1] == ["證券代號"] and "權重(%)" in row), None)
    if not date_match or header is None:
        return None
    parsed = [{"code": row[0].strip(), "name": row[1].strip(), "shares": _number(row[2]), "amount": _number(row[3]),
               "weight": _number(row[4].rstrip("%"))} for row in rows[header + 1:] if len(row) >= 5]
    return "-".join(date_match.groups()), parsed


class FuhuaEtfProvider:
    name = "復華投信"
    BASE = "https://www.fhtrust.com.tw"

    def __init__(self, http: ResilientHttpClient):
        self.http = http

    async def _text(self, path: str) -> str:
        return await self.http.get_text(self.name, f"{self.BASE}{path}", cache_ttl=CACHE_SECONDS, min_interval=MIN_INTERVAL_SECONDS)

    async def holdings(self, symbol: str) -> dict[str, Any] | None:
        listing = await self._text("/ETF/etf_list")
        pairs = dict(re.findall(r'etfListTable-code[^>]*>\s*(00[0-9A-Z]+)\s*</td>.{0,600}?etf_detail/(ETF\d+)', listing, re.S))
        fund = pairs.get(symbol)
        if not fund:
            return None
        detail_path = f"/ETF/etf_detail/{fund}"
        found = re.search(rf"/api/assetsExcel/{fund}/(\d{{8}})", await self._text(detail_path))
        if not found:
            return None
        response = await self.http.request(self.name, f"{self.BASE}{found.group(0)}", cache_ttl=CACHE_SECONDS, min_interval=MIN_INTERVAL_SECONDS)
        parsed = parse_fuhua(response.content, symbol)
        return _finish(symbol, self.name, f"{self.BASE}{detail_path}", parsed[0], parsed[1]) if parsed else None


# ── 野村：官網前端使用的公開 JSON 查詢 ──────────────────────────────
def parse_nomura(payload: Any, symbol: str) -> tuple[str, list[dict[str, Any]]] | None:
    entries = payload.get("Entries") if isinstance(payload, dict) else None
    if not isinstance(entries, dict) or entries.get("FundID") != symbol:
        return None
    data = entries.get("Data") or {}
    day = str((data.get("FundAsset") or {}).get("NavDate") or "")
    table = next((item for item in data.get("Table") or [] if item.get("TableTitle") == "股票"), None)
    if not re.fullmatch(r"\d{4}/\d{2}/\d{2}", day) or not table:
        return None
    if [column.get("Name") for column in table.get("Columns") or []] != ["股票代號", "股票名稱", "股數", "權重(%)"]:
        return None
    return day.replace("/", "-"), [{"code": str(row[0]).strip(), "name": str(row[1]).strip(), "shares": _number(str(row[2])),
                                    "amount": None, "weight": _number(str(row[3]))} for row in table.get("Rows") or [] if len(row) == 4]


class NomuraEtfProvider:
    name = "野村投信"
    URL = "https://www.nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundAssets"

    def __init__(self, http: ResilientHttpClient):
        self.http = http

    async def holdings(self, symbol: str) -> dict[str, Any] | None:
        payload = await self.http.get_json(self.name, self.URL, json_body={"FundID": symbol}, cache_ttl=CACHE_SECONDS, min_interval=MIN_INTERVAL_SECONDS)
        parsed = parse_nomura(payload, symbol)
        return _finish(symbol, self.name, f"https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo={symbol}&tab=Shareholding", parsed[0], parsed[1]) if parsed else None


# ── 台新（含原新光 ETF）：官網申購買回清單頁 ─────────────────────────
TAISHIN_HEADER = ["代號", "名稱", "股數", "持股權重"]


def parse_taishin(page: str, symbol: str) -> tuple[str, list[dict[str, Any]]] | None:
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", page))
    # 下拉選單會列出所有基金，身分要看「查詢日期」後面的基金標題。
    heading = re.search(r"查詢日期[\s|]*[^|]*\(([0-9A-Z]+)\)", text)
    day = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})每基數申購總價金差額", text)
    if not heading or heading.group(1) != symbol or not day:
        return None
    parser = _TableParser()
    parser.feed(page)
    table = next((rows for rows in parser.tables if rows and rows[0] == TAISHIN_HEADER), None)
    if not table:
        return None
    rows = [{"code": row[0].removesuffix(" TT").strip(), "name": row[1].strip(), "shares": _number(row[2]), "amount": None,
             "weight": _number(row[3].rstrip("%"))} for row in table[1:] if len(row) == 4 and "合計" not in row[0]]
    return f"{day.group(1)}-{int(day.group(2)):02d}-{int(day.group(3)):02d}", rows


class TaishinEtfProvider:
    name = "台新投信"

    def __init__(self, http: ResilientHttpClient):
        self.http = http

    async def holdings(self, symbol: str) -> dict[str, Any] | None:
        url = f"https://www.tsit.com.tw/ETF/Home/Pcf/{quote(symbol)}"
        parsed = parse_taishin(await self.http.get_text(self.name, url, cache_ttl=CACHE_SECONDS, min_interval=MIN_INTERVAL_SECONDS), symbol)
        return _finish(symbol, self.name, url, parsed[0], parsed[1]) if parsed else None


# ── 永豐：官網現金申購買回清單頁 ─────────────────────────────────
SINOPAC_HEADER = ["證券代碼", "證券名稱", "股數", "佔基金淨資產之權重(%)"]


def parse_sinopac(page: str, symbol: str) -> tuple[str, list[dict[str, Any]]] | None:
    day = re.search(r"資料日期：(\d{4})/(\d{2})/(\d{2})", page)
    if f"證劵代碼：{symbol}）" not in page or not day:
        return None
    parser = _TableParser()
    parser.feed(page)
    table = next((rows for rows in parser.tables if rows and rows[0] == SINOPAC_HEADER), None)
    if not table:
        return None
    return "-".join(day.groups()), [{"code": row[0].strip(), "name": row[1].strip(), "shares": _number(row[2]), "amount": None,
                                     "weight": _number(row[3])} for row in table[1:] if len(row) == 4 and "合計" not in row[0]]


class SinopacEtfProvider:
    name = "永豐投信"

    def __init__(self, http: ResilientHttpClient):
        self.http = http

    async def holdings(self, symbol: str) -> dict[str, Any] | None:
        url = f"https://sitc.sinopac.com/SinopacEtfs/Etfs/SinglePcf/{quote(symbol)}"
        parsed = parse_sinopac(await self.http.get_text(self.name, url, cache_ttl=CACHE_SECONDS, min_interval=MIN_INTERVAL_SECONDS), symbol)
        return _finish(symbol, self.name, url, parsed[0], parsed[1]) if parsed else None


# ── 兆豐：官網 ETF 產品頁的基金配置 ───────────────────────────────
def parse_mega(page: str, symbol: str) -> tuple[str, list[dict[str, Any]]] | None:
    identity = re.search(r"彭博代碼</div>\s*<div[^>]*>\s*([0-9A-Z]+) TT Equity", page)
    day = re.search(r"資料來源：兆豐投信，(\d{4})/(\d{2})/(\d{2})", page)
    tab = re.search(r'id="fund_tab_(\d+)"[^>]*>股票<', page)
    if not identity or identity.group(1) != symbol or not day or not tab:
        return None
    # 同一份持股另有手機版區塊，只讀 fund_content_list（桌面版）。
    start = page.find(f'id="fund_content_list_{tab.group(1)}"')
    end = page.find("<!--", start)
    section = page[start:end if end > start else len(page)]
    if start < 0 or "持股權重" not in section:
        return None
    cells = [" ".join(item.split()) for item in re.findall(r'class="fund-content[^"]*">([^<]*)<', section)]
    return "-".join(day.groups()), [{"code": cells[i], "name": cells[i + 1], "shares": _number(cells[i + 2]), "amount": None,
                                     "weight": _number(cells[i + 3].replace("%", "").strip())} for i in range(0, len(cells) - 3, 4)]


class MegaEtfProvider:
    name = "兆豐投信"
    BASE = "https://www.megafunds.com.tw/MEGA/etf/etf_product.aspx"

    def __init__(self, http: ResilientHttpClient):
        self.http = http

    async def _page(self, fund_id: str | None = None) -> str:
        return await self.http.get_text(self.name, self.BASE, params={"id": fund_id or "5"}, cache_ttl=CACHE_SECONDS, min_interval=MIN_INTERVAL_SECONDS)

    async def holdings(self, symbol: str) -> dict[str, Any] | None:
        select = re.search(r'id="fund_id".*?</select>', await self._page(), re.S)
        # 網址只用內部編號，代號要逐頁比對；每頁快取半天。
        for fund_id in re.findall(r'<option[^>]*value="(\d+)"', select.group(0) if select else ""):
            page = await self._page(fund_id)
            parsed = parse_mega(page, symbol)
            if parsed:
                return _finish(symbol, self.name, f"{self.BASE}?id={fund_id}", parsed[0], parsed[1])
        return None


class EtfHoldingsService:
    """依證交所基金清單的基金名稱判斷投信，再交給該投信的來源。"""

    def __init__(self, http: ResilientHttpClient, fund_list, settings: Any):
        self.fund_list = fund_list
        taishin = TaishinEtfProvider(http)
        # 備援查找會依序試，直接組網址的元大放最後。
        self.providers = {"富邦": FubonEtfProvider(settings, http), "國泰": CathayEtfProvider(http), "復華": FuhuaEtfProvider(http),
                          "野村": NomuraEtfProvider(http), "台新": taishin, "新光": taishin, "永豐": SinopacEtfProvider(http),
                          "兆豐": MegaEtfProvider(http), "元大": YuantaEtfProvider(http)}

    async def holdings(self, symbol: str) -> dict[str, Any] | None:
        # 槓桿／反向型的曝險在期貨，現股明細不代表實際部位，不當成份股顯示。
        if not SYMBOL_PATTERN.match(symbol) or symbol.endswith(("L", "R")):
            return None
        # K 結尾是同一檔基金的外幣級別，持股與原代號相同。
        code = symbol[:-1] if symbol.endswith("K") else symbol
        # 清單只用來判斷投信；暫時拿不到時，改由各投信核對代號後回答。
        try:
            funds = await self.fund_list()
        except Exception:
            funds = []
        name = next((row["name"] for row in funds if row["code"] == code), "")
        matched = [item for prefix, item in self.providers.items() if name.startswith(prefix)]
        # 上櫃 ETF 不在證交所清單、少數基金名稱不以投信開頭，改由各家核對代號後回答。
        for provider in matched or list(dict.fromkeys(self.providers.values())):
            try:
                result = await provider.holdings(code)
            except Exception:
                if matched:
                    raise
                continue
            if result:
                return {**result, "symbol": symbol}
        return None
