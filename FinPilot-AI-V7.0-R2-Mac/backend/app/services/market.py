from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import date, timedelta
from typing import Any

from ..core.models import PickerRequest
from ..core.normalization import normalized_symbol
from ..providers.finmind import FinMindProvider
from ..providers.mops import MOPSProvider
from ..providers.tpex import TPExProvider
from ..providers.twse import TWSEProvider
from .analytics import price_metrics


INDUSTRY_CODES = {
    "ai伺服器散熱": {"25", "28", "31"}, "伺服器散熱": {"25", "28", "31"},
    "被動元件": {"28"}, "電子零組件": {"28"},
    "ic載板": {"28"}, "載板": {"28"}, "pcb": {"28"}, "印刷電路板": {"28"},
    "矽光子": {"24", "27", "28"}, "光通訊": {"27", "28"},
    "記憶體": {"24"},
    "semi": {"24"}, "半導體": {"24"},
    "biotech": {"22"}, "生技": {"22"}, "醫療": {"22"},
    "finance": {"17"}, "金融": {"17"},
    "shipping": {"15"}, "航運": {"15"},
    "ai-server": {"25"}, "伺服器": {"25"},
    "power": {"05", "28", "31"}, "電力": {"05", "28", "31"},
    "資料中心": {"25", "28", "31"},
    "ev": {"05", "12", "28"}, "電動車": {"05", "12", "28"},
    "electronic": {"25", "26", "27", "28", "29", "30", "31", "32", "33"},
}
INDUSTRY_LABELS = {
    "semi": "半導體", "biotech": "生技", "finance": "金融", "shipping": "航運", "ai-server": "伺服器",
    "power": "電力", "ev": "電動車", "electronic": "電子",
}

# Reviewed reference scope, not market data and not an exhaustive industry list.
# A broad exchange code (28) alone does not establish passive-component membership.
PASSIVE_COMPONENT_REFERENCES = {
    "2327": "https://www.twse.com.tw/pdf/ch/2327_ch.pdf",
    "2492": "https://www.passivecomponent.com/zh-hant/",
}

# 年化波動門檻與股票詳情的「相對平穩／中等／波動大」標記一致（25%／45%）。
RISK_VOLATILITY_RANGES = {
    "low": (0.0, 25.0),
    "medium": (25.0, 45.0),
    "high": (45.0, float("inf")),
}
PERIOD_DAYS = {"3m": 180, "1y": 365 * 3, "3y": 365 * 5}
GENERIC_QUERY_TERMS = {
    "值得研究", "推薦", "標的", "公司", "股票", "台股", "個股",
    "請問", "請幫我", "幫我", "想找", "想要", "有哪些", "可以", "一下",
}


def explicit_symbols_from_query(query: str) -> list[str]:
    """Extract stock-like codes while excluding unambiguous calendar dates.

    Four-digit Taiwan stock codes can overlap with years (for example 2026 is
    also a listed security), so a bare number remains valid.  Only numbers
    that are visibly used as a year or as the year component of a date are
    removed.
    """
    date_neutralized = re.sub(r"(?<!\d)(?:19|20)\d{2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{1,2}(?!\d)", " ", query)
    date_neutralized = re.sub(r"(?<!\d)(?:19|20)\d{2}\s*年", " ", date_neutralized)
    # ETF 代號可能以英文結尾（00981A）；只抓數字會變成不存在的 00981，整份結果被濾空。
    return [code.upper() for code in re.findall(r"(?<!\d)(00\d{2,4}[A-Za-z](?![0-9A-Za-z])|\d{4,6}(?!\d))", date_neutralized)]


