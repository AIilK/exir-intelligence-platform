"""پرداخت تجاری: حساب‌های پرداختنی تجاری (معین 511002) و غیرتجاری (512001) — راهکاران، فقط خواندنی.

همان «مرور حساب» راهکاران به تفکیک تفصیلی سطح ۴: همه اسناد سال مالی جاری
(FIN3.VoucherItem → FIN3.Voucher، کد معین از FIN3.SL، عنوان تفصیلی از FIN3.DL).
روی فایل‌های مرور ۱۴۰۵ واحد مالی بررسی شد: ۱۵۴ از ۱۵۵ و ۳۶۹ از ۳۷۲ ردیف دقیقاً برابر
(اختلاف‌ها اسناد ثبت‌شده بعد از گرفتن خروجی بودند).
مانده بستانکار = بدهی شرکت به طرف حساب؛ مانده بدهکار = پیش‌پرداخت / طلب شرکت.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
from typing import Any

from sqlalchemy import bindparam, text

from app.utils.jalali import format_jalali_date

MODULES = {
    "trade": {"sl_code": "511002", "title": "حساب‌های پرداختنی تجاری"},
    "nontrade": {"sl_code": "512001", "title": "حساب‌های پرداختنی غیرتجاری"},
}
CACHE_SECONDS = 300
_cache: dict[Any, tuple[float, Any]] = {}
_lock = threading.Lock()

# سال مالی جاری = سال مالیِ بیشترِ اسناد بازه سال شمسی جاری (Fixed internal SQL).
_FISCAL_YEAR = """
    SELECT TOP (1) v.FiscalYearRef FROM FIN3.Voucher v
    WHERE v.Date >= :year_start AND v.Date < :year_end
    GROUP BY v.FiscalYearRef ORDER BY COUNT(*) DESC
