from __future__ import annotations

import re
import unicodedata
from calendar import monthrange
from datetime import date
from difflib import SequenceMatcher
from typing import Iterable

from pypinyin import Style, lazy_pinyin

from ..core.models import (
    CompanyProfile, InputCandidate, InputConstraint, InputHypothesis,
    InputUnderstandingRequest, InputUnderstandingResponse,
)


GENERIC_TERMS = {
    "請", "請問", "幫我", "想知道", "想了解", "研究", "分析", "看看", "查詢", "幫忙",
    "最近", "近期", "表現", "怎樣", "怎麼樣", "如何", "的", "在", "於", "公司", "股票", "標的", "個股",
    "未來", "展望", "預測", "走勢", "風險", "報酬", "波動", "一下", "呢", "嗎", "呀", "啊",
    # 「值得」與個股「直得」同音，不移除會被讀音比對誤認成股票。
    "值得",
}
INDUSTRY_TERMS = {
    "半導體", "ai伺服器", "伺服器", "電動車", "生技", "醫療", "金融", "航運", "etf", "高股息",
    "電子", "電力", "能源", "消費", "市值型", "產業", "台股", "市場", "被動元件", "pcb",
    "ic載板", "載板", "散熱", "矽光子", "記憶體", "光通訊", "網通", "電池", "機器人", "面板",
}
CONSTRAINT_PATTERNS = (
    (re.compile(r"風險(?:不要|別)?太?高|低風險"), "風險偏低"),
    (re.compile(r"中等風險|風險中等"), "風險中等"),
    (re.compile(r"高股息|配息"), "偏好股息"),
    (re.compile(r"不要etf|排除etf", re.I), "排除 ETF"),
)

FULL_RESEARCH_PATTERN = re.compile(r"完整研究|深入研究|建立研究|開始研究|跑一份研究|研究報告")
REPHRASE_PATTERN = re.compile(r"換個說法|再解釋|重新解釋|重新說明|用白話|講白話|白話一點|簡單一點|說清楚一點")
COMPARE_PATTERN = re.compile(r"比較|相比|對比|差異|哪(?:個|一個|檔|一檔)|兩檔|兩家|(?:和|跟|與).{0,20}(?:比|差在哪|有何不同|有什麼不同)")
KNOWLEDGE_PATTERN = re.compile(r"是什麼|什麼是|為什麼|怎麼看|教我|解釋|意思是|如何計算|差在哪|有何不同|有什麼不同|有什麼差別|區別")
DECISION_PATTERN = re.compile(r"值得(?:買|投資|持有)|可以買|適合(?:買|投資|長期持有)|該不該|要不要買|能不能買|買進|進場|加碼|減碼|賣出|停損|長期持有")
VALUATION_PATTERN = re.compile(r"合理價|估值|高估|低估|便宜|昂貴|本益比|股價淨值比|殖利率|值多少")
RISK_PATTERN = re.compile(r"風險|利多|利空|多空|上漲原因|下跌原因|催化劑|不利因素")
TARGET_PATTERN = re.compile(r"目標價|漲回|跌回|漲到|跌到|上看|下看|突破|跌破|有機會.{0,12}(?:到|回)")
SWITCH_TARGET_PATTERN = re.compile(r"先不要看|不要看|改(?:研究|看|成)|換(?:研究|看|成)|切換(?:到|成)?")
MARKET_INTENTS = {
    "investment_decision", "target_price_scenario", "valuation", "risk_analysis",
    "compare", "full_research", "research", "screen", "track",
}
ETF_DEFAULT_GROUPS = {
    "generic": ["0050", "0056", "00878"],
    "high_dividend": ["0056", "00878", "00919"],
    "semiconductor": ["00891", "00927", "0052"],
    "alternate": ["006208", "00713", "00919"],
}
PLANNING_PATTERN = re.compile(r"存到|存錢|存款目標|退休金|退休規劃|財務規劃|資產累積|每月投入")
CONCEPT_PATTERN = re.compile(r"本益比|股價淨值比|殖利率|roe|eps|etf.{0,8}個股|個股.{0,8}etf|定期定額|交易稅|手續費", re.I)
# 指「使用者已經持有的部位」才算；「可以／適合／該持有哪種股票」是在問類型，不是要讀持股。
PORTFOLIO_WITHOUT_SYMBOL_PATTERN = re.compile(
    r"(?<!可以)(?<!適合)(?<!應該)(?<!建議)(?<!長期)(?<![可該要能])"
    r"(?:目前|我的|我現在)?(?:持有|持股|庫存|投資組合)(?:的)?(?:股票|標的|部位)?"
)
# 同音比對時，句子裡的日常用語不能當成打錯的公司名（「我適合買什麼」的 適合 shihe ≠ 世禾）。
COMMON_PHRASES = {
    "適合", "是否", "時候", "什麼", "市場", "事情", "世界", "實際", "收益", "需要", "現在", "可以", "公司",
    "股票", "投資", "風險", "新手", "長期", "短期", "推薦", "建議", "報酬", "比較", "分析", "價格", "成長",
    "穩定", "配息", "獲利", "未來", "最近", "應該", "知道", "問題", "資料", "偏好", "持有", "賺錢", "虧損",
    "便宜", "安全", "選擇", "方式", "類型", "怎麼", "如何", "為何", "時機", "趨勢", "產業", "表現",
}
COMPARE_SPLIT = re.compile(r"[和跟與及、,，/]|vs|VS|比較|對比|相比|差在哪|差別|哪個|哪一個|有什麼|誰比較|\s+")


