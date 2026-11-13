from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .research import NUMBER_PATTERN, URL_PATTERN, _canonical_number, _number_tokens


DATE_PATTERN = re.compile(
    r"(?<!\d)((?:19|20)\d{2})\s*(?:[-/.年]\s*(\d{1,2})\s*(?:[-/.月]\s*(\d{1,2})\s*日?)?)"
)
HYPOTHESIS_WORDS = re.compile(r"假設|目標(?:價)?|情境|如果|若|漲到|跌到|漲回|跌回|上看|下看")
FACT_WORDS = re.compile(r"現價|目前股價|最新價|收盤(?:價)?|開盤(?:價)?|最高(?:價)?|最低(?:價)?|成交量|報酬(?:率)?|波動(?:率|度)?|回撤")
MISSING_WORDS = re.compile(r"缺少|缺漏|未取得|無法取得|資料不足|尚無|不能確認|無可用")
INFERENCE_WORDS = re.compile(r"可能|推測|情境|若|如果|風險|有利|不利|值得|建議|傾向|機會|展望")
DEPENDENCY_PREFIX = re.compile(r"^(?:[-*]\s*)?(?:因此|所以|故|由此|這(?:代表|顯示|意味著)|基於上述|據此|因而)")
LEADING_NON_ENTITY = {"今日", "昨日", "目前", "最新", "截至", "官方", "資料", "日資料"}
# 句首常見的一般詞（近期、年化、平均每日…），不是公司名稱。
GENERIC_LEADING_WORDS = (
    "近期", "期間", "區間", "整體", "這段", "同期", "短期", "長期", "歷史", "今年", "本月", "本週",
    "年化", "平均", "每日", "股價", "價格", "近六個月", "近半年", "觀察", "統計",
    "累積", "最大", "單日", "過去", "半年", "日均", "區間", "最新",
    "當天", "當日", "盤中", "前日", "前一", "這天", "該日", "隔日", "今天", "昨天", "全天", "上週", "上月", "去年", "總成交",
)
# 「波動超過 25%」「回撤接近 11%」這類門檻描述：只要和資料比較後成立，就不算沒有根據的數字。
COMPARATOR_BEFORE = re.compile(r"(超過|高於|大於|逾|突破|多於|低於|不到|少於|小於|未達|接近|將近|約)\s*[-+]?$")
# 用「下跌／回檔」等字搭配正數描述負值時，數字以絕對值核對。
DECLINE_WORDS = re.compile(r"下跌|跌幅|跌了|下滑|回檔|回撤|拉回|虧損|虧|減少|衰退|走低")
# price_history 指標對應到可驗證的價格欄位（期間高低點以收盤價計）。
HISTORY_PRICE_FIELDS = {
    "average_volume_shares": ("volume",),
    "latest_close": ("close",),
    "period_high": ("high", "close"),
    "period_low": ("low", "close"),
}
# Keys holding historical daily rows (not the latest observation).
HISTORICAL_KEYS = {"history", "points", "recent_points"}
# A kept sentence that only introduces what follows (「依據…資料：」).
LEAD_IN_PATTERN = re.compile(r"[：:]\s*$")
# A note that only qualifies removed numbers (「（註：以上數據…）」).
ORPHAN_NOTE_PATTERN = re.compile(r"^[\s>*_]*[（(]?\s*註[：:].{0,40}(?:以上|上述|上表|前述)")

FIELD_PATTERNS = {
    "close": re.compile(r"(?:目前股價|現價|最新價|收盤價|收盤)[^\d+\-]{0,16}([-+]?\d[\d,]*(?:\.\d+)?)\s*([^\s，。；、]*)"),
    "open": re.compile(r"開盤(?:價)?[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*([^\s，。；、]*)"),
    "high": re.compile(r"最高(?:價)?[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*([^\s，。；、]*)"),
    "low": re.compile(r"最低(?:價)?[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*([^\s，。；、]*)"),
    "change": re.compile(r"漲跌[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*([^\s，。；、]*)"),
    "volume": re.compile(r"成交量[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*([^\s，。；、]*)"),
    "period_return_pct": re.compile(r"(?:期間)?報酬(?:率)?[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*([^\s，。；、]*)"),
    "annualized_volatility_pct": re.compile(r"(?:年化)?波動(?:率|度)?[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*([^\s，。；、]*)"),
    "max_drawdown_pct": re.compile(r"最大回撤[^\d+\-]{0,12}([-+]?\d[\d,]*(?:\.\d+)?)\s*([^\s，。；、]*)"),
}
PERCENT_FIELDS = {"period_return_pct", "annualized_volatility_pct", "max_drawdown_pct"}
PRICE_FIELDS = {"close", "open", "high", "low", "change"}