class MarketService:
    def __init__(self, *, twse: TWSEProvider, tpex: TPExProvider, mops: MOPSProvider, finmind: FinMindProvider):
        self.twse = twse
        self.tpex = tpex
        self.mops = mops
        self.finmind = finmind

    async def universe(self):
        quotes, companies = await asyncio.gather(
            self._partial(self.twse.quotes(), self.tpex.quotes()),
            self._partial(self.twse.companies(), self.tpex.companies()),
        )
        profiles = {item.symbol: item for item in companies}
        return quotes, profiles

    @staticmethod
    async def _partial(*operations):
        results = await asyncio.gather(*operations, return_exceptions=True)
        lists = [value for value in results if isinstance(value, list)]
        if not lists:
            error = next((value for value in results if isinstance(value, Exception)), RuntimeError("資料來源沒有回傳資料"))
            raise error
        return [item for values in lists for item in values]

    @staticmethod
    def _is_etf(symbol: str, name: str | None) -> bool:
        return symbol.startswith("00") or "ETF" in (name or "").upper()

    @staticmethod
    def _industry_match(request: PickerRequest) -> tuple[str, set[str]]:
        """回傳（中文主題詞, 產業代碼）；進階條件的英文代號換成中文，供理由文字與 ETF 名稱比對。"""
        text = f"{request.industry or ''} {request.query}".lower()
        for key, codes in INDUSTRY_CODES.items():
            if key in text:
                return INDUSTRY_LABELS.get(key, key), codes
        return "", set()

    @classmethod
    def _industry_filter(cls, request: PickerRequest) -> set[str]:
        return cls._industry_match(request)[1]

    @staticmethod
    def _meaningful_query_terms(query: str) -> list[str]:
        """Remove generic request words without turning them into a match-all."""
        remaining = query
        for term in sorted(GENERIC_QUERY_TERMS, key=len, reverse=True):
            remaining = remaining.replace(term, " ")
        return [
            term for term in re.findall(r"[a-z0-9\u4e00-\u9fff]+", remaining)
            if term not in {"的", "嗎", "呢", "和", "與"}
        ]

    async def select(self, request: PickerRequest, funnel: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Filter the official universe.  When ``funnel`` is given it is filled
        with step counts so the interface can explain which condition emptied
        the result (matched before risk, risk checked/matched, volatilities)."""
        funnel = funnel if funnel is not None else {}
        # 全形英數（００９８１Ａ）先轉半形，否則比對不到代號。
        query = unicodedata.normalize("NFKC", request.query).strip().lower()
        explicit = set(explicit_symbols_from_query(query))
        industry_key, industry_codes = self._industry_match(request)
        query_terms = self._meaningful_query_terms(query)
        # "ETF" names a product type; Taiwan ETF names (e.g. 元大台灣50) rarely contain the letters.
        product_type = request.product_type
        if "etf" in query_terms:
            query_terms = [term for term in query_terms if term != "etf"]
            if product_type == "all":
                product_type = "etf"
        elif product_type == "all" and any(word in query for word in ("公司", "個股")):
            # 「有哪些公司」問的是個股；不然成交金額大的市值型、槓桿型 ETF 會排在最前面。
            product_type = "stock"
        requested_industry = (request.industry or "").strip().lower()
        passive_scope = "被動元件" in f"{requested_industry} {query}" and not explicit
        if requested_industry and requested_industry != "all" and not industry_codes:
            funnel.update({"matched": 0, "scope": "unsupported_industry", "returned": 0})
            return []
        quotes, profiles = await self.universe()
        # 只打了部分代號（00981）時不是完整代號，改用一般的部分比對。
        if explicit and not explicit & {quote.symbol for quote in quotes}:
            explicit = set()
        rows = []
        for quote in quotes:
            profile = profiles.get(quote.symbol)
            name = quote.name or profile.name if profile else quote.name
            is_etf = self._is_etf(quote.symbol, name)
            if request.market != "all" and quote.market != request.market:
                continue
            if product_type == "etf" and not is_etf:
                continue
            if product_type == "stock" and is_etf:
                continue
            if explicit and quote.symbol not in explicit:
                continue
            if passive_scope and quote.symbol not in PASSIVE_COMPONENT_REFERENCES:
                continue
            if industry_codes and not is_etf and (not profile or profile.industry_code not in industry_codes):
                continue
            # ETF 沒有交易所產業代碼；指定產業時只留名稱就有該主題的 ETF（例如「生技」），
            # 否則 0050、正二這類大型 ETF 會因成交金額大而混進產業結果。
            if industry_codes and is_etf and industry_key not in (name or "").lower():
                continue
            if query and not explicit and not industry_codes:
                haystack = f"{quote.symbol} {name or ''}".lower()
                # A recognized structured risk filter may intentionally start
                # from the whole universe. Generic words alone must not do so,
                # and any unknown meaningful term must still fail closed.
                if query_terms and not any(term in haystack for term in query_terms):
                    continue
                if not query_terms and request.risk not in RISK_VOLATILITY_RANGES and product_type == request.product_type:
                    continue
            rows.append((quote, profile, is_etf))
        rows.sort(key=lambda item: (item[0].trade_value_twd or 0, item[0].volume_shares or 0), reverse=True)
        funnel.update({
            "matched": len(rows),
            "matched_sample": [f"{quote.symbol} {quote.name or ''}".strip() for quote, _, _ in rows[:5]],
            "scope": "passive_reference" if passive_scope else "industry" if industry_codes else "query" if query_terms or explicit else "all",
        })
        if request.risk in RISK_VOLATILITY_RANGES:
            # Risk is never inferred from a company name.  It is calculated
            # deterministically from official daily history over the requested
            # observation window.  A bounded shortlist keeps anonymous
            # FinMind use inside a reasonable request budget.
            shortlist = rows[:min(30, max(request.limit * 2, request.limit))]
            days = PERIOD_DAYS.get(request.period or "", 180)
            end = date.today()
            histories = await asyncio.gather(*(
                self.finmind.history(quote.symbol, end - timedelta(days=days), end)
                for quote, _, _ in shortlist
            ), return_exceptions=True)
            enriched = []
            lower, upper = RISK_VOLATILITY_RANGES[request.risk]
            checked: list[dict[str, Any]] = []
            for row, history in zip(shortlist, histories):
                if isinstance(history, Exception):
                    continue
                metrics = price_metrics(history)
                volatility = metrics.get("annualized_volatility_pct")
                if volatility is not None:
                    checked.append({"symbol": row[0].symbol, "name": row[0].name or "", "volatility_pct": volatility})
                if volatility is None or not (lower <= volatility <= upper):
                    continue
                enriched.append((*row, metrics))
            level_counts = {
                level: sum(1 for item in checked if low <= item["volatility_pct"] <= high)
                for level, (low, high) in RISK_VOLATILITY_RANGES.items()
            }
            funnel.update({
                "risk": request.risk, "risk_window_days": days, "risk_checked": len(checked),
                "risk_shortlist_limit": len(shortlist), "risk_matched": len(enriched),
                "risk_level_counts": level_counts,
                "risk_checked_sample": sorted(checked, key=lambda item: item["volatility_pct"])[:8],
            })
        else:
            enriched = [(*row, None) for row in rows]
        funnel["returned"] = min(len(enriched), request.limit)

        return [{
            "symbol": quote.symbol,
            "name": name,
            "market": quote.market,
            "product_type": "etf" if is_etf else "stock",
            "industry_code": profile.industry_code if profile else None,
            "quote": quote.model_dump(mode="json"),
            "metrics": metrics,
            "selection_period": request.period,
            "risk_method": (
                f"以日收盤資料計算年化波動度；" + (f"{lower:g}% 以上" if upper == float("inf") else f"{lower:g}% 至 {upper:g}%")
                if request.risk in RISK_VOLATILITY_RANGES else None
            ),
            "selection_reason": "符合明示代號" if explicit else (
                "被動元件小範圍：產品參考資料已人工核對，代號與日價由交易所資料取得；不是完整產業名單"
                if passive_scope else self._reason_text(industry_key, is_etf, metrics, request.risk, rank)
            ),
            "data_frequency": "daily",
        } for rank, (quote, profile, is_etf, metrics) in enumerate(enriched[:request.limit], start=1)
          for name in [quote.name or (profile.short_name if profile else None)]]

    @staticmethod
    def _reason_text(industry_key: str, is_etf: bool, metrics: dict | None, risk: str | None, rank: int) -> str:
        """每檔理由寫出實際符合的條件與數值，不用同一句通用文字。"""
        # 卡片較窄時只顯示第一句，所以把最有資訊量的波動數值放最前面。
        parts = []
        volatility = (metrics or {}).get("annualized_volatility_pct")
        if risk in RISK_VOLATILITY_RANGES and volatility is not None:
            lower, upper = RISK_VOLATILITY_RANGES[risk]
            band = f"{lower:g}% 以上" if upper == float("inf") else f"{lower:g}%–{upper:g}%"
            parts.append(f"年化波動 {volatility}%（條件 {band}）")
        if industry_key:
            parts.append(f"名稱含「{industry_key}」的主題 ETF" if is_etf else f"符合「{industry_key}」對應的交易所產業分類")
        parts.append(f"成交金額排序第 {rank}")
        return "；".join(parts)

    async def resolve_symbols(self, query: str, requested: list[str], limit: int = 5) -> list[str]:
        explicit = [normalized_symbol(value) for value in requested]
        explicit += explicit_symbols_from_query(query)
        explicit = list(dict.fromkeys(value for value in explicit if value))
        if explicit:
            return explicit[:limit]
        selected = await self.select(PickerRequest(query=query, limit=limit))
        return [item["symbol"] for item in selected]

    async def resolve_industry_scope(self, topic: str, limit: int = 5) -> dict[str, Any]:
        """Build a bounded official-market scope without fuzzy company names.

        Exchange industry codes are broader than product sub-industries.  The
        returned limitation is intentionally preserved for the research prompt
        so selected companies remain candidates to verify, not asserted members
        of a narrow supply chain.
        """
        codes = self._industry_filter(PickerRequest(query="", industry=topic, product_type="stock", limit=limit))
        if not codes:
            return {
                "topic": topic, "symbols": [], "industry_codes": [],
                "selection_basis": "unsupported_topic",
                "limitations": ["現有官方公司清單無法把此主題對應到可核實的產業分類；未以名稱模糊比對替代。"],
            }
        narrow = "被動元件" in topic
        rows = await self.select(PickerRequest(
            query="", industry=topic, product_type="stock", limit=max(1, min(limit, 8)),
        )) if not narrow else await self.select(PickerRequest(
            query=" ".join(PASSIVE_COMPONENT_REFERENCES), product_type="stock", limit=max(1, min(limit, 8)),
        ))
        return {
            "topic": topic,
            "symbols": [str(item["symbol"]) for item in rows],
            "industry_codes": sorted(codes),
            "selection_basis": "reviewed_product_references_and_official_symbol_match" if narrow else "official_exchange_industry_code_then_daily_trade_value",
            "membership_references": PASSIVE_COMPONENT_REFERENCES if narrow else {},
            "limitations": [
                "被動元件僅採已核對產品參考資料的國巨、華新科作小範圍研究，非完整產業名單；參考連結不是本次即時 API 證據，不計入來源覆蓋率。" if narrow else
                "交易所產業代碼只能驗證較廣的產業分類；個別公司與狹義主題的產品關聯仍須以公司公告或法說資料逐一核對。"
            ],
        }

    @staticmethod
    def newer_quote(quote, history):
        """官方日行情較慢時，用歷史日價中較新的交易日取代；官方已是最新就不動。"""
        if quote is None:
            return None
        points = [point for point in history if point.close is not None and point.close > 0]
        if not points or (quote.trade_date and points[-1].trade_date <= quote.trade_date):
            return quote
        last = points[-1]
        change = round(last.close - points[-2].close, 2) if len(points) > 1 else last.change
        return quote.model_copy(update={
            "trade_date": last.trade_date, "open": last.open, "high": last.high, "low": last.low, "close": last.close,
            "change": change, "volume_shares": last.volume_shares, "trade_value_twd": last.trade_value_twd,
            "transactions": last.transactions, "metadata": last.metadata,
        })

    async def snapshot(self, symbol: str, *, scope: str = "full") -> dict[str, Any]:
        """Return a bounded snapshot.

        ``quote`` avoids history/MOPS calls for a simple price question;
        ``market`` adds normalized history; ``full`` preserves the original
        company, history and disclosure payload used by research questions.
        """
        code = normalized_symbol(symbol)
        scope = scope if scope in {"quote", "market", "full"} else "full"
        quote_results = await asyncio.gather(self.twse.quote(code), self.tpex.quote(code), return_exceptions=True)
        quote = next((item for item in quote_results if item is not None and not isinstance(item, Exception)), None)
        if scope == "quote" and quote is None:
            error = next((item for item in quote_results if isinstance(item, Exception)), None)
            if error:
                raise error
            raise RuntimeError("TWSE／TPEx 最近日行情沒有此標的資料")
        errors = []
        company = None
        history = []
        disclosures = []
        capabilities = ["market_snapshot"]
        if scope == "market":
            history_result = (await asyncio.gather(
                self.finmind.history(code, date.today() - timedelta(days=180), date.today()),
                return_exceptions=True,
            ))[0]
            if isinstance(history_result, Exception):
                errors.append({"source": "FinMind", "capability": "price_history", "message": str(history_result)})
            else:
                history = history_result
                capabilities.append("price_history")
        elif scope == "full":
            company_result, history_result, disclosures_result = await asyncio.gather(
                self.mops.company(code),
                self.finmind.history(code, date.today() - timedelta(days=180), date.today()),
                self.mops.disclosures(code, limit=10),
                return_exceptions=True,
            )
            company = None if isinstance(company_result, Exception) else company_result
            history = [] if isinstance(history_result, Exception) else history_result
            disclosures = [] if isinstance(disclosures_result, Exception) else disclosures_result
            if isinstance(company_result, Exception):
                errors.append({"source": "MOPS", "capability": "company_profile", "message": str(company_result)})
            else:
                capabilities.append("company_profile")
            if isinstance(history_result, Exception):
                errors.append({"source": "FinMind", "capability": "price_history", "message": str(history_result)})
            else:
                capabilities.append("price_history")
            if isinstance(disclosures_result, Exception):
                errors.append({"source": "MOPS", "capability": "material_events", "message": str(disclosures_result)})
            else:
                capabilities.append("material_events")
        if scope == "quote" and quote is not None:
            # 只問價格時也要最新：取近兩週日價比對；取不到就維持官方日行情。
            try:
                quote = self.newer_quote(quote, await self.finmind.history(code, date.today() - timedelta(days=14), date.today()))
            except Exception:
                pass
        else:
            quote = self.newer_quote(quote, history)
        if not quote and not company and not history:
            return {
                "symbol": code, "found": False, "errors": errors,
                "data_frequency": "daily", "scope": scope, "capabilities": capabilities,
            }
        return {
            "symbol": code,
            "found": True,
            "name": (quote.name if quote else None) or (company.short_name if company else None) or (company.name if company else None),
            "market": (quote.market if quote else None) or (company.market if company else "UNKNOWN"),
            "quote": quote.model_dump(mode="json") if quote else None,
            "company": company.model_dump(mode="json") if company else None,
            "metrics": price_metrics(history),
            "history": [point.model_dump(mode="json") for point in history[-30:]],
            "events": [event.model_dump(mode="json") for event in disclosures[:10]],
            "errors": errors,
            "data_frequency": "daily",
            "as_of": quote.trade_date.isoformat() if quote and quote.trade_date else (history[-1].trade_date.isoformat() if history else None),
            "scope": scope,
            "capabilities": list(dict.fromkeys(capabilities)),
        }

    async def snapshots(self, symbols: list[str]) -> list[dict[str, Any]]:
        unique = list(dict.fromkeys(normalized_symbol(value) for value in symbols if normalized_symbol(value)))[:20]
        return await asyncio.gather(*(self.snapshot(symbol) for symbol in unique))