def _homophone_targets(fragment: str, profiles, exclude: set[str]) -> list[InputCandidate]:
    """片段讀音和公司名稱完全相同、且至少有一個字相同時，視為打錯字（復喬→富喬、台機電→台積電）。"""
    fragment_pinyin = _pinyin(fragment)
    found: list[InputCandidate] = []
    if not fragment_pinyin:
        return found
    for profile in profiles:
        if profile.symbol in exclude:
            continue
        for alias, kind in _company_aliases(profile):
            if kind == "symbol" or len(alias) < 2 or not set(alias) & set(fragment):
                continue
            if _pinyin(alias) == fragment_pinyin:
                candidate = _profile_candidate(profile, alias, "phonetic", 0.96)
                candidate.typed_text = fragment
                found.append(candidate)
                break
    return found


# 問題明確要依「我的偏好」回答時，交給助手用已保存的個人化偏好，不當成要讀持股。
PREFERENCE_REQUEST_PATTERN = re.compile(r"偏好|個人化|風險承受|我的(?:條件|設定|狀況)|我適合|適合我")
THEME_MARKER_PATTERN = re.compile(r"產業|供應鏈|產業鏈|族群|類股|市場趨勢|相關領域|相關公司")
THEME_DOMAIN_PATTERN = re.compile(
    r"半導體|被動元件|電子零組件|pcb|印刷電路板|ic載板|載板|伺服器|散熱|矽光子|記憶體|"
    r"光通訊|網通|電動車|電池|機器人|面板|生技|醫療|金融|航運|能源|太陽能|風電|消費電子",
    re.I,
)
THEME_OUTLOOK_PATTERN = re.compile(r"機會|風險|發展|前景|趨勢|需求|供需|景氣|循環|競爭|成長動能")
MARKET_TREND_PATTERN = re.compile(r"(?:台股|大盤|市場).{0,12}(?:趨勢|展望|走勢|風險|機會)")


def normalize_input(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff-]+", "", value)


def _chinese_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value == "十":
        return 10
    if "十" in value:
        left, right = value.split("十", 1)
        return (digits.get(left, 1) * 10) + digits.get(right, 0)
    if value and all(char in digits for char in value):
        return int("".join(str(digits[char]) for char in value))
    return None


def _subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def parse_period(text: str, *, default_months: int = 6, today: date | None = None) -> tuple[dict, dict | None]:
    """Parse historical observation separately from future outlook."""
    today = today or date.today()
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    future = bool(re.search(r"未來|展望|預測|接下來", compact))
    if future and (historical_clause := re.search(r"(?:歷史|觀察|回顧|過去)(.+)$", compact)):
        clause = historical_clause.group(1)
        if re.search(r"半年|一年|(?:\d{1,3}|[零〇一二兩两三四五六七八九十]{1,4})(?:個月|月|年)", clause):
            historical, _ = parse_period(clause, default_months=default_months, today=today)
            return historical, {"label": "未來展望（與歷史觀察期間分開）", "kind": "future_outlook"}
    year_match = re.search(r"(?<!\d)((?:19|20)\d{2})年", compact)
    if year_match:
        year = int(year_match.group(1))
        if year <= today.year and not future:
            end = today if year == today.year else date(year, 12, 31)
            return ({"label": f"{year} 年", "start": date(year, 1, 1).isoformat(), "end": end.isoformat(),
                     "defaulted": False, "kind": "calendar_year"}, None)
        outlook = {"label": f"{year} 年未來展望", "year": year, "kind": "future_outlook"}
        start = _subtract_months(today, default_months)
        return ({"label": f"預設近 {default_months} 個月（展望的歷史依據）", "start": start.isoformat(),
                 "end": today.isoformat(), "defaulted": True, "kind": "relative"}, outlook)

    number = r"\d{1,3}|[零〇一二兩两三四五六七八九十]{1,4}"
    range_match = re.search(rf"({number})[\-–—~～到至]({number})(個月|月|年)", compact)
    single_match = re.search(rf"(?:近|最近)?({number})(個月|月|年)", compact)
    months = None
    if range_match:
        amount = _chinese_number(range_match.group(2))
        unit = range_match.group(3)
        if amount:
            months = amount * (12 if unit == "年" else 1)
    elif single_match:
        amount = _chinese_number(single_match.group(1))
        unit = single_match.group(2)
        if amount:
            months = amount * (12 if unit == "年" else 1)
    elif "半年" in compact:
        months = 6
    elif "一年" in compact:
        months = 12

    applied = max(1, min(months or default_months, 120))
    defaulted = months is None
    label = f"預設近 {applied} 個月" if defaulted else (f"近 {applied // 12} 年" if applied % 12 == 0 else f"近 {applied} 個月")
    historical = {"label": label, "start": _subtract_months(today, applied).isoformat(), "end": today.isoformat(),
                  "defaulted": defaulted, "kind": "relative"}
    outlook = {"label": "未來展望（不作為已發生的歷史資料）", "kind": "future_outlook"} if future else None
    return historical, outlook


def _pinyin(value: str) -> str:
    return "".join(lazy_pinyin(value, style=Style.NORMAL, errors=lambda chars: list(chars))).lower()


def _company_aliases(profile: CompanyProfile) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for kind, value in (("official_name", profile.name), ("short_name", profile.short_name)):
        normalized = normalize_input(value or "")
        if normalized:
            result.append((normalized, kind))
        stripped = re.sub(r"(股份)?有限公司$", "", normalized)
        if stripped and stripped != normalized:
            result.append((stripped, "alias"))
    result.append((profile.symbol.lower(), "symbol"))
    return list(dict.fromkeys(result))