"""


def _year_bounds() -> tuple[date, date]:
    import jdatetime
    y = jdatetime.date.today().year
    return jdatetime.date(y, 1, 1).togregorian(), jdatetime.date(y + 1, 1, 1).togregorian()


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


class PayablesService:
    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            from app.database.sqlserver import get_sqlserver_engine
            self._engine = get_sqlserver_engine()
        return self._engine

    def _cached(self, key, build):
        with _lock:
            hit = _cache.get(key)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
        value = build()
        with _lock:
            _cache[key] = (time.time(), value)
        return value

    # ---------------------------------------------------------------- overview
    def overview(self) -> dict[str, Any]:
        return self._cached(("overview",), self._overview)

    def _overview(self) -> dict[str, Any]:
        start, end = _year_bounds()
        codes = [m["sl_code"] for m in MODULES.values()]
        with self.engine.connect() as c:
            rows = c.execute(text(f"""
                WITH fy AS ({_FISCAL_YEAR})
                SELECT sl.Code AS SLCode, vi.DLLevel4 AS DLCode, MAX(dl.Title) AS DLTitle,
                       SUM(ISNULL(vi.Debit, 0)) AS Debit, SUM(ISNULL(vi.Credit, 0)) AS Credit,
                       COUNT(*) AS Items,
                       MAX(v.Date) AS LastDate,
                       MAX(CASE WHEN ISNULL(vi.Debit, 0) > 0 THEN v.Date END) AS LastDebitDate,
                       MAX(CASE WHEN ISNULL(vi.Credit, 0) > 0 THEN v.Date END) AS LastCreditDate
                FROM FIN3.VoucherItem vi
                JOIN FIN3.Voucher v ON v.VoucherID = vi.VoucherRef
                JOIN FIN3.SL sl ON sl.SLID = vi.SLRef
                LEFT JOIN FIN3.DL dl ON dl.Code = vi.DLLevel4
                WHERE sl.Code IN :codes AND v.FiscalYearRef = (SELECT FiscalYearRef FROM fy)
                GROUP BY sl.Code, vi.DLLevel4
            """).bindparams(bindparam("codes", expanding=True)),
                {"year_start": start, "year_end": end, "codes": codes}).mappings().all()

        modules: dict[str, dict[str, Any]] = {}
        for key, meta in MODULES.items():
            items = []
            for r in rows:
                if str(r["SLCode"]) != meta["sl_code"]:
                    continue
                debit, credit = _money(r["Debit"]), _money(r["Credit"])
                balance = round(credit - debit, 2)  # + = شرکت بدهکار است (مانده بستانکار)
                items.append({
                    "dl_code": str(r["DLCode"] or "").strip() or "—",
                    "title": str(r["DLTitle"] or "").strip() or "بدون تفصیلی",
                    "debit_rial": debit,
                    "credit_rial": credit,
                    "credit_balance_rial": max(balance, 0.0),
                    "debit_balance_rial": max(-balance, 0.0),
                    "item_count": int(r["Items"] or 0),
                    "last_date_jalali": format_jalali_date(_as_date(r["LastDate"])) or "",
                    "last_payment_date_jalali": format_jalali_date(_as_date(r["LastDebitDate"])) or "",
                    "last_invoice_date_jalali": format_jalali_date(_as_date(r["LastCreditDate"])) or "",
                })
            items.sort(key=lambda x: (-x["credit_balance_rial"], -x["debit_balance_rial"], -x["credit_rial"]))
            modules[key] = {
                "key": key,
                "sl_code": meta["sl_code"],
                "title": meta["title"],
                "counterparty_count": len(items),
                "open_count": sum(1 for x in items if x["credit_balance_rial"] or x["debit_balance_rial"]),
                "debit_rial": _money(sum(x["debit_rial"] for x in items)),
                "credit_rial": _money(sum(x["credit_rial"] for x in items)),
                "credit_balance_rial": _money(sum(x["credit_balance_rial"] for x in items)),
                "debit_balance_rial": _money(sum(x["debit_balance_rial"] for x in items)),
                "creditor_count": sum(1 for x in items if x["credit_balance_rial"] > 0),
                "debtor_count": sum(1 for x in items if x["debit_balance_rial"] > 0),
                "counterparties": items,
            }
        return {
            "status": "success",
            "fiscal_year_from_jalali": format_jalali_date(start),
            "generated_at_jalali": format_jalali_date(date.today()),
            "modules": modules,
            "note": "مانده بستانکار = بدهی شرکت به طرف حساب؛ مانده بدهکار = پیش‌پرداخت یا طلب شرکت. "
                    "همه اسناد سال مالی جاری راهکاران، مثل گزارش «مرور حساب».",
        }

    # ------------------------------------------------------------------ detail
    def ledger(self, module: str, dl_code: str) -> dict[str, Any]:
        if module not in MODULES:
            raise ValueError("ماژول نامعتبر است.")
        return self._cached(("ledger", module, dl_code), lambda: self._ledger(module, dl_code))

    def _ledger(self, module: str, dl_code: str) -> dict[str, Any]:
        start, end = _year_bounds()
        sl_code = MODULES[module]["sl_code"]
        dl_filter = "vi.DLLevel4 IS NULL" if dl_code in ("", "—") else "vi.DLLevel4 = :dl_code"
        with self.engine.connect() as c:
            title = c.execute(text("SELECT TOP (1) Title FROM FIN3.DL WHERE Code = :dl_code"), {"dl_code": dl_code}).scalar()
            rows = c.execute(text(f"""
                WITH fy AS ({_FISCAL_YEAR})
                SELECT v.Date, v.Number, v.Sequence, vi.RowNumber, vi.Description, v.Description AS VoucherDescription,
                       ISNULL(vi.Debit, 0) AS Debit, ISNULL(vi.Credit, 0) AS Credit,
                       vi.FollowUpNumber, vi.FollowUpDate, b.Title AS BranchTitle
                FROM FIN3.VoucherItem vi
                JOIN FIN3.Voucher v ON v.VoucherID = vi.VoucherRef
                JOIN FIN3.SL sl ON sl.SLID = vi.SLRef
                LEFT JOIN GNR3.Branch b ON b.BranchID = vi.BranchRef
                WHERE sl.Code = :sl_code AND {dl_filter} AND v.FiscalYearRef = (SELECT FiscalYearRef FROM fy)
                ORDER BY v.Date, v.Number, vi.RowNumber
            """), {"year_start": start, "year_end": end, "sl_code": sl_code, "dl_code": dl_code}).mappings().all()
        running = 0.0
        lines = []
        for r in rows:
            debit, credit = _money(r["Debit"]), _money(r["Credit"])
            running = round(running + credit - debit, 2)
            lines.append({
                "date_jalali": format_jalali_date(_as_date(r["Date"])) or "",
                "voucher_number": str(r["Number"] or ""),
                "reference_number": str(r["Sequence"] or ""),  # شماره عطف
                "row_number": r["RowNumber"],
                "description": str(r["Description"] or r["VoucherDescription"] or "").strip(),
                "debit_rial": debit,
                "credit_rial": credit,
                "balance_rial": running,  # + بستانکار (بدهی شرکت)، − بدهکار
                "follow_up_number": str(r["FollowUpNumber"] or "").strip(),
                "follow_up_date_jalali": format_jalali_date(_as_date(r["FollowUpDate"])) or "",
                "branch": str(r["BranchTitle"] or "").strip(),
                "is_opening": "افتتاحیه" in str(r["Description"] or r["VoucherDescription"] or ""),
            })
        debit_total = _money(sum(x["debit_rial"] for x in lines))
        credit_total = _money(sum(x["credit_rial"] for x in lines))
        opening = _money(sum(x["credit_rial"] - x["debit_rial"] for x in lines if x["is_opening"]))
        return {
            "status": "success",
            "module": module,
            "sl_code": sl_code,
            "dl_code": dl_code,
            "title": str(title or "").strip() or "بدون تفصیلی",
            "debit_rial": debit_total,
            "credit_rial": credit_total,
            "balance_rial": round(credit_total - debit_total, 2),
            "opening_balance_rial": opening,
            "payments_rial": _money(sum(x["debit_rial"] for x in lines if not x["is_opening"])),
            "invoices_rial": _money(sum(x["credit_rial"] for x in lines if not x["is_opening"])),
            "lines": lines,
        }
