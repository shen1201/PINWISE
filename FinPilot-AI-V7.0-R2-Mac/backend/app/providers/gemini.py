from __future__ import annotations

import json
import time
from typing import Any

from google import genai
from google.genai import types

from ..core.config import Settings
from ..core.http_client import ResilientHttpClient
from ..core.models import HealthResult
from ..core.models import utc_now


RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "candidates": {"type": "array", "items": {"type": "string"}},
        "evidence_notes": {"type": "array", "items": {"type": "string"}},
        "invalidation_conditions": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        # 可持續追蹤：之後要觀察哪些可由官方資料更新的條件
        "watch_items": {"type": "array", "items": {"type": "object", "properties": {
            "symbol": {"type": "string"}, "item": {"type": "string"}, "why": {"type": "string"},
        }, "required": ["symbol", "item", "why"]}},
    },
    "required": ["summary", "risks", "candidates", "evidence_notes", "invalidation_conditions", "limitations", "watch_items"],
}



RETRY_DELAY_SECONDS = 1.5


def _transient(exc: Exception) -> bool:
    """Gemini 伺服器忙碌或內部錯誤（500／502／503）。429 額度、400 參數錯誤與逾時都不算。"""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code in (500, 502, 503)

class GeminiProvider:
    name = "Gemini"

    is_fixture = False

    def __init__(self, settings: Settings, http: ResilientHttpClient, budget=None):
        self.settings = settings
        self.http = http
        self.budget = budget
        self.last_connection = None
        self.last_call = None
        self.blocked_status = None

    def _record(self, started, *, status=200, usage=None, operation="generation"):
        ok = status == 200
        self.last_connection = HealthResult(source=self.name, status="healthy" if ok else "error",
            latency_ms=round((time.perf_counter() - started) * 1000), http_status=status,
            message=f"{self.settings.gemini_model}：{'實際生成成功' if ok else '呼叫失敗，已停止自動重試'}（HTTP {status or '未取得回應'}）")
        self.last_call = {"operation": operation, "model": self.settings.gemini_model,
            "http_status": status, "latency_ms": self.last_connection.latency_ms,
            "checked_at": utc_now().isoformat(), "usage": usage or {}}
        if status in {401, 403, 404, 429}:
            self.blocked_status = status

    def _assert_available(self):
        if not self.available:
            raise RuntimeError("Gemini 未啟用或缺少 GEMINI_API_KEY")
        if self.blocked_status:
            raise RuntimeError(f"Gemini 先前回傳 HTTP {self.blocked_status}；本程序已停止後續生成，請確認設定後重啟")

    @property
    def available(self) -> bool:
        return bool(getattr(self.settings, "gemini_enabled", True) and self.settings.gemini_api_key)

    async def health(self) -> HealthResult:
        from urllib.parse import quote
        endpoint = "https://generativelanguage.googleapis.com/v1beta/models/" + quote(self.settings.gemini_model, safe="")
        if not getattr(self.settings, "gemini_enabled", True):
            return HealthResult(
                source=self.name,
                status="disabled",
                message="真實 Gemini 已由伺服器設定關閉",
                endpoint=endpoint,
            )
        if not self.settings.gemini_api_key:
            return HealthResult(
                source=self.name,
                status="pending",
                message="缺少 GEMINI_API_KEY，程式已完成但尚未驗證帳戶權限",
                endpoint=endpoint,
                required_settings=["GEMINI_API_KEY"],
            )
        started = time.perf_counter()
        response = await self.http.get_json(
            self.name,
            endpoint,
            headers={"x-goog-api-key": self.settings.gemini_api_key},
            cache_ttl=60,
            min_interval=1.0,
        )
        model_found = isinstance(response, dict) and response.get("name") == f"models/{self.settings.gemini_model}"
        return HealthResult(
            source=self.name,
            status="healthy" if model_found else "degraded",
            latency_ms=round((time.perf_counter() - started) * 1000),
            record_count=int(model_found),
            message=f"金鑰與設定模型 {self.settings.gemini_model} 的 metadata 請求成功；未測試生成" if model_found else "請求成功，但回傳模型與設定不符",
            endpoint=endpoint,
            http_status=200,
        )

    async def generate_research(self, prompt: str) -> dict[str, Any]:
        return await self.generate_json(
            prompt, schema=RESEARCH_SCHEMA, operation="research", temperature=0.2,
            max_output_tokens=getattr(self.settings, "research_max_output_tokens", 2048),
            system_instruction=(
                "你是台灣股票研究助理，對象包含第一次投資的新手。只能依輸入的可追溯資料整理，不得補造數字或來源；"
                "先用白話回答使用者真正的問題，再說明依據；資料不足時明確指出缺口。內容僅供研究教育，不構成投資建議。"
            ),
        )

    async def generate_json(self, prompt: str, *, schema: dict[str, Any], system_instruction: str,
                            max_output_tokens: int, temperature: float = 0.2,
                            operation: str = "generation") -> dict[str, Any]:
        """One structured JSON generation: budget reserved first, SDK retries disabled."""
        self._assert_available()
        started = time.perf_counter()

        reservation = None
        if self.budget:
            reservation = await self.budget.reserve(prompt, max_output_tokens)

        def _generate():
            # 真實驗證不在 SDK 內對 429、5xx 或逾時連續重試；
            # 研究服務會將原始失敗分類後如實回報給前端。
            request_timeout_ms = int(max(30, self.settings.request_timeout_seconds * 5) * 1000)
            client = genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=types.HttpOptions(
                    timeout=request_timeout_ms,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            try:
                response = client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_json_schema=schema,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                    ),
                )
            finally:
                client.close()
            parsed = json.loads(response.text)
            usage = getattr(response, "usage_metadata", None)
            if usage:
                if hasattr(usage, "model_dump"):
                    parsed["_usage"] = usage.model_dump(mode="json", exclude_none=True)
                else:
                    parsed["_usage"] = {
                        key: value for key in ("prompt_token_count", "candidates_token_count", "total_token_count")
                        if (value := getattr(usage, key, None)) is not None
                    }
            return parsed

        import asyncio

        try:
            try:
                result = await asyncio.wait_for(asyncio.to_thread(_generate), timeout=max(30, self.settings.request_timeout_seconds * 5))
            except Exception as first:
                # 伺服器忙碌（500／503）通常幾秒後就恢復，且沒有產生 Token：等一下重試一次。429 額度與逾時不重試。
                if not _transient(first):
                    raise
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                result = await asyncio.wait_for(asyncio.to_thread(_generate), timeout=max(30, self.settings.request_timeout_seconds * 5))
        except Exception as exc:
            self._record(started, status=getattr(exc, "code", None), operation=operation)
            import httpx
            if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
                raise asyncio.TimeoutError("Gemini 連線逾時；未自動重試") from None
            raise RuntimeError(f"Gemini 呼叫失敗（HTTP {getattr(exc, 'code', None) or '未取得回應'}）；{'已重試 1 次仍失敗' if _transient(exc) else '未自動重試'}") from None
        self._record(started, usage=result.get("_usage"), operation=operation)
        if reservation:
            await reservation.commit(result.get("_usage"))
        return result

    async def stream_assistant(self, prompt: str):
        """Stream one assistant answer with SDK retries disabled."""
        self._assert_available()
        started = time.perf_counter()
        reservation = None
        if self.budget:
            reservation = await self.budget.reserve(prompt, self.settings.assistant_max_output_tokens)
        request_timeout_ms = int(max(20, self.settings.request_timeout_seconds * 4) * 1000)
        client = genai.Client(
            api_key=self.settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=request_timeout_ms,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        usage_payload: dict[str, Any] | None = None
        yielded = False
        retried = False

        async def open_stream():
            return await client.aio.models.generate_content_stream(
                model=self.settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "你是單一的 PINWISE 助手。使用繁體中文，依當次問題自然調整深淺。"
                        "當次明確要求優先於歷史偏好。只能把系統提供的工具結果當作行情、公司或公告證據；"
                        "歷史對話不是新行情證據。日行情必須說明交易日且不得稱為即時價。"
                        "第一句用粗體寫出一句話結論，再補充必要背景。research_context 中的 verified_market_information 是已確認資料，"
                        "user_hypotheses 是使用者提出的假設而不是行情，missing_or_unavailable 是不可假裝已取得的缺口。"
                        "程式計算指標、已確認事實、使用者假設與模型情境推論必須用文字清楚區分。"
                        "投資決策只能提供有利條件、風險、觀察條件與失效情境，不得宣稱保證漲跌或唯一合理價；"
                        "小標題用白話，例如「優點」「要注意的地方」「適合誰」，不要用「支持因素」「反方風險與失效情境」等報告術語。"
                        "條列的子項目要縮排在所屬項目之下。"
                        "不得補造數字、公司、日期、來源或 URL。資料不足就明確說明。"
                        "工具結果沒有資料或本次沒有查詢工具時，不得說「沒有公告」「目前沒有」這類否定事實，要說查不到、無法確認；"
                        "也不得憑一般印象描述特定公司或基金的事件、公告與制度慣例。"
                        "一般對話使用自然段落，不要固定輸出「已確認市場事實」、「風險」、「資料缺口」等報告標題；"
                        "只在問題複雜、條列或表格有助閱讀時才使用 Markdown 結構。"
                        "介面會在回答下方另外顯示資料日期、來源與核對結果，回答結尾不要再寫資料來源、資料時效或核對說明。"
                        "不要在回答中使用「已確認事實」「程式計算之」「確定指標」等系統內部用語，直接用一般人看得懂的說法。"
                        "若 instructions 表示系統會產生數字比較表，文字只說明差異的意義，不要再逐一重複表格裡的數字。"
                        "回答可改變措辭、例子與順序，但不得改變事實。內容僅供研究教育，不構成投資建議。"
                    ),
                    temperature=0.65,
                    max_output_tokens=self.settings.assistant_max_output_tokens,
                    # Tools run through PINWISE's validated allowlist before
                    # this call; Gemini itself cannot invoke functions.
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )

        try:
            while True:
                try:
                    stream = await open_stream()
                    async for chunk in stream:
                        if text := getattr(chunk, "text", None):
                            yielded = True
                            yield {"text": text}
                        usage = getattr(chunk, "usage_metadata", None)
                        if usage:
                            usage_payload = usage.model_dump(mode="json", exclude_none=True) if hasattr(usage, "model_dump") else {}
                            yield {"usage": usage_payload}
                    break
                except Exception as exc:
                    # 還沒收到任何文字、而且是伺服器忙碌（500／503）時，等一下重試一次；已經開始回答就不重試，避免重複內容。
                    if yielded or retried or not _transient(exc):
                        raise
                    retried = True
                    import asyncio
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
            self._record(started, usage=usage_payload, operation="assistant")
        except Exception as exc:
            self._record(started, status=getattr(exc, "code", None), operation="assistant")
            import asyncio
            import httpx
            if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
                raise RuntimeError("Gemini 助手連線逾時；未自動重試") from None
            raise RuntimeError(f"Gemini 呼叫失敗（HTTP {getattr(exc, 'code', None) or '未取得回應'}）；{'已重試 1 次仍失敗' if retried else '未自動重試'}") from None
        finally:
            await client.aio.aclose()
            if reservation:
                await reservation.commit(usage_payload)