GENERAL_HOWTO_PATTERN = re.compile(
    r"新手|入門|第一次(?:投資|買)|怎麼(?:開始|買|投資|存)|如何(?:開始|買|投資|存)|要先做什麼|小資|零股|定期定額|定額|存股|開戶|小額"
)
# 「我有 1000 塊」「每月 3000 元」是可投入的錢，不是目標股價。
BUDGET_CONTEXT = re.compile(r"(?:我有|只有|手上有|手邊有|預算|資金|本金|可投入|打算投入|投入|每月|每個月|一個月|月薪|薪水|存了?|拿)\s*(?:約|大概|大約)?\s*$")


def _price_hypotheses(text: str) -> list[InputHypothesis]:
    """Extract user-supplied price assumptions without treating codes or years as quotes."""
    compact = unicodedata.normalize("NFKC", text)
    number = r"([0-9][0-9,]*(?:\.[0-9]+)?)"
    patterns = (
        ("price_target", re.compile(rf"(?:目標價|合理價|上看|下看|有機會.{{0,12}}(?:漲|跌|到|回)|漲回|跌回).{{0,8}}?{number}\s*(?:元|塊)?")),
        ("price_scenario", re.compile(rf"(?:如果|假設|若|跌到|漲到|跌破|突破).{{0,12}}?{number}\s*(?:元|塊)?")),
        ("price_scenario", re.compile(rf"{number}\s*(?:元|塊)(?:時|的話|附近|以下|以上)?")),
    )
    found: list[InputHypothesis] = []
    seen_values: set[float] = set()
    for kind, pattern in patterns:
        for match in pattern.finditer(compact):
            raw_number = next((group for group in match.groups() if group and re.fullmatch(r"[0-9][0-9,]*(?:\.[0-9]+)?", group)), None)
            if raw_number is None:
                continue
            value = float(raw_number.replace(",", ""))
            if value <= 0 or (1900 <= value <= 2100 and "元" not in match.group(0)):
                continue
            number_at = compact.find(raw_number, match.start())
            if BUDGET_CONTEXT.search(compact[max(0, number_at - 8):number_at]):
                continue
            if value in seen_values:
                continue
            seen_values.add(value)
            found.append(InputHypothesis(type=kind, value=value, raw_text=match.group(0).strip()))
    return found[:4]


def _structured_constraints(text: str, labels: list[str]) -> list[InputConstraint]:
    result = [InputConstraint(type="risk_preference", value=label, raw_text=label) for label in labels]
    amount = r"([0-9][0-9,]*(?:\.[0-9]+)?|[零〇一二兩两三四五六七八九十]{1,4})"
    for match in re.finditer(rf"(?:我有|只有|手上有|預算(?:是|約|有)?|資金(?:是|約|有)?|本金|可投入|打算投入|每月|每個月)\s*(?:約|大概)?\s*{amount}\s*(萬)?\s*(?:元|塊)", unicodedata.normalize("NFKC", text)):
        raw = match.group(1)
        value = float(raw.replace(",", "")) if re.fullmatch(r"[0-9][0-9,]*(?:\.[0-9]+)?", raw) else _chinese_number(raw)
        if value is None or value <= 0:
            continue
        if match.group(2):
            value *= 10000
        result.append(InputConstraint(
            type="budget", value=float(value), unit="TWD", raw_text=match.group(0).strip(),
        ))
    return result[:8]


def _explicit_codes(text: str) -> list[str]:
    neutralized = re.sub(r"(?:19|20)\d{2}\s*年", " ", unicodedata.normalize("NFKC", text))
    neutralized = re.sub(r"[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:[萬億]\s*(?:元|塊)?|元|塊)", " ", neutralized)
    # ETF 代號可能以英文結尾（00981A、00631L）；一般代號沿用純數字規則。
    return [code.upper() for code in re.findall(r"(?<!\d)(00\d{2,4}[A-Za-z](?![0-9A-Za-z])|\d{4,6}(?!\d))", neutralized)]


def _intent(text: str, hypotheses: list[InputHypothesis]) -> tuple[str, list[str]]:
    """Classify with ordered semantic signals, not a single keyword match."""
    lowered = unicodedata.normalize("NFKC", text).lower()
    # 存錢、退休這類個人財務規劃沒有特定標的；不可把金額當目標價，也不可去比對公司名稱。
    if PLANNING_PATTERN.search(lowered) and "買" not in lowered and not _explicit_codes(text):
        return "explain", ["personal_finance_planning"]
    signals: list[str] = []
    if FULL_RESEARCH_PATTERN.search(lowered):
        return "full_research", ["explicit_full_research"]
    if REPHRASE_PATTERN.search(lowered):
        return "rephrase", ["rephrase_request"]
    if (KNOWLEDGE_PATTERN.search(lowered)
            and re.search(r"(?:etf.*個股|個股.*etf)", lowered, re.I)
            and not DECISION_PATTERN.search(lowered)):
        return "explain", ["general_knowledge_question", "concept_comparison"]
    if re.search(r"(?:分析|研究|比較|找|推薦).{0,8}(?:\d+|[一二三四五六七八九十兩]+)檔.{0,8}etf", lowered, re.I):
        return "compare", ["multi_etf_request"]
    if re.search(r"不是.{0,12}(?:檔|個|這些)|換成其他\s*etf|改成.{0,12}etf|我要.{0,12}etf", lowered, re.I):
        return "compare", ["selection_correction"]
    if COMPARE_PATTERN.search(lowered):
        signals.append("comparison_language")
        if re.search(r"適合|持有|投資|買", lowered):
            signals.append("decision_language")
        return "compare", signals
    if KNOWLEDGE_PATTERN.search(lowered) and not DECISION_PATTERN.search(lowered) and not TARGET_PATTERN.search(lowered):
        return "explain", ["general_knowledge_question"]
    if hypotheses or TARGET_PATTERN.search(lowered):
        signals.append("user_price_hypothesis" if hypotheses else "target_price_language")
        if re.search(r"未來|有機會|如果|假設|若", lowered):
            signals.append("scenario_language")
        return "target_price_scenario", signals
    if DECISION_PATTERN.search(lowered):
        signals.append("investment_action_language")
        if re.search(r"現在|近期|未來|長期", lowered):
            signals.append("time_context")
        return "investment_decision", signals
    if VALUATION_PATTERN.search(lowered):
        return "valuation", ["valuation_language"]
    if RISK_PATTERN.search(lowered):
        return "risk_analysis", ["risk_or_catalyst_language"]
    if re.search(r"選股|推薦|找.*股|候選|值得關注的股票|有哪些.{0,8}股票|關注.{0,8}股票", lowered):
        return "screen", ["screening_language"]
    if re.search(r"追蹤|監控", lowered):
        return "track", ["tracking_language"]
    if THEME_MARKER_PATTERN.search(lowered) or (THEME_DOMAIN_PATTERN.search(lowered) and THEME_OUTLOOK_PATTERN.search(lowered)):
        return "research", ["research_language", "theme_language"]
    if re.search(r"研究|分析|表現|走勢|報酬|波動|展望", lowered):
        return "research", ["research_language"]
    return "unknown", []


