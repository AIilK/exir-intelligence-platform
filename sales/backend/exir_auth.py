"""ورود و سطح دسترسی برای API فروش — همان کاربران و ماژول‌های بک‌اند مالی (backend/app/auth).

- مرورگر کوکی «exir_session» را می‌فرستد (یک بار ورود در داشبورد یکپارچه یا مالی کافی است)؛
  این‌جا با GET {FINANCE_API_URL}/api/v1/auth/me کاربر و ماژول‌هایش شناخته می‌شود (۳۰ ثانیه کش).
- فراخوانی‌های سرور-به-سرور بک‌اند مالی با هدر X-Exir-Internal-Key (فایل مشترک «.exir_internal_key» ریشه مخزن) عبور می‌کنند.
- تنظیم در sales/.env یا متغیر محیطی: FINANCE_API_URL (پیش‌فرض http://127.0.0.1:8010)، SALES_AUTH_ENABLED=false برای خاموش کردن.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from secrets import compare_digest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent.parent          # sales/
KEY_FILE = ROOT.parent / ".exir_internal_key"          # ریشه مخزن، کنار backend/ مالی
COOKIE = "exir_session"
CACHE_SECONDS = 30
_cache: dict[str, tuple[float, dict | None]] = {}

# مسیرهایی که هر کاربر واردشده می‌بیند (وضعیت منبع داده و فیلترهای سربرگ داشبورد یکپارچه)
ANY_USER = ("/api/meta", "/api/stamp")
# فقط مدیر سیستم: تغییر منبع داده، تنظیمات و تارگت
ADMIN_ONLY = ("/api/sources/sql", "/api/sources/refresh", "/api/settings", "/api/plan/target", "/api/plan/settings",
              "/api/inventory/settings")
# API فروش ← ماژول‌های مجاز (کلیدها همان backend/app/auth/modules.py؛ مسیر صفحه‌ها در unified/src/Shell.jsx).
SALES_ALL = {"sales", "salesOverview", "salesHybrid", "salesTeam", "salesProducts", "salesCustomers", "salesAnalysis",
             "salesInventory", "salesB2B", "salesExport"}
REPORTS = {"salesProducts", "salesAnalysis"}
# (مسیر، فقط دقیقاً همین مسیر؟، ماژول‌ها) — اولین تطابق اعمال می‌شود
API_MODULES: list[tuple[str, bool, set[str]]] = [
    ("/api/overview", False, {"salesOverview"}),
    ("/api/monthly", False, {"sales", "management", "salesOverview", "salesHybrid", "salesTeam"}),
    ("/api/hybrid", False, {"sales", "management", "salesOverview", "salesHybrid"}),
    ("/api/team", False, {"salesTeam"}),
    ("/api/inactive", False, {"salesTeam"}),
    ("/api/products", False, {"salesProducts"}),
    ("/api/customers", False, {"salesCustomers"}),
    ("/api/analysis", False, {"salesAnalysis"}),
    ("/api/report_tree", False, REPORTS), ("/api/category_matrix", False, REPORTS),
    ("/api/daily_matrix", False, REPORTS), ("/api/brand_share", False, REPORTS),
    ("/api/detail", False, SALES_ALL),
    ("/api/inventory", False, {"salesInventory"}),
    ("/api/chain_sellout", False, {"salesInventory"}), ("/api/online_sellout", False, {"salesInventory"}),
    # پرونده نمایندگان راهکاران برای «پرونده مشتری» هم باز است
    ("/api/rk_sales/customers", True, {"salesB2B", "customers"}),
    ("/api/rk_sales/customer", True, {"salesB2B", "customers"}),
    ("/api/rk_sales", False, {"salesB2B"}),
    ("/api/rk_export", False, {"salesExport"}),
    ("/api/plan", False, {"sales"}),
]


def _env_value(name: str, default: str) -> str:
    if os.environ.get(name):
        return os.environ[name].strip()
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return default


FINANCE_API = _env_value("FINANCE_API_URL", "http://127.0.0.1:8010").rstrip("/")
ENABLED = _env_value("SALES_AUTH_ENABLED", "true").lower() not in ("0", "false", "no")


def internal_key() -> str:
    env = os.environ.get("EXIR_INTERNAL_KEY", "").strip()
    if env:
        return env
    try:
        with open(KEY_FILE, "x", encoding="utf-8") as f:
            key = secrets.token_urlsafe(32)
            f.write(key)
            return key
    except FileExistsError:
        return KEY_FILE.read_text(encoding="utf-8").strip()


def _token(request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(COOKIE)


def _profile(token: str) -> dict | None:
    """None = نشست نامعتبر. خطای اتصال به بک‌اند مالی بالا داده می‌شود."""
    hit = _cache.get(token)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    req = Request(f"{FINANCE_API}/api/v1/auth/me", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=10) as r:
            profile = json.loads(r.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code not in (401, 403):
            raise
        profile = None
    if len(_cache) > 2000:
        _cache.clear()
    _cache[token] = (time.monotonic(), profile)
    return profile


def allowed(profile: dict, path: str, method: str) -> bool:
    user = profile.get("user") or {}
    if user.get("is_admin"):
        return True
    mods = set(profile.get("modules") or [])
    if path.startswith(ANY_USER) or (path == "/api/sources" and method == "GET"):
        return True
    if path.startswith(ADMIN_ONLY) or method not in ("GET", "HEAD"):
        return False
    for prefix, exact, need in API_MODULES:
        if path == prefix or (not exact and path.startswith(prefix)):
            return bool(mods & need)
    return bool(mods & SALES_ALL)


async def middleware(request, call_next):
    path = request.url.path
    if not ENABLED or request.method == "OPTIONS" or not path.startswith("/api/"):
        return await call_next(request)
    key = request.headers.get("x-exir-internal-key", "")
    if key and compare_digest(key, internal_key()):
        return await call_next(request)
    token = _token(request)
    if not token:
        return JSONResponse({"detail": "برای استفاده از داشبورد وارد شوید.", "code": "login_required"}, status_code=401)
    from fastapi.concurrency import run_in_threadpool
    try:
        profile = await run_in_threadpool(_profile, token)
    except (URLError, OSError, ValueError):
        return JSONResponse({"detail": f"سرور ورود (بک‌اند مالی {FINANCE_API}) در دسترس نیست."}, status_code=503)
    if not profile:
        return JSONResponse({"detail": "برای استفاده از داشبورد وارد شوید.", "code": "login_required"}, status_code=401)
    if not allowed(profile, path, request.method):
        return JSONResponse({"detail": "به این بخش دسترسی ندارید.", "code": "forbidden"}, status_code=403)
    return await call_next(request)
