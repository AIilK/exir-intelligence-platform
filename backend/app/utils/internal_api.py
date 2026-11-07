"""فراخوانی APIهای خود بک‌اند مالی از داخل همین پروسه (ابزارهای چت‌بات، آماده‌سازی نمای مدیر).

درخواست مستقیم به اپ FastAPI همین پروسه می‌رود (بدون شبکه)، پس به پورتی که سرور روی آن اجرا شده
(8010 در اجرای عادی) وابسته نیست. ورود با INTERNAL_TOKEN همین پروسه است (کاربر «سیستم»).
"""

from __future__ import annotations

import threading
from typing import Any

_local = threading.local()


class InternalApiError(RuntimeError):
    pass


def _client():
    client = getattr(_local, "client", None)
    if client is None:
        from fastapi.testclient import TestClient

        from app.main import app

        # بدون «with»: lifespan (زمان‌بندها و آماده‌سازی‌ها) دوباره اجرا نمی‌شود
        client = TestClient(app, raise_server_exceptions=False)
        _local.client = client
    return client


def internal_get(path: str) -> Any:
    """GET /api/v1{path} و JSON پاسخ. خطای HTTP به InternalApiError تبدیل می‌شود."""
    from app.auth.guard import INTERNAL_HEADER, INTERNAL_TOKEN

    response = _client().get(f"/api/v1{path}", headers={INTERNAL_HEADER: INTERNAL_TOKEN})
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text[:200]
        raise InternalApiError(f"{response.status_code} {path}: {detail}")
    return response.json()
