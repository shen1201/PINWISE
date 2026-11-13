"""Post-restart public-data smoke check. Never invokes Gemini or loads secrets."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx


def main():
    report = {"at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(), "gemini_generation_requests": 0, "requests": 0, "checks": []}
    def record(name, success, **extra):
        row = {"check": name, "success": bool(success), **extra}
        report["checks"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    with httpx.Client(base_url="http://127.0.0.1:8097", timeout=30, trust_env=False) as client:
        def request(method, path, **kwargs):
            report["requests"] += 1
            if report["requests"] > 16:
                raise RuntimeError("已達本次 smoke check 請求上限")
            return client.request(method, path, **kwargs)
        health = request("GET", "/api/health").json()
        report["initial_health"] = health
        assert health["data_mode"] == "live" and not health["preview_fixture_mode"]
        quote = request("GET", "/api/market/quote/0050").json()
        record("0050 official dated daily quote", quote.get("symbol") == "0050" and quote.get("metadata", {}).get("data_status") in {"real", "cache"}, quote=quote)
        today = datetime.now(ZoneInfo("Asia/Taipei")).date()
        history = request("GET", "/api/market/history/2327", params={"start_date": str(today-timedelta(days=30)), "end_date": str(today)}).json()
        valid = isinstance(history, list) and bool(history) and all(row["symbol"] == "2327" for row in history)
        record("2327 symbol-bound history", valid, count=len(history) if isinstance(history, list) else 0,
               latest=max((row["trade_date"] for row in history), default=None) if valid else None)
        payload = request("POST", "/api/stocks/select", json={"query": "台灣被動元件", "product_type": "stock", "limit": 5}).json()
        items = payload.get("items", [])
        record("corrected bounded passive component scope", {row["symbol"] for row in items} == {"2327", "2492"},
               items=[{key: row.get(key) for key in ("symbol", "name", "selection_reason")} for row in items])
        for source in ("TWSE", "TPEx", "MOPS", "FinMind", "官方新聞", "公司法說會"):
            response = request("GET", "/api/sources/health", params={"source": source})
            rows = response.json()
            record(source, response.status_code == 200 and rows[0]["status"] in {"healthy", "stale", "degraded"}, result=rows)
        report["sources"] = request("GET", "/api/sources/status").json()
        report["final_health"] = request("GET", "/api/health").json()
        for path in ("/.env", "/backend/", "/docs/acceptance/p3/live-api.json"):
            response = request("GET", path)
            record("blocked private path " + path, response.status_code == 404, http_status=response.status_code)
    output = Path(__file__).resolve().parents[1] / "docs/acceptance/p3/final-smoke.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evidence: {output}")
    assert all(row["success"] for row in report["checks"])


if __name__ == "__main__":
    main()
