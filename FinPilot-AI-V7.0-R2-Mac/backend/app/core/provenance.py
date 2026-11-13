from __future__ import annotations

from urllib.parse import urlparse


def contains_fixture(value) -> bool:
    """Catch both explicitly tagged fixtures and older saved preview records."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, list):
        return any(contains_fixture(item) for item in value)
    if isinstance(value, dict):
        if value.get("data_status") == "fixture":
            return True
        for key in ("url", "source_url"):
            host = urlparse(str(value.get(key) or "")).hostname or ""
            if host.endswith(".invalid"):
                return True
        return any(contains_fixture(item) for item in value.values() if isinstance(item, (dict, list)))
    return False


def require_live_data(value):
    if contains_fixture(value):
        raise ValueError("正式模式拒絕使用隔離資料；本次來源已標記缺失")
    return value
