from __future__ import annotations

import math
import statistics
from typing import Any


# 台股單日漲跌幅上限 10%、槓桿型 ETF 20%，超出這個範圍的跳動幾乎都是分割或合併，不是真實報酬。
SPLIT_RATIO_LOW = 0.55
SPLIT_RATIO_HIGH = 1.8


def price_metrics(points: list[Any]) -> dict[str, Any]:
    """Calculate reproducible metrics from normalized daily closes."""
    symbols = {point.symbol for point in points if hasattr(point, "symbol")}
    if len(symbols) > 1:
        raise ValueError("不同股票的歷史行情不可混合計算")
    valid = [point for point in points if getattr(point, "close", None) is not None
             and math.isfinite(float(point.close)) and float(point.close) > 0]
    valid = list({point.trade_date: point for point in valid}.values())
    if not valid:
        return {
            "observations": 0,
            "period_return_pct": None,
            "annualized_volatility_pct": None,
            "max_drawdown_pct": None,
            "average_volume_shares": None,
            "period_high": None,
            "period_low": None,
        }
    valid.sort(key=lambda point: point.trade_date)
    closes = [float(point.close) for point in valid]
    returns = [(current / previous) - 1 for previous, current in zip(closes, closes[1:]) if previous]
    peak = closes[0]
    drawdowns = []
    for close in closes:
        peak = max(peak, close)
        drawdowns.append((close / peak) - 1 if peak else 0)
    volumes = [point.volume_shares for point in valid if point.volume_shares is not None]
    period_return = (closes[-1] / closes[0] - 1) * 100 if len(closes) > 1 and closes[0] else None
    volatility = statistics.stdev(returns) * math.sqrt(252) * 100 if len(returns) > 1 else None
    return {
        "observations": len(valid),
        "period_start": valid[0].trade_date.isoformat(),
        "period_end": valid[-1].trade_date.isoformat(),
        "period_return_pct": round(period_return, 2) if period_return is not None else None,
        "annualized_volatility_pct": round(volatility, 2) if volatility is not None else None,
        "max_drawdown_pct": round(min(drawdowns) * 100, 2),
        "average_volume_shares": round(sum(volumes) / len(volumes)) if volumes else None,
        "period_high": max(closes),
        "period_low": min(closes),
        "latest_close": closes[-1],
        # 歷史價未還原：有這個欄位時，報酬、波動與回撤都會被分割扭曲。
        "suspected_split_dates": [point.trade_date.isoformat() for previous, point in zip(closes, valid[1:])
                                  if not SPLIT_RATIO_LOW <= float(point.close) / previous <= SPLIT_RATIO_HIGH],
    }


def completeness(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(evidence)
    from urllib.parse import urlparse
    def eligible(item):
        url = urlparse(str(item.get("url") or ""))
        return (not item.get("missing") and item.get("data_status") in {"real", "cache"}
                and url.scheme in {"http", "https"} and bool(url.hostname)
                and not url.hostname.endswith(".invalid") and "Gemini" not in item.get("source", ""))
    available = sum(1 for item in evidence if eligible(item))
    stale = sum(1 for item in evidence if item.get("stale"))
    return {
        "available_sources": available,
        "missing_sources": sum(1 for item in evidence if item.get("missing")),
        "unverified_sources": sum(1 for item in evidence if not item.get("missing") and not eligible(item)),
        "fixture_sources": sum(1 for item in evidence if item.get("data_status") == "fixture"),
        "stale_sources": stale,
        "total_sources": total,
        "completeness_pct": round(available / total * 100) if total else 0,
        "rule": "real-or-cache-with-source-url / planned-evidence-items; per-symbol 5 datasets + 1 market-wide news; Gemini excluded; stale counted but disclosed",
        "verified_evidence_ids": [item.get("evidence_id") for item in evidence if eligible(item)],
    }
