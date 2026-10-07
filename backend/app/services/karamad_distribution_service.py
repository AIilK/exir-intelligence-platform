"""توزیع بار کارآمد: فاکتورهایی که هنوز حواله خروج ندارند، حواله‌های باز، سرعت خروج بار و عملکرد موزعان.

ساختار کارآمد (بررسی‌شده روی KDB):
- هر فاکتور فروش (tblFactorF) با ExitRef به حواله خروج (tblExit) وصل می‌شود؛ فاکتور بدون
  ExitRef هنوز برای توزیع بار نشده است. فیلد Delivered در این نصب همیشه صفر است و استفاده نمی‌شود.
- حواله خروج: DateE (تاریخ خروج)، DeliverRef (موزع، tblDeliver)، DriverRef (راننده، tblDriver)،
  Status (در این نصب ۰ یا ۱؛ معنی ۰ هنوز از واحد توزیع تأیید نشده و جدا نمایش داده می‌شود).
- فاکتورهای صفر/جایزه‌ای (کمتر از MIN_LAST_INVOICE_AMOUNT_RIAL) کنار گذاشته می‌شوند.
- فاکتوری که به‌طور کامل مرجوع شده (tblFactorB.FactorFRef) توزیع لازم ندارد و حذف می‌شود.
"""

from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any

from sqlalchemy import text

from app.services.customer_file_service import MIN_LAST_INVOICE_AMOUNT_RIAL
from app.services.karamad_sales_network_service import KaramadSalesNetworkService, _as_date, _num, _text
from app.utils.jalali import format_jalali_date

CACHE_SECONDS = 300
_cache: dict[str, Any] = {"at": 0.0, "data": None}
_lock = threading.Lock()
_month_cache: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}