def _normalize_date(year: str, month: str | None, day: str | None) -> str:
    if month is None:
        return year
    if day is None:
        return f"{year}-{int(month):02d}"
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _dates(value: Any) -> set[str]:
    serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return {_normalize_date(*match.groups()) for match in DATE_PATTERN.finditer(serialized)}


def _clean_url(value: str) -> str:
    return value.rstrip(".,;:!?，。；：！？)]}》」』")


def _split_claims(text: str) -> list[tuple[str, bool]]:
    """Return claim-sized text chunks and whether a paragraph break preceded them."""
    chunks: list[tuple[str, bool]] = []
    paragraph_break = False
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        if not body.strip():
            chunks.append((line, True))
            paragraph_break = True
            continue
        parts = re.findall(r".*?[。！？；]+|.+$", body)
        # 粗體內有句號時（**結論一。結論二。**）不能從中間切開，否則刪掉一句會留下單獨的「**」。
        merged: list[str] = []
        for part in parts:
            if merged and merged[-1].count("**") % 2 == 1:
                merged[-1] += part
            else:
                merged.append(part)
        parts = merged
        for index, part in enumerate(parts):
            if index == len(parts) - 1:
                part += ending
            chunks.append((part, paragraph_break))
            paragraph_break = False
    if not chunks and text:
        chunks.append((text, False))
    return chunks


