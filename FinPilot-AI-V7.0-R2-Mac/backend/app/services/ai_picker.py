"""Natural-language stock picker Agent.

understand (Gemini, rule fallback) -> validate plan against allow-listed fields
-> screen official data (program, never the model) -> per-stock reasons from
real values -> optional plain-language explanation (Gemini, sentence-validated)
-> beginner glossary.  Every step is returned as a trace for the UI.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import date, timedelta
from typing import Any

from ..core.models import AIPickerRequest
from ..security.preview_security import PreviewLimitError
from .analytics import price_metrics
from .market import GENERIC_QUERY_TERMS, INDUSTRY_CODES, PASSIVE_COMPONENT_REFERENCES, MarketService
from .research import _number_tokens, fundamental_metrics, validated_sentences

PRODUCT_TYPES = ("all", "stock", "etf")
MARKETS = ("all", "TWSE", "TPEX")
VOLATILITY = {"any": None, "low": (0.0, 25.0), "medium": (25.0, 45.0), "high": (45.0, 1000.0)}
VOLATILITY_LABEL = {"low": "低波動（年化波動 < 25%）", "medium": "中等波動（25%–45%）", "high": "高波動（> 45%）"}
SORTS = {
    "trade_value": ("成交金額", True), "dividend_yield": ("殖利率", True), "pe_ratio": ("本益比", False),
    "pb_ratio": ("股價淨值比", False), "revenue_yoy": ("月營收年增率", True), "eps": ("累計 EPS", True),
    "volatility": ("年化波動", False),
}
NUMERIC_LIMITS = {
    "min_dividend_yield_pct": (0, 20), "max_pe_ratio": (1, 200), "max_pb_ratio": (0.1, 30),
    "min_revenue_yoy_pct": (-100, 1000), "min_eps": (-100, 1000),
}
HISTORY_DAYS = 180
SHORTLIST = 30
# Beginner safeguards: rank only reasonably liquid stocks, and treat extreme
# yields (one-off payouts, capital returns) as outliers rather than top picks.
MIN_TRADE_VALUE_TWD = 10_000_000
MAX_PLAUSIBLE_YIELD_PCT = 15.0
LEVERAGED_ETF = re.compile(r"正\d|反\d|槓桿|反向|[LR]$")

GLOSSARY = {
    "殖利率": "每年配發的現金股利 ÷ 股價。數字越高代表以現在價格買進、每年可領回的比例越高，但股利可能變動，高殖利率不代表沒有風險。",
    "本益比": "股價 ÷ 每股盈餘（EPS），代表市場願意為每 1 元獲利付出幾元。偏低可能較便宜，也可能是市場預期獲利會下滑。",
    "股價淨值比": "股價 ÷ 每股淨值。低於 1 代表股價低於帳面價值，常用於金融、傳產等資產型公司。",
    "月營收年增率": "本月營收和去年同月相比的成長幅度。可看出業績是否成長，但單月可能受季節或一次性因素影響。",
    "EPS": "每股盈餘：公司稅後淨利 ÷ 股數。這裡是今年度到最新一季的累計數字，代表每一股目前賺了多少錢。",
    "年化波動": "以每日股價變動換算成一年的波動幅度。越高代表價格上下起伏越大，持有時心理壓力也越大。",
    "ETF": "指數股票型基金，一次買進一籃子股票，可分散單一公司的風險；名稱常會說明它追蹤的主題，例如市值型、高股息。",
    "成交金額": "當天這檔股票成交的總金額。金額越大代表交易越熱絡，買賣也比較容易成交。",
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "product_type": {"type": "string", "enum": list(PRODUCT_TYPES)},
        "market": {"type": "string", "enum": list(MARKETS)},
        "industries": {"type": "array", "items": {"type": "string"}},
        "name_keywords": {"type": "array", "items": {"type": "string"}},
        "min_dividend_yield_pct": {"type": "number"},
        "max_pe_ratio": {"type": "number"},
        "max_pb_ratio": {"type": "number"},
        "min_revenue_yoy_pct": {"type": "number"},
        "min_eps": {"type": "number"},
        "volatility": {"type": "string", "enum": list(VOLATILITY)},
        "sort_by": {"type": "string", "enum": list(SORTS)},
        "interpretation": {"type": "string"},
        "unsupported": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["product_type", "market", "industries", "name_keywords", "volatility", "sort_by",
                 "interpretation", "unsupported"],
}

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "overall": {"type": "string"},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "symbol": {"type": "string"}, "explanation": {"type": "string"},
        }, "required": ["symbol", "explanation"]}},
    },
    "required": ["overall", "items"],
}


def _fmt(value: float) -> str:
    return f"{value:g}"


class AIPickerService:
    def __init__(self, *, market: MarketService, fundamentals, gemini, finmind):
        self.market = market
        self.fundamentals = fundamentals
        self.gemini = gemini
        self.finmind = finmind

    # ── data ───────────────────────────────────────────────────────────
    async def _data(self):
        """Market universe is required; fundamentals are optional (missing values simply fail numeric filters)."""
        if self.fundamentals is None:
            quotes, profiles = await self.market.universe()
            return quotes, profiles, {}
        universe, snapshots = await asyncio.gather(self.market.universe(), self.fundamentals.snapshots(),
                                                   return_exceptions=True)
        if isinstance(universe, Exception):
            raise universe
        quotes, profiles = universe
        return quotes, profiles, ({} if isinstance(snapshots, Exception) else snapshots)

    @staticmethod
    def _industry_catalog(profiles, snapshots) -> dict[str, str]:
        """TWSE industry code -> official industry name, derived from live data (no hard-coded list)."""
        catalog: dict[str, str] = {}
        for symbol, profile in profiles.items():
            name = getattr(snapshots.get(symbol), "industry_name", None)
            if profile.industry_code and name and profile.industry_code not in catalog:
                catalog[profile.industry_code] = name
        return catalog

    def _gemini_ready(self) -> bool:
        return bool(getattr(self.gemini, "available", False) and not getattr(self.gemini, "is_fixture", False)
                     and hasattr(self.gemini, "generate_json"))

    # ── step 1: understand ─────────────────────────────────────────────
    async def _plan_with_gemini(self, request: AIPickerRequest, catalog: dict[str, str]) -> dict[str, Any]:
        payload = {
            "user_request": request.query,
            "user_preferences": request.preferences,
            "industry_names": sorted(set(catalog.values())),
            "available_fields": {
                "product_type": "all／stock（個股）／etf",
                "market": "all／TWSE（上市）／TPEX（上櫃）",
                "industries": "只能從 industry_names 選",
                "name_keywords": "公司或 ETF 名稱必須包含的詞（例如 ETF 的「高股息」「台灣50」）",
                "min_dividend_yield_pct": "最低殖利率 %（只適用個股）",
                "max_pe_ratio": "最高本益比（倍，只適用個股）",
                "max_pb_ratio": "最高股價淨值比（倍，只適用個股）",
                "min_revenue_yoy_pct": "最新月營收年增率下限 %（只適用個股）",
                "min_eps": "今年度累計 EPS 下限（元，只適用個股）",
                "volatility": "近 6 個月年化波動：low<25%、medium 25–45%、high>45%",
                "sort_by": list(SORTS),
            },
        }
        prompt = (
            "把使用者的選股需求轉成篩選條件 JSON。規則：\n"
            "1. 只能使用 available_fields；industries 只能從 industry_names 原字選取。\n"
            "2. 無法用這些欄位表達的條件（例如 AI 概念、題材、外資買超、技術線型、未來股價）放進 unsupported，"
            "用一句白話說明為什麼目前做不到；不要自行推薦任何股票代號。\n"
            "3. 「ETF」→ product_type=etf；ETF 沒有殖利率、本益比與營收資料，高股息 ETF 用 name_keywords=['高股息']。\n"
            "4. 個股的「高股息／存股／穩定配息」可設 min_dividend_yield_pct（約 4）並以 dividend_yield 排序；"
            "「便宜／低估」可設 max_pe_ratio（約 15）；「成長」可設 min_revenue_yoy_pct（約 10）；"
            "「穩健／新手／保守」可設 volatility=low；未明確提到就不要設數值條件。\n"
            "5. 使用者沒有指定波動時，可參考 user_preferences.riskTolerance，但只有「較難接受」才設 low。\n"
            "6. interpretation：用一句白話告訴使用者你如何理解需求。\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        return await self.gemini.generate_json(
            prompt, schema=PLAN_SCHEMA, operation="picker_plan", temperature=0.1, max_output_tokens=600,
            system_instruction="你是台股選股條件解析器，只輸出 JSON，不給投資建議，不推薦特定股票。",
        )

    @staticmethod
    def _plan_with_rules(query: str, catalog: dict[str, str]) -> dict[str, Any]:
        text = query.lower()
        plan: dict[str, Any] = {"product_type": "all", "market": "all", "industries": [], "name_keywords": [],
                                "volatility": "any", "sort_by": "trade_value", "unsupported": []}
        consumed = set()

        def hit(*words):
            found = [word for word in words if word in text]
            consumed.update(found)
            return bool(found)

        if hit("etf"):
            plan["product_type"] = "etf"
        elif hit("個股", "股票", "公司"):
            plan["product_type"] = "stock"
        if hit("上櫃"):
            plan["market"] = "TPEX"
        elif hit("上市"):
            plan["market"] = "TWSE"
        if hit("高股息", "殖利率", "配息", "股息", "存股", "領息"):
            if plan["product_type"] == "etf":
                plan["name_keywords"].append("高股息")
            else:
                plan.update(min_dividend_yield_pct=4, sort_by="dividend_yield")
        if hit("低本益比", "本益比低", "本益比", "便宜", "低估"):
            plan.update(max_pe_ratio=15, sort_by="pe_ratio")
        if hit("淨值比"):
            plan.update(max_pb_ratio=1.5, sort_by="pb_ratio")
        if hit("成長", "年增", "營收"):
            plan.update(min_revenue_yoy_pct=10, sort_by="revenue_yoy")
        if hit("獲利", "賺錢", "eps"):
            plan.setdefault("min_eps", 0)
            if plan["sort_by"] == "trade_value":
                plan["sort_by"] = "eps"
        hit("大型", "權值", "龍頭", "熱門")  # already the default ranking: turnover (trade value)
        if hit("穩", "低波動", "保守", "新手", "安全"):
            plan["volatility"] = "low"
        elif hit("高波動", "飆"):
            plan["volatility"] = "high"
        for code, name in catalog.items():
            short = re.sub(r"(工業|業)$", "", name)
            if short and hit(short.lower()):
                plan["industries"].append(name)
        for alias, codes in INDUSTRY_CODES.items():
            if alias in text and not plan["industries"]:
                consumed.add(alias)
                plan["industries"].extend(catalog[code] for code in codes if code in catalog)
        leftover = text
        for word in sorted(consumed | GENERIC_QUERY_TERMS | {"推薦", "幫我找", "找", "有哪些", "的", "適合", "高", "低"}, key=len, reverse=True):
            leftover = leftover.replace(word, " ")
        plan["_leftover"] = [term for term in re.findall(r"[a-z0-9一-鿿]+", leftover) if len(term) >= 2]
        plan["interpretation"] = "以關鍵字規則解讀需求（AI 解析暫時不可用）"
        return plan

    def _validate_plan(self, raw: dict[str, Any], catalog: dict[str, str], names: list[str]) -> dict[str, Any]:
        plan = {
            "product_type": raw.get("product_type") if raw.get("product_type") in PRODUCT_TYPES else "all",
            "market": raw.get("market") if raw.get("market") in MARKETS else "all",
            "volatility": raw.get("volatility") if raw.get("volatility") in VOLATILITY else "any",
            "sort_by": raw.get("sort_by") if raw.get("sort_by") in SORTS else "trade_value",
            "interpretation": str(raw.get("interpretation") or "").strip()[:200],
            "unsupported": [str(item)[:160] for item in raw.get("unsupported") or [] if str(item).strip()][:5],
        }
        valid_names = {name: code for code, name in catalog.items()}
        plan["industries"], plan["industry_codes"] = [], []
        for name in raw.get("industries") or []:
            match = next((official for official in valid_names
                          if str(name) and (str(name) == official or re.sub(r"(工業|業)$", "", official) == str(name))), None)
            if match and match not in plan["industries"]:
                plan["industries"].append(match)
                plan["industry_codes"].append(valid_names[match])
            elif match is None:
                plan["unsupported"].append(f"「{name}」不是官方產業分類，未用於篩選")
        lowered_names = [name.lower() for name in names]
        keywords = []
        for keyword in list(raw.get("name_keywords") or []) + list(raw.get("_leftover") or []):
            keyword = str(keyword).strip()
            if not keyword or keyword in keywords:
                continue
            if any(keyword.lower() in name for name in lowered_names):
                keywords.append(keyword)
            else:
                plan["unsupported"].append(f"名稱中找不到「{keyword}」，未用於篩選")
        plan["name_keywords"] = keywords[:5]
        for field, (lower, upper) in NUMERIC_LIMITS.items():
            value = raw.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                plan[field] = round(min(upper, max(lower, float(value))), 2)
        if plan["product_type"] == "etf":
            dropped = [field for field in NUMERIC_LIMITS if field in plan]
            for field in dropped:
                plan.pop(field)
            if dropped:
                plan["unsupported"].append("ETF 沒有本益比、殖利率、營收與 EPS 的官方欄位，已改用名稱與波動條件")
            if plan["sort_by"] in {"dividend_yield", "pe_ratio", "pb_ratio", "revenue_yoy", "eps"}:
                plan["sort_by"] = "trade_value"
        plan["unsupported"] = list(dict.fromkeys(plan["unsupported"]))[:6]
        return plan

    # ── step 2: screen ─────────────────────────────────────────────────
    async def _screen(self, plan, quotes, profiles, snapshots, limit):
        funnel = [{"label": "官方日行情母體", "count": len(quotes)}]
        rows = []
        for quote in quotes:
            profile = profiles.get(quote.symbol)
            name = quote.name or (profile.short_name if profile else None) or quote.symbol
            is_etf = MarketService._is_etf(quote.symbol, name)
            if quote.close is None:
                continue
            rows.append({"quote": quote, "profile": profile, "name": name, "is_etf": is_etf,
                         "facts": fundamental_metrics(snapshots[quote.symbol]) if quote.symbol in snapshots else {}})

        def stage(label, keep):
            nonlocal rows
            rows = [row for row in rows if keep(row)]
            funnel.append({"label": label, "count": len(rows)})

        if plan.get("symbol_scope"):
            scope = set(plan["symbol_scope"])
            stage("被動元件（人工核對名單）", lambda row: row["quote"].symbol in scope)
        if plan["product_type"] != "all":
            stage("ETF" if plan["product_type"] == "etf" else "個股",
                  lambda row: row["is_etf"] == (plan["product_type"] == "etf"))
        if plan["market"] != "all":
            stage("上市" if plan["market"] == "TWSE" else "上櫃", lambda row: row["quote"].market == plan["market"])
        if plan["industry_codes"]:
            codes = set(plan["industry_codes"])
            stage("產業：" + "、".join(plan["industries"]),
                  lambda row: not row["is_etf"] and row["profile"] is not None and row["profile"].industry_code in codes)
        if plan["name_keywords"]:
            keywords = [keyword.lower() for keyword in plan["name_keywords"]]
            stage("名稱含：" + "、".join(plan["name_keywords"]), lambda row: any(k in row["name"].lower() for k in keywords))
        checks = [
            ("min_dividend_yield_pct", "dividend_yield_pct", "殖利率 ≥ {}%", lambda value, limit_: value >= limit_),
            ("max_pe_ratio", "pe_ratio", "本益比 ≤ {} 倍", lambda value, limit_: value <= limit_),
            ("max_pb_ratio", "pb_ratio", "股價淨值比 ≤ {} 倍", lambda value, limit_: value <= limit_),
            ("min_revenue_yoy_pct", "revenue_yoy_pct", "月營收年增 ≥ {}%", lambda value, limit_: value >= limit_),
            ("min_eps", "eps_ytd", "累計 EPS ≥ {} 元", lambda value, limit_: value >= limit_),
        ]
        for field, fact, label, ok in checks:
            if field in plan:
                threshold = plan[field]
                stage(label.format(_fmt(threshold)),
                      lambda row, fact=fact, ok=ok, threshold=threshold:
                      row["facts"].get(fact) is not None and ok(row["facts"][fact], threshold))
        if plan["product_type"] != "etf" and (plan["sort_by"] != "trade_value" or any(field in plan for field in NUMERIC_LIMITS)):
            stage(f"成交金額 ≥ {MIN_TRADE_VALUE_TWD // 10_000:,} 萬元（排除交易清淡標的）",
                  lambda row: (row["quote"].trade_value_twd or 0) >= MIN_TRADE_VALUE_TWD)
        if "min_dividend_yield_pct" in plan or plan["sort_by"] == "dividend_yield":
            stage(f"排除殖利率 > {MAX_PLAUSIBLE_YIELD_PCT:g}% 的異常值（多為一次性配發）",
                  lambda row: (row["facts"].get("dividend_yield_pct") or 0) <= MAX_PLAUSIBLE_YIELD_PCT)

        sort_key = {"trade_value": lambda row: row["quote"].trade_value_twd or 0,
                    "dividend_yield": lambda row: row["facts"].get("dividend_yield_pct", -1),
                    "pe_ratio": lambda row: row["facts"].get("pe_ratio", 1e9),
                    "pb_ratio": lambda row: row["facts"].get("pb_ratio", 1e9),
                    "revenue_yoy": lambda row: row["facts"].get("revenue_yoy_pct", -1e9),
                    "eps": lambda row: row["facts"].get("eps_ytd", -1e9),
                    "volatility": lambda row: row["quote"].trade_value_twd or 0}[plan["sort_by"]]
        _, descending = SORTS[plan["sort_by"]]
        rows.sort(key=sort_key, reverse=descending)

        needs_history = plan["volatility"] != "any" or plan["sort_by"] == "volatility"
        if needs_history and rows:
            shortlist = rows[:SHORTLIST]
            end = date.today()
            histories = await asyncio.gather(*(
                self.finmind.history(row["quote"].symbol, end - timedelta(days=HISTORY_DAYS), end) for row in shortlist
            ), return_exceptions=True)
            for row, history in zip(shortlist, histories):
                if not isinstance(history, Exception):
                    metrics = price_metrics(history)
                    row["facts"].update({key: metrics[key] for key in ("annualized_volatility_pct", "period_return_pct",
                                         "max_drawdown_pct", "period_start", "period_end") if metrics.get(key) is not None})
            rows = shortlist
            funnel.append({"label": f"取前 {len(shortlist)} 檔計算近 6 個月波動", "count": len(rows)})
            band = VOLATILITY.get(plan["volatility"])
            measured = [row for row in rows if row["facts"].get("annualized_volatility_pct") is not None]
            if band:
                lower, upper = band
                stage(VOLATILITY_LABEL[plan["volatility"]], lambda row: row["facts"].get("annualized_volatility_pct") is not None
                      and lower <= row["facts"]["annualized_volatility_pct"] < upper)
                if not rows and measured:
                    # Never silently return nothing: show the closest matches and say the condition was relaxed.
                    target = {"low": 0.0, "medium": (lower + upper) / 2, "high": 1000.0}[plan["volatility"]]
                    rows = sorted(measured, key=lambda row: abs(row["facts"]["annualized_volatility_pct"] - target))
                    plan["relaxed"] = (f"目前沒有標的符合「{VOLATILITY_LABEL[plan['volatility']]}」，"
                                       "改列出波動最接近條件的標的，請留意它們並未完全符合。")
                    funnel.append({"label": "放寬：改列最接近條件者", "count": len(rows)})
            if plan["sort_by"] == "volatility":
                rows.sort(key=lambda row: row["facts"].get("annualized_volatility_pct", 1e9))
        return rows[:limit], funnel

    # ── step 3: reasons ────────────────────────────────────────────────
    @staticmethod
    def _reasons(row, plan, rank, catalog) -> list[str]:
        quote, facts = row["quote"], row["facts"]
        market = "上市" if quote.market == "TWSE" else "上櫃" if quote.market == "TPEX" else quote.market
        industry = catalog.get(row["profile"].industry_code) if row["profile"] and row["profile"].industry_code else None
        reasons = [f"{'ETF' if row['is_etf'] else '股票'}・{market}" + (f"・{industry}" if industry else "")]
        if plan["name_keywords"]:
            reasons.append("名稱符合「" + "、".join(k for k in plan["name_keywords"] if k.lower() in row["name"].lower()) + "」")
        if "min_dividend_yield_pct" in plan:
            reasons.append(f"殖利率 {facts['dividend_yield_pct']}%（條件 ≥ {_fmt(plan['min_dividend_yield_pct'])}%，{facts.get('valuation_date')}）")
        if "max_pe_ratio" in plan:
            reasons.append(f"本益比 {facts['pe_ratio']} 倍（條件 ≤ {_fmt(plan['max_pe_ratio'])} 倍）")
        if "max_pb_ratio" in plan:
            reasons.append(f"股價淨值比 {facts['pb_ratio']} 倍（條件 ≤ {_fmt(plan['max_pb_ratio'])} 倍）")
        if "min_revenue_yoy_pct" in plan:
            reasons.append(f"{facts.get('revenue_month')} 月營收年增 {facts['revenue_yoy_pct']}%（條件 ≥ {_fmt(plan['min_revenue_yoy_pct'])}%）")
        if "min_eps" in plan:
            reasons.append(f"{facts.get('eps_period')} EPS {facts['eps_ytd']} 元（條件 ≥ {_fmt(plan['min_eps'])} 元）")
        if facts.get("annualized_volatility_pct") is not None and plan["volatility"] != "any":
            lower, upper = VOLATILITY[plan["volatility"]]
            fits = lower <= facts["annualized_volatility_pct"] < upper
            reasons.append(f"近 6 個月年化波動 {facts['annualized_volatility_pct']}%，"
                           + (f"屬{VOLATILITY_LABEL[plan['volatility']]}" if fits else f"未達{VOLATILITY_LABEL[plan['volatility']]}（放寬後列入）"))
        label, descending = SORTS[plan["sort_by"]]
        reasons.append(f"依{label}{'由高到低' if descending else '由低到高'}排序第 {rank}")
        if row["is_etf"] and LEVERAGED_ETF.search(row["quote"].symbol + " " + row["name"]):
            reasons.append("⚠ 槓桿或反向型 ETF：每日重新平衡，長期持有的報酬可能明顯偏離指數，較不適合新手長期持有")
        return reasons

    # ── step 4: explain ────────────────────────────────────────────────
    async def _explain(self, request, plan, items, usages: list | None = None):
        facts = [{"symbol": item["symbol"], "name": item["name"], "product_type": item["product_type"],
                  "reasons": item["reasons"], "facts": item["facts"]} for item in items]
        prompt = (
            "以下是程式依官方資料篩選出的結果。請用繁體中文、對第一次投資的新手說明：\n"
            "overall：2–3 句說明這次的篩選邏輯，以及新手該怎麼解讀這些條件與限制。\n"
            "items：每檔 1–2 句白話說明它為什麼出現在清單、這些數字代表什麼、要留意什麼。\n"
            "只能原樣引用 facts 與 reasons 中的數字，一律使用與資料相同的阿拉伯數字（例如 11.1%），"
            "不得改寫成中文數字、換算、推算或新增數字；不得使用「買進」「賣出」「推薦」等指令式用語；"
            "不得預測股價。\n"
            + json.dumps({"request": request.query, "plan": {k: v for k, v in plan.items() if k != "industry_codes"},
                          "explanation_style": request.preferences.get("explanationStyle"), "results": facts},
                         ensure_ascii=False, default=str)
        )
        generated = await self.gemini.generate_json(
            prompt, schema=EXPLAIN_SCHEMA, operation="picker_explain", temperature=0.3, max_output_tokens=1200,
            system_instruction="你是投資教育助理，只解釋已提供的官方數據，不提供投資建議。",
        )
        if usages is not None:
            usages.append(generated.get("_usage"))
        allowed = _number_tokens({"plan": plan, "results": facts})
        rejected = []
        overall, dropped, _ = validated_sentences(generated.get("overall"), allowed)
        rejected.extend(dropped)
        by_symbol = {}
        for row in generated.get("items") or []:
            if isinstance(row, dict) and row.get("symbol") in {item["symbol"] for item in items}:
                text, dropped, _ = validated_sentences(row.get("explanation"), allowed)
                rejected.extend(dropped)
                if text:
                    by_symbol[row["symbol"]] = text
        return overall, by_symbol, rejected

    # ── orchestration ──────────────────────────────────────────────────
    async def select(self, request: AIPickerRequest) -> dict[str, Any]:
        trace = []
        started = time.perf_counter()

        def step(agent, action, detail, status="completed", **metadata):
            trace.append({"agent": agent, "action": action, "detail": detail, "status": status,
                          "elapsed_ms": round((time.perf_counter() - started) * 1000), "metadata": metadata})

        quotes, profiles, snapshots = await self._data()
        catalog = self._industry_catalog(profiles, snapshots)
        step("Data Agent", "載入官方資料", f"日行情 {len(quotes)} 檔、估值與財務 {len(snapshots)} 檔、官方產業 {len(catalog)} 類",
             sources=["TWSE", "TPEx", "MOPS"])

        source = "rules"
        usages: list = []
        if self._gemini_ready():
            try:
                raw = await self._plan_with_gemini(request, catalog)
                usages.append(raw.pop("_usage", None))
                source = "gemini"
            except PreviewLimitError as exc:
                raw = self._plan_with_rules(request.query, catalog)
                step("Planner Agent", "AI 解析需求", f"Gemini 額度已達上限，改用關鍵字規則：{exc}", "failed")
            except Exception as exc:
                raw = self._plan_with_rules(request.query, catalog)
                step("Planner Agent", "AI 解析需求", f"Gemini 解析失敗，改用關鍵字規則：{exc}", "failed")
        else:
            raw = self._plan_with_rules(request.query, catalog)
        plan = self._validate_plan(raw, catalog, [row.name or "" for row in quotes])
        # 「被動元件」不是交易所產業分類；AI 或關鍵字規則常把它對到範圍很大的「電子零組件業」。
        # 改用與一般篩選相同的人工核對名單，兩種篩選結果一致。
        if "被動元件" in request.query:
            plan["industries"], plan["industry_codes"] = [], []
            plan["symbol_scope"] = sorted(PASSIVE_COMPONENT_REFERENCES)
            plan["unsupported"] = [item for item in plan["unsupported"] if "被動元件" not in item]
        plan["source"] = source
        step("Planner Agent", "理解需求並轉成條件", plan["interpretation"] or "已轉成篩選條件",
             source=source, unsupported=plan["unsupported"])

        items_rows, funnel = await self._screen(plan, quotes, profiles, snapshots, request.limit)
        step("Screening Agent", "依官方資料篩選與排序", " → ".join(f"{stage['label']} {stage['count']}" for stage in funnel),
             funnel=funnel)

        items = []
        for rank, row in enumerate(items_rows, start=1):
            quote = row["quote"]
            reasons = self._reasons(row, plan, rank, catalog)
            items.append({
                "symbol": quote.symbol, "name": row["name"], "market": quote.market,
                "product_type": "etf" if row["is_etf"] else "stock",
                "industry": catalog.get(row["profile"].industry_code) if row["profile"] and row["profile"].industry_code else None,
                "quote": quote.model_dump(mode="json"), "facts": row["facts"],
                "reasons": reasons, "explanation": None,
                "selection_reason": "；".join(reasons[1:]) or reasons[0],
            })
        step("Explain Agent", "產生每檔理由", f"{len(items)} 檔，理由全部由程式依實際數值產生")

        overall, rejected = None, []
        if request.explain and items and self._gemini_ready():
            try:
                overall, explanations, rejected = await self._explain(request, plan, items, usages)
                for item in items:
                    item["explanation"] = explanations.get(item["symbol"])
                step("Explain Agent", "白話解說", f"Gemini 解說已逐句核對數字，移除 {len(rejected)} 句無法對應資料的內容",
                     rejected_sentences=rejected[:5])
            except Exception as exc:
                step("Explain Agent", "白話解說", f"略過 AI 白話解說：{exc}", "skipped")

        terms = {"成交金額"}
        if plan["product_type"] == "etf" or any(item["product_type"] == "etf" for item in items):
            terms.add("ETF")
        for field, term in (("min_dividend_yield_pct", "殖利率"), ("max_pe_ratio", "本益比"), ("max_pb_ratio", "股價淨值比"),
                            ("min_revenue_yoy_pct", "月營收年增率"), ("min_eps", "EPS")):
            if field in plan:
                terms.add(term)
        if plan["volatility"] != "any":
            terms.add("年化波動")
        sort_terms = {"dividend_yield": "殖利率", "pe_ratio": "本益比", "pb_ratio": "股價淨值比",
                      "revenue_yoy": "月營收年增率", "eps": "EPS", "volatility": "年化波動"}
        if plan["sort_by"] in sort_terms:
            terms.add(sort_terms[plan["sort_by"]])

        return {
            "query": request.query,
            "plan": {key: value for key, value in plan.items() if key != "industry_codes"},
            "funnel": funnel, "items": items, "overall_explanation": overall,
            "glossary": [{"term": term, "explanation": GLOSSARY[term]} for term in GLOSSARY if term in terms],
            "tokens": sum(int((usage or {}).get("total_token_count") or (usage or {}).get("total_tokens") or 0) for usage in usages),
            "trace": trace, "data_frequency": "daily",
            "notice": "篩選與排序完全由程式依官方日資料計算；AI 只負責理解需求與白話解說，不是買賣建議。",
        }