JALALI_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")


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
        - توزیع نشده = invoices with no exit document (ExitRef); توزیع شده = the rest;
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
                       ISNULL(p.[CashN], 0) + ISNULL(p.[Draft], 0) + ISNULL(p.[Cheque], 0) AS Collected
                FROM dbo.[tblFactorF] f
                JOIN dbo.[tblBranch] b ON b.[ID] = f.[BranchRef]
                LEFT JOIN dbo.[tblCustomer] cu ON cu.[ID] = f.[CustomerRef]
                LEFT JOIN dbo.[tblVisitor] v ON v.[ID] = f.[VisitorRef]
                LEFT JOIN dbo.[vwFactorFPayoff] p ON p.[ID] = f.[ID]
                WHERE f.[DateE] >= :start AND f.[DateE] < :end AND b.[Name] LIKE N'%هیبرید%'
                """
            ), params).mappings().all()
            returns = connection.execute(text(
                """
                SELECT r.[FactorFRef], r.[FactorNo], r.[BranchRef], r.[FactorPriceP]
                FROM dbo.[tblFactorB] r WHERE r.[DateE] >= :start AND r.[DateE] < :end
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
        for r in invoices:
            inv_id = int(r["ID"])
            net = float(r["FactorPriceP"] or 0) - returned.get(inv_id, 0.0)
            branch = _text(r["BranchName"])
            b = branches.setdefault(branch, {"branch_name": branch, "sales_rial": 0.0, "undistributed_rial": 0.0,
                                             "distributed_rial": 0.0, "collected_rial": 0.0, "remaining_rial": 0.0,
                                             "undistributed_count": 0})
            dl = int(r["DLRef"]) if r["DLRef"] is not None else None
            c = customers.setdefault((branch, dl), {"branch_name": branch, "dl_ref": dl, "customer_name": _text(r["CustomerName"]),
                                                   "customer_code": _text(r["CustomerCode"]), "distributed_rial": 0.0,
                                                   "undistributed_rial": 0.0, "collected_rial": 0.0})
            b["sales_rial"] += net
            c["collected_rial"] += float(r["Collected"] or 0)
            if r["ExitRef"] is None:
                b["undistributed_rial"] += net
                b["undistributed_count"] += 1
                c["undistributed_rial"] += net
                issued = _as_date(r["DateE"])
                undistributed.append({
                    "invoice_id": inv_id, "number": _text(r["Code"]), "date_jalali": format_jalali_date(issued),
                    "days_waiting": (today - issued).days if issued else None, "amount_rial": _num(net),
                    "branch_name": branch, "customer_name": _text(r["CustomerName"]),
                    "customer_code": _text(r["CustomerCode"]), "visitor_name": _text(r["VisitorName"]),
                })
            else:
                c["distributed_rial"] += net

        rows = []
        for c in customers.values():
            balance = float(positions.get(c["dl_ref"], {}).get("balance_rial") or 0) if c["dl_ref"] is not None else 0.0
            c["system_balance_rial"] = balance
            c["remaining_rial"] = min(balance, c["distributed_rial"] - c["collected_rial"])
            b = branches[c["branch_name"]]
            b["collected_rial"] += c["collected_rial"]
            b["remaining_rial"] += c["remaining_rial"]
            rows.append({k: (_num(v) if k.endswith("_rial") else v) for k, v in c.items()})
        for b in branches.values():
            b["distributed_rial"] = b["sales_rial"] - b["undistributed_rial"]
        branch_rows = sorted(({k: (_num(v) if k.endswith("_rial") else v) for k, v in b.items()} for b in branches.values()),
                             key=lambda x: x["branch_name"])
        totals = {k: _num(sum(b[k] for b in branch_rows)) for k in
                  ("sales_rial", "undistributed_rial", "distributed_rial", "collected_rial", "remaining_rial")}
        return {
            "status": "success",
            "year": year, "month": month, "month_label": f"{JALALI_MONTHS[month - 1]} {year}",
            "branches": branch_rows,
            "totals": totals,
            "customers": sorted(rows, key=lambda x: (x["branch_name"], -x["distributed_rial"])),
            "undistributed": sorted(undistributed, key=lambda x: -(x["days_waiting"] or 0)),
        }

    # ------------------------------------------------------------- per-invoice timeline
    def timeline(self, days: int = 14) -> dict[str, Any]:
        """زمان‌بندی توزیع هر فاکتور: تاریخ فاکتور، ثبت در سیستم، ثبت حواله خروج و تاریخ خروج.

        - ثبت فاکتور = tblFactorF.CreateDate (ساعت واقعی ثبت؛ ممکن است بعد از تاریخ فاکتور باشد).
        - ثبت حواله خروج = اولین «ذخیره خروج کالا از انبار با شناسه{ID}» در tblUsersLogs؛
          tblExit خودش زمان ثبت ندارد. چند ذخیره = حواله بعداً ویرایش شده است.
        - لاگ‌هایی که ساعت کامپیوترشان اشتباه است (مثلاً سال ۲۰۴۹) کنار گذاشته می‌شوند.
        """
        safe_days = max(1, min(int(days), 90))
        key = ("timeline", safe_days)
        with _lock:
            hit = _month_cache.get(key)
            if hit and time.time() - hit[0] < CACHE_SECONDS:
                return hit[1]
        data = self._timeline(safe_days)
        with _lock:
            _month_cache[key] = (time.time(), data)
        return data

    def _timeline(self, days: int) -> dict[str, Any]:
        from datetime import datetime, timedelta
        today = date.today()
        start = today - timedelta(days=days)
        prefix = "ذخیره خروج کالا از انبار با شناسه"
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                """
                WITH inv AS (
                    SELECT f.[ID], f.[Code], f.[DateE], f.[CreateDate], f.[FactorPriceP], f.[ExitRef], f.[UserRef],
                           f.[BranchRef], f.[CustomerRef], f.[VisitorRef]
                    FROM dbo.[tblFactorF] f
                    WHERE f.[DateE] >= :start AND f.[FactorPriceP] >= :min_amount
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
                       e.[Status] AS ExitStatus, eu.[Name] AS ExitUser,
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
            ), {"start": start, "min_amount": MIN_LAST_INVOICE_AMOUNT_RIAL, "prefix": prefix}).mappings().all()

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
                "exit_status": None if r["ExitStatus"] is None else int(bool(r["ExitStatus"])),
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
            "from_date_jalali": format_jalali_date(start),
            "to_date_jalali": format_jalali_date(today),
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
                WHERE f.[FiscalYear] = :fy AND f.[ExitRef] IS NULL AND f.[FactorPriceP] >= :min_amount
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

            open_exits = [{
                "exit_id": int(r["ID"]),
                "code": _text(r["Code"]),
                "date_jalali": format_jalali_date(r["DateE"]),
                "days_open": (today - _as_date(r["DateE"])).days if r["DateE"] else None,
                "branch_name": _text(r["BranchName"]),
                "deliver_name": _text(r["DeliverName"]),
                "driver_name": _text(r["DriverName"]),
                "invoice_count": int(r["InvoiceCount"] or 0),
                "amount_rial": _num(r["Amount"]),
            } for r in connection.execute(text(
                """
                SELECT e.[ID], e.[Code], e.[DateE], b.[Name] AS BranchName, dl.[Name] AS DeliverName, dr.[Name] AS DriverName,
                       COUNT(f.[ID]) AS InvoiceCount, SUM(f.[FactorPriceP]) AS Amount
                FROM dbo.[tblExit] e
                JOIN dbo.[tblFactorF] f ON f.[ExitRef] = e.[ID]
                LEFT JOIN dbo.[tblBranch] b ON b.[ID] = e.[BranchRef]
                LEFT JOIN dbo.[tblDeliver] dl ON dl.[ID] = e.[DeliverRef]
                LEFT JOIN dbo.[tblDriver] dr ON dr.[ID] = e.[DriverRef]
                WHERE e.[FiscalYear] = :fy AND e.[Status] = 0
                GROUP BY e.[ID], e.[Code], e.[DateE], b.[Name], dl.[Name], dr.[Name]
                ORDER BY e.[DateE], e.[ID]
                """
            ), params).mappings()]

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
            "open_exits": open_exits,
            "lead_time": sorted(lead_time, key=lambda x: -x["average_days"]),
            "distributors": distributors,
            "notes": [
                "فاکتور توزیع‌نشده = فاکتور فروش سال جاری که هنوز حواله خروج ندارد (بدون فاکتورهای صفر/جایزه‌ای و فاکتورهای کاملاً مرجوع‌شده).",
                "این فاکتورها از همین حالا در فروش و بدهی مشتری حساب شده‌اند.",
                "حواله‌های با وضعیت «۰» جدا نمایش داده می‌شوند؛ معنی دقیق این وضعیت باید از واحد توزیع تأیید شود.",
            ],
        }
