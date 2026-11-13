"""上市櫃公司自行申報的 ESG 揭露（證交所、櫃買中心 OpenAPI）。

只整理「揭露了什麼、有沒有驗證」，不評分、不比較好壞。
要擴充主題時，在 TOPICS 加一列即可，前端依回傳內容自動顯示。
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from ..core.config import Settings
from ..core.http_client import ResilientHttpClient
from ..core.normalization import clean_text, parse_roc_date

CACHE_SECONDS = 43200  # 年度資料，半天更新一次已足夠
INDEX_SECONDS = 3600
META_COLUMNS = {"出表日期", "報告年度", "公司代號", "公司名稱"}
BLANK_VALUES = {"", "N/A", "NA", "-", "無"}
NEGATIVE_VERIFICATION = BLANK_VALUES | {"否"}

# (key, 標題, 面向, 資料集編號, 代表揭露的欄位：(欄名開頭, 短標籤, 單位))
TOPICS: tuple[tuple[str, str, str, int, tuple[tuple[str, str, str], ...]], ...] = (
    ("greenhouse", "溫室氣體", "E", 1, (("範疇一排放量", "範疇一", "噸"), ("範疇二排放量", "範疇二", "噸"), ("範疇三排放量", "範疇三", "噸"))),
    ("energy", "能源管理", "E", 2, (("使用率", "再生能源占比", ""),)),
    ("water", "水資源", "E", 3, (("用水量", "用水量", "公噸"),)),
    ("waste", "廢棄物", "E", 4, (("總重量(有害+非有害)-數據", "廢棄物總重", "公噸"),)),
    ("people", "人力發展", "S", 5, (("員工薪資平均數", "平均薪資", "仟元"), ("非擔任主管之全時員工薪資中位數", "非主管中位數", "仟元"), ("員工福利平均數", "平均福利", "仟元"), ("管理職女性主管佔比", "女性主管", ""))),
    ("safety", "職業安全", "S", 21, (("職業災害人數及比率-人數", "職災人數", "人"), ("職業災害人數及比率-比率", "職災比率", ""), ("火災件數", "火災件數", "件"), ("火災死傷人數(", "火災死傷", "人"))),
    ("board", "董事會", "G", 6, (("董事席次", "董事席次", "席"), ("獨立董事席次", "獨立董事", "席"), ("女性董事席次及比率-比率", "女性董事", ""), ("董事出席董事會出席率", "出席率", ""))),
    ("committee", "功能性委員會", "G", 9, (("審計委員會席次", "審計委員", "席"), ("審計委員會出席率", "審計出席", ""), ("薪酬委員會席次", "薪酬委員", "席"), ("薪酬委員會出席率", "薪酬出席", ""))),
    ("investor", "投資人溝通", "G", 7, (("公司年度召開法說會次數", "年度法說會", "次"),)),
)


def format_value(value: Any) -> str | None:
    """原始值轉成顯示文字；未填回傳 None。只整理格式，不改變數值。"""
    text = clean_text(value)
    if text is None or text in BLANK_VALUES:
        return None
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(%?)", text.replace(",", ""))
    if not match:
        return text
    number = float(match.group(1))
    return f"{number:,.2f}".rstrip("0").rstrip(".") + match.group(2)


def _find(row: dict[str, Any], prefix: str) -> Any:
    return next((value for key, value in row.items() if key.strip().startswith(prefix)), None)


def _is_verified(row: dict[str, Any]) -> bool:
    return any("取得驗證" in key and (clean_text(value) or "") not in NEGATIVE_VERIFICATION for key, value in row.items())


def _has_verification_field(row: dict[str, Any]) -> bool:
    return any("取得驗證" in key for key in row)


def _verification_text(row: dict[str, Any]) -> str | None:
    """溫室氣體是逐範疇的是／否，其他主題填驗證或標準名稱。"""
    values = [clean_text(value) or "" for key, value in row.items() if "取得驗證" in key]
    if values and all(value in {"是", "否"} for value in values):
        return f"{values.count('是')}／{len(values)} 個範疇有驗證"
    return next((value for value in values if value not in NEGATIVE_VERIFICATION), None)


def _scope_text(row: dict[str, Any]) -> str | None:
    return next((format_value(value) for key, value in row.items() if ("資料範圍" in key or "資料邊界" in key) and format_value(value)), None)


class EsgProvider:
    name = "ESG 揭露"

    def __init__(self, settings: Settings, http: ResilientHttpClient):
        self.settings = settings
        self.http = http
        self._index: dict[str, dict[str, Any]] = {}
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    def _url(self, market: str, number: int) -> str:
        if market == "TWSE":
            return f"{self.settings.twse_base_url}/opendata/t187ap46_L_{number}"
        return f"{self.settings.tpex_base_url}/t187ap46_O_{number}"

    async def _rows(self, url: str) -> list[dict[str, Any]]:
        data = await self.http.get_json(self.name, url, cache_ttl=CACHE_SECONDS, min_interval=0.1)
        if not isinstance(data, list):
            raise ValueError("官方 OpenAPI 回傳格式不是資料列陣列")
        return data

    async def _load(self) -> dict[str, dict[str, Any]]:
        async with self._lock:
            if self._index and time.monotonic() - self._loaded_at < INDEX_SECONDS:
                return self._index
            jobs = [(market, topic) for market in ("TWSE", "TPEx") for topic in TOPICS]
            results = await asyncio.gather(*(self._rows(self._url(market, topic[3])) for market, topic in jobs), return_exceptions=True)
            index: dict[str, dict[str, Any]] = {}
            failed = 0
            for (market, topic), rows in zip(jobs, results):
                if isinstance(rows, Exception):
                    failed += 1
                    continue
                for row in rows:
                    symbol = clean_text(row.get("公司代號"))
                    if not symbol:
                        continue
                    item = index.setdefault(symbol, {"symbol": symbol, "name": clean_text(row.get("公司名稱")), "market": market, "report_year": clean_text(row.get("報告年度")), "as_of": parse_roc_date(row.get("出表日期")), "topics": {}})
                    item["topics"][topic[0]] = row
            if failed == len(jobs):
                raise RuntimeError("ESG 資料來源目前無法連線")
            # 部分資料集失敗時不留快取，下次請求重新取得，避免把缺資料當成未揭露。
            self._index, self._loaded_at = index, time.monotonic() if not failed else 0.0
            return index

    def _detail(self, item: dict[str, Any]) -> dict[str, Any]:
        topics = []
        for key, title, pillar, number, fields in TOPICS:
            row = item["topics"].get(key)
            highlights = [{"label": label, "value": format_value(_find(row, prefix)), "unit": unit} for prefix, label, unit in fields] if row else []
            has_verification = bool(row) and _has_verification_field(row)
            topics.append({
                "key": key, "title": title, "pillar": pillar,
                "disclosed": any(entry["value"] is not None for entry in highlights),
                "has_verification_field": has_verification,
                "verified": has_verification and _is_verified(row),
                "highlights": highlights,
                "verification": _verification_text(row) if has_verification else None,
                "scope": _scope_text(row) if row else None,
                "fields": [{"label": name.strip(), "value": format_value(value)} for name, value in row.items() if name not in META_COLUMNS] if row else [],
                "source_url": self._url(item["market"], number),
            })
        return {
            "symbol": item["symbol"], "name": item["name"], "market": item["market"],
            "report_year": item["report_year"], "as_of": item["as_of"].isoformat() if item["as_of"] else None,
            "disclosed_count": sum(topic["disclosed"] for topic in topics), "topic_count": len(topics),
            "verified_count": sum(topic["verified"] for topic in topics),
            "verifiable_count": sum(topic["has_verification_field"] for topic in topics),
            "topics": topics,
        }

    async def company(self, symbol: str) -> dict[str, Any] | None:
        item = (await self._load()).get(symbol)
        return self._detail(item) if item else None

    async def summaries(self, symbols: list[str]) -> list[dict[str, Any]]:
        index = await self._load()
        return [{key: value for key, value in self._detail(index[symbol]).items() if key != "topics"} for symbol in symbols if symbol in index]
