"""سهم راهکاران (B2B و صادرات) در شاخص‌های نمای مدیر، تا هر شاخص جمع همه ماژول‌ها باشد.

- فروش خالص ماه نمایندگان B2B راهکاران: همان عدد داشبورد فروش (/api/rk_sales?period=YYYY/MM، خالص = NetPrice پس از کسور و اضافات)؛
- فروش صادراتی ماه: دلار و معادل ریالی با نرخ اسناد (/api/rk_export/month).
- مطالبات مشتریان راهکاران: مانده معین‌های دریافتنی تجاری (۱۲۳۰۰۳/۴/۹/۱۱) هر تفصیلی سطح ۴ در سال مالی جاری
  (همان روش finance_prediction_service)، فقط مانده‌های بدهکار و بدون حساب هیبریدها (تسویه داخلی با کارآمد).
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import text

CACHE_SECONDS = 300
_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()

RECEIVABLE_SQL = text(
    """
    WITH active_fy AS (
        SELECT TOP (1) lfy.[StartDate], CASE WHEN :as_of < lfy.[EndDate] THEN :as_of ELSE lfy.[EndDate] END AS [EndDate]
        FROM GNR3.[LedgerFiscalYear] lfy
        WHERE lfy.[LedgerRef] = 1 AND :as_of >= CAST(lfy.[StartDate] AS date) AND :as_of <= CAST(lfy.[EndDate] AS date)
        ORDER BY lfy.[StartDate] DESC
    )
    SELECT b.[DLCode], dl.[Title], b.[Balance]
    FROM (
        SELECT vi.[DLLevel4] AS [DLCode], SUM(COALESCE(vi.[Debit], 0) - COALESCE(vi.[Credit], 0)) AS [Balance]
        FROM FIN3.[VoucherItem] vi
        INNER JOIN FIN3.[Voucher] v ON v.[VoucherID] = vi.[VoucherRef]
        INNER JOIN FIN3.[SL] sl ON sl.[SLID] = vi.[SLRef]
        CROSS JOIN active_fy fy
        WHERE sl.[Code] IN (N'123003', N'123004', N'123009', N'123011') AND vi.[DLLevel4] IS NOT NULL
          AND v.[Date] >= fy.[StartDate] AND v.[Date] < DATEADD(day, 1, fy.[EndDate])
        GROUP BY vi.[DLLevel4]
    ) b
    LEFT JOIN FIN3.[DL] dl ON dl.[Code] = b.[DLCode]
    """
)


def _cached(key: str, loader):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    value = loader()
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def _sales_api(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    from app.auth.internal_key import internal_headers
    from app.services.karamad_distribution_service import SALES_API

    try:
        with urlopen(Request(f"{SALES_API}{path}?{urlencode(params)}", headers={"Accept": "application/json", **internal_headers()}),
                     timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def rahkaran_sales(year: int, month: int) -> dict[str, Any]:
    """فروش خالص نمایندگان B2B راهکاران در ماه (تا امروز برای ماه جاری)؛ None = داشبورد فروش در دسترس نیست."""
    def load():
        data = _sales_api("/api/rk_sales", {"period": f"{year}/{month:02d}"})
        if not data or not data.get("kpis"):
            return {"net_rial": None, "customers": None}
        k = data["kpis"]
        top = lambda rows: [{"key": r.get("key"), "net_rial": float(r.get("net") or 0)}  # noqa: E731
                            for r in sorted(rows or [], key=lambda r: -float(r.get("net") or 0))[:12] if r.get("key")]
        return {"net_rial": float(k.get("net") or 0), "returns_rial": float(k.get("returns") or 0),
                "customers": k.get("customers_period"), "today": data.get("today"),
                "provinces": top(data.get("provinces")), "brands": top(data.get("brands"))}
    return _cached(f"sales:{year}/{month}", load)


def rahkaran_export(year: int, month: int) -> dict[str, Any]:
    """فروش صادراتی ماه (دلار و معادل ریالی با نرخ اسناد) با تفکیک کشور و مشتری."""
    def load():
        data = _sales_api("/api/rk_export/month", {"month": f"{year}/{month:02d}"})
        return data or {"net_rial": None, "net_usd": None, "countries": [], "customers": []}
    return _cached(f"export:{year}/{month}", load)


def rahkaran_receivables() -> dict[str, Any]:
    def load():
        from app.database.sqlserver import get_sqlserver_engine

        with get_sqlserver_engine().connect() as c:
            rows = c.execute(RECEIVABLE_SQL, {"as_of": date.today()}).mappings().all()
        own = [r for r in rows if "هیبرید" not in str(r["Title"] or "")]
        debtors = [r for r in own if float(r["Balance"] or 0) > 0]
        debtors.sort(key=lambda r: -float(r["Balance"]))
        return {"open_receivable_rial": round(sum(float(r["Balance"]) for r in debtors), 2),
                "debtor_count": len(debtors),
                "top": [{"key": str(r["Title"] or r["DLCode"]), "code": str(r["DLCode"]), "amount_rial": round(float(r["Balance"]), 2)}
                        for r in debtors[:12]],
                "excluded_hybrid_rial": round(sum(max(0.0, float(r["Balance"] or 0)) for r in rows if r not in own), 2)}
    return _cached("receivables", load)


def overview(year: int, month: int) -> dict[str, Any]:
    prev = (year - 1, 12) if month == 1 else (year, month - 1)
    out: dict[str, Any] = {"year": year, "month": month, "errors": []}
    try:
        out["sales"] = {"cur": rahkaran_sales(year, month), "prev": rahkaran_sales(*prev)}
        out["export"] = {"cur": rahkaran_export(year, month), "prev": rahkaran_export(*prev)}
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"فروش راهکاران: {exc}")
    try:
        out["receivables"] = rahkaran_receivables()
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"مطالبات راهکاران: {exc}")
    return out


def warm_up() -> None:
    """داده سنگین نمای مدیر را در پس‌زمینه می‌سازد تا اولین بازکردن صفحه منتظر SQL نماند
    (چک‌های دریافتی حدود یک دقیقه، P&L لایو حدود ۳۰ ثانیه)."""
    def run():
        import jdatetime

        from app.services import pnl_live_service, process_health_service
        from app.services.liquidity.issued_cheques import IssuedChequeService
        from app.services.liquidity.received_cheques import ReceivedChequeService

        t = jdatetime.date.today()
        steps = [lambda: ReceivedChequeService().report(horizon_days=30), lambda: IssuedChequeService().report(horizon_days=30),
                 lambda: overview(t.year, t.month), lambda: process_health_service.load()]
        steps += [lambda k=k: pnl_live_service.load(k) for k in ("b2b", "hybrid", "export")]
        for step in steps:
            try:
                step()
            except Exception:  # noqa: BLE001 — آماده‌سازی؛ خطا در درخواست واقعی نشان داده می‌شود
                pass
    threading.Thread(target=run, daemon=True).start()