def _is_theme_query(normalized: str, explicit_codes: list[str]) -> bool:
    """Keep industry/theme discovery questions from becoming one alias match.

    For example, 「台灣半導體產業有哪些公司」 contains the listed company
    alias 「台灣半導體」, but the user's target is the industry rather than 5425.
    An explicit code remains authoritative.
    """
    if explicit_codes:
        return False
    has_domain = bool(THEME_DOMAIN_PATTERN.search(normalized))
    has_marker = bool(THEME_MARKER_PATTERN.search(normalized))
    asks_for_scope = bool(re.search(r"產業|供應鏈|產業鏈|族群|類股|有哪些|哪幾|相關公司|機會|風險|趨勢|需求|景氣|循環|前景|發展", normalized))
    return has_marker or (has_domain and asks_for_scope)


COUNT_PATTERN = re.compile(r"(\d{1,2}|[一二三四五六七八九十兩两]{1,3})\s*(?:檔|家|支|隻)")


def requested_count(text: str, *, maximum: int = 5) -> int | None:
    """使用者指定的研究檔數（「三檔」「3 家」「兩支」），限制在 1～maximum；沒指定回傳 None。"""
    match = COUNT_PATTERN.search(unicodedata.normalize("NFKC", text or ""))
    if not match:
        return None
    value = _chinese_number(match.group(1))
    return max(1, min(maximum, value)) if value else None


def strip_count(text: str) -> str:
    """主題名稱去掉檔數（「三檔半導體產業」→「半導體產業」）。"""
    return COUNT_PATTERN.sub("", text or "").strip()


def _research_topic(text: str) -> str | None:
    """Extract a topic label without pretending it is an official company."""
    value = strip_count(unicodedata.normalize("NFKC", text).strip())
    value = re.sub(r"^[\s，,。.!！?？]*(?:請|幫我|想請你|可以)?\s*(?:先)?\s*(?:研究|分析|評估|整理|比較)?\s*", "", value, flags=re.I)
    value = re.sub(r"^(?:先不要看.+?[，,。]\s*)?(?:改成|換成|改研究|改看)\s*", "", value)
    value = re.sub(
        r"(?:的)?(?:未來)?(?:機會|主要風險|風險|發展|前景|趨勢|需求|供需|景氣循環|景氣|競爭|成長動能).*$",
        "", value,
    )
    value = re.sub(r"(?:有哪些|哪幾家)?(?:值得研究)?(?:的)?(?:相關公司|公司|標的)[?？。.!！]*$", "", value)
    value = value.strip(" ，,。.!！?？：:")
    return value[:120] or None


def _research_type(normalized: str, intent: str, explicit_codes: list[str]) -> str:
    if _is_theme_query(normalized, explicit_codes):
        return "industry_supply_chain"
    if MARKET_TREND_PATTERN.search(normalized):
        return "market_trend"
    if intent == "screen":
        return "stock_screen"
    if intent in {"explain", "rephrase"}:
        return "knowledge"
    if "etf" in normalized:
        return "multi_target_comparison" if intent == "compare" else "etf"
    if intent == "compare":
        return "multi_target_comparison"
    if explicit_codes:
        return "single_company"
    return "unknown"


def _requested_etf_count(normalized: str) -> int | None:
    match = re.search(r"(?:分析|研究|比較|找|推薦)?.{0,6}(\d+|[一二三四五六七八九十兩]+)檔.{0,8}etf", normalized)
    if not match:
        return None
    return _chinese_number(match.group(1))


def _etf_default_symbols(normalized: str, explicit_codes: list[str]) -> tuple[list[str], str] | None:
    count = _requested_etf_count(normalized)
    is_correction = bool(re.search(r"不是.{0,10}(?:檔|個|這些)|其他etf|換成|改成", normalized))
    if explicit_codes or "etf" not in normalized or (count is None and not is_correction):
        return None
    if "半導體" in normalized:
        group, reason = "semiconductor", "以三檔不同發行商的台灣半導體主題 ETF 作為可修改的比較起點"
    elif "高股息" in normalized or "配息" in normalized:
        group, reason = "high_dividend", "以三檔具代表性的台股高股息 ETF 作為可修改的比較起點"
    elif is_correction and "其他" in normalized:
        group, reason = "alternate", "已排除上一組常用範例，改用另一組不同策略 ETF 作為比較起點"
    else:
        group, reason = "generic", "以市值型與高股息策略的代表性 ETF 作為可修改的比較起點"
    requested = max(2, min(count or 3, 3))
    return ETF_DEFAULT_GROUPS[group][:requested], reason


