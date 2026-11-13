from __future__ import annotations

import asyncio
import time

from ..core.config import Settings
from ..core.models import HealthResult


class ShioajiProvider:
    name = "Shioaji"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def health(self) -> HealthResult:
        if not self.settings.shioaji_enabled:
            return HealthResult(
                source=self.name,
                status="disabled",
                message="選配行情來源目前關閉；競賽基本功能不依賴 Shioaji",
                required_settings=["SHIOAJI_ENABLED=true", "SHIOAJI_API_KEY", "SHIOAJI_SECRET_KEY"],
            )
        missing = []
        if not self.settings.shioaji_api_key:
            missing.append("SHIOAJI_API_KEY")
        if not self.settings.shioaji_secret_key:
            missing.append("SHIOAJI_SECRET_KEY")
        if missing:
            return HealthResult(
                source=self.name,
                status="pending",
                message="已啟用但缺少必要登入設定",
                required_settings=missing,
            )
        try:
            import shioaji as sj
        except ImportError:
            return HealthResult(
                source=self.name,
                status="pending",
                message="尚未安裝選配套件；請安裝 backend/requirements-shioaji.txt",
                required_settings=["shioaji package"],
            )

        started = time.perf_counter()

        def _check():
            api = sj.Shioaji(simulation=self.settings.shioaji_simulation)
            try:
                accounts = api.login(
                    api_key=self.settings.shioaji_api_key,
                    secret_key=self.settings.shioaji_secret_key,
                    subscribe_trade=False,
                )
                return len(accounts or [])
            finally:
                try:
                    api.logout()
                except Exception:
                    pass

        count = await asyncio.wait_for(asyncio.to_thread(_check), timeout=45)
        return HealthResult(
            source=self.name,
            status="healthy",
            latency_ms=round((time.perf_counter() - started) * 1000),
            record_count=count,
            message="已驗證登入；僅啟用唯讀行情能力，未載入憑證或下單",
        )
