from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

from ..core.config import Settings
from ..core.http_client import ResilientHttpClient


BASE_URL = "https://websys.fsit.com.tw/FubonETF/Fund/Assets.aspx"
SYMBOL_PATTERN = re.compile(r"^00[0-9A-Z]{2,6}$")
# 基金持股每天更新一次；快取半天，避免重複連線。
CACHE_SECONDS = 12 * 60 * 60
MIN_INTERVAL_SECONDS = 1.0
# 個股權重加總與頁面「股票合計」允許的誤差（百分點），超過視為頁面格式改變。
WEIGHT_TOLERANCE = 0.5


class _TableParser(HTMLParser):
    """把頁面上的每張 table 轉成「列 → 儲存格文字」。"""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self.tables:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def supported_symbols(page: str) -> set[str]:
    return set(re.findall(r"Assets\.aspx\?stkId=([0-9A-Z]+)", page))


def parse_holdings(page: str, symbol: str) -> dict[str, Any] | None:
    """解析單檔基金的股票持股；不是該基金的頁面、沒有股票持股或數字對不起來時回傳 None。"""
    # 網站收到未知代號時不會報錯，而是回傳另一檔基金，所以一定要核對頁面上的代號。
    if f"Download.aspx?stkId={symbol}" not in page:
        return None
    parser = _TableParser()
    parser.feed(page)
    table = next((rows for rows in parser.tables if rows and rows[0][:1] == ["股票代碼"] and "權重(%)" in rows[0]), None)
    if table is None:
        return None
    holdings: list[dict[str, Any]] = []
    stated_total: float | None = None
    for row in table[1:]:
        if row and row[0].startswith("股票合計"):
            stated_total = _number(row[-1])
            continue
        if len(row) != 5 or not row[0]:
            continue
        shares, amount, weight = _number(row[2]), _number(row[3]), _number(row[4])
        if weight is None:
            continue
        holdings.append({"code": row[0], "name": row[1], "shares": shares, "amount": amount, "weight": weight})
    if not holdings:
        return None
    total = round(sum(item["weight"] for item in holdings), 4)
    if stated_total is None or abs(total - stated_total) > WEIGHT_TOLERANCE:
        return None
    match = re.search(r"資料日期：\s*(\d{4}/\d{1,2}/\d{1,2})", page)
    if not match:
        return None
    as_of: date = datetime.strptime(match.group(1), "%Y/%m/%d").date()
    holdings.sort(key=lambda item: item["weight"], reverse=True)
    return {"as_of": as_of.isoformat(), "holdings": holdings, "stock_weight_total": stated_total}


class FubonEtfProvider:
    """富邦投信 ETF 公開的基金資產頁。只連這一個固定網址，代號必須在官網清單內。"""

    name = "富邦投信"

    def __init__(self, settings: Settings, http: ResilientHttpClient):
        self.settings = settings
        self.http = http

    async def _page(self, symbol: str | None = None) -> str:
        return await self.http.get_text(
            self.name, BASE_URL, params={"stkId": symbol} if symbol else None,
            cache_ttl=CACHE_SECONDS, min_interval=MIN_INTERVAL_SECONDS,
        )

    async def holdings(self, symbol: str) -> dict[str, Any] | None:
        """回傳持股；不是富邦的 ETF 時不對該代號發出請求，直接回傳 None。"""
        if not SYMBOL_PATTERN.match(symbol) or symbol not in supported_symbols(await self._page()):
            return None
        parsed = parse_holdings(await self._page(symbol), symbol)
        if parsed is None:
            return None
        return {**parsed, "symbol": symbol, "issuer": self.name, "source_url": f"{BASE_URL}?stkId={symbol}"}
