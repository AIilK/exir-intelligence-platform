"""توزیع بار کارآمد: فاکتورهایی که هنوز حواله خروج ندارند، سرعت خروج بار و عملکرد موزعان.

ساختار کارآمد (بررسی‌شده روی KDB):
- هر فاکتور فروش (tblFactorF) با ExitRef به حواله خروج (tblExit) وصل می‌شود؛ فقط فاکتوری که
  «خروجی» (کد حواله خروج) ندارد، یعنی خروجی کمتر از ۱، توزیع‌نشده حساب می‌شود — برای هر تاریخ و
  همه هیبریدها. Status حواله در این تعریف دخالتی ندارد (تطبیق با «توزیع وصول.xlsx» شهریور ۱۴۰۵:
  حواله‌های Status ۰ خروجی دارند و توزیع‌شده‌اند).
  فیلد Delivered در این نصب همیشه صفر است و استفاده نمی‌شود.
- حواله خروج: DateE (تاریخ خروج)، DeliverRef (موزع، tblDeliver)، DriverRef (راننده، tblDriver)،
  Status (۰ یا ۱) نمایش داده نمی‌شود؛ حواله‌های وضعیت ۰ به درخواست مدیریت از صفحه حذف شده‌اند.
- فاکتورهای صفر/جایزه‌ای (کمتر از MIN_LAST_INVOICE_AMOUNT_RIAL) کنار گذاشته می‌شوند.
- فاکتوری که به‌طور کامل مرجوع شده (tblFactorB.FactorFRef) توزیع لازم ندارد و حذف می‌شود.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import date
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import text

from app.services.customer_file_service import MIN_LAST_INVOICE_AMOUNT_RIAL
from app.services.karamad_sales_network_service import KaramadSalesNetworkService, _as_date, _num, _text
from app.utils.jalali import format_jalali_date

CACHE_SECONDS = 300
_cache: dict[str, Any] = {"at": 0.0, "data": None}
_lock = threading.Lock()
_month_cache: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}

JALALI_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")


SALES_API = os.environ.get("SALES_API_URL", "http://127.0.0.1:8000").rstrip("/")
SALES_TIMEOUT_SECONDS = 120


def _norm_branch(name: Any) -> str:
    return " ".join(str(name or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ").split())


def sales_dashboard_branch_sales(year: int, month: int) -> dict[str, float] | None:
    """فروش خالص هر هیبرید در ماه، همان عدد داشبورد فروش (/api/hybrid، با ارزش افزوده = قابل پرداخت).
    None اگر داشبورد فروش در دسترس نباشد؛ آن‌وقت گزارش با فروش محاسبه‌شده از کارآمد می‌ماند."""
    import jdatetime
    last = (jdatetime.date(year + 1, 1, 1) if month == 12 else jdatetime.date(year, month + 1, 1)) - jdatetime.timedelta(days=1)
    query = urlencode({"date_from": f"{year}/{month:02d}/01", "date_to": last.strftime("%Y/%m/%d"), "vat": "1"})
    try:
        with urlopen(Request(f"{SALES_API}/api/hybrid?{query}", headers={"Accept": "application/json"}),
                     timeout=SALES_TIMEOUT_SECONDS) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return {_norm_branch(b.get("key")): float(b.get("net") or 0) for b in data.get("branches") or []}


def _month_range(year: int, month: int) -> tuple[date, date]:
    """Gregorian [start, end) of a Jalali month."""
    import jdatetime
    start = jdatetime.date(year, month, 1).togregorian()
    end = (jdatetime.date(year + 1, 1, 1) if month == 12 else jdatetime.date(year, month + 1, 1)).togregorian()
    return start, end


class KaramadDistributionService:
    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
            self._engine = get_karamad_sqlserver_engine()
        return self._engine

    def overview(self) -> dict[str, Any]:
        with _lock:
            if _cache["data"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
                return _cache["data"]
        data = self._overview()
        with _lock:
            _cache.update(at=time.time(), data=data)
        return data

    # ------------------------------------------------------------- monthly report
    def monthly(self, year: int, month: int) -> dict[str, Any]:
        """«توزیع و وصول فاکتورهای ماه» — the finance team's report, rebuilt from SQL.

        Verified on «توزیع و وصول فاکتورهای شهریور 1405- هیبرید.xlsx»: all 18 branches and all
        1,982 customers match exactly given the same data:
        - sales of the month = each sales invoice dated in the month (قابل پرداخت) minus the returns
          dated in the month that point to it (FactorFRef, else same branch + FactorNo = invoice Code);
        - توزیع نشده = invoices with no exit code («خروجی» < 1, i.e. no ExitRef), whatever the exit's Status; توزیع شده = the rest;
        - وصول = cash + draft + cheque settled on the month's invoices (vwFactorFPayoff);
        - مانده سیستم = customer ledger balance (posted + not yet posted);
        - مانده فاکتورهای ماه = MIN(مانده سیستم, توزیع شده − وصول), per customer.
        Only branches named «هیبرید…», as in the report.
        """
        key = (int(year), int(month))
        with _lock:
            hit = _month_cache.get(key)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
        data = self._monthly(*key)
        with _lock:
            _month_cache[key] = (time.time(), data)
        return data

    def _monthly(self, year: int, month: int) -> dict[str, Any]:
        from app.services.karamad_customer_account_service import LEDGER_READ_ISOLATION
        from app.services.karamad_sales_network_service import ledger_positions
        start, end = _month_range(year, month)
        params = {"start": start, "end": end}
        positions = ledger_positions()
        with self.engine.connect().execution_options(isolation_level=LEDGER_READ_ISOLATION) as connection:
            invoices = connection.execute(text(
                """
                SELECT f.[ID], f.[Code], f.[DateE], f.[FactorPriceP], f.[ExitRef], f.[BranchRef], b.[Name] AS BranchName,
                       cu.[DLRef], cu.[Name] AS CustomerName, cu.[Code] AS CustomerCode, v.[Name] AS VisitorName,
                       ISNULL(p.[CashN], 0) + ISNULL(p.[Draft], 0) + ISNULL(p.[Cheque], 0) AS Collected,
                       CASE WHEN ISNULL(e.[Code], 0) >= 1 THEN 1 ELSE 0 END AS [Distributed],
                       -- ستون‌های «کنترل وصول» گزارش واحد مالی
                       dl.[Code] AS DLCode, ln.[Name] AS LineName, pt.[Name] AS PaymentName, ct.[Name] AS CityName,
                       dv.[Name] AS DeliverName, e.[Code] AS ExitCode, e.[DateE] AS ExitDate,
                       f.[FactorPrice], f.[FactorDiscount], f.[FactorCashDiscount], f.[FactorVat],
                       ISNULL(p.[CashN], 0) AS CashN, ISNULL(p.[Draft], 0) AS Draft, ISNULL(p.[Cheque], 0) AS Cheque,
                       ISNULL(p.[FactorB], 0) AS PayoffReturn, ISNULL(p.[Barter], 0) AS Barter,
                       ISNULL(p.[SharedFactor], 0) + ISNULL(p.[SharedCustomerDebt], 0) + ISNULL(p.[SharedReturnCheque], 0)
                         + ISNULL(p.[SharedReturn], 0) AS Shared,
                       rm.[UnPaid]
                FROM dbo.[tblFactorF] f
                JOIN dbo.[tblBranch] b ON b.[ID] = f.[BranchRef]
                LEFT JOIN dbo.[tblExit] e ON e.[ID] = f.[ExitRef]
                LEFT JOIN dbo.[tblCustomer] cu ON cu.[ID] = f.[CustomerRef]
                LEFT JOIN dbo.[tblDL] dl ON dl.[ID] = cu.[DLRef]
                LEFT JOIN dbo.[tblVisitor] v ON v.[ID] = f.[VisitorRef]
                LEFT JOIN dbo.[tblLine] ln ON ln.[ID] = f.[LineRef]
                LEFT JOIN dbo.[tblPaymentType] pt ON pt.[ID] = f.[PaymentRef]
                LEFT JOIN dbo.[tblCity] ct ON ct.[ID] = cu.[CityRef]
                LEFT JOIN dbo.[tblDeliver] dv ON dv.[ID] = e.[DeliverRef]
                LEFT JOIN dbo.[vwFactorFPayoff] p ON p.[ID] = f.[ID]
                LEFT JOIN dbo.[vwFactorFRemain] rm ON rm.[ID] = f.[ID]
                WHERE f.[DateE] >= :start AND f.[DateE] < :end AND b.[Name] LIKE N'%هیبرید%'
                """
            ), params).mappings().all()
            returns = connection.execute(text(
                """
                SELECT r.[FactorFRef], r.[FactorNo], r.[BranchRef], r.[FactorPriceP]
                FROM dbo.[tblFactorB] r WHERE r.[DateE] >= :start AND r.[DateE] < :end
                """
            ), params).mappings().all()
            # فروش کل ماه (تعریف گزارش فروش واحد مالی): همه شعب، قابل پرداخت بعد از تخفیف (با ارزش افزوده)،
            # منهای همه برگشتی‌هایی که در همین ماه ثبت شده‌اند (هر فاکتوری که باشد).
            company = connection.execute(text(
                """
                SELECT b.[Name] AS BranchName,
                       SUM(CASE WHEN x.[k] = 0 THEN x.[P] ELSE 0 END) AS Invoices,
                       SUM(CASE WHEN x.[k] = 1 THEN x.[P] ELSE 0 END) AS Returns
                FROM (SELECT [BranchRef], [FactorPriceP] AS P, 0 AS k FROM dbo.[tblFactorF] WHERE [DateE] >= :start AND [DateE] < :end
                      UNION ALL
                      SELECT [BranchRef], [FactorPriceP], 1 FROM dbo.[tblFactorB] WHERE [DateE] >= :start AND [DateE] < :end) x
                LEFT JOIN dbo.[tblBranch] b ON b.[ID] = x.[BranchRef]
                GROUP BY b.[Name]
                """
            ), params).mappings().all()

        by_id = {int(r["ID"]): r for r in invoices}
        by_number = {(int(r["BranchRef"]), _text(r["Code"])): int(r["ID"]) for r in invoices}
        returned: dict[int, float] = {}
        for r in returns:
            target = int(r["FactorFRef"]) if r["FactorFRef"] is not None and int(r["FactorFRef"]) in by_id else \
                by_number.get((int(r["BranchRef"] or 0), _text(r["FactorNo"])))
            if target is not None:
                returned[target] = returned.get(target, 0.0) + float(r["FactorPriceP"] or 0)

        today = date.today()
        branches: dict[str, dict[str, Any]] = {}
        customers: dict[tuple[str, Any], dict[str, Any]] = {}
        undistributed = []
        control = []
        for r in invoices:
            inv_id = int(r["ID"])
            net = float(r["FactorPriceP"] or 0) - returned.get(inv_id, 0.0)
            branch = _text(r["BranchName"])
            b = branches.setdefault(branch, {"branch_name": branch, "sales_rial": 0.0, "undistributed_rial": 0.0,
                                             "distributed_rial": 0.0, "collected_rial": 0.0, "remaining_rial": 0.0,
                                             "undistributed_count": 0,
                                             # همان توزیع‌نشده‌ها پیش از کسر برگشتی (فاکتورهای ابطالی صفر حساب نمی‌شوند)
                                             "undistributed_gross_rial": 0.0, "undistributed_gross_count": 0})
            dl = int(r["DLRef"]) if r["DLRef"] is not None else None
            c = customers.setdefault((branch, dl), {"branch_name": branch, "dl_ref": dl, "dl_code": _text(r["DLCode"]),
                                                   "customer_name": _text(r["CustomerName"]),
                                                   "customer_code": _text(r["CustomerCode"]), "distributed_rial": 0.0,
                                                   "undistributed_rial": 0.0, "collected_rial": 0.0})
            b["sales_rial"] += net
            c["collected_rial"] += float(r["Collected"] or 0)
            if not r["Distributed"] and float(r["FactorPriceP"] or 0) > 0:
                b["undistributed_gross_rial"] += float(r["FactorPriceP"] or 0)
                b["undistributed_gross_count"] += 1
            # فاکتور ابطالی (قابل پرداخت صفر) یا کاملاً مرجوع‌شده خروجی ندارد ولی باری هم برای توزیع ندارد
            if not r["Distributed"] and net > 0:
                b["undistributed_rial"] += net
                b["undistributed_count"] += 1
                c["undistributed_rial"] += net
                issued = _as_date(r["DateE"])
                undistributed.append({
                    "invoice_id": inv_id, "number": _text(r["Code"]), "date_jalali": format_jalali_date(issued),
                    "days_waiting": (today - issued).days if issued else None, "amount_rial": _num(net),
                    "invoice_rial": _num(r["FactorPriceP"]), "returned_rial": _num(returned.get(inv_id, 0.0)),
                    "branch_name": branch, "customer_name": _text(r["CustomerName"]),
                    "customer_code": _text(r["CustomerCode"]), "visitor_name": _text(r["VisitorName"]),
                })
            else:
                c["distributed_rial"] += net
            exit_date = _as_date(r["ExitDate"]) if r["Distributed"] else None
            control.append({
                "invoice_id": inv_id, "branch_name": branch, "line_name": _text(r["LineName"]), "number": _text(r["Code"]),
                "exit_code": _text(r["ExitCode"]) if r["Distributed"] else "",
                "date_jalali": format_jalali_date(_as_date(r["DateE"])),
                "distribution_date_jalali": format_jalali_date(exit_date) if exit_date else "",
                "days_since_distribution": (today - exit_date).days if exit_date else None,
                "payment_name": _text(r["PaymentName"]), "customer_code": _text(r["CustomerCode"]),
                "customer_name": _text(r["CustomerName"]), "visitor_name": _text(r["VisitorName"]),
                "city_name": _text(r["CityName"]), "deliver_name": _text(r["DeliverName"]) if r["Distributed"] else "",
                "gross_rial": _num(r["FactorPrice"]), "volume_discount_rial": _num(r["FactorDiscount"]),
                "cash_discount_rial": _num(r["FactorCashDiscount"]), "vat_rial": _num(r["FactorVat"]),
                "payable_rial": _num(r["FactorPriceP"]), "cash_rial": _num(r["CashN"]), "draft_rial": _num(r["Draft"]),
                "cheque_rial": _num(r["Cheque"]), "collected_rial": _num(r["Collected"]),
                "returned_rial": _num(r["PayoffReturn"]), "shared_rial": _num(r["Shared"]), "barter_rial": _num(r["Barter"]),
                "unpaid_rial": _num(r["UnPaid"]), "distributed": bool(r["Distributed"]),
            })

        rows = []
        for c in customers.values():
            balance = float(positions.get(c["dl_ref"], {}).get("balance_rial") or 0) if c["dl_ref"] is not None else 0.0
            c["system_balance_rial"] = balance
            c["remaining_rial"] = min(balance, c["distributed_rial"] - c["collected_rial"])
            b = branches[c["branch_name"]]
            b["collected_rial"] += c["collected_rial"]
            b["remaining_rial"] += c["remaining_rial"]
            rows.append({k: (_num(v) if k.endswith("_rial") else v) for k, v in c.items()})
        # «کل فروش» هر هیبرید از داشبورد فروش خوانده می‌شود تا دو داشبورد یک عدد نشان دهند
        dashboard_sales = sales_dashboard_branch_sales(year, month)
        for b in branches.values():
            if dashboard_sales is not None:
                b["sales_rial"] = dashboard_sales.get(_norm_branch(b["branch_name"]), 0.0)
            b["distributed_rial"] = b["sales_rial"] - b["undistributed_rial"]
        branch_rows = sorted(({k: (_num(v) if k.endswith("_rial") else v) for k, v in b.items()} for b in branches.values()),
                             key=lambda x: x["branch_name"])
        totals = {k: _num(sum(b[k] for b in branch_rows)) for k in
                  ("sales_rial", "undistributed_rial", "distributed_rial", "collected_rial", "remaining_rial",
                   "undistributed_gross_rial")}
        totals["undistributed_count"] = sum(b["undistributed_count"] for b in branch_rows)
        totals["undistributed_gross_count"] = sum(b["undistributed_gross_count"] for b in branch_rows)
        return {
            "status": "success",
            "year": year, "month": month, "month_label": f"{JALALI_MONTHS[month - 1]} {year}",
            "company_sales": {
                "invoices_rial": _num(sum(float(r["Invoices"] or 0) for r in company)),
                "returns_rial": _num(sum(float(r["Returns"] or 0) for r in company)),
                "net_rial": _num(sum(float(r["Invoices"] or 0) - float(r["Returns"] or 0) for r in company)),
                "by_branch": sorted(({"branch_name": _text(r["BranchName"]) or "—",
                                      "net_rial": _num(float(r["Invoices"] or 0) - float(r["Returns"] or 0))} for r in company),
                                    key=lambda x: -x["net_rial"]),
                "rule": "همه شعب، فاکتور فروش ماه منهای همه برگشتی‌های ثبت‌شده در همان ماه (قابل پرداخت، با ارزش افزوده).",
            },
            "sales_source": "sales_dashboard" if dashboard_sales is not None else "karamad",
            "branches": branch_rows,
            "totals": totals,
            "customers": sorted(rows, key=lambda x: (x["branch_name"], -x["distributed_rial"])),
            "undistributed": sorted(undistributed, key=lambda x: -(x["days_waiting"] or 0)),
            # «کنترل وصول»: هر فاکتور ماه با اجزای مبلغ و تسویه (همان ستون‌های گزارش واحد مالی)
            "collection_control": sorted(control, key=lambda x: (x["branch_name"], x["date_jalali"], x["number"])),
        }

    # ------------------------------------------------------------- per-invoice timeline
    def timeline(self, days: int = 14, year: int | None = None, month: int | None = None) -> dict[str, Any]:
        """زمان‌بندی توزیع هر فاکتور: تاریخ فاکتور، ثبت در سیستم، ثبت حواله خروج و تاریخ خروج.

        - ثبت فاکتور = tblFactorF.CreateDate (ساعت واقعی ثبت؛ ممکن است بعد از تاریخ فاکتور باشد).
        - ثبت حواله خروج = اولین «ذخیره خروج کالا از انبار با شناسه{ID}» در tblUsersLogs؛
          tblExit خودش زمان ثبت ندارد. چند ذخیره = حواله بعداً ویرایش شده است.
        - لاگ‌هایی که ساعت کامپیوترشان اشتباه است (مثلاً سال ۲۰۴۹) کنار گذاشته می‌شوند.
        """
        from datetime import timedelta
        safe_days = max(1, min(int(days), 90))
        if year and month:
            # یک ماه شمسی کامل (برای نمای ماهانه)
            start, end = _month_range(int(year), int(month))
            key = ("timeline_month", int(year), int(month))
            label = f"{JALALI_MONTHS[int(month) - 1]} {int(year)}"
        else:
            start, end = date.today() - timedelta(days=safe_days), None
            key = ("timeline", safe_days)
            label = None
        with _lock:
            hit = _month_cache.get(key)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
        data = self._timeline(safe_days, start, end, label)
        with _lock:
            _month_cache[key] = (time.time(), data)
        return data

    def _timeline(self, days: int, start: date, end: date | None = None, label: str | None = None) -> dict[str, Any]:
        from datetime import datetime, timedelta
        today = date.today()
        prefix = "ذخیره خروج کالا از انبار با شناسه"
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                """
                WITH inv AS (
                    SELECT f.[ID], f.[Code], f.[DateE], f.[CreateDate], f.[FactorPriceP], f.[ExitRef], f.[UserRef],
                           f.[BranchRef], f.[CustomerRef], f.[VisitorRef]
                    FROM dbo.[tblFactorF] f
                    WHERE f.[DateE] >= :start AND (:end IS NULL OR f.[DateE] < :end) AND f.[FactorPriceP] >= :min_amount
                      AND NOT EXISTS (SELECT 1 FROM dbo.[tblFactorB] rb WHERE rb.[FactorFRef] = f.[ID]
                                      GROUP BY rb.[FactorFRef] HAVING SUM(rb.[FactorPriceP]) >= f.[FactorPriceP])
                ),
                exit_log AS (
                    SELECT s.[ExitID], MIN(s.[Date]) AS FirstSave, MAX(s.[Date]) AS LastSave, COUNT(*) AS Saves
                    FROM (
                        SELECT l.[Date],
                               TRY_CONVERT(int, LTRIM(RTRIM(REPLACE(SUBSTRING(l.[Description], LEN(:prefix) + 1, 30), N'-', N'')))) AS ExitID
                        FROM dbo.[tblUsersLogs] l
                        WHERE l.[Description] LIKE :prefix + N'%'
                          AND l.[Date] >= DATEADD(day, -3, :start) AND l.[Date] < DATEADD(day, 1, GETDATE())
                    ) s
                    WHERE s.[ExitID] IS NOT NULL
                    GROUP BY s.[ExitID]
                )
                SELECT i.[ID], i.[Code], i.[DateE], i.[CreateDate], i.[FactorPriceP],
                       b.[Name] AS BranchName, cu.[Name] AS CustomerName, cu.[Code] AS CustomerCode,
                       v.[Name] AS VisitorName, iu.[Name] AS InvoiceUser,
                       e.[ID] AS ExitID, e.[Code] AS ExitCode, e.[DateE] AS ExitDate, e.[DisDateE] AS DistributionDate,
                       eu.[Name] AS ExitUser,
                       dl.[Name] AS DeliverName, dl2.[Name] AS Deliver2Name, dr.[Name] AS DriverName,
                       lg.[FirstSave], lg.[LastSave], lg.[Saves],
                       (SELECT COUNT(*) FROM dbo.[tblFactorF] ff WHERE ff.[ExitRef] = e.[ID]) AS ExitInvoiceCount
                FROM inv i
                LEFT JOIN dbo.[tblBranch] b ON b.[ID] = i.[BranchRef]
                LEFT JOIN dbo.[tblCustomer] cu ON cu.[ID] = i.[CustomerRef]
                LEFT JOIN dbo.[tblVisitor] v ON v.[ID] = i.[VisitorRef]
                LEFT JOIN dbo.[tblUser] iu ON iu.[ID] = i.[UserRef]
                LEFT JOIN dbo.[tblExit] e ON e.[ID] = i.[ExitRef]
                LEFT JOIN dbo.[tblUser] eu ON eu.[ID] = e.[UserRef]
                LEFT JOIN dbo.[tblDeliver] dl ON dl.[ID] = e.[DeliverRef]
                LEFT JOIN dbo.[tblDeliver] dl2 ON dl2.[ID] = e.[Deliver2Ref]
                LEFT JOIN dbo.[tblDriver] dr ON dr.[ID] = e.[DriverRef]
                LEFT JOIN exit_log lg ON lg.[ExitID] = e.[ID]
                ORDER BY i.[CreateDate] DESC, i.[ID] DESC
                """
            ), {"start": start, "end": end, "min_amount": MIN_LAST_INVOICE_AMOUNT_RIAL, "prefix": prefix}).mappings().all()

        def stamp(value: Any) -> dict[str, Any] | None:
            if not isinstance(value, datetime):
                return None
            return {"iso": value.isoformat(timespec="minutes"), "date_jalali": format_jalali_date(value),
                    "time": value.strftime("%H:%M")}

        def hours_between(a: Any, b: Any) -> float | None:
            if not isinstance(a, datetime) or not isinstance(b, datetime):
                return None
            return round(max(0.0, (b - a).total_seconds() / 3600.0), 1)

        invoices = []
        for r in rows:
            invoice_date = _as_date(r["DateE"])
            exit_date = _as_date(r["ExitDate"])
            created = r["CreateDate"]
            exit_saved = r["FirstSave"]
            if r["ExitID"] is None:
                stage = "waiting"
            elif exit_date and exit_date > today:
                stage = "scheduled"
            else:
                stage = "dispatched"
            invoices.append({
                "invoice_id": int(r["ID"]),
                "number": _text(r["Code"]),
                "branch_name": _text(r["BranchName"]),
                "customer_name": _text(r["CustomerName"]),
                "customer_code": _text(r["CustomerCode"]),
                "visitor_name": _text(r["VisitorName"]),
                "amount_rial": _num(r["FactorPriceP"]),
                "stage": stage,
                "invoice_date_jalali": format_jalali_date(invoice_date),
                "invoice_created": stamp(created),
                "invoice_user": _text(r["InvoiceUser"]),
                "exit_id": int(r["ExitID"]) if r["ExitID"] is not None else None,
                "exit_code": _text(r["ExitCode"]),
                "exit_registered": stamp(exit_saved),
                "exit_last_edit": stamp(r["LastSave"]) if (r["Saves"] or 0) > 1 else None,
                "exit_save_count": int(r["Saves"] or 0),
                "exit_user": _text(r["ExitUser"]),
                "exit_date_jalali": format_jalali_date(exit_date),
                "distribution_date_jalali": format_jalali_date(r["DistributionDate"]),
                "exit_invoice_count": int(r["ExitInvoiceCount"] or 0),
                "deliver_name": _text(r["DeliverName"]),
                "deliver2_name": _text(r["Deliver2Name"]),
                "driver_name": _text(r["DriverName"]),
                "registration_delay_days": (created.date() - invoice_date).days
                if isinstance(created, datetime) and invoice_date else None,
                "hours_to_exit_registration": hours_between(created, exit_saved),
                "days_invoice_to_exit": max(0, (exit_date - invoice_date).days) if exit_date and invoice_date else None,
                "days_waiting": (today - invoice_date).days if stage == "waiting" and invoice_date else None,
            })
        return {
            "status": "success",
            "days": days,
            "month_label": label,
            "from_date_jalali": format_jalali_date(start),
            "to_date_jalali": format_jalali_date(min(today, end - timedelta(days=1)) if end else today),
            "branches": sorted({x["branch_name"] for x in invoices if x["branch_name"]}),
            "invoices": invoices,
            "notes": [
                "ثبت فاکتور = ساعت واقعی ثبت در کارآمد؛ ثبت حواله = اولین ذخیره حواله خروج در لاگ کاربران کارآمد.",
                "تاریخ خروج = تاریخ حواله خروج؛ تاریخ توزیع = تاریخ توزیع روی همان حواله.",
                "فاکتورهای صفر/جایزه‌ای و فاکتورهای کاملاً مرجوع‌شده نمایش داده نمی‌شوند.",
            ],
        }

    def _overview(self) -> dict[str, Any]:
        today = date.today()
        with self.engine.connect() as connection:
            fy = KaramadSalesNetworkService._fiscal_years(connection)
            params = {"fy": fy["current_id"], "min_amount": MIN_LAST_INVOICE_AMOUNT_RIAL}

            undistributed = []
            for r in connection.execute(text(
                """
                SELECT f.[ID], f.[Code], f.[DateE], f.[FactorPriceP], b.[Name] AS BranchName,
                       cu.[Name] AS CustomerName, cu.[Code] AS CustomerCode, v.[Name] AS VisitorName
                FROM dbo.[tblFactorF] f
                LEFT JOIN dbo.[tblBranch] b ON b.[ID] = f.[BranchRef]
                LEFT JOIN dbo.[tblCustomer] cu ON cu.[ID] = f.[CustomerRef]
                LEFT JOIN dbo.[tblVisitor] v ON v.[ID] = f.[VisitorRef]
                WHERE f.[FiscalYear] = :fy AND f.[FactorPriceP] >= :min_amount
                  -- توزیع‌نشده = «خروجی» کمتر از ۱ (حواله خروج ندارد)، مستقل از Status حواله
                  AND NOT EXISTS (SELECT 1 FROM dbo.[tblExit] e WHERE e.[ID] = f.[ExitRef] AND e.[Code] >= 1)
                  AND NOT EXISTS (SELECT 1 FROM dbo.[tblFactorB] rb WHERE rb.[FactorFRef] = f.[ID]
                                  GROUP BY rb.[FactorFRef] HAVING SUM(rb.[FactorPriceP]) >= f.[FactorPriceP])
                ORDER BY f.[DateE], f.[ID]
                """
            ), params).mappings():
                issued = _as_date(r["DateE"])
                undistributed.append({
                    "invoice_id": int(r["ID"]),
                    "number": _text(r["Code"]),
                    "date_jalali": format_jalali_date(issued),
                    "days_waiting": (today - issued).days if issued else None,
                    "amount_rial": _num(r["FactorPriceP"]),
                    "branch_name": _text(r["BranchName"]),
                    "customer_name": _text(r["CustomerName"]),
                    "customer_code": _text(r["CustomerCode"]),
                    "visitor_name": _text(r["VisitorName"]),
                })

            # Days from invoice to its exit, per branch (negative gaps are data-entry noise → 0).
            lead_time = [{
                "branch_name": _text(r["BranchName"]),
                "invoice_count": int(r["n"] or 0),
                "average_days": round(float(r["avg_days"] or 0), 1),
                "within_1_day_percent": round(100.0 * float(r["d1"] or 0) / float(r["n"]), 1) if r["n"] else 0.0,
                "within_3_days_percent": round(100.0 * float(r["d3"] or 0) / float(r["n"]), 1) if r["n"] else 0.0,
                "over_7_days": int(r["d7"] or 0),
            } for r in connection.execute(text(
                """
                WITH lead AS (
                    SELECT f.[BranchRef], CASE WHEN DATEDIFF(day, f.[DateE], e.[DateE]) < 0 THEN 0
                                              ELSE DATEDIFF(day, f.[DateE], e.[DateE]) END AS days
                    FROM dbo.[tblFactorF] f JOIN dbo.[tblExit] e ON e.[ID] = f.[ExitRef]
                    WHERE f.[FiscalYear] = :fy AND f.[FactorPriceP] >= :min_amount
                )
                SELECT b.[Name] AS BranchName, COUNT(*) AS n, AVG(CAST(l.days AS float)) AS avg_days,
                       SUM(CASE WHEN l.days <= 1 THEN 1 ELSE 0 END) AS d1,
                       SUM(CASE WHEN l.days <= 3 THEN 1 ELSE 0 END) AS d3,
                       SUM(CASE WHEN l.days > 7 THEN 1 ELSE 0 END) AS d7
                FROM lead l LEFT JOIN dbo.[tblBranch] b ON b.[ID] = l.[BranchRef]
                GROUP BY b.[Name]
                """
            ), params).mappings()]

            distributors = [{
                "deliver_name": _text(r["DeliverName"]) or "بدون موزع",
                "branch_name": _text(r["BranchName"]),
                "exit_count": int(r["Exits"] or 0),
                "invoice_count": int(r["Invoices"] or 0),
                "amount_rial": _num(r["Amount"]),
                "average_lead_days": round(float(r["AvgLead"] or 0), 1),
                "last_exit_date_jalali": format_jalali_date(r["LastExit"]),
            } for r in connection.execute(text(
                """
                SELECT dl.[Name] AS DeliverName, b.[Name] AS BranchName,
                       COUNT(DISTINCT e.[ID]) AS Exits, COUNT(f.[ID]) AS Invoices, SUM(f.[FactorPriceP]) AS Amount,
                       AVG(CAST(CASE WHEN DATEDIFF(day, f.[DateE], e.[DateE]) < 0 THEN 0 ELSE DATEDIFF(day, f.[DateE], e.[DateE]) END AS float)) AS AvgLead,
                       MAX(e.[DateE]) AS LastExit
                FROM dbo.[tblExit] e
                JOIN dbo.[tblFactorF] f ON f.[ExitRef] = e.[ID] AND f.[FactorPriceP] >= :min_amount
                LEFT JOIN dbo.[tblDeliver] dl ON dl.[ID] = e.[DeliverRef]
                LEFT JOIN dbo.[tblBranch] b ON b.[ID] = e.[BranchRef]
                WHERE e.[FiscalYear] = :fy
                GROUP BY dl.[Name], b.[Name]
                ORDER BY SUM(f.[FactorPriceP]) DESC
                """
            ), params).mappings()]

        return {
            "status": "success",
            "fiscal_year_label": fy["current_label"],
            "undistributed": undistributed,
            "lead_time": sorted(lead_time, key=lambda x: -x["average_days"]),
            "distributors": distributors,
            "notes": [
                "فاکتور توزیع‌نشده = فاکتور فروش سال جاری که هنوز «خروجی» (حواله خروج) ندارد، یعنی خروجی کمتر از ۱ (بدون فاکتورهای صفر/جایزه‌ای و فاکتورهای کاملاً مرجوع‌شده).",
                "این فاکتورها از همین حالا در فروش و بدهی مشتری حساب شده‌اند.",
            ],
        }


# --------------------------------------------------------------------------- Excel
def _timing_by_branch(invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """خلاصه زمان‌بندی هر هیبرید (همان شاخص‌های بالای خط زمان صفحه)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for x in invoices:
        groups.setdefault(x["branch_name"] or "—", []).append(x)
    rows = []
    for name, items in groups.items():
        exited = [x for x in items if x["hours_to_exit_registration"] is not None]
        hours = sorted(x["hours_to_exit_registration"] for x in exited)
        leads = [x["days_invoice_to_exit"] for x in items if x["days_invoice_to_exit"] is not None]
        same_day = sum(1 for x in exited
                       if (x["invoice_created"] or {}).get("date_jalali") == (x["exit_registered"] or {}).get("date_jalali"))
        waiting = [x for x in items if x["stage"] == "waiting"]
        rows.append({
            "branch_name": name,
            "invoice_count": len(items),
            "amount_rial": sum(x["amount_rial"] for x in items),
            "waiting_count": len(waiting),
            "waiting_amount_rial": sum(x["amount_rial"] for x in waiting),
            "median_hours_to_exit": hours[len(hours) // 2] if hours else None,
            "same_day_percent": round(100 * same_day / len(exited), 1) if exited else None,
            "average_days_to_exit": round(sum(leads) / len(leads), 1) if leads else None,
            "late_registered_count": sum(1 for x in items if (x["registration_delay_days"] or 0) > 0),
            "max_waiting_days": max((x["days_waiting"] or 0 for x in waiting), default=0),
        })
    return sorted(rows, key=lambda r: -r["amount_rial"])


def distribution_workbook(year: int, month: int, days: int = 30):
    """Excel همه بخش‌های صفحه توزیع بار؛ هر بخش یک برگه با فیلتر. مبالغ به تومان."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    service = KaramadDistributionService()
    monthly = service.monthly(year, month)
    overview = service.overview()
    timeline = service.timeline(days, year, month)

    def toman(rial):
        return round(float(rial or 0) / 10)

    head = PatternFill("solid", fgColor="1F4E78")
    wb = Workbook()
    first = [True]

    def sheet(title, headers, rows, widths, money=()):
        ws = wb.active if first[0] else wb.create_sheet()
        first[0] = False
        ws.title = title[:31]
        ws.sheet_view.rightToLeft = True
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for row in rows:
            ws.append(row)
        for col in money:
            for cell in ws[get_column_letter(col)][1:]:
                cell.number_format = "#,##0"
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "B2"
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"

    label = monthly.get("month_label") or f"{year}-{month}"
    t = monthly.get("totals") or {}
    sheet(f"توزیع و وصول {label}",
          ["هیبرید", "کل فروش", "توزیع نشده", "تعداد فاکتور توزیع‌نشده", "توزیع شده", "وصولی ماه", "مانده ماه"],
          [[b["branch_name"], toman(b["sales_rial"]), toman(b["undistributed_rial"]), b["undistributed_count"],
            toman(b["distributed_rial"]), toman(b["collected_rial"]), toman(b["remaining_rial"])]
           for b in monthly.get("branches", [])]
          + [["جمع کل", toman(t.get("sales_rial")), toman(t.get("undistributed_rial")), None,
              toman(t.get("distributed_rial")), toman(t.get("collected_rial")), toman(t.get("remaining_rial"))]],
          [24, 18, 18, 14, 18, 18, 18], (2, 3, 5, 6, 7))
    sheet("مشتریان ماه",
          ["کد تفضیلی", "هیبرید", "کد مشتری", "نام مشتری", "مانده سیستم", "توزیع شده", "توزیع نشده", "وصول", "مانده فاکتورهای ماه"],
          [[c.get("dl_code"), c["branch_name"], c["customer_code"], c["customer_name"], toman(c.get("system_balance_rial")),
            toman(c["distributed_rial"]), toman(c["undistributed_rial"]), toman(c["collected_rial"]),
            toman(c.get("remaining_rial"))] for c in monthly.get("customers", [])],
          [16, 20, 14, 34, 16, 16, 16, 16, 18], (5, 6, 7, 8, 9))
    sheet("توزیع‌نشده‌های ماه",
          ["هیبرید", "کد مشتری", "مشتری", "شماره فاکتور", "تاریخ", "روز انتظار", "ویزیتور", "قابل پرداخت", "برگشتی", "توزیع نشده"],
          [[x["branch_name"], x["customer_code"], x["customer_name"], x["number"], x["date_jalali"], x["days_waiting"],
            x["visitor_name"], toman(x.get("invoice_rial", x["amount_rial"])), toman(x.get("returned_rial")), toman(x["amount_rial"])]
           for x in monthly.get("undistributed", [])],
          [20, 14, 32, 12, 12, 10, 26, 16, 14, 16], (8, 9, 10))
    sheet("کنترل وصول",
          ["شعبه", "لاین", "شناسه", "شماره فاکتور", "خروجی", "تاریخ فاکتور", "تاریخ توزیع", "روز از توزیع", "نحوه پرداخت", "کد مشتری",
           "نام مشتری", "فروشنده", "شهر", "عامل توزیع", "مبلغ ناخالص", "تخفیف حجمی", "تخفیف نقدی", "ارزش افزوده", "قابل پرداخت",
           "نقد", "حواله", "چک", "پرداختی", "برگشت از فروش", "تسهیم", "تهاتر", "مانده"],
          [[x["branch_name"], x["line_name"], x["invoice_id"], x["number"], x["exit_code"], x["date_jalali"], x["distribution_date_jalali"],
            x["days_since_distribution"], x["payment_name"], x["customer_code"], x["customer_name"], x["visitor_name"], x["city_name"],
            x["deliver_name"], toman(x["gross_rial"]), toman(x["volume_discount_rial"]), toman(x["cash_discount_rial"]), toman(x["vat_rial"]),
            toman(x["payable_rial"]), toman(x["cash_rial"]), toman(x["draft_rial"]), toman(x["cheque_rial"]), toman(x["collected_rial"]),
            toman(x["returned_rial"]), toman(x["shared_rial"]), toman(x["barter_rial"]), toman(x["unpaid_rial"])]
           for x in monthly.get("collection_control", [])],
          [18, 22, 10, 11, 9, 12, 12, 10, 14, 13, 28, 26, 14, 18] + [14] * 13, tuple(range(15, 28)))

    undistributed = overview.get("undistributed", [])
    by_branch: dict[str, dict[str, Any]] = {}
    for x in undistributed:
        b = by_branch.setdefault(x["branch_name"] or "—", {"n": 0, "amount": 0.0, "oldest": 0, "old14": 0})
        b["n"] += 1
        b["amount"] += x["amount_rial"]
        b["oldest"] = max(b["oldest"], x["days_waiting"] or 0)
        b["old14"] += 1 if (x["days_waiting"] or 0) > 14 else 0
    lead = {item["branch_name"]: item for item in overview.get("lead_time", [])}
    sheet("توزیع‌نشده به تفکیک هیبرید",
          ["هیبرید", "فاکتور توزیع‌نشده", "مبلغ", "بیش از ۱۴ روز", "قدیمی‌ترین (روز)", "میانگین صدور تا خروج (روز)"],
          sorted([[name, v["n"], toman(v["amount"]), v["old14"], v["oldest"], (lead.get(name) or {}).get("average_days")]
                  for name, v in by_branch.items()], key=lambda r: -r[2]),
          [24, 14, 18, 14, 14, 18], (3,))
    sheet("فاکتورهای توزیع‌نشده",
          ["هیبرید", "شماره فاکتور", "تاریخ", "روز انتظار", "کد مشتری", "مشتری", "ویزیتور", "مبلغ"],
          [[x["branch_name"], x["number"], x["date_jalali"], x["days_waiting"], x["customer_code"], x["customer_name"],
            x["visitor_name"], toman(x["amount_rial"])]
           for x in sorted(undistributed, key=lambda x: -(x["days_waiting"] or 0))],
          [20, 12, 12, 10, 14, 32, 26, 16], (8,))
    sheet("سرعت خروج بار",
          ["هیبرید", "تعداد فاکتور", "میانگین (روز)", "تا ۱ روز ٪", "تا ۳ روز ٪", "بیش از ۷ روز"],
          [[item["branch_name"], item["invoice_count"], item["average_days"], item.get("within_1_day_percent"),
            item.get("within_3_days_percent"), item.get("over_7_days")] for item in overview.get("lead_time", [])],
          [24, 12, 12, 12, 12, 12])
    sheet("عملکرد موزعان",
          ["موزع", "هیبرید", "حواله", "فاکتور", "مبلغ بار", "میانگین صدور تا خروج (روز)", "آخرین خروج"],
          [[d["deliver_name"], d["branch_name"], d["exit_count"], d["invoice_count"], toman(d["amount_rial"]),
            d["average_lead_days"], d["last_exit_date_jalali"]] for d in overview.get("distributors", [])],
          [24, 20, 10, 10, 18, 20, 14], (5,))

    tlabel = timeline.get("month_label") or f"{days} روز اخیر"
    sheet(f"زمان‌بندی هیبرید {tlabel}",
          ["هیبرید", "فاکتور", "مبلغ", "در انتظار حواله", "مبلغ در انتظار", "میانه ثبت فاکتور تا حواله (ساعت)",
           "حواله همان روز ٪", "میانگین فاکتور تا خروج (روز)", "ثبت دیرتر از تاریخ فاکتور", "بیشترین انتظار (روز)"],
          [[r["branch_name"], r["invoice_count"], toman(r["amount_rial"]), r["waiting_count"],
            toman(r["waiting_amount_rial"]), r["median_hours_to_exit"], r["same_day_percent"],
            r["average_days_to_exit"], r["late_registered_count"], r["max_waiting_days"]]
           for r in _timing_by_branch(timeline.get("invoices", []))],
          [22, 10, 18, 14, 16, 20, 14, 18, 18, 14], (3, 5))
    stage_fa = {"waiting": "در انتظار حواله خروج", "dispatched": "خارج شده", "scheduled": "خروج در روزهای آینده"}

    def stamp_text(s):
        return f'{s["date_jalali"]} {s["time"]}' if s else ""

    sheet(f"زمان‌بندی فاکتور {tlabel}",
          ["هیبرید", "شماره فاکتور", "مشتری", "کد مشتری", "ویزیتور", "مبلغ", "وضعیت", "تاریخ فاکتور", "ثبت فاکتور",
           "ثبت‌کننده فاکتور", "ثبت حواله خروج", "کد حواله", "تاریخ خروج", "موزع", "راننده",
           "ثبت فاکتور تا حواله (ساعت)", "فاکتور تا خروج (روز)", "روز انتظار"],
          [[x["branch_name"], x["number"], x["customer_name"], x["customer_code"], x["visitor_name"],
            toman(x["amount_rial"]), stage_fa.get(x["stage"], x["stage"]), x["invoice_date_jalali"],
            stamp_text(x["invoice_created"]), x["invoice_user"], stamp_text(x["exit_registered"]), x["exit_code"],
            x["exit_date_jalali"], x["deliver_name"], x["driver_name"], x["hours_to_exit_registration"],
            x["days_invoice_to_exit"], x["days_waiting"]] for x in timeline.get("invoices", [])],
          [18, 12, 30, 12, 24, 16, 18, 12, 18, 18, 18, 10, 12, 20, 20, 16, 14, 10], (6,))
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out
