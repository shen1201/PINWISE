"""P1 browser-acceptance server using the real assistant orchestration and fixed providers.

It forces dotenv loading off, never calls external APIs, and exposes only a small
QA audit route containing fixture call counts (no prompts, keys, or user secrets).
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import shutil
import tempfile
from dataclasses import replace

os.environ["FINPILOT_SKIP_DOTENV"] = "1"
os.environ["FINPILOT_PREVIEW_FIXTURE_MODE"] = "1"
_fixture_data_dir = tempfile.mkdtemp(prefix="finpilot-p1-browser-")
os.environ["FINPILOT_DATA_DIR"] = _fixture_data_dir
atexit.register(shutil.rmtree, _fixture_data_dir, ignore_errors=True)

import uvicorn
from fastapi.responses import JSONResponse
from starlette.routing import Route

from backend.app import main as main_module
from backend.tests.test_assistant import FakeFinMind, FakeMarket, FakeMops, make_service


class BrowserFixtureGemini:
    def __init__(self):
        self.calls = 0
        self.messages: list[str] = []

    async def stream_assistant(self, prompt):
        self.calls += 1
        payload = json.loads(prompt.split("\n", 1)[1])
        message = payload["current_message"]
        intent = payload["research_context"]["intent"]
        self.messages.append(message)

        if "[fixture:429]" in message:
            raise RuntimeError("429 RESOURCE_EXHAUSTED fixture")
        if "[fixture:timeout]" in message:
            raise asyncio.TimeoutError()
        if "[fixture:interrupt]" in message:
            yield {"text": "已收到部分隔離回答 👩‍💻，但後續串流"}
            await asyncio.sleep(0.12)
            raise RuntimeError("fixture connection reset")

        if "慢速" in message or "停止" in message:
            answer = (
                "這是 P1 隔離長回答 👩‍💻，用來驗證逐字顯示與捲動控制。\n"
                "第一點：使用者向上閱讀時，畫面位置必須保持。\n"
                "第二點：中文、emoji 🇹🇼 與換行不能被切壞。\n"
                "第三點：停止後保留部分內容，重試才建立新回答。\n"
            ) * 4
            delay = 0.06
        elif intent == "investment_decision":
            if "0050" in message and "新手" in message:
                answer = (
                    "先說結論：**0050** 是一籃子大型股，比單押一家公司分散，"
                    "但不等於不會處損。新手是否適合，主要看這筆錢能放多久、下跌時能否繼續持有。\n\n"
                    "- 優點：單次參與多家大型企業。\n"
                    "- 要注意：持股仍可能集中在少數大型公司，也有整體市場風險。\n\n"
                    "這是隔離資料驗收，不是目前行情或個人買賣建議。"
                )
            else:
                answer = "先說結論：是否值得買仍要看可承受風險；本回答只使用剛取得的公開資料與缺漏。"
            delay = 0.012
        elif intent == "target_price_scenario":
            answer = "900 元是使用者提出的環球晶價格假設，不是已確認行情；分析會保留這個前提。"
            delay = 0.012
        elif intent == "compare":
            symbols = payload["research_context"].get("research_targets") or []
            if symbols and all(str(symbol).startswith("00") for symbol in symbols):
                assumptions = payload.get("understanding", {}).get("assumptions") or []
                prefix = f"系統已透明採用可修改的比較起點：{assumptions[0]}。" if assumptions else ""
                answer = prefix + "ETF 比較只使用隔離日資料；費用、成分與配息來源若未取得會明確列為缺漏。"
            else:
                answer = "比較時保留原本的環球晶，再加入中美晶，並以相同資料口徑說明差異與風險。"
            delay = 0.012
        elif intent == "rephrase":
            answer = "白話說：現在是在比較環球晶和中美晶；900 元只是你替環球晶設定的假設，不是市場現價。"
            delay = 0.012
        elif intent == "risk_analysis":
            answer = "承接目前唯一標的說明風險；資料日期與缺漏仍以這一輪工具結果為準。"
            delay = 0.012
        else:
            answer = "這是 P1 隔離知識回答，不包含即時行情或私人投資資料。"
            delay = 0.012

        for index in range(0, len(answer), 6):
            yield {"text": answer[index:index + 6]}
            await asyncio.sleep(delay)
        yield {"usage": {"total_token_count": 0}}


fixture_market = FakeMarket()
fixture_finmind = FakeFinMind()
fixture_mops = FakeMops()
fixture_gemini = BrowserFixtureGemini()
fixture_assistant = make_service(
    market=fixture_market, finmind=fixture_finmind, mops=fixture_mops, gemini=fixture_gemini,
)

main_module.settings = replace(main_module.settings, gemini_api_key="fixture-only")
main_module.assistant = fixture_assistant


async def qa_audit(_request):
    return JSONResponse({
        "isolated_fixture": True,
        "research_preview_fixture": bool(main_module.settings.preview_fixture_mode),
        "real_gemini_calls": 0,
        "fixture_model_calls": fixture_gemini.calls,
        "messages": fixture_gemini.messages,
        "market_snapshot_calls": fixture_market.calls,
        "history_calls": [symbol for symbol, _start, _end in fixture_finmind.calls],
        "company_calls": fixture_mops.company_calls,
        "material_event_calls": fixture_mops.disclosure_calls,
    })


# StaticFiles is mounted at `/`; prepend the audit route so it cannot be shadowed.
main_module.app.router.routes.insert(0, Route("/__qa/p1-audit", qa_audit, methods=["GET"]))


if __name__ == "__main__":
    uvicorn.run(main_module.app, host="127.0.0.1", port=8093, log_level="warning")