def _is_broad_discovery_query(normalized: str, intent: str, explicit_codes: list[str]) -> bool:
    if explicit_codes or intent not in {"screen", "research"}:
        return False
    return bool(re.search(r"產業|供應鏈|族群|類股|市場|有哪些|哪幾|幾檔|值得關注|候選|推薦", normalized))


def _target_fragment(text: str) -> str:
    value = normalize_input(text)
    value = re.sub(r"(?:19|20)\d{2}年", "", value)
    value = re.sub(r"\d{1,3}(?:個月|月|年)", "", value)
    value = re.sub(r"\d+(?:萬)?(?:元|塊)", "", value)
    value = SWITCH_TARGET_PATTERN.sub("", value)
    for term in sorted(GENERIC_TERMS | INDUSTRY_TERMS, key=len, reverse=True):
        value = value.replace(normalize_input(term), "")
    return re.sub(r"^(?:近|最近)+|(?:近|最近)+$", "", value)


def _homophone_of_longer_name(text: str, matched: str, profiles, chosen_symbol: str):
    """短名稱完全符合，但連同後面的字其實是另一家長名稱的同音錯字時（聯發客 → 聯發科）回傳該公司。"""
    position = text.find(matched)
    if position < 0:
        return None
    for profile in profiles:
        if profile.symbol == chosen_symbol:
            continue
        for alias, kind in _company_aliases(profile):
            offset = alias.find(matched) if kind != "symbol" and len(alias) > len(matched) else -1
            start = position - offset
            if offset < 0 or start < 0:
                continue
            typed = text[start:start + len(alias)]
            if len(typed) == len(alias) and typed != alias and _pinyin(typed) == _pinyin(alias):
                return profile, alias, typed
    return None


def _typed_part(fragment: str, alias: str) -> str:
    """在輸入片段中找出和公司名稱長度相同、讀音最接近的幾個字（國劇投資 → 國劇）。"""
    size = len(alias)
    if len(fragment) <= size:
        return fragment
    target = _pinyin(alias)
    windows = [fragment[index:index + size] for index in range(len(fragment) - size + 1)]
    return max(windows, key=lambda part: SequenceMatcher(None, _pinyin(part), target).ratio())


def _profile_candidate(profile: CompanyProfile, alias: str, kind: str, score: float) -> InputCandidate:
    return InputCandidate(
        symbol=profile.symbol,
        name=profile.short_name or profile.name or profile.symbol,
        short_name=profile.short_name,
        market=profile.market,
        matched_text=alias,
        match_kind=kind,
        confidence=round(max(0.0, min(score, 1.0)), 3),
    )


