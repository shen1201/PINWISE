from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


class UpstreamError(RuntimeError):
    def __init__(self, source: str, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.source = source
        self.status_code = status_code


@dataclass
class _CacheEntry:
    expires_at: float
    value: Any


class ResilientHttpClient:
    def __init__(self, timeout_seconds: float, retries: int, cache_ttl_seconds: int):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            headers={"User-Agent": "FinPilot-R2/1.0 (+local educational research app)"},
        )
        self._retries = retries
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}
        self._observations: dict[str, dict[str, Any]] = {}

    def provenance(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Keep the original network fetch time even when normalized from cache."""
        row = self._observations.get(self._cache_key(url, params))
        return {"fetched_at": row["fetched_at"], "data_status": row["data_status"]} if row else {"data_status": "unverified"}

    def source_observation(self, source: str) -> dict[str, Any] | None:
        rows = [row for row in self._observations.values() if row["source"] == source]
        return max(rows, key=lambda row: row["checked_at"]) if rows else None

    async def close(self) -> None:
        await self._client.aclose()

    async def _pace(self, source: str, min_interval: float) -> None:
        lock = self._locks.setdefault(source, asyncio.Lock())
        async with lock:
            elapsed = time.monotonic() - self._last_request.get(source, 0.0)
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_request[source] = time.monotonic()

    def forget(self, *needles: str) -> None:
        """清掉網址或參數含指定文字的快取，下次請求會重新向來源取得。"""
        for key in [key for key in self._cache if any(needle in key for needle in needles)]:
            del self._cache[key]

    def drop(self, url: str, params: dict[str, Any] | None = None) -> None:
        """移除單一請求的快取（例如來源以 HTTP 200 回傳錯誤內容時，不該被記住）。"""
        self._cache.pop(self._cache_key(url, params), None)

    @staticmethod
    def _cache_key(url: str, params: dict[str, Any] | None) -> str:
        safe = tuple(sorted((key, "<secret>" if "token" in key.lower() or "key" in key.lower() else str(value)) for key, value in (params or {}).items()))
        return f"{url}|{safe}"

    async def request(
        self,
        source: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cache_ttl: int | None = None,
        min_interval: float = 0.2,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        key = self._cache_key(url, {**(params or {}), **(json_body or {})} or None)
        cached = self._cache.get(key)
        if cached and cached.expires_at > time.monotonic():
            if key in self._observations:
                self._observations[key].update(data_status="cache", checked_at=datetime.now(timezone.utc))
            return cached.value

        await self._pace(source, min_interval)
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                if json_body is None:
                    response = await self._client.get(url, params=params, headers=headers)
                else:
                    response = await self._client.post(url, params=params, headers=headers, json=json_body)
                now = datetime.now(timezone.utc)
                self._observations[key] = {"source": source, "checked_at": now, "fetched_at": now,
                    "data_status": "real" if response.status_code < 400 else "missing",
                    "http_status": response.status_code, "endpoint": url}
                if response.status_code < 400:
                    ttl = self._cache_ttl if cache_ttl is None else cache_ttl
                    if ttl > 0:
                        self._cache[key] = _CacheEntry(time.monotonic() + ttl, response)
                    return response
                if response.status_code not in {429, 500, 502, 503, 504}:
                    raise UpstreamError(source, f"上游服務回傳 HTTP {response.status_code}", status_code=response.status_code)
                last_error = UpstreamError(source, f"上游服務暫時無法使用（HTTP {response.status_code}）", status_code=response.status_code)
                retry_after = response.headers.get("Retry-After")
                delay = min(5.0, float(retry_after)) if retry_after and retry_after.isdigit() else min(4.0, 0.5 * (2**attempt))
            except UpstreamError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                now = datetime.now(timezone.utc)
                self._observations[key] = {"source": source, "checked_at": now, "fetched_at": now,
                    "data_status": "missing", "http_status": None, "endpoint": url}
                delay = min(4.0, 0.5 * (2**attempt))
            if attempt < self._retries:
                await asyncio.sleep(delay)

        if isinstance(last_error, UpstreamError):
            # Preserve the final 429/5xx response after retries.  Replacing it
            # with a generic network error prevents the API and UI from
            # distinguishing rate limits from upstream failures.
            raise last_error
        if isinstance(last_error, httpx.TimeoutException):
            raise UpstreamError(source, "連線逾時") from last_error
        raise UpstreamError(source, "無法連線上游服務") from last_error

    async def get_json(self, source: str, url: str, **kwargs: Any) -> Any:
        response = await self.request(source, url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            params, body = kwargs.get("params"), kwargs.get("json_body")
            key = self._cache_key(url, {**(params or {}), **(body or {})} or None)
            # 上游可能以 HTTP 200 回傳維護或驗證頁，這種回應不能留在快取裡。
            self._cache.pop(key, None)
            if key in self._observations:
                self._observations[key]["data_status"] = "missing"
            raise UpstreamError(source, "上游回傳不是有效 JSON") from exc

    async def get_text(self, source: str, url: str, **kwargs: Any) -> str:
        response = await self.request(source, url, **kwargs)
        return response.text