@dataclass
class EvidenceIndex:
    symbols: set[str] = field(default_factory=set)
    names: dict[str, set[str]] = field(default_factory=dict)
    numbers: dict[str, set[str]] = field(default_factory=dict)
    dates: dict[str, set[str]] = field(default_factory=dict)
    tool_dates: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    facts: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    successful_tools: dict[str, set[str]] = field(default_factory=dict)
    failed_tools: dict[str, set[str]] = field(default_factory=dict)
    stale_tools: dict[str, set[str]] = field(default_factory=dict)
    # 歷史日價中的實際交易日（期間起訖與每日資料日期），不含查詢區間的日期。
    history_trade_dates: dict[str, set[str]] = field(default_factory=dict)
    urls: set[str] = field(default_factory=set)
    hypothesis_values: dict[str, str | None] = field(default_factory=dict)
    period_label: str = ""

    @classmethod
    def build(cls, tools: list[dict[str, Any]], hypotheses: list[Any], context: dict[str, Any]) -> "EvidenceIndex":
        index = cls(period_label=str((context.get("historical_observation_period") or {}).get("label") or ""))

        def collect_urls(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    collect_urls(item)
                return
            if not isinstance(node, dict):
                return
            for key, value in node.items():
                if key in {"url", "source_url"} and isinstance(value, str) and value.startswith(("http://", "https://")):
                    index.urls.add(_clean_url(value))
                elif isinstance(value, (dict, list)):
                    collect_urls(value)

        def collect_semantic_dates(node: Any) -> set[str]:
            values: set[str] = set()
            if isinstance(node, list):
                for item in node:
                    values.update(collect_semantic_dates(item))
                return values
            if not isinstance(node, dict):
                return values
            date_keys = {
                "as_of", "trade_date", "event_date", "published_at",
                "period_start", "period_end", "start", "end",
            }
            for key, value in node.items():
                if key in date_keys and isinstance(value, str):
                    values.update(_dates(value))
                elif isinstance(value, (dict, list)):
                    values.update(collect_semantic_dates(value))
            return values

        def contains_stale_metadata(node: Any) -> bool:
            # Historical daily points are old by definition; their per-row
            # "stale" flag only means "older than the freshness window" and
            # must not mark the current quote or metrics as outdated.
            if isinstance(node, list):
                return any(contains_stale_metadata(item) for item in node)
            if not isinstance(node, dict):
                return False
            metadata = node.get("metadata")
            if isinstance(metadata, dict) and metadata.get("stale") is True:
                return True
            return any(
                contains_stale_metadata(value) for key, value in node.items()
                if key not in HISTORICAL_KEYS and isinstance(value, (dict, list))
            )

        for item in hypotheses:
            row = item if isinstance(item, dict) else item.model_dump(mode="json")
            token = _canonical_number(str(row.get("value")))
            if token is not None:
                index.hypothesis_values[token] = row.get("symbol")
        for result in tools:
            symbol = str(result.get("symbol") or "")
            tool = str(result.get("tool") or "")
            if not symbol:
                continue
            index.symbols.add(symbol)
            destination = index.successful_tools if result.get("status") == "completed" else index.failed_tools
            destination.setdefault(symbol, set()).add(tool)
            if result.get("status") != "completed":
                continue
            raw_data = result.get("data")
            # 公告、法說會等工具回傳的是清單；包成 dict 讀取（以前直接 .get 會讓追問公告的回答中斷）。
            data = raw_data if isinstance(raw_data, dict) else {"items": raw_data or []}
            capabilities = {tool} | {
                str(value) for value in (data.get("capabilities") or [])
                if str(value) in {"market_snapshot", "price_history", "company_profile", "material_events", "investor_conferences"}
            }
            index.successful_tools.setdefault(symbol, set()).update(capabilities)
            index.numbers.setdefault(symbol, set()).update(_number_tokens(data) | _scaled_tokens(_number_tokens(data)))
            semantic_dates = collect_semantic_dates(data)
            index.dates.setdefault(symbol, set()).update(semantic_dates)
            for capability in capabilities:
                index.tool_dates.setdefault(symbol, {}).setdefault(capability, set()).update(semantic_dates)
            if contains_stale_metadata(data):
                index.stale_tools.setdefault(symbol, set()).update(capabilities)
            index.facts.setdefault(symbol, {})
            index.names.setdefault(symbol, set())
            for key in ("name", "short_name"):
                if data.get(key):
                    index.names[symbol].add(str(data[key]))
            company = data.get("company")
            if isinstance(company, dict):
                for key in ("name", "short_name"):
                    if company.get(key):
                        index.names[symbol].add(str(company[key]))
            quote = data.get("quote") if isinstance(data.get("quote"), dict) else {}
            metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
            for key in ("close", "open", "high", "low", "change", "volume"):
                token = _canonical_number(str(quote.get(key))) if quote.get(key) is not None else None
                if token is not None:
                    index.facts[symbol].setdefault(key, set()).add(token)
            for key, value in metrics.items():
                token = _canonical_number(str(value)) if isinstance(value, (int, float)) else None
                if token is not None:
                    index.facts[symbol].setdefault(key, set()).add(token)
                    # 歷史日價的最新收盤與期間高低點（以收盤價計）也是可驗證的價格。
                    for field_name in HISTORY_PRICE_FIELDS.get(key, ()):
                        index.facts[symbol].setdefault(field_name, set()).add(token)
            trade_dates = index.history_trade_dates.setdefault(symbol, set())
            if tool == "price_history":
                for key in ("period_start", "period_end"):
                    if metrics.get(key):
                        trade_dates.update(_dates(str(metrics[key])))
            for row in (data.get("points") or []) + (data.get("history") or []):
                if not isinstance(row, dict):
                    continue
                if tool == "price_history" and (row.get("trade_date") or row.get("date")):
                    trade_dates.update(_dates(str(row.get("trade_date") or row.get("date"))))
                for key in ("close", "open", "high", "low"):
                    token = _canonical_number(str(row.get(key))) if row.get(key) is not None else None
                    if token is not None:
                        index.facts[symbol].setdefault(key, set()).add(token)
            collect_urls(data)
        for calculation in context.get("deterministic_calculations") or []:
            if not isinstance(calculation, dict):
                continue
            symbol = str(calculation.get("symbol") or "")
            if symbol and symbol in index.symbols:
                index.numbers.setdefault(symbol, set()).update(_number_tokens(calculation))
                index.dates.setdefault(symbol, set()).update(collect_semantic_dates(calculation))
        return index


@dataclass
class ClaimValidationResult:
    text: str
    status: str
    claim_summary: dict[str, Any]
    # 給介面顯示在回答下方的資料說明；不寫進回答本文。
    notes: list[str] = field(default_factory=list)


def _mentioned_symbols(text: str, index: EvidenceIndex) -> set[str]:
    mentioned = {symbol for symbol in index.symbols if re.search(rf"(?<!\d){re.escape(symbol)}(?!\d)", text)}
    for symbol, names in index.names.items():
        if any(name and name in text for name in names):
            mentioned.add(symbol)
    return mentioned


def _claim_subject(text: str, index: EvidenceIndex) -> str | None:
    mentioned = _mentioned_symbols(text, index)
    if len(mentioned) == 1:
        return next(iter(mentioned))
    if not mentioned and len(index.symbols) == 1:
        return next(iter(index.symbols))
    return None


def _classification(text: str, index: EvidenceIndex) -> str:
    numbers = {_canonical_number(raw) for raw in NUMBER_PATTERN.findall(text)}
    numbers.discard(None)
    if MISSING_WORDS.search(text):
        return "data_gap"
    if HYPOTHESIS_WORDS.search(text) and numbers.intersection(index.hypothesis_values):
        return "user_hypothesis"
    if re.search(r"程式計算|期間報酬|波動率|波動度|最大回撤", text):
        return "calculated_metric"
    if FACT_WORDS.search(text) or re.search(r"官方日資料|公司資料|重大訊息|法說", text):
        return "verified_fact"
    if INFERENCE_WORDS.search(text):
        return "model_inference"
    return "analysis"


def _required_tool(text: str) -> str | None:
    if re.search(r"現價|股價|收盤|開盤|最高|最低|成交量|官方日資料", text):
        return "market_snapshot"
    if re.search(r"報酬|波動|回撤|歷史走勢|期間高|期間低", text):
        return "price_history"
    if re.search(r"公司資料|資本額|產業|基本面", text):
        return "company_profile"
    if re.search(r"法人說明會|法說", text):
        return "investor_conferences"
    if re.search(r"重大訊息|公告", text):
        return "material_events"
    return None


def _negated(token: str) -> str:
    """-4.93 ↔ 4.93：「下跌 4.93%」與資料的 -4.93 是同一個數字。"""
    return token[1:] if token.startswith("-") else f"-{token}"


def _source_satisfied(required: str, available: set[str]) -> bool:
    # 歷史日價含每日開高低收，收盤價與期間高低點問題可由它支持。
    return required in available or (required == "market_snapshot" and "price_history" in available)


def _unit_problem(field: str, suffix: str) -> bool:
    suffix = suffix.strip("：:=約為是")
    if field in PRICE_FIELDS:
        return not suffix.startswith(("元", "塊", "TWD", "新台幣", "台幣"))
    if field == "volume":
        return not suffix.startswith("股")
    if field in PERCENT_FIELDS:
        return not (suffix.startswith("%") or suffix.startswith("％"))
    return False


def _scaled_tokens(tokens: set[str]) -> set[str]:
    """大數字的常見換算：股→張（÷1,000）、元→萬（÷10,000）、元→億（÷100,000,000），四捨五入到 0～2 位小數。
    例：成交量 36,575,123 股 ＝「約 36,575 張」；成交金額 8,285,000,000 元 ＝「約 82.85 億元」。"""
    scaled = set()
    for token in tokens:
        try:
            value = float(token)
        except (TypeError, ValueError):
            continue
        if abs(value) < 10_000:
            continue
        for divisor in (1_000, 10_000, 100_000_000):
            converted = value / divisor
            if abs(converted) < 0.01:
                continue
            for digits in (0, 1, 2):
                rounded = _canonical_number(f"{round(converted, digits):.{digits}f}")
                if rounded:
                    scaled.add(rounded)
    return scaled


def _threshold_holds(word: str, number: str, values: set[str]) -> bool:
    try:
        target = abs(float(number))
        known = [abs(float(value)) for value in values]
    except (TypeError, ValueError):
        return False
    if word in {"超過", "高於", "大於", "逾", "突破", "多於"}:
        return any(value > target for value in known)
    if word in {"低於", "不到", "少於", "小於", "未達"}:
        return any(value < target for value in known)
    return any(abs(value - target) <= max(0.1 * value, 0.5) for value in known)


def _true_thresholds(text: str, values: set[str]) -> set[str]:
    """回傳句中以比較詞描述、而且和資料比較後成立的數字。"""
    passed = set()
    for match in NUMBER_PATTERN.finditer(text):
        before = COMPARATOR_BEFORE.search(text[max(0, match.start() - 4):match.start()])
        token = _canonical_number(match.group(0))
        if before and token and _threshold_holds(before.group(1), token, values):
            passed.add(token)
    return passed


def _nearest_subject(text: str, position: int, mentioned: set[str], index: EvidenceIndex) -> str | None:
    """同一句提到多家公司時，數字歸給它前面最靠近的那一家（「富喬收盤 128 元；環球晶收盤 612 元」）。"""
    best, best_at = None, -1
    for symbol in mentioned:
        for label in {symbol} | (index.names.get(symbol) or set()):
            if not label:
                continue
            at = text.rfind(label, 0, position)
            if at > best_at:
                best, best_at = symbol, at
    return best


def _claim_issues(text: str, category: str, index: EvidenceIndex, context_subject: str | None = None) -> list[str]:
    issues: list[str] = []
    stripped = text.strip()
    if not stripped:
        return issues
    mentioned = _mentioned_symbols(stripped, index)
    # 子項目沒寫公司名時，沿用上一行（例如「* **富喬**」底下的「收盤價為 128 元」）。
    subject = _claim_subject(stripped, index) or (context_subject if not mentioned else None)

    for url in URL_PATTERN.findall(stripped):
        if _clean_url(url) not in index.urls:
            issues.append("unverified_url")

    scrubbed = DATE_PATTERN.sub(" ", stripped)
    hypothesis_tokens = set(index.hypothesis_values)
    known_fact_tokens = set().union(*(index.numbers.values() or [set()]))
    for code in re.findall(r"(?<!\d)(\d{4,6})(?!\d)", scrubbed):
        token = _canonical_number(code)
        if code not in index.symbols and token not in hypothesis_tokens and token not in known_fact_tokens:
            issues.append("symbol_mismatch")

    for symbol in mentioned:
        allowed_names = index.names.get(symbol) or set()
        name_after_code = re.search(
            rf"(?<!\d){re.escape(symbol)}(?!\d)\s*([\u4e00-\u9fff]{{2,8}})(?=(?:目前|現價|最新價|收盤|開盤|最高|最低|成交量))",
            stripped,
        )
        if name_after_code and allowed_names and name_after_code.group(1) not in allowed_names:
            issues.append("company_name_mismatch")
    if len(index.symbols) == 1 and FACT_WORDS.search(stripped):
        leading_name = re.search(
            r"^(?:[-*#]\s*)?([\u4e00-\u9fff]{2,8})(?=(?:目前股價|現價|最新價|收盤|開盤|最高|最低|成交量|期間報酬|報酬率|波動率|最大回撤))",
            stripped,
        )
        if leading_name:
            candidate = leading_name.group(1)
            allowed_names = set().union(*(index.names.values() or [set()]))
            looks_contextual = candidate in LEADING_NON_ENTITY or candidate.startswith(GENERIC_LEADING_WORDS) or any(
                marker in candidate for marker in {"目前", "截至", "官方", "資料", "今日", "昨日", "從", "以"}
            )
            if not looks_contextual and not any(name in candidate or candidate in name for name in allowed_names):
                issues.append("company_name_mismatch")

    required = _required_tool(stripped)
    claim_dates = _dates(stripped)
    if claim_dates:
        if subject and required:
            allowed_dates = set(index.tool_dates.get(subject, {}).get(required, set()))
            if required == "market_snapshot" and "market_snapshot" not in index.successful_tools.get(subject, set()):
                allowed_dates |= index.history_trade_dates.get(subject, set())
        else:
            allowed_dates = index.dates.get(subject, set()) if subject else set().union(*(index.dates.values() or [set()]))
        if not claim_dates.issubset(allowed_dates):
            issues.append("date_mismatch")

    claim_numbers = {_canonical_number(raw) for raw in NUMBER_PATTERN.findall(DATE_PATTERN.sub(" ", stripped))}
    claim_numbers.discard(None)
    hypothesis_in_claim = claim_numbers.intersection(hypothesis_tokens)
    if hypothesis_in_claim and FACT_WORDS.search(stripped) and not HYPOTHESIS_WORDS.search(stripped):
        issues.append("hypothesis_as_market_fact")

    declines = bool(DECLINE_WORDS.search(stripped))
    # 欄位數字在去掉日期後的文字裡找，避免「收盤價出現在 2026 年…」把年份當成收盤價。
    for field, pattern in FIELD_PATTERNS.items():
        for match in pattern.finditer(scrubbed):
            token = _canonical_number(match.group(1))
            owner = subject or (_nearest_subject(scrubbed, match.start(), mentioned, index) if len(mentioned) > 1 else None)
            if owner is None:
                issues.append("ambiguous_symbol_binding")
                continue
            expected = index.facts.get(owner, {}).get(field) or set()
            if declines:
                expected = expected | {_negated(item) for item in expected}
            if token not in expected and token not in _true_thresholds(scrubbed, expected):
                issues.append("unsupported_fact_value")
            if _unit_problem(field, match.group(2) or ""):
                issues.append("unit_mismatch")

    duration = re.search(r"近\s*(\d{1,3})\s*(個月|月|年)", stripped)
    if duration and re.search(r"報酬|波動|回撤|走勢|表現", stripped):
        compact_claim = re.sub(r"\s+|個", "", duration.group(0))
        compact_period = re.sub(r"\s+|個", "", index.period_label)
        if compact_claim not in compact_period:
            issues.append("period_mismatch")

    if required and category != "data_gap":
        subjects = mentioned or ({subject} if subject else set())
        if subjects and any(not _source_satisfied(required, index.successful_tools.get(item, set())) for item in subjects):
            issues.append("required_source_missing")
        elif subjects and any(required in index.stale_tools.get(item, set()) for item in subjects):
            discloses_staleness = bool(claim_dates or re.search(r"過期|較舊|可能不是最新|資料日期|截至", stripped))
            if not discloses_staleness:
                issues.append("stale_evidence_not_disclosed")

    financially_numeric = bool(FACT_WORDS.search(stripped) or re.search(r"[%％元塊美元股張]", stripped))
    if financially_numeric:
        allowed = index.numbers.get(subject, set()) if subject else set().union(*(index.numbers.values() or [set()]))
        allowed |= hypothesis_tokens if category == "user_hypothesis" else set()
        if declines:
            allowed = allowed | {_negated(item) for item in allowed}
        ignored = set(index.symbols) | set().union(*(index.dates.values() or [set()]))
        ignored |= _true_thresholds(scrubbed, allowed)
        for token in claim_numbers:
            if token not in allowed and token not in ignored:
                issues.append("unsupported_number")

    return list(dict.fromkeys(issues))


HEADING_LINE = re.compile(r"^\s{0,3}(?:#{1,6}\s+\S.*|(?:[-*+]\s+)?\*\*[^*]{1,30}\*\*[：:]?)\s*$")
ORPHAN_MARKUP = re.compile(r"(?m)^\s*(?:[-*+]\s*)?(?:\*\*|__)?\s*(?:\*\*|__)?\s*$")


def _tidy_markup(text: str) -> str:
    """刪句後的收尾：去掉只剩符號的行，並修正同一行內落單的粗體記號。"""
    lines = []
    for line in text.splitlines():
        if line.strip() and ORPHAN_MARKUP.fullmatch(line):
            continue
        if line.count("**") % 2 == 1:
            # 落單的記號在行尾就去掉行尾那個，否則去掉第一個。
            head, _, tail = line.rpartition("**")
            line = head + tail if not tail.strip() else line.replace("**", "", 1)
        lines.append(line)
    return "\n".join(lines)


def _drop_empty_headings(text: str) -> str:
    """Remove a heading whose content was entirely rejected (next is another heading or the end)."""
    lines = text.splitlines()
    keep: list[str] = []
    for i, line in enumerate(lines):
        if HEADING_LINE.match(line):
            following = next((row for row in lines[i + 1:] if row.strip()), None)
            if following is None or HEADING_LINE.match(following):
                continue
        keep.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


def _drop_empty_tables(text: str) -> str:
    """Remove Markdown tables whose data rows were all rejected (header and separator only)."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            block = lines[i:j]
            data_rows = [row for row in block[1:] if not re.fullmatch(r"\s*\|?[\s:\-|]+\|?\s*", row)]
            if data_rows:
                out.extend(block)
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def validate_assistant_answer(
    text: str,
    *,
    tools: list[dict[str, Any]],
    hypotheses: list[Any],
    research_context: dict[str, Any],
    fallback: str,
    previous_answer: str | None = None,
) -> ClaimValidationResult:
    """Validate claim-sized units without releasing rejected market assertions."""
    index = EvidenceIndex.build(tools, hypotheses, research_context)
    notes_out: list[str] = []
    output: list[str] = []
    records: list[dict[str, Any]] = []
    paragraph_tainted = False
    kept_meaningful = 0
    rejected = 0
    dependent = 0

    last_kept: tuple[int, int] | None = None  # (output index, record index) of the latest kept sentence
    # Blank lines seen since the last rejection; a footnote one paragraph
    # after removed numbers still refers to them.
    paragraphs_since_rejection = 99
    context_subject: str | None = None
    for claim_index, (chunk, paragraph_break) in enumerate(_split_claims(text)):
        if paragraph_break:
            paragraph_tainted = False
        if not chunk.strip():
            paragraphs_since_rejection += 1
            output.append(chunk)
            continue
        recent_rejection = paragraphs_since_rejection <= 1
        category = _classification(chunk, index)
        issues = _claim_issues(chunk, category, index, context_subject)
        named = _mentioned_symbols(chunk, index)
        if len(named) == 1:
            context_subject = next(iter(named))
        elif len(named) > 1:
            context_subject = None
        if paragraph_tainted and DEPENDENCY_PREFIX.search(chunk.strip()):
            issues.append("depends_on_rejected_claim")
            dependent += 1
        if recent_rejection and not issues and ORPHAN_NOTE_PATTERN.search(chunk):
            issues.append("note_for_removed_content")
            dependent += 1
        if issues:
            rejected += 1
            paragraph_tainted = True
            paragraphs_since_rejection = 0
            # The sentence that only introduced this content is now dangling.
            if last_kept and LEAD_IN_PATTERN.search(output[last_kept[0]].strip()):
                output_index, record_index = last_kept
                output[output_index] = "\n" if output[output_index].endswith(("\n", "\r")) else ""
                records[record_index]["status"] = "rejected"
                records[record_index]["reason_codes"] = ["lead_in_without_content"]
                kept_meaningful -= 1
                rejected += 1
                dependent += 1
                last_kept = None
            # Never echo a rejected claim.  A single audit note is appended
            # after validation instead of filling the answer with one marker
            # per rejected sentence.
            if chunk.endswith(("\n", "\r")):
                output.append("\n")
            status = "rejected"
        else:
            output.append(chunk)
            kept_meaningful += 1
            status = "kept"
            last_kept = (len(output) - 1, len(records))
        records.append({
            "claim_index": claim_index,
            "category": category,
            "status": status,
            "reason_codes": list(dict.fromkeys(issues)),
        })

    if rejected == 0:
        status = "verified"
        final_text = text
    elif kept_meaningful:
        status = "claims_filtered"
        final_text = "".join(output).strip()
        final_text = re.sub(r"(?m)^\s*[-*]\s*$", "", final_text)
        final_text = _tidy_markup(final_text)
        final_text = _drop_empty_tables(final_text)
        final_text = _drop_empty_headings(final_text)
        final_text = re.sub(r"\n{3,}", "\n\n", final_text).strip()
        substantive_lines = [
            line for line in final_text.splitlines()
            if line.strip() and not re.match(r"^\s{0,3}#{1,6}\s+\S", line)
        ]
        meaningful = re.sub(r"[#>*_`\s\-]", "", "\n".join(substantive_lines))
        if len(meaningful) < 6:
            status = "rephrase_kept_previous_verified_answer" if previous_answer else "replaced_with_verified_facts"
            final_text = previous_answer or fallback
        else:
            notes_out.append(f"{rejected} 項數字或日期未通過資料核對，已省略")
    else:
        status = "rephrase_kept_previous_verified_answer" if previous_answer else "replaced_with_verified_facts"
        final_text = previous_answer or fallback

    categories: dict[str, int] = {}
    for record in records:
        categories[record["category"]] = categories.get(record["category"], 0) + 1
    return ClaimValidationResult(
        text=final_text,
        status=status,
        claim_summary={
            "total": len(records),
            "kept": kept_meaningful,
            "rejected": rejected,
            "dependent_rejected": dependent,
            "categories": categories,
            "claims": records,
        },
        notes=notes_out,
    )