class InputUnderstandingService:
    def __init__(self, *, twse, tpex):
        self.twse = twse
        self.tpex = tpex

    async def _companies(self) -> tuple[list[CompanyProfile], list[str], str]:
        import asyncio

        results = await asyncio.gather(self.twse.companies(), self.tpex.companies(), return_exceptions=True)
        rows: list[CompanyProfile] = []
        sources: list[str] = []
        for source, result in zip(("TWSE", "TPEx"), results):
            if isinstance(result, list):
                rows.extend(result)
                sources.append(source)
        if not rows:
            error = next((item for item in results if isinstance(item, Exception)), RuntimeError("官方公司清單無資料"))
            raise error
        return rows, sources, "official" if len(sources) == 2 else "partial"

    async def _listed_products(self, symbols: set[str]) -> list[InputCandidate]:
        """Resolve explicit ETF/security codes from official quote lists when absent from company lists."""
        import asyncio

        if not symbols:
            return []
        operations = [provider.quotes() for provider in (self.twse, self.tpex) if callable(getattr(provider, "quotes", None))]
        if not operations:
            return []
        results = await asyncio.gather(*operations, return_exceptions=True)
        candidates: list[InputCandidate] = []
        for result in results:
            if not isinstance(result, list):
                continue
            for quote in result:
                if quote.symbol not in symbols:
                    continue
                candidates.append(InputCandidate(
                    symbol=quote.symbol, name=quote.name or quote.symbol, short_name=quote.name,
                    market=quote.market, matched_text=quote.symbol, match_kind="symbol", confidence=1.0,
                ))
        return candidates

    async def understand(self, request: InputUnderstandingRequest) -> InputUnderstandingResponse:
        raw = request.text.strip()
        normalized = normalize_input(raw)
        explicit_codes = _explicit_codes(raw)
        historical, outlook = parse_period(raw, default_months=request.default_history_months)
        constraints = [label for pattern, label in CONSTRAINT_PATTERNS if pattern.search(raw)]
        structured_constraints = _structured_constraints(raw, constraints)
        hypotheses = _price_hypotheses(raw)
        intent, classification_signals = _intent(raw, hypotheses)
        research_type = _research_type(normalized, intent, explicit_codes)
        research_topic = _research_topic(raw) if research_type in {"industry_supply_chain", "market_trend"} else None
        base = dict(raw_input=raw, normalized_input=normalized, context=request.context, intent=intent,
                    historical_period=historical, outlook_period=outlook, constraints=constraints,
                    structured_constraints=structured_constraints,
                    hypotheses=hypotheses, requires_market_data=intent in MARKET_INTENTS,
                    classification_signals=classification_signals, research_type=research_type,
                    research_topic=research_topic)
        # Pure concept questions do not need the company universe.  Keeping this
        # path independent prevents a TWSE/TPEx outage from turning a definition
        # question into an unnecessary stock clarification.
        if intent == "explain" and not explicit_codes and (CONCEPT_PATTERN.search(normalized) or PLANNING_PATTERN.search(normalized)):
            return InputUnderstandingResponse(
                **base, target_status="not_required", candidates=[], selected_symbol=None,
                message="這是投資知識問答，不需要先指定股票，也不會啟動正式研究。",
                source_status="official", source_names=[],
            )
        # Industry and supply-chain questions describe a topic scope.  Resolve
        # them before any company-universe lookup or fuzzy matching so a topic
        # can never become an unrelated high-confidence stock candidate.
        # 「廣達在 AI 伺服器的成長與風險」：以完整公司簡稱開頭、只是提到產業的句子，
        # 研究的是那家公司，不是整個產業（只認開頭的完整簡稱，不做模糊比對）。
        # 「台積電供應鏈有哪些公司」仍是供應鏈主題，不算。
        if (research_type == "industry_supply_chain" and not explicit_codes
                and not re.search(r"供應鏈|產業鏈|哪些|相關|概念|族群|同業|上下游", normalized)):
            try:
                profiles, _, _ = await self._companies()
            except Exception:
                profiles = []
            leading = next((p for p in profiles if p.short_name and len(p.short_name) >= 2
                            and normalized.startswith(normalize_input(p.short_name))), None)
            if leading:
                research_type = base["research_type"] = "single_company"
                base["research_topic"] = None
                classification_signals.append("company_subject_with_theme")
        if research_type == "industry_supply_chain":
            classification_signals.append("industry_or_theme_query")
            if SWITCH_TARGET_PATTERN.search(normalized):
                classification_signals.append("explicit_topic_switch")
            return InputUnderstandingResponse(
                **base, target_status="not_required", candidates=[], selected_symbol=None,
                message=(f"已辨識為「{research_topic or raw}」產業／供應鏈研究；研究流程會建立主題範圍，"
                         "不會把產業名稱送進單一公司模糊比對。"),
                source_status="official", source_names=[],
            )
        if research_type == "market_trend":
            classification_signals.append("market_trend_query")
            return InputUnderstandingResponse(
                **base, target_status="not_required", candidates=[], selected_symbol=None,
                message="已辨識為市場趨勢研究，不需要先指定單一公司。",
                source_status="official", source_names=[],
            )
        try:
            profiles, sources, source_status = await self._companies()
        except Exception:
            explicit_code_set = set(explicit_codes)
            products = await self._listed_products(explicit_code_set)
            if products:
                candidates = sorted(products, key=lambda item: item.symbol)
                if intent == "compare" and len({item.symbol for item in candidates}) > 1:
                    resolved = list(dict.fromkeys(item.symbol for item in candidates))[:3]
                    classification_signals.append("explicit_multi_target")
                    return InputUnderstandingResponse(
                        **base, target_status="recognized", candidates=candidates,
                        selected_symbol=None, resolved_symbols=resolved,
                        message="已由官方行情清單辨識比較標的：" + "、".join(
                            f"{item.symbol} {item.name}" for item in candidates if item.symbol in resolved
                        ) + "。",
                        source_status="partial", source_names=["TWSE／TPEx 官方行情清單"],
                    )
                chosen = candidates[0] if len(candidates) == 1 else None
                return InputUnderstandingResponse(
                    **base, target_status="recognized" if chosen else "ambiguous", candidates=candidates,
                    selected_symbol=chosen.symbol if chosen else None,
                    message=(f"已辨識為 {chosen.symbol} {chosen.name}。" if chosen else "找到多個官方標的，請先選擇要使用的標的。"),
                    source_status="partial", source_names=["TWSE／TPEx 官方行情清單"],
                )
            return InputUnderstandingResponse(**base, target_status="source_error", candidates=[],
                message="官方公司清單目前無法取得，已保留原問題；請稍後重試或明確輸入代號。",
                source_status="error", source_names=[])

        exact: dict[tuple[str, str], InputCandidate] = {}
        if PORTFOLIO_WITHOUT_SYMBOL_PATTERN.search(normalized) and not explicit_codes and not PREFERENCE_REQUEST_PATTERN.search(normalized):
            classification_signals.append("personal_portfolio_symbols_missing")
            return InputUnderstandingResponse(
                **base, target_status="needs_confirmation", candidates=[], selected_symbol=None,
                message="我無法讀取你的私人持股。請直接輸入想分析的股票名稱或代號，我會接著處理。",
                source_status=source_status, source_names=sources,
            )
        etf_defaults = _etf_default_symbols(normalized, explicit_codes)
        if etf_defaults:
            default_symbols, reason = etf_defaults
            products = await self._listed_products(set(default_symbols))
            by_symbol = {item.symbol: item for item in products}
            candidates = [by_symbol[symbol] for symbol in default_symbols if symbol in by_symbol]
            resolved = [item.symbol for item in candidates]
            classification_signals.extend(["representative_etf_defaults", "transparent_system_assumption"])
            if "selection_correction" in classification_signals:
                classification_signals.append("replace_previous_selection")
            message = (
                f"未指定代號；{reason}："
                + ("、".join(f"{item.symbol} {item.name}" for item in candidates) if candidates else "將由研究流程依主題篩選")
                + "。你仍可直接改用其他代號。"
            )
            return InputUnderstandingResponse(
                **base, target_status="recognized" if len(resolved) >= 2 else "not_required",
                candidates=candidates, selected_symbol=None, resolved_symbols=resolved,
                assumptions=[reason], message=message,
                source_status=source_status, source_names=sources,
            )
        if _is_broad_discovery_query(normalized, intent, explicit_codes):
            classification_signals.append("broad_market_discovery")
            return InputUnderstandingResponse(
                **base, target_status="not_required", candidates=[], selected_symbol=None,
                message="已辨識為市場篩選問題；將保留完整條件，不會要求先指定單一公司。",
                source_status=source_status, source_names=sources,
            )
        for profile in profiles:
            for alias, kind in _company_aliases(profile):
                if kind == "symbol":
                    if alias in explicit_codes:
                        exact[(profile.symbol, profile.market)] = _profile_candidate(profile, alias, kind, 1.0)
                elif len(alias) >= 2 and alias in normalized:
                    exact[(profile.symbol, profile.market)] = _profile_candidate(profile, alias, kind, 1.0)
        unresolved_codes = set(explicit_codes) - {item.symbol for item in exact.values()}
        for candidate in await self._listed_products(unresolved_codes):
            exact[(candidate.symbol, candidate.market)] = candidate
        corrections_found: list[dict[str, str]] = []
        if exact:
            if base["research_type"] == "unknown":
                base["research_type"] = "single_company"
            switch_match = list(SWITCH_TARGET_PATTERN.finditer(normalized))
            switch_candidates: list[InputCandidate] = []
            if switch_match:
                suffix = normalized[switch_match[-1].end():]
                switch_candidates = [item for item in exact.values() if item.matched_text in suffix]
                if switch_candidates:
                    classification_signals.append("explicit_target_switch")
            # 兩家公司用「和／跟／與／、／vs」連在一起（台積電和聯發科），就是要比較，不必寫「比較」兩個字。
            named = list(exact.values())
            outer = {item.symbol for item in named if not any(
                item.matched_text != other.matched_text and item.matched_text in other.matched_text for other in named)}
            if base["intent"] != "compare" and len(outer) >= 2 and re.search(r"和|跟|與|及|、|vs|VS|還是", normalized):
                base["intent"] = "compare"
                classification_signals.append("implicit_comparison")
            if base["intent"] == "compare":
                candidates = sorted(exact.values(), key=lambda item: (
                    normalized.find(item.matched_text) if item.matched_text in normalized else len(normalized), item.symbol,
                ))
                comparison_candidates = [
                    item for item in candidates
                    if not any(
                        item.matched_text != other.matched_text
                        and item.matched_text in other.matched_text
                        for other in candidates
                    )
                ]
                # 比較題只對上一檔時，剩下的字可能是打錯的另一檔（「復喬和環球晶」的 復喬＝富喬）。
                if len({item.symbol for item in comparison_candidates}) < 2:
                    leftover = normalized
                    for item in sorted(candidates, key=lambda row: -len(row.matched_text)):
                        leftover = leftover.replace(item.matched_text, " ")
                    for fragment in COMPARE_SPLIT.split(leftover):
                        fragment = fragment.strip()
                        if not 2 <= len(fragment) <= 6:
                            continue
                        typo = _homophone_targets(fragment, profiles, {item.symbol for item in comparison_candidates})
                        if len({row.symbol for row in typo}) == 1:
                            comparison_candidates.append(typo[0])
                            candidates.append(typo[0])
                            corrections_found.append({"from": typo[0].typed_text, "to": typo[0].name})
                    comparison_candidates.sort(key=lambda item: normalized.find(item.typed_text or item.matched_text))
            else:
                candidates = sorted(exact.values(), key=lambda item: (-len(item.matched_text), item.symbol))
                comparison_candidates = candidates
            # A complete, longer official alias is more specific than another
            # company's shorter name embedded inside it (聯發科 vs. 聯發).
            # Identical numeric codes across markets remain ambiguous.
            distinct_symbols = list(dict.fromkeys(item.symbol for item in comparison_candidates))
            duplicate_code = len(candidates) > 1 and len(distinct_symbols) == 1
            if base["intent"] == "compare" and len(distinct_symbols) > 1:
                classification_signals.append("explicit_multi_target")
                return InputUnderstandingResponse(
                    **base, target_status="recognized", candidates=candidates[:8], selected_symbol=None,
                    resolved_symbols=distinct_symbols[:3], corrections=corrections_found,
                    message="".join(f"「{row['from']}」視為「{row['to']}」。" for row in corrections_found) + "已辨識比較標的：" + "、".join(
                        f"{item.symbol} {item.name}" for item in comparison_candidates
                        if item.symbol in distinct_symbols[:3]
                    ) + "。",
                    source_status=source_status, source_names=sources,
                )
            if len(switch_candidates) == 1:
                chosen = switch_candidates[0]
            elif duplicate_code:
                chosen = None
            else:
                longest_length = len(candidates[0].matched_text)
                most_specific = [item for item in candidates if len(item.matched_text) == longest_length]
                chosen = most_specific[0] if len(most_specific) == 1 else None
            # 打錯字時短名稱會先命中（聯發客 含「聯發」）：列出兩者請使用者選，不直接認定。
            homophone = (_homophone_of_longer_name(normalized, chosen.matched_text, profiles, chosen.symbol)
                         if chosen and len(switch_candidates) != 1 and base["intent"] != "compare" else None)
            if homophone:
                profile, alias, typed = homophone
                likely = _profile_candidate(profile, alias, "phonetic", 0.96)
                likely.typed_text = typed
                return InputUnderstandingResponse(
                    **base, target_status="ambiguous", candidates=[likely, chosen], selected_symbol=None,
                    message=f"你輸入的是「{typed}」，是 {likely.symbol} {likely.name} 嗎？也可能是 {chosen.symbol} {chosen.name}。",
                    source_status=source_status, source_names=sources,
                )
            status = "recognized" if chosen else "ambiguous"
            selected = chosen.symbol if chosen else None
            message = (f"已辨識為 {chosen.symbol} {chosen.name}。" if chosen
                       else "我找到多個可能標的。請直接輸入公司全名或代號；也可以點選下方候選。")
            return InputUnderstandingResponse(**base, target_status=status, candidates=candidates[:8], selected_symbol=selected,
                message=message, source_status=source_status, source_names=sources)

        # Explanatory/general-knowledge questions do not imply a stock target.
        # Exact official-name matching above still lets「解釋台積電…」work;
        # fuzzy/pinyin coincidences in「用生活化例子解釋 ROE」are ignored.
        if base["intent"] in {"explain", "rephrase"}:
            return InputUnderstandingResponse(**base, target_status="not_required", candidates=[], selected_symbol=None,
                message="沒有必須先確認的單一標的；將保留完整問題與期間條件。",
                source_status=source_status, source_names=sources)

        fragment = _target_fragment(raw)
        scored: dict[tuple[str, str], InputCandidate] = {}
        if len(fragment) >= 2:
            fragment_pinyin = _pinyin(fragment)
            for profile in profiles:
                best: InputCandidate | None = None
                for alias, original_kind in _company_aliases(profile):
                    if original_kind == "symbol" or len(alias) < 2:
                        continue
                    shape = SequenceMatcher(None, fragment, alias).ratio()
                    alias_pinyin = _pinyin(alias)
                    phonetic = SequenceMatcher(None, fragment_pinyin, alias_pinyin).ratio() if fragment_pinyin else 0
                    if fragment_pinyin and fragment_pinyin == alias_pinyin:
                        # Homophones are strong correction candidates, but a
                        # second close official name must still be offered.
                        phonetic = 0.96
                    elif fragment_pinyin and alias_pinyin in fragment_pinyin:
                        # The whole name is spoken inside the sentence (台機電怎樣).
                        phonetic = max(phonetic, 0.9)
                    elif fragment_pinyin and fragment_pinyin in alias_pinyin:
                        # A short input found inside a long name only counts when
                        # it covers most of that name; otherwise a common word such
                        # as 「測試」(ceshi) matches inside 漢民測試系統(hanminceshixitong).
                        if len(fragment_pinyin) / len(alias_pinyin) >= 0.6:
                            phonetic = max(phonetic, 0.9)
                    score = max(shape, phonetic)
                    # Two-character fragments are mostly everyday words (你好、測試);
                    # plain similarity ratios (你好 nihao ↔ 今皓 jinhao ≈ 0.73) are
                    # coincidences, so only homophones or close containment count.
                    if len(fragment) <= 2 and score < 0.9:
                        continue
                    kind = "phonetic" if phonetic > shape else "approximate"
                    candidate = _profile_candidate(profile, alias, kind, score)
                    candidate.typed_text = _typed_part(fragment, alias)
                    if kind == "phonetic" and candidate.typed_text in COMMON_PHRASES and candidate.typed_text != alias:
                        continue
                    # 打錯公司名通常還留著一個對的字（台機電→台積電、聯發客→聯發科）；
                    # 一個字都不同的同音巧合（磣要→宸曜、新的公告→興能高、他的營收→泰碩）不採用。
                    if kind == "phonetic" and not set(candidate.typed_text or "") & set(alias):
                        continue
                    if best is None or candidate.confidence > best.confidence:
                        best = candidate
                if best and best.confidence >= 0.7:
                    scored[(profile.symbol, profile.market)] = best
        candidates = sorted(scored.values(), key=lambda item: (-item.confidence, item.symbol))[:8]
        if candidates:
            top = candidates[0]
            runner = candidates[1].confidence if len(candidates) > 1 else 0
            unique = top.confidence >= 0.86 and top.confidence - runner >= 0.08
            if unique:
                return InputUnderstandingResponse(**base, target_status="recognized", candidates=candidates[:3],
                    selected_symbol=top.symbol, corrections=[{"from": fragment, "to": top.name}],
                    message=f"已辨識為 {top.symbol} {top.name}（原輸入：{fragment}）。",
                    source_status=source_status, source_names=sources)
            return InputUnderstandingResponse(**base, target_status="ambiguous", candidates=candidates[:5],
                corrections=[], message="輸入可能對應多個標的。請直接補充公司全名或代號；也可以點選下方候選。",
                source_status=source_status, source_names=sources)

        if not fragment or base["intent"] in {"explain", "rephrase"}:
            return InputUnderstandingResponse(**base, target_status="not_required", candidates=[], selected_symbol=None,
                message="沒有必須先確認的單一標的；將保留完整問題與期間條件。",
                source_status=source_status, source_names=sources)
        # In the assistant, a message with no stock language and no matching
        # name (問候、閒聊、測試) is an ordinary question, not a missing target.
        # Formal research keeps asking for confirmation.
        if request.context == "assistant" and base["intent"] == "unknown":
            return InputUnderstandingResponse(**base, target_status="not_required", candidates=[], selected_symbol=None,
                message="沒有指定標的，將以一般問答回覆。",
                source_status=source_status, source_names=sources)
        # 新手入門、小額預算、零股／定期定額這類「怎麼開始買」的問題，不需要先指定哪一檔。
        if request.context == "assistant" and (
            GENERAL_HOWTO_PATTERN.search(normalized) or any(item.type == "budget" for item in base.get("structured_constraints") or [])
        ):
            classification_signals.append("general_howto_question")
            return InputUnderstandingResponse(**base, target_status="not_required", candidates=[], selected_symbol=None,
                message="這是一般投資入門問題，不需要先指定標的。",
                source_status=source_status, source_names=sources)
        return InputUnderstandingResponse(**base, target_status="needs_confirmation", candidates=[], selected_symbol=None,
            message="我還不能安全判斷你指的是哪個標的。請直接補充公司全名或代號；原問題已保留。",
            source_status=source_status, source_names=sources)
