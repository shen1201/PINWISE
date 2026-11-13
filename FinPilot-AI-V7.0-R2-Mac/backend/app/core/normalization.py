from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


MISSING_TEXT = {"", "--", "---", "-", "－", "N/A", "null", "None"}


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text in MISSING_TEXT else text


def parse_number(value: Any) -> float | None:
    text = clean_text(value)
    if text is None:
        return None
    text = text.replace(",", "").replace("＋", "+").replace("－", "-")
    text = re.sub(r"[^0-9.+-]", "", text)
    if text in {"", "+", "-", "."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_integer(value: Any) -> int | None:
    number = parse_number(value)
    return None if number is None else int(number)


def parse_roc_date(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    try:
        if len(digits) == 7:  # YYYMMDD
            return date(int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:7]))
        if len(digits) == 8:  # YYYYMMDD
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_datetime(date_value: Any, time_value: Any = None) -> datetime | None:
    parsed_date = parse_roc_date(date_value)
    if not parsed_date:
        return None
    digits = re.sub(r"\D", "", str(time_value or ""))
    digits = digits.zfill(6)[:6]
    try:
        return datetime(
            parsed_date.year,
            parsed_date.month,
            parsed_date.day,
            int(digits[:2] or 0),
            int(digits[2:4] or 0),
            int(digits[4:6] or 0),
            tzinfo=ZoneInfo("Asia/Taipei"),
        )
    except ValueError:
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=ZoneInfo("Asia/Taipei"))


def parse_iso_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        parsed_date = parse_roc_date(text)
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc) if parsed_date else None


def is_stale(value: date | datetime | None, hours: int) -> bool:
    if value is None:
        return True
    moment = value if isinstance(value, datetime) else datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds() > hours * 3600


def normalized_symbol(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z-]", "", value.strip()).upper()
