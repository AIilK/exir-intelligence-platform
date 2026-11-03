"""نگهبان APIها: هر درخواست /api/v1 باید از کاربر واردشده باشد و به ماژول همان API دسترسی داشته باشد.

- نشست با کوکی HttpOnly «exir_session» (یا هدر Authorization: Bearer) شناخته می‌شود.
- فراخوانی‌های داخلی خود بک‌اند (ابزارهای چت‌بات) با INTERNAL_TOKEN که فقط در حافظه همین پروسه است عبور می‌کنند.
- پنل مغایرت‌گیری که کلید API معتبر خودش را می‌فرستد، مثل قبل کار می‌کند.
"""

from __future__ import annotations

import secrets
import time
from secrets import compare_digest
from typing import Any

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.auth import store
from app.auth.modules import api_allowed
from app.core.config import settings

COOKIE_NAME = "exir_session"
INTERNAL_HEADER = "X-Exir-Internal"
INTERNAL_TOKEN = secrets.token_urlsafe(32)
SYSTEM_USER: dict[str, Any] = {"id": 0, "username": "system", "full_name": "سیستم", "is_admin": True, "modules": []}
PUBLIC_PATHS = {"/api/v1/auth/login", "/api/v1/auth/status", "/api/v1/auth/setup", "/api/v1/auth/logout"}
CACHE_SECONDS = 20
_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}


def request_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(COOKIE_NAME)


async def _user(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    hit = _cache.get(token)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    user = await run_in_threadpool(store.user_for_token, token)
    if len(_cache) > 2000:
        _cache.clear()
    _cache[token] = (time.monotonic(), user)
    return user


def forget_token(token: str | None) -> None:
    if token:
        _cache.pop(token, None)


def forget_all() -> None:
    _cache.clear()


def _reconciliation_key_ok(request: Request) -> bool:
    configured = settings.reconciliation_api_key.strip()
    provided = (request.headers.get("x-reconciliation-api-key") or "").strip()
    return bool(configured and provided and compare_digest(configured, provided))


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if not settings.auth_enabled or request.method == "OPTIONS" or not path.startswith("/api/v1") or path in PUBLIC_PATHS:
        return await call_next(request)
    internal = request.headers.get(INTERNAL_HEADER, "")
    if internal and compare_digest(internal, INTERNAL_TOKEN):
        request.state.user = SYSTEM_USER
        return await call_next(request)
    if path.startswith("/api/v1/treasury") and _reconciliation_key_ok(request):
        request.state.user = SYSTEM_USER
        return await call_next(request)
    user = await _user(request_token(request))
    if not user:
        return JSONResponse({"detail": "برای استفاده از اپ وارد شوید.", "code": "login_required"}, status_code=401)
    if not api_allowed(user, path):
        return JSONResponse({"detail": "به این بخش دسترسی ندارید.", "code": "forbidden"}, status_code=403)
    request.state.user = user
    return await call_next(request)


def current_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if user is None and not settings.auth_enabled:
        return SYSTEM_USER
    if user is None:
        raise HTTPException(401, detail="برای استفاده از اپ وارد شوید.")
    return user


def require_admin(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if not user.get("is_admin"):
        raise HTTPException(403, detail="فقط مدیر سیستم به این بخش دسترسی دارد.")
    return user
