"""Bounded real-provider acceptance. At most two generation requests, no retries.

Run against a separately started loopback backend. The backend owns credentials;
this client never loads .env. Non-successful Gemini generation stops the run's
Gemini branch immediately. Public market tests continue independently.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8097")
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    if not args.base.startswith(("http://127.0.0.1:", "http://localhost:")):
        parser.error("驗收只允許本機指定後端")
    report = {"at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(), "base": args.base,
              "gemini_generation_requests": 0, "api_requests": 0, "checks": []}
    client = httpx.Client(base_url=args.base, timeout=55, trust_env=False)
    def call(method, path, **kwargs):
        report["api_requests"] += 1
        if report["api_requests"] > 35:
            raise RuntimeError("本輪已達 35 次 API 請求上限")
        started = time.perf_counter()
        response = client.request(method, path, **kwargs)
        return response, round((time.perf_counter() - started) * 1000)
    def check(check_name, **fields):
        row = {"check": check_name, **fields}
        report["checks"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    try:
        response, ms = call("GET", "/api/health")
        health = response.json()
        report["initial_health"] = health
        if health.get("preview_fixture_mode") or health.get("data_mode") != "live":
            raise RuntimeError("後端不是正式 Provider，拒絕真實驗收")
        report["configuration"] = call("GET", "/api/sources/status")[0].json()
        response, ms = call("GET", "/api/market/quote/0050")
        payload = response.json()
        check("0050 official daily quote", http_status=response.status_code, latency_ms=ms,
              symbol=payload.get("symbol"), name=payload.get("name"), trade_date=payload.get("trade_date"),
              close=payload.get("close"), metadata=payload.get("metadata"), error=payload.get("detail"))
        today = datetime.now(ZoneInfo("Asia/Taipei")).date()
        response, ms = call("GET", "/api/market/history/2327", params={"start_date": (today-timedelta(days=30)).isoformat(), "end_date": today.isoformat()})
        rows = response.json()
        valid = isinstance(rows, list) and bool(rows) and all(row["symbol"] == "2327" for row in rows)
        from backend.app.core.models import PricePoint
        from backend.app.services.analytics import price_metrics
        check("2327 real history", http_status=response.status_code, latency_ms=ms, valid_symbol_binding=valid,
              records=len(rows) if isinstance(rows, list) else 0,
              metrics=price_metrics([PricePoint.model_validate(row) for row in rows]) if valid else {},
              metadata=rows[-1]["metadata"] if valid else None, error=rows.get("detail") if isinstance(rows, dict) else None)
        for source in ("TWSE", "TPEx", "MOPS", "FinMind", "官方新聞", "公司法說會"):
            response, ms = call("GET", "/api/sources/health", params={"source": source})
            check(source, api_http_status=response.status_code, latency_ms=ms, result=response.json())
        if args.generate and health.get("gemini_mode") == "enabled":
            report["gemini_generation_requests"] += 1
            response, ms = call("POST", "/api/assistant/stream", json={"conversation_id": "p3_live_minimal", "message": "請用一句繁體中文解釋分散投資，不需要行情或工具。"})
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            errors = [e for e in events if e.get("type") == "error"]
            done = [e for e in events if e.get("type") == "done"]
            check("real Gemini knowledge SSE", http_status=response.status_code, latency_ms=ms, success=bool(done) and not errors, errors=errors,
                  text="".join(str(e.get("text") or e.get("delta") or "") for e in events if e.get("type") == "delta"), done=done)
            if response.status_code == 200 and done and not errors:
                report["gemini_generation_requests"] += 1
                response, ms = call("POST", "/api/research", json={"query":"研究台灣被動元件近一個月的可核對日價與主要資料缺口", "research_type":"industry_supply_chain", "research_topic":"台灣被動元件", "horizon":"近 1 個月"})
                payload = response.json()
                report["research"] = payload
                check("real industry research", http_status=response.status_code, latency_ms=ms, success=response.status_code==200,
                      model=payload.get("model"), mode=payload.get("data_mode"), verification_status=payload.get("verification_status"),
                      candidates=payload.get("candidates"), coverage=payload.get("metrics",{}).get("coverage"), usage=payload.get("usage"), error=payload.get("detail"))
            else:
                report["gemini_stopped"] = "First actual Gemini request failed; second generation was not sent."
        report["final_health"] = call("GET", "/api/health")[0].json()
        report["final_sources"] = call("GET", "/api/sources/status")[0].json()
    finally:
        client.close()
        output = Path(__file__).resolve().parents[1] / "docs/acceptance/p3/live-api.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Evidence: {output}")


if __name__ == "__main__":
    main()
