"""Isolated browser-acceptance server. Never loads .env or calls Gemini."""
from __future__ import annotations

import asyncio
import os
from dataclasses import replace

os.environ["FINPILOT_SKIP_DOTENV"] = "1"

import uvicorn

from backend.app import main as main_module


class FixtureAssistant:
    async def stream(self, request):
        message = request.message
        yield {"type": "start", "model": "fixture-model", "conversation_id": request.conversation_id}
        yield {"type": "understanding", "data": {
            "raw_input": message, "normalized_input": message, "context": "assistant", "intent": "explain",
            "target_status": "not_required", "candidates": [], "selected_symbol": None,
            "historical_period": {"label": "預設近 6 個月", "defaulted": True},
            "outlook_period": None, "constraints": [], "corrections": [],
            "message": "隔離驗收理解結果", "source_status": "official", "source_names": ["fixture"],
        }}
        if "[fixture:429]" in message:
            yield {"type": "error", "code": "quota_exceeded", "message": "Gemini 額度或速率限制已達上限，本次已停止，沒有自動重試。"}
            return
        if "[fixture:timeout]" in message:
            yield {"type": "error", "code": "timeout", "message": "Gemini 回答逾時，本次已停止，沒有改用示範回答。"}
            return
        if "[fixture:interrupt]" in message:
            yield {"type": "delta", "text": "已收到部分回答 👩‍💻，但後續串流"}
            await asyncio.sleep(0.12)
            yield {"type": "error", "code": "stream_interrupted", "message": "Gemini 串流中斷，已保留收到的文字，沒有改用示範回答。"}
            return
        if "精彩" in message:
            yield {"type": "clarification", "message": "輸入可能對應多個標的，請先選擇後再繼續。", "candidates": [
                {"symbol": "3374", "name": "精材", "market": "TPEX"},
                {"symbol": "3535", "name": "晶彩科", "market": "TPEX"},
            ]}
            return
        if "那它風險呢" in message and not request.memory.confirmed_symbol:
            yield {"type": "clarification", "message": "目前對話沒有唯一且已確認的標的，請先告訴我要看哪一家公司。", "candidates": []}
            return

        memory = request.memory.model_dump(mode="json")
        if "比較台積電和聯發科" in message:
            answer = "比較結果採相同日期的官方日資料：\n- 2330 台積電：2026-10-08 收盤 100 元。\n- 2454 聯發科：2026-10-08 收盤 80 元。\n這些是日資料，不是即時報價。"
            memory.update(confirmed_symbol=None, recent_symbols=["2330", "2454"], last_intent="compare")
            for symbol in ("2330", "2454"):
                yield {"type": "tool", "name": "market_snapshot", "symbol": symbol, "status": "completed"}
        elif "那它風險呢" in message:
            symbol = request.memory.confirmed_symbol
            answer = f"承接本對話最近確認的 {symbol}：風險說明只使用這段對話的標的，不會混入其他對話。"
        elif "聯發科" in message:
            answer = "聯發科（2454）在 2026-10-08 的官方日收盤為 80 元。這不是即時報價。"
            memory.update(confirmed_symbol="2454", recent_symbols=["2454", "2330"], last_intent="price")
            yield {"type": "tool", "name": "market_snapshot", "symbol": "2454", "status": "completed"}
        elif "台積電" in message:
            answer = "台積電（2330）在 2026-10-08 的官方日收盤為 100 元。這不是即時報價。"
            memory.update(confirmed_symbol="2330", recent_symbols=["2330"], last_intent="price")
            yield {"type": "tool", "name": "market_snapshot", "symbol": "2330", "status": "completed"}
        elif "慢速" in message or "停止" in message:
            answer = (
                "這是隔離的長回答 👩‍💻，用來驗證逐字顯示與捲動控制。\n"
                "第一點：使用者向上閱讀時，畫面位置必須保持。\n"
                "第二點：中文、emoji 🇹🇼 與換行不能被切壞。\n"
                "第三點：只有點擊『查看最新』才移動到新內容。\n"
            ) * 4
        elif "換個說法" in message:
            answer = "換個角度說，ROE 是公司運用股東資金創造獲利的效率；事實定義不變，但例子與說明順序可以不同。"
        else:
            answer = "ROE 可理解為公司使用股東投入資金創造獲利的效率。這是隔離測試回答，不包含即時行情。"

        yield {"type": "verification", "status": "verified", "message": "數字與來源核對完成。"}
        chunks = [answer[index:index + 7] for index in range(0, len(answer), 7)]
        for chunk in chunks:
            yield {"type": "delta", "text": chunk}
            await asyncio.sleep(0.055 if "慢速" in message or "停止" in message else 0.018)
        yield {"type": "done", "memory": memory, "usage": {"total_token_count": 0},
               "model": "fixture-model", "tool_count": 0, "verification": "verified"}


main_module.settings = replace(main_module.settings, gemini_api_key="fixture-only")
main_module.assistant = FixtureAssistant()


if __name__ == "__main__":
    uvicorn.run(main_module.app, host="127.0.0.1", port=8092, log_level="warning")
