"""ابزارهای فروش چت‌بات: داده زنده بک‌اند فروش (sales/backend، دیتابیس کارآمد و فروش B2B راهکاران).

همان اعدادی که صفحه‌های فروش داشبورد یکپارچه نشان می‌دهند؛ مبالغ ریال بک‌اند فروش به تومان تبدیل می‌شوند.
فقط برای کاربرانی که ماژول «فروش» دارند (app/auth/modules.py).
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

SALES_API = os.environ.get("SALES_API_URL", "http://127.0.0.1:8000").rstrip("/")
CACHE_SECONDS = 120
TOP = 10
_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()
# کلیدهای مبلغ (ریال) در پاسخ‌های بک‌اند فروش
MONEY = {"net", "gross", "disc", "vat", "payable", "sales_net", "sales_gross", "returns_net", "returns", "req_net", "req_net_done",
         "req_gross", "forecast", "req_forecast", "daily_avg", "avg_invoice", "ly_net", "cash", "net_cash", "sales_disc"}
RATES = {"share", "return_rate", "disc_rate", "req_conv", "growth"}


def _get(path: str, **params: Any) -> Any:
    from app.auth.internal_key import internal_headers

    q = urllib.parse.urlencode([(k, v) for k, v in params.items() if v not in (None, "")], doseq=True)
    url = f"{SALES_API}{path}{'?' + q if q else ''}"
    with _lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    req = urllib.request.Request(url, headers={"Accept": "application/json", **internal_headers()})
    with urllib.request.urlopen(req, timeout=240) as r:  # noqa: S310 (local API only)
        data = json.loads(r.read().decode("utf-8"))
    with _lock:
        _cache[url] = (time.time(), data)
    return data


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _clean(row: dict[str, Any], keep: tuple[str, ...]) -> dict[str, Any]:
    """ریال ← تومان، نسبت‌ها ← درصد؛ فقط کلیدهای خواسته‌شده."""
    out: dict[str, Any] = {}
    for k in keep:
        if k not in row:
            continue
        v = row[k]
        if k in MONEY and _num(v) is not None:
            out[f"{k}_toman"] = round(_num(v) / 10)
        elif k in RATES and _num(v) is not None:
            out[f"{k}_percent"] = round(_num(v) * 100, 1)
        else:
            out[k] = v
    return out


KPI_KEYS = ("net", "sales_net", "returns_net", "return_rate", "disc_rate", "invoices", "customers", "forecast", "req_net", "req_conv",
            "days", "full_month", "sellers_active", "sku")
ROW_KEYS = ("label", "net", "share", "returns_net", "return_rate", "forecast", "req_net", "req_conv", "customers", "invoices", "supervisor", "branch")


def _period(date_from: str | None, date_to: str | None) -> dict[str, str | None]:
    return {"date_from": date_from or None, "date_to": date_to or None}


def sales_hybrids(date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    d = _get("/api/hybrid", vat=1, **_period(date_from, date_to))
    rows = sorted(d.get("branches") or [], key=lambda b: -(_num(b.get("net")) or 0))
    return {"period": "ماه جاری تا امروز (با پیش‌بینی پایان ماه)" if not (date_from or date_to) else f"{date_from or ''} تا {date_to or ''}",
            "note": "فروش کارآمد با ارزش افزوده؛ net = فروش خالص پس از برگشتی",
            "kpis": _clean(d.get("kpis") or {}, KPI_KEYS),
            "branches_top": [_clean(b, ROW_KEYS) for b in rows[:TOP]], "branch_count": len(rows),
            "weakest": [_clean(b, ROW_KEYS) for b in rows[-3:]] if len(rows) > TOP else []}


def sales_team(date_from: str | None = None, date_to: str | None = None, branch: str | None = None) -> dict[str, Any]:
    d = _get("/api/team", vat=1, branch=branch or None, **_period(date_from, date_to))
    sellers = sorted(d.get("sellers") or [], key=lambda s: -(_num(s.get("net")) or 0))
    return {"kpis": _clean(d.get("kpis") or {}, KPI_KEYS), "sellers_top": [_clean(s, ROW_KEYS) for s in sellers[:TOP]],
            "sellers_bottom": [_clean(s, ROW_KEYS) for s in sellers[-5:]] if len(sellers) > TOP else [],
            "supervisors": [_clean(s, ROW_KEYS) for s in sorted(d.get("supervisors") or [], key=lambda s: -(_num(s.get("net")) or 0))[:TOP]]}


def sales_b2b(period: str | None = None) -> dict[str, Any]:
    d = _get("/api/rk_sales", period=period or "YTD")
    def rows(key: str) -> list[dict[str, Any]]:
        items = d.get(key) or []
        items = items if isinstance(items, list) else []
        return [_clean(x, ("key", "label", "name", "net", "gross", "share", "growth", "customers", "ly_net")) for x in items[:TOP]]
    return {"period": d.get("period"), "today": d.get("today"), "note": "فروش B2B راهکاران؛ growth نسبت به همین دوره سال قبل",
            "kpis": _clean(d.get("kpis") or {}, ("net", "gross", "invoices", "avg_invoice", "disc_rate", "customers", "customers_total",
                                                  "customers_inactive", "returns", "return_rate", "ly_net", "growth", "cash")),
            "provinces": rows("provinces"), "brands": rows("brands"), "customers_top": rows("customers")}


_DATE = {"type": ["string", "null"], "description": "تاریخ شمسی YYYY/MM/DD؛ null یعنی ماه جاری"}
TOOLS = {
    "sales_hybrids": (sales_hybrids, "فروش کارآمد هیبریدها (شعب): فروش خالص، برگشتی، تعداد فاکتور و مشتری، پیش‌بینی پایان ماه، تبدیل درخواست به فاکتور و رتبه شعب در یک بازه.",
                      {"date_from": _DATE, "date_to": _DATE}),
    "sales_team": (sales_team, "فروش تیم فروش کارآمد: برترین و ضعیف‌ترین ویزیتورها/فروشنده‌ها و سرپرست‌ها در یک بازه؛ branch = نام دقیق یک هیبرید (اختیاری).",
                   {"date_from": _DATE, "date_to": _DATE, "branch": {"type": ["string", "null"], "description": "نام هیبرید، مثلاً «هیبرید تهران»"}}),
    "sales_b2b": (sales_b2b, "فروش B2B راهکاران (نمایندگان): فروش خالص، رشد نسبت به پارسال، استان‌ها، برندها و بزرگ‌ترین نمایندگان.",
                  {"period": {"type": ["string", "null"], "description": "YTD (از ابتدای سال) یا ماه شمسی YYYY/MM"}}),
}
