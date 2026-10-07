"""پرونده شبکه فروش کارآمد: هیبرید من ← ویزیتور (بدون نام مشتریان).

ساختار کارآمد (بررسی‌شده روی KDB):
- «هیبرید من» = tblDL با کلاس «هیبرید من ها» (tblDLClass.ID = 28)؛ هر شعبه یک یا چند نفر.
- ویزیتور = tblVisitor (BranchRef، SupervisorRef)؛ هر فاکتور tblFactorF ویزیتور و سرپرست دارد.
- چک دریافتی tblChequeD.FactorRef → tblFactorF.ID (۹۳٪ چک‌های باز)؛ پس چک به ویزیتور فاکتورش نسبت داده می‌شود.
- شناسه و کد شعبه در همه جداول یکی است.

مطالبات: «مانده» فاکتورهای قدیمی در کارآمد به فاکتور تخصیص داده نشده (جمع UnPaid همه سال‌ها
چند برابر مانده دفتر کل است)، بنابراین بدهی شعبه/ویزیتور از مانده دفتر کل مشتریانش خوانده می‌شود:
- شعبه: مشتریانی که شعبه اصلی‌شان همین شعبه است (tblCustomer.BranchRef).
- ویزیتور: FIFO — پرداخت‌ها اول قدیمی‌ترین فاکتورهای مشتری را تسویه می‌کنند، پس مانده بدهی
  مال جدیدترین فاکتورهاست و هر بخش به ویزیتورِ همان فاکتور می‌رسد (هر ریال فقط یک‌بار شمرده می‌شود).
  چک برگشتیِ تسویه‌نشده بدهی قطعی است و به ویزیتورِ فاکتورِ همان چک می‌رسد.
نام مشتری فقط در «جزئیات مانده بدهی» (debt_detail) برمی‌گردد؛ پرونده‌ها و فهرست شبکه نام مشتری ندارند.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any

from sqlalchemy import bindparam, text

from app.services.customer_cheque_return_risk import attach_return_risk
from app.services.customer_file_service import (
    KARAMAD_HYBRID_DL_CLASS_ID,
    LAST_INVOICE_COUNT,
    MIN_LAST_INVOICE_AMOUNT_RIAL,
    karamad_invoice_settlements,
)
from app.utils.jalali import format_jalali_date

OPEN_CHEQUE_STATUSES = (1, 2, 3, 6, 7, 10)
COLLECTED_CHEQUE_STATUS = 4
RETURNED_CHEQUE_STATUSES = (6, 7, 8, 10)
JALALI_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
OPEN_RETURNED_CHEQUE_STATUSES = (6, 7, 10)  # returned and not yet settled (8 = returned, then collected)
# Customer scopes (fixed internal SQL returning tblCustomer.ID; :sid is the branch/visitor id).
VISITOR_CUSTOMERS = "SELECT [CustomerRef] FROM dbo.[tblFactorF] WHERE [VisitorRef] = :sid"
BRANCH_VISITOR_CUSTOMERS = """SELECT x.[CustomerRef] FROM dbo.[tblFactorF] x
    INNER JOIN dbo.[tblVisitor] xv ON xv.[ID] = x.[VisitorRef] WHERE xv.[BranchRef] = :sid"""
BRANCH_MAIN_CUSTOMERS = "SELECT [ID] FROM dbo.[tblCustomer] WHERE [BranchRef] = :sid"
LEDGER_CACHE_SECONDS = 600
FILE_CACHE_SECONDS = 300
# Leavers are recorded in Karamad personnel (tblPR_Employee.LeaveDate); Karamad itself
# keeps them Status=1. Some people still sell after their recorded leave date (e.g. moved
# from employee to contractor), so a leaver must ALSO have no invoice in this many days.
LEFT_GRACE_DAYS = 60


def _left_sql(alias: str, invoice_column: str) -> str:
    """SQL condition: the supervisor/visitor ``alias`` has left the company (fixed internal fragment)."""
    return f"""(
        EXISTS (SELECT 1 FROM (SELECT TOP (1) e.[LeaveDate] FROM dbo.[tblPR_Employee] e
                               WHERE e.[DLRef] = {alias}.[DLRef] ORDER BY e.[EmpDate] DESC, e.[ID] DESC) le
                WHERE le.[LeaveDate] IS NOT NULL AND le.[LeaveDate] <= CAST(GETDATE() AS date))
        AND NOT EXISTS (SELECT 1 FROM dbo.[tblFactorF] rf WHERE rf.[{invoice_column}] = {alias}.[ID]
                        AND rf.[DateE] >= DATEADD(day, -{LEFT_GRACE_DAYS}, CAST(GETDATE() AS date)))
    )"""


SUPERVISOR_LEFT = _left_sql("s", "SupervisorRef")
VISITOR_LEFT = _left_sql("v", "VisitorRef")

_ledger_cache: dict[str, Any] = {"at": 0.0, "data": None}
_ledger_lock = threading.Lock()
_file_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}
_file_lock = threading.Lock()


def _num(value: Any) -> float:
    return round(float(value or 0), 2)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def ledger_positions() -> dict[int, dict[str, Any]]:
    """All customer ledger balances (one ~14s query), cached for 10 minutes."""
    with _ledger_lock:
        if _ledger_cache["data"] is None or time.time() - _ledger_cache["at"] > LEDGER_CACHE_SECONDS:
            from app.services.karamad_customer_account_service import KaramadCustomerAccountService
            _ledger_cache["data"] = KaramadCustomerAccountService().bulk_account_positions()
            _ledger_cache["at"] = time.time()
        return _ledger_cache["data"]


def _debt(dl_refs: list[int], positions: dict[int, dict[str, Any]]) -> dict[str, Any]:
    balances = [float(positions[d].get("balance_rial") or 0) for d in set(dl_refs) if d in positions]
    return {
        "open_account_receivable_rial": _num(sum(b for b in balances if b > 0)),
        "customer_credit_rial": _num(sum(-b for b in balances if b < 0)),
        "debtor_customer_count": sum(1 for b in balances if b > 0),
        "customer_count": len(set(dl_refs)),
    }


# Sales are reported like the finance team's Karamad sales report: returns (tblFactorB) are
# subtracted in the year they were booked.
#   ناخالص (gross) = جمع قبل تخفیف (FactorPrice) of sales − returns
#   خالص (net)     = قابل پرداخت (FactorPriceP: after discounts, incl. VAT) of sales − returns
SALES_SOURCE = """(
    SELECT [ID], [BranchRef], [VisitorRef], [FiscalYear], [DateE], [FactorPrice], [FactorPriceP], 0 AS [is_return]
    FROM dbo.[tblFactorF]
    UNION ALL
    SELECT [ID], [BranchRef], [VisitorRef], [FiscalYear], [DateE], -[FactorPrice], -[FactorPriceP], 1
    FROM dbo.[tblFactorB]
)"""
SALES_COLUMNS = """SUM(CASE WHEN f.[is_return] = 0 THEN 1 ELSE 0 END) AS invoice_count,
                   SUM(f.[FactorPrice]) AS gross_amount, SUM(f.[FactorPriceP]) AS net_amount"""


def _sales_fields(cur: Any, prev: Any) -> dict[str, Any]:
    """Current/previous-year sales fields from two SALES_COLUMNS rows (net is the headline figure)."""
    return {
        "current_year_invoice_count": int(cur.get("invoice_count") or 0),
        "current_year_sales_rial": _num(cur.get("net_amount")),
        "current_year_gross_sales_rial": _num(cur.get("gross_amount")),
        "previous_year_invoice_count": int(prev.get("invoice_count") or 0),
        "previous_year_sales_rial": _num(prev.get("net_amount")),
        "previous_year_gross_sales_rial": _num(prev.get("gross_amount")),
    }


def _group_by_customer(invoices, returned) -> tuple[dict[int, list], dict[int, list]]:
    """Invoice rows (DLRef, VisitorRef, FactorPriceP, DateE; newest first per customer) and open
    returned-cheque rows (DLRef, VisitorRef, Price, DueDate) keyed by customer DL."""
    by_invoice: dict[int, list] = {}
    for r in invoices:
        by_invoice.setdefault(int(r["DLRef"]), []).append(
            (int(r["VisitorRef"]) if r["VisitorRef"] is not None else None, float(r["FactorPriceP"] or 0), _as_date(r["DateE"])))
    by_returned: dict[int, list] = {}
    for r in returned:
        by_returned.setdefault(int(r["DLRef"]), []).append(
            (int(r["VisitorRef"]) if r["VisitorRef"] is not None else None, float(r["Price"] or 0), _as_date(r["DueDate"])))
    return by_invoice, by_returned


def _allocate_debt(balance: float, invoices: list, returned: list) -> list[dict[str, Any]]:
    """Split one customer's ledger debt into slices, each owned by a visitor.

    An open returned cheque is debt the customer certainly still owes, so it is taken first
    and goes to the visitor of the invoice it paid. The rest follows FIFO: payments settle the
    oldest invoices first, so what is still owed belongs to the newest invoices (``invoices`` is
    newest first). A balance larger than all of that (e.g. an opening balance) is "unmatched" and
    goes to the visitor of the customer's latest invoice.
    """
    latest = next((v for v, _, _ in invoices if v is not None), None)
    slices: list[dict[str, Any]] = []
    remaining = balance
    for kind, rows in (("returned_cheque", returned), ("invoice", invoices)):
        for visitor_id, amount, when in rows:
            if remaining <= 0:
                return slices
            share = min(remaining, max(amount, 0.0))
            if share > 0:
                remaining -= share
                slices.append({"visitor_id": visitor_id if visitor_id is not None else latest,
                               "kind": kind, "date": when, "amount": share})
    if remaining > 0:
        slices.append({"visitor_id": latest, "kind": "unmatched", "date": None, "amount": remaining})
    return slices


def _visitor_debts(invoices, returned, positions: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Box-1 debt per visitor (see ``_allocate_debt``); credit balances follow the latest invoice."""
    by_invoice, by_returned = _group_by_customer(invoices, returned)
    result: dict[int, dict[str, Any]] = {}

    def slot(visitor_id: int) -> dict[str, Any]:
        return result.setdefault(visitor_id, {"receivable": 0.0, "credit": 0.0, "debtors": set(), "customers": set()})

    for dl, rows in by_invoice.items():
        for visitor_id, _, _ in rows:
            if visitor_id is not None:
                slot(visitor_id)["customers"].add(dl)
        latest = next((v for v, _, _ in rows if v is not None), None)
        balance = float(positions.get(dl, {}).get("balance_rial") or 0)
        if balance < 0 and latest is not None:
            slot(latest)["credit"] += -balance
        for s in _allocate_debt(balance, rows, by_returned.get(dl, [])):
            if s["visitor_id"] is not None:
                slot(s["visitor_id"])["receivable"] += s["amount"]
                slot(s["visitor_id"])["debtors"].add(dl)

    return {
        visitor_id: {
            "open_account_receivable_rial": _num(s["receivable"]),
            "customer_credit_rial": _num(s["credit"]),
            "debtor_customer_count": len(s["debtors"]),
            "customer_count": len(s["customers"]),
        }
        for visitor_id, s in result.items()
    }


_EMPTY_DEBT = {"open_account_receivable_rial": 0.0, "customer_credit_rial": 0.0, "debtor_customer_count": 0, "customer_count": 0}


class KaramadSalesNetworkService:
    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
            self._engine = get_karamad_sqlserver_engine()
        return self._engine

    # ----------------------------------------------------------------- helpers
    def _parallel(self, tasks: dict[str, tuple[Any, tuple]]) -> dict[str, Any]:
        """Run independent sections on separate connections; the shared Karamad server
        is often busy, so sequential sections added up to 10-25s per file."""
        def run(fn, args):
            with self.engine.connect() as connection:
                return fn(connection, *args)
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {name: pool.submit(run, fn, args) for name, (fn, args) in tasks.items()}
            return {name: f.result() for name, f in futures.items()}

    @staticmethod
    def _cached(key: tuple[str, int], build) -> dict[str, Any]:
        with _file_lock:
            hit = _file_cache.get(key)
            if hit and time.time() - hit[0] < FILE_CACHE_SECONDS:
                return hit[1]
        result = build()
        if result.get("status") == "success":
            with _file_lock:
                _file_cache[key] = (time.time(), result)
        return result

    @staticmethod
    def _fiscal_years(connection) -> dict[str, Any]:
        years = connection.execute(text(
            "SELECT [ID], [Name], [DateStart], [DateEnd] FROM dbo.[tblFiscalYear] ORDER BY [DateStart] DESC"
        )).mappings().all()
        today = date.today()
        current = next((y for y in years if _as_date(y["DateStart"]) <= today <= _as_date(y["DateEnd"])), None)
        previous = next((y for y in years if current and _as_date(y["DateEnd"]) < _as_date(current["DateStart"])), None)
        return {
            "current_id": current["ID"] if current else -1,
            "previous_id": previous["ID"] if previous else -1,
            "current_label": _text(current["Name"]) if current else "",
            "previous_label": _text(previous["Name"]) if previous else "",
        }

    @staticmethod
    def _hybrids_by_branch(connection, branch_ids: list[int] | None = None) -> dict[int, list[str]]:
        sql = "SELECT [BranchRef], [Name] FROM dbo.[tblDL] WHERE [ClassRef] = :cls AND [BranchRef] IS NOT NULL"
        params: dict[str, Any] = {"cls": KARAMAD_HYBRID_DL_CLASS_ID}
        query = text(sql + " ORDER BY [Name]")
        if branch_ids is not None:
            query = text(sql + " AND [BranchRef] IN :branches ORDER BY [Name]").bindparams(bindparam("branches", expanding=True))
            params["branches"] = branch_ids or [-1]
        result: dict[int, list[str]] = {}
        for row in connection.execute(query, params).mappings():
            result.setdefault(int(row["BranchRef"]), []).append(_text(row["Name"]))
        return result

    # ---------------------------------------------------------------- overview
    def overview(self) -> dict[str, Any]:
        return self._cached(("overview", 0), self._overview)

    def _overview(self) -> dict[str, Any]:
        positions = ledger_positions()
        with self.engine.connect() as connection:
            fy = self._fiscal_years(connection)
            hybrids = self._hybrids_by_branch(connection)
            branch_ids = sorted(hybrids)
            expand = lambda sql: text(sql).bindparams(bindparam("branches", expanding=True))  # noqa: E731
            params = {"branches": branch_ids or [-1], "cur": fy["current_id"], "prev": fy["previous_id"]}
            names = {int(r["ID"]): _text(r["Name"]) for r in connection.execute(expand(
                "SELECT [ID], [Name] FROM dbo.[tblBranch] WHERE [ID] IN :branches"), params).mappings()}
            supervisors = {int(r["BranchRef"]): int(r["n"]) for r in connection.execute(expand(
                f"SELECT s.[BranchRef], COUNT(*) AS n FROM dbo.[tblSupervisor] s WHERE s.[Status] = 1 AND NOT {SUPERVISOR_LEFT} AND s.[BranchRef] IN :branches GROUP BY s.[BranchRef]"
            ), params).mappings()}
            visitors = {int(r["BranchRef"]): int(r["n"]) for r in connection.execute(expand(
                f"SELECT v.[BranchRef], COUNT(*) AS n FROM dbo.[tblVisitor] v WHERE v.[Status] = 1 AND NOT {VISITOR_LEFT} AND v.[BranchRef] IN :branches GROUP BY v.[BranchRef]"
            ), params).mappings()}
            sales: dict[tuple[int, Any], Any] = {
                (int(r["BranchRef"]), r["FiscalYear"]): r for r in connection.execute(expand(
                    f"""
                    SELECT [BranchRef], [FiscalYear], {SALES_COLUMNS}
                    FROM {SALES_SOURCE} f
                    WHERE [BranchRef] IN :branches AND [FiscalYear] IN (:cur, :prev)
                    GROUP BY [BranchRef], [FiscalYear]
                    """
                ), params).mappings()
            }
            customers: dict[int, list[int]] = {}
            for r in connection.execute(expand(
                "SELECT [BranchRef], [DLRef] FROM dbo.[tblCustomer] WHERE [DLRef] IS NOT NULL AND [BranchRef] IN :branches"
            ), params).mappings():
                customers.setdefault(int(r["BranchRef"]), []).append(int(r["DLRef"]))
            cheques = {int(r["BranchRef"]): r for r in connection.execute(text(
                f"""
                SELECT [BranchRef], COUNT(*) AS n, SUM([Price]) AS amount
                FROM dbo.[tblChequeD]
                WHERE [StatusRef] IN ({",".join(str(s) for s in OPEN_CHEQUE_STATUSES)}) AND [BranchRef] IN :branches
                GROUP BY [BranchRef]
                """
            ).bindparams(bindparam("branches", expanding=True)), params).mappings()}

        rows = []
        for bid in branch_ids:
            cur = sales.get((bid, fy["current_id"]), {})
            prev = sales.get((bid, fy["previous_id"]), {})
            rows.append({
                "branch_id": bid,
                "branch_name": names.get(bid, str(bid)),
                "hybrids": hybrids.get(bid, []),
                "active_supervisor_count": supervisors.get(bid, 0),
                "active_visitor_count": visitors.get(bid, 0),
                **_sales_fields(cur, prev),
                "debt": _debt(customers.get(bid, []), positions),
                "open_cheque_count": int((cheques.get(bid) or {}).get("n") or 0),
                "open_cheque_amount_rial": _num((cheques.get(bid) or {}).get("amount")),
            })
        rows.sort(key=lambda r: r["current_year_sales_rial"], reverse=True)
        return {
            "status": "success",
            "current_year_label": fy["current_label"],
            "previous_year_label": fy["previous_label"],
            "branches": rows,
            "summary": {
                "hybrid_count": sum(len(r["hybrids"]) for r in rows),
                "branch_count": len(rows),
                "active_visitor_count": sum(r["active_visitor_count"] for r in rows),
                **{key: _num(sum(r[key] for r in rows)) for key in (
                    "current_year_sales_rial", "current_year_gross_sales_rial",
                    "previous_year_sales_rial", "previous_year_gross_sales_rial")},
                "open_account_receivable_rial": _num(sum(r["debt"]["open_account_receivable_rial"] for r in rows)),
            },
            "debt_note": "بدهی از مانده دفتر کل مشتریان شعبه (شعبه اصلی مشتری) محاسبه شده است.",
        }

    # ------------------------------------------------------------------- files
    def branch_file(self, branch_id: int) -> dict[str, Any]:
        return self._cached(("branch", int(branch_id)), lambda: self._branch_file(int(branch_id)))

    def _fiscal_years_cached(self) -> dict[str, Any]:
        with _file_lock:
            hit = _file_cache.get(("fiscal_years", 0))
            if hit and time.time() - hit[0] < 3600:
                return hit[1]
        with self.engine.connect() as connection:
            fy = self._fiscal_years(connection)
        with _file_lock:
            _file_cache[("fiscal_years", 0)] = (time.time(), fy)
        return fy

    # Every round trip to the Karamad server costs ~0.5s, so each file runs its
    # sections (header, sales/debt, cheques, visitors) concurrently.
    def _branch_file(self, branch_id: int) -> dict[str, Any]:
        fy = self._fiscal_years_cached()
        parts = self._parallel({
            "header": (self._branch_header, (branch_id,)),
            "file": (self._branch_core, (fy, branch_id)),
            "cheques": (self._cheques, ("d.[BranchRef] = :scope_id", branch_id)),
            "visitors": (self._branch_visitors, (fy, branch_id)),
        })
        if parts["header"] is None:
            return {"status": "not_found"}
        return {
            **parts["file"],
            **parts["header"],
            "cheques": parts["cheques"],
            "visitors": parts["visitors"],
            "scope": "branch",
            "branch_id": branch_id,
        }

    def _branch_header(self, connection, branch_id: int) -> dict[str, Any] | None:
        branch = connection.execute(text(
            "SELECT [ID], [Name] FROM dbo.[tblBranch] WHERE [ID] = :bid"), {"bid": branch_id}).mappings().first()
        if not branch:
            return None
        supervisors = [_text(r["Name"]) for r in connection.execute(text(
            f"SELECT s.[Name] FROM dbo.[tblSupervisor] s WHERE s.[BranchRef] = :bid AND s.[Status] = 1 AND NOT {SUPERVISOR_LEFT} ORDER BY s.[Name]"
        ), {"bid": branch_id}).mappings()]
        return {
            "branch_name": _text(branch["Name"]),
            "hybrids": self._hybrids_by_branch(connection, [branch_id]).get(branch_id, []),
            "supervisors": supervisors,
        }

    def _branch_core(self, connection, fy: dict[str, Any], branch_id: int) -> dict[str, Any]:
        dl_refs = [int(r[0]) for r in connection.execute(text(
            "SELECT [DLRef] FROM dbo.[tblCustomer] WHERE [BranchRef] = :bid AND [DLRef] IS NOT NULL"
        ), {"bid": branch_id}).all()]
        return self._file(connection, fy, "f.[BranchRef] = :scope_id", branch_id, dl_refs)

    def visitor_file(self, visitor_id: int) -> dict[str, Any]:
        return self._cached(("visitor", int(visitor_id)), lambda: self._visitor_file(int(visitor_id)))

    def _visitor_file(self, visitor_id: int) -> dict[str, Any]:
        fy = self._fiscal_years_cached()
        parts = self._parallel({
            "header": (self._visitor_header, (visitor_id,)),
            "file": (self._visitor_core, (fy, visitor_id)),
            "cheques": (self._cheques, ("fx.[VisitorRef] = :scope_id", visitor_id)),
        })
        if parts["header"] is None:
            return {"status": "not_found"}
        return {
            **parts["file"],
            **parts["header"],
            "cheques": parts["cheques"],
            "scope": "visitor",
            "visitor_id": visitor_id,
        }

    def _visitor_header(self, connection, visitor_id: int) -> dict[str, Any] | None:
        visitor = connection.execute(text(
            f"""
            SELECT v.[ID], v.[Name], v.[Status], v.[BranchRef], b.[Name] AS BranchName, s.[Name] AS SupervisorName,
                   (SELECT TOP (1) s.[Name] FROM dbo.[tblFactorF] ff
                    INNER JOIN dbo.[tblSupervisor] s ON s.[ID] = ff.[SupervisorRef]
                    WHERE ff.[VisitorRef] = v.[ID] AND NOT {SUPERVISOR_LEFT}
                    ORDER BY ff.[DateE] DESC, ff.[ID] DESC) AS InvoiceSupervisor
            FROM dbo.[tblVisitor] v
            LEFT JOIN dbo.[tblBranch] b ON b.[ID] = v.[BranchRef]
            LEFT JOIN dbo.[tblSupervisor] s ON s.[ID] = v.[SupervisorRef] AND NOT {SUPERVISOR_LEFT}
            WHERE v.[ID] = :vid
            """
        ), {"vid": visitor_id}).mappings().first()
        if not visitor:
            return None
        branch_id = visitor["BranchRef"]
        return {
            "visitor_name": _text(visitor["Name"]),
            "active": bool(visitor["Status"]),
            "branch_id": int(branch_id) if branch_id is not None else None,
            "branch_name": _text(visitor["BranchName"]),
            "supervisor": _text(visitor["SupervisorName"]) or _text(visitor["InvoiceSupervisor"]),
            "hybrids": self._hybrids_by_branch(connection, [int(branch_id)]).get(int(branch_id), []) if branch_id is not None else [],
        }

    @staticmethod
    def _customer_invoices(connection, customer_scope: str, params: dict[str, Any]):
        """Every invoice (all visitors, all years) of the customers in ``customer_scope``
        (a fixed internal SQL fragment), ordered for ``_group_by_customer``."""
        return connection.execute(text(
            f"""
            SELECT cu.[DLRef], f.[VisitorRef], f.[FactorPriceP], f.[DateE]
            FROM dbo.[tblFactorF] f INNER JOIN dbo.[tblCustomer] cu ON cu.[ID] = f.[CustomerRef]
            WHERE cu.[DLRef] IS NOT NULL AND f.[CustomerRef] IN ({customer_scope})
            ORDER BY cu.[DLRef], f.[DateE] DESC, f.[ID] DESC
            """
        ), params).mappings().all()

    @staticmethod
    def _customer_returned_cheques(connection, customer_scope: str, params: dict[str, Any]):
        """Open (not yet settled) returned cheques of the customers in ``customer_scope``."""
        statuses = ",".join(str(s) for s in OPEN_RETURNED_CHEQUE_STATUSES)
        return connection.execute(text(
            f"""
            SELECT d.[DLRef], fx.[VisitorRef], d.[Price], d.[DueDate]
            FROM dbo.[tblChequeD] d LEFT JOIN dbo.[tblFactorF] fx ON fx.[ID] = d.[FactorRef]
            WHERE d.[StatusRef] IN ({statuses})
              AND d.[DLRef] IN (SELECT cu.[DLRef] FROM dbo.[tblCustomer] cu WHERE cu.[ID] IN ({customer_scope}))
            ORDER BY d.[DLRef], d.[DueDate] DESC
            """
        ), params).mappings().all()

    def _visitor_core(self, connection, fy: dict[str, Any], visitor_id: int) -> dict[str, Any]:
        # Debt attribution: returned cheques + FIFO over the invoices of every customer this visitor sold to.
        scope, params = VISITOR_CUSTOMERS, {"sid": visitor_id}
        debt = _visitor_debts(
            self._customer_invoices(connection, scope, params),
            self._customer_returned_cheques(connection, scope, params),
            ledger_positions(),
        ).get(visitor_id, _EMPTY_DEBT)
        return self._file(connection, fy, "f.[VisitorRef] = :scope_id", visitor_id, [], debt=debt)

    def _file(self, connection, fy: dict[str, Any], invoice_scope: str, scope_id: int, dl_refs: list[int],
              debt: dict[str, Any] | None = None) -> dict[str, Any]:
        # invoice_scope (like cheque_scope in _cheques) is a fixed internal SQL fragment, never user input.
        params = {"scope_id": scope_id, "cur": fy["current_id"], "prev": fy["previous_id"]}
        by_year = connection.execute(text(
            f"""
            SELECT f.[FiscalYear], {SALES_COLUMNS},
                   MIN(CASE WHEN f.[is_return] = 0 THEN f.[DateE] END) AS first_date,
                   MAX(CASE WHEN f.[is_return] = 0 THEN f.[DateE] END) AS last_date
            FROM {SALES_SOURCE} f WHERE {invoice_scope} GROUP BY f.[FiscalYear]
            """
        ), params).mappings().all()
        year = {r["FiscalYear"]: r for r in by_year}
        cur, prev = year.get(fy["current_id"], {}), year.get(fy["previous_id"], {})
        stats = {
            "invoice_count": int(sum(r["invoice_count"] or 0 for r in by_year)),
            "sales_amount_rial": _num(sum(float(r["net_amount"] or 0) for r in by_year)),
            "gross_sales_amount_rial": _num(sum(float(r["gross_amount"] or 0) for r in by_year)),
            **_sales_fields(cur, prev),
            "first_invoice_date_jalali": format_jalali_date(min((r["first_date"] for r in by_year if r["first_date"]), default=None)),
            "last_invoice_date_jalali": format_jalali_date(max((r["last_date"] for r in by_year if r["last_date"]), default=None)),
        }

        last = [
            {
                "invoice_id": int(r["ID"]),
                "number": _text(r["Code"]),
                "date": r["DateE"],
                "amount_rial": _num(r["FactorPriceP"]),
                "visitor_name": _text(r["VisitorName"]),
            }
            for r in connection.execute(text(
                f"""
                SELECT TOP ({LAST_INVOICE_COUNT}) f.[ID], f.[Code], f.[DateE], f.[FactorPriceP], v.[Name] AS VisitorName
                FROM dbo.[tblFactorF] f LEFT JOIN dbo.[tblVisitor] v ON v.[ID] = f.[VisitorRef] AND NOT {VISITOR_LEFT}
                WHERE {invoice_scope} AND f.[FiscalYear] = :cur AND f.[FactorPriceP] >= :min_amount
                ORDER BY f.[DateE] DESC, f.[ID] DESC
                """
            ), {**params, "min_amount": MIN_LAST_INVOICE_AMOUNT_RIAL}).mappings()
        ]
        current_unpaid = connection.execute(text(
            f"""
            SELECT COALESCE(SUM(CASE WHEN r.[UnPaid] > 0 THEN r.[UnPaid] END), 0) AS unpaid,
                   SUM(CASE WHEN r.[UnPaid] > 0 THEN 1 ELSE 0 END) AS unpaid_count
            FROM dbo.[tblFactorF] f INNER JOIN dbo.[vwFactorFRemain] r ON r.[ID] = f.[ID]
            WHERE {invoice_scope} AND f.[FiscalYear] = :cur
            """
        ), params).mappings().one()

        return {
            "status": "success",
            "current_year_label": fy["current_label"],
            "previous_year_label": fy["previous_label"],
            "sales_stats": stats,
            "last_invoices": karamad_invoice_settlements(connection, last),
            "debt": {
                **(debt if debt is not None else _debt(dl_refs, ledger_positions())),
                "current_year_unpaid_invoice_rial": _num(current_unpaid["unpaid"]),
                "current_year_unpaid_invoice_count": int(current_unpaid["unpaid_count"] or 0),
            },
        }

    def _branch_visitors(self, connection, fy: dict[str, Any], branch_id: int) -> list[dict[str, Any]]:
        params = {"bid": branch_id, "cur": fy["current_id"], "prev": fy["previous_id"]}
        rows = connection.execute(text(
            f"""
            SELECT v.[ID], v.[Name], v.[Status], s.[Name] AS SupervisorName,
                   SUM(CASE WHEN f.[FiscalYear] = :cur THEN 1 ELSE 0 END) AS cur_count,
                   SUM(CASE WHEN f.[FiscalYear] = :prev THEN 1 ELSE 0 END) AS prev_count,
                   MAX(f.[DateE]) AS last_date,
                   MAX(CASE WHEN f.[DateE] = lastf.[DateE] THEN f.[SupervisorRef] END) AS last_supervisor_ref
            FROM dbo.[tblVisitor] v
            LEFT JOIN dbo.[tblSupervisor] s ON s.[ID] = v.[SupervisorRef] AND NOT {SUPERVISOR_LEFT}
            LEFT JOIN dbo.[tblFactorF] f ON f.[VisitorRef] = v.[ID] AND f.[FiscalYear] IN (:cur, :prev)
            OUTER APPLY (SELECT MAX(x.[DateE]) AS [DateE] FROM dbo.[tblFactorF] x
                         WHERE x.[VisitorRef] = v.[ID] AND x.[FiscalYear] IN (:cur, :prev)) lastf
            WHERE v.[BranchRef] = :bid AND NOT {VISITOR_LEFT}
            GROUP BY v.[ID], v.[Name], v.[Status], s.[Name]
            """
        ), params).mappings().all()
        sales: dict[tuple[int, Any], Any] = {
            (int(s["VisitorRef"]), s["FiscalYear"]): s for s in connection.execute(text(
                f"""
                SELECT f.[VisitorRef], f.[FiscalYear], {SALES_COLUMNS}
                FROM {SALES_SOURCE} f INNER JOIN dbo.[tblVisitor] v ON v.[ID] = f.[VisitorRef]
                WHERE v.[BranchRef] = :bid AND f.[FiscalYear] IN (:cur, :prev)
                GROUP BY f.[VisitorRef], f.[FiscalYear]
                """
            ), params).mappings()
        }
        sup_ids = sorted({int(r["last_supervisor_ref"]) for r in rows if r["last_supervisor_ref"] is not None and not r["SupervisorName"]})
        sup_names = {
            int(r["ID"]): _text(r["Name"]) for r in connection.execute(text(
                f"SELECT s.[ID], s.[Name] FROM dbo.[tblSupervisor] s WHERE s.[ID] IN :ids AND NOT {SUPERVISOR_LEFT}"
            ).bindparams(bindparam("ids", expanding=True)), {"ids": sup_ids or [-1]}).mappings()
        }
        # Debt per visitor: same attribution as the visitor file, over every customer the branch's visitors sold to.
        scope, scope_params = BRANCH_VISITOR_CUSTOMERS, {"sid": branch_id}
        debts = _visitor_debts(
            self._customer_invoices(connection, scope, scope_params),
            self._customer_returned_cheques(connection, scope, scope_params),
            ledger_positions(),
        )

        result = []
        for r in rows:
            active = bool(r["Status"])
            if not active and not (r["cur_count"] or r["prev_count"]):
                continue  # inactive and silent for two years: not part of the current network
            result.append({
                "visitor_id": int(r["ID"]),
                "visitor_name": _text(r["Name"]),
                "active": active,
                "supervisor": _text(r["SupervisorName"]) or sup_names.get(int(r["last_supervisor_ref"] or -1), ""),
                **_sales_fields(sales.get((int(r["ID"]), fy["current_id"]), {}), sales.get((int(r["ID"]), fy["previous_id"]), {})),
                "last_invoice_date_jalali": format_jalali_date(r["last_date"]),
                "debt": debts.get(int(r["ID"]), _EMPTY_DEBT),
            })
        result.sort(key=lambda x: (x["current_year_sales_rial"], x["previous_year_sales_rial"]), reverse=True)
        return result

    # ------------------------------------------------------------ debt detail
    def debt_detail(self, kind: str, scope_id: int) -> dict[str, Any]:
        """Breakdown of box 1 (مانده بدهی مشتریان): age, origin, visitors and debtor customers."""
        return self._cached((f"debt_{kind}", int(scope_id)), lambda: self._debt_detail(kind, int(scope_id)))

    def _debt_detail(self, kind: str, scope_id: int) -> dict[str, Any]:
        # Same customers as box 1: a branch file shows its main-branch customers, a visitor
        # file shows the visitor's slices of every customer they sold to.
        scope = BRANCH_MAIN_CUSTOMERS if kind == "branch" else VISITOR_CUSTOMERS
        params = {"sid": scope_id}
        positions = ledger_positions()
        from app.services.karamad_customer_account_service import LEDGER_READ_ISOLATION
        with self.engine.connect().execution_options(isolation_level=LEDGER_READ_ISOLATION) as connection:
            customers = {int(r["DLRef"]): r for r in connection.execute(text(
                f"SELECT [DLRef], [Name], [Code] FROM dbo.[tblCustomer] WHERE [DLRef] IS NOT NULL AND [ID] IN ({scope})"
            ), params).mappings()}
            by_invoice, by_returned = _group_by_customer(
                self._customer_invoices(connection, scope, params),
                self._customer_returned_cheques(connection, scope, params))

            today = date.today()
            aging = [["زیر ۳۰ روز", 30], ["۳۱ تا ۹۰ روز", 90], ["۹۱ تا ۱۸۰ روز", 180], ["۱۸۱ تا ۳۶۵ روز", 365], ["بیش از یک سال", None]]
            aging_rows = [{"label": label, "amount_rial": 0.0, "customers": set()} for label, _ in aging]
            origin = {"invoice": 0.0, "returned_cheque": 0.0, "unmatched": 0.0}
            by_visitor: dict[int | None, dict[str, Any]] = {}
            debtors = []
            for dl, row in customers.items():
                balance = float(positions.get(dl, {}).get("balance_rial") or 0)
                if balance <= 0:
                    continue
                slices = _allocate_debt(balance, by_invoice.get(dl, []), by_returned.get(dl, []))
                if kind == "visitor":
                    slices = [s for s in slices if s["visitor_id"] == scope_id]
                if not slices:
                    continue
                for s in slices:
                    origin[s["kind"]] += s["amount"]
                    v = by_visitor.setdefault(s["visitor_id"], {"amount_rial": 0.0, "customers": set()})
                    v["amount_rial"] += s["amount"]
                    v["customers"].add(dl)
                    if s["kind"] == "invoice":
                        age = (today - s["date"]).days if s["date"] else None
                        bucket = next(i for i, (_, limit) in enumerate(aging) if limit is None or (age is not None and age <= limit))
                        aging_rows[bucket]["amount_rial"] += s["amount"]
                        aging_rows[bucket]["customers"].add(dl)
                invoice_dates = [s["date"] for s in slices if s["kind"] == "invoice" and s["date"]]
                visitor_totals: dict[int | None, float] = {}
                for s in slices:
                    visitor_totals[s["visitor_id"]] = visitor_totals.get(s["visitor_id"], 0.0) + s["amount"]
                debtors.append({
                    "dl_ref": dl,
                    "customer_name": _text(row["Name"]),
                    "customer_code": _text(row["Code"]),
                    "debt_rial": _num(sum(s["amount"] for s in slices)),
                    "returned_cheque_rial": _num(sum(s["amount"] for s in slices if s["kind"] == "returned_cheque")),
                    "oldest_unpaid_invoice_date_jalali": format_jalali_date(min(invoice_dates)) if invoice_dates else "",
                    "last_invoice_date_jalali": format_jalali_date(max((d for _, _, d in by_invoice.get(dl, []) if d), default=None)),
                    "_visitors": visitor_totals,
                })

            visitor_ids = sorted(v for v in by_visitor if v is not None)
            names = {int(r["ID"]): _text(r["Name"]) for r in connection.execute(text(
                "SELECT [ID], [Name] FROM dbo.[tblVisitor] WHERE [ID] IN :ids"
            ).bindparams(bindparam("ids", expanding=True)), {"ids": visitor_ids or [-1]}).mappings()}
            last_payment = self._last_payment_dates(connection, scope, params)
            monthly = self._monthly_debt(connection, scope, params, {d["dl_ref"]: d["debt_rial"] for d in debtors}) if kind == "branch" else {}

        visitor_name = lambda vid: names.get(vid, "") if vid is not None else "نامشخص"  # noqa: E731
        debtors.sort(key=lambda d: d["debt_rial"], reverse=True)
        month_totals: dict[int, float] = {}
        for d in debtors:
            d["visitors"] = [{"visitor_name": visitor_name(vid), "amount_rial": _num(amount)}
                             for vid, amount in sorted(d.pop("_visitors").items(), key=lambda x: -x[1])]
            d["last_payment_date_jalali"] = format_jalali_date(last_payment.get(d["dl_ref"]))
            if kind == "branch":
                months = monthly.get(d["dl_ref"], {})
                d["months"] = {str(m): _num(v) for m, v in months.items()}
                for m, v in months.items():
                    month_totals[m] = month_totals.get(m, 0.0) + v
        return {
            "status": "success",
            "scope": kind,
            "total_debt_rial": _num(sum(d["debt_rial"] for d in debtors)),
            "debtor_customer_count": len(debtors),
            "aging": [{"label": r["label"], "amount_rial": _num(r["amount_rial"]), "customer_count": len(r["customers"])} for r in aging_rows],
            "origin": {key: _num(value) for key, value in origin.items()},
            "visitors": sorted(
                ({"visitor_name": visitor_name(vid), "amount_rial": _num(v["amount_rial"]), "customer_count": len(v["customers"])}
                 for vid, v in by_visitor.items()),
                key=lambda x: -x["amount_rial"]),
            "customers": debtors,
            # Branch only: debt aged by Jalali month of the ledger debit, like the finance team's
            # «مانده حساب‌های هیبرید مشتریان» report (months present, 1 = فروردین).
            "months": [{"month": m, "label": JALALI_MONTHS[m - 1], "amount_rial": _num(v)} for m, v in sorted(month_totals.items())],
        }

    @staticmethod
    def _monthly_debt(connection, customer_scope: str, params: dict[str, Any], balances: dict[int, float]) -> dict[int, dict[int, float]]:
        """Each customer's debt by Jalali month, the same way the finance report ages it: credits
        settle the oldest debit lines first, so what is still owed sits on the newest debit lines
        (posted + not yet posted ledger), each counted in the month of its date."""
        from app.services.karamad_customer_account_service import _LEDGER_LINES, _RECEIVABLE_SL_CODES
        codes = ", ".join(f"N'{code}'" for code in _RECEIVABLE_SL_CODES)
        dls = f"SELECT cu.[DLRef] FROM dbo.[tblCustomer] cu WHERE cu.[ID] IN ({customer_scope})"
        rows = connection.execute(text(
            f"""
            WITH active_fy AS (
                SELECT TOP (1) [ID] AS FiscalYearRef FROM dbo.[tblFiscalYear]
                WHERE CAST(GETDATE() AS date) BETWEEN [DateStart] AND [DateEnd] ORDER BY [DateStart] DESC
            ),
            ledger AS ({_LEDGER_LINES}),
            debit AS (
                SELECT l.[DateE], l.[Debtor], l.[DLRef], l.[DL2Ref], l.[DL3Ref] FROM ledger l JOIN dbo.[tblSL] sl ON sl.[ID] = l.[SLRef]
                WHERE sl.[Code] IN ({codes}) AND l.[Debtor] > 0
            ),
            by_dl AS (
                SELECT [DLRef] AS dl, [DateE], [Debtor] FROM debit WHERE [DLRef] IN ({dls})
                UNION ALL SELECT [DL2Ref], [DateE], [Debtor] FROM debit WHERE [DL2Ref] IN ({dls})
                UNION ALL SELECT [DL3Ref], [DateE], [Debtor] FROM debit WHERE [DL3Ref] IN ({dls})
            )
            SELECT dl, [DateE], SUM([Debtor]) AS amount FROM by_dl GROUP BY dl, [DateE] ORDER BY dl, [DateE] DESC
            """
        ), params).mappings().all()
        lines: dict[int, list[tuple[Any, float]]] = {}
        for r in rows:
            lines.setdefault(int(r["dl"]), []).append((r["DateE"], float(r["amount"] or 0)))
        result: dict[int, dict[int, float]] = {}
        for dl, balance in balances.items():
            remaining, months = float(balance), {}
            for when, amount in lines.get(dl, []):  # newest first
                if remaining <= 0:
                    break
                share = min(remaining, amount)
                remaining -= share
                jalali = format_jalali_date(when)
                month = int(jalali[5:7]) if jalali and len(jalali) >= 7 else 1
                months[month] = months.get(month, 0.0) + share
            if remaining > 0:
                months[1] = months.get(1, 0.0) + remaining
            result[dl] = months
        return result

    @staticmethod
    def _last_payment_dates(connection, customer_scope: str, params: dict[str, Any]) -> dict[int, Any]:
        """Latest date each customer's receivable account was credited this fiscal year (a payment,
        cheque or return), from the same ledger lines box 1 reads (posted + not yet posted)."""
        from app.services.karamad_customer_account_service import _LEDGER_LINES, _RECEIVABLE_SL_CODES
        codes = ", ".join(f"N'{code}'" for code in _RECEIVABLE_SL_CODES)
        dls = f"SELECT cu.[DLRef] FROM dbo.[tblCustomer] cu WHERE cu.[ID] IN ({customer_scope})"
        rows = connection.execute(text(
            f"""
            WITH active_fy AS (
                SELECT TOP (1) [ID] AS FiscalYearRef FROM dbo.[tblFiscalYear]
                WHERE CAST(GETDATE() AS date) BETWEEN [DateStart] AND [DateEnd] ORDER BY [DateStart] DESC
            ),
            ledger AS ({_LEDGER_LINES}),
            credit AS (
                SELECT l.[DateE], l.[DLRef], l.[DL2Ref], l.[DL3Ref] FROM ledger l JOIN dbo.[tblSL] sl ON sl.[ID] = l.[SLRef]
                WHERE sl.[Code] IN ({codes}) AND l.[Creditor] > 0
            ),
            by_dl AS (
                SELECT [DLRef] AS dl, [DateE] FROM credit WHERE [DLRef] IN ({dls})
                UNION ALL SELECT [DL2Ref], [DateE] FROM credit WHERE [DL2Ref] IN ({dls})
                UNION ALL SELECT [DL3Ref], [DateE] FROM credit WHERE [DL3Ref] IN ({dls})
            )
            SELECT dl, MAX([DateE]) AS last_date FROM by_dl GROUP BY dl
            """
        ), params).mappings().all()
        return {int(r["dl"]): r["last_date"] for r in rows}

    def _cheques(self, connection, cheque_scope: str, scope_id: int) -> dict[str, Any]:
        statuses = ",".join(str(s) for s in OPEN_CHEQUE_STATUSES)
        rows = connection.execute(text(
            f"""
            SELECT d.[inx], d.[Serial], d.[InquiryCode], d.[Price], d.[BookDate], d.[DueDate], d.[DLRef],
                   st.[Name] AS StatusName, COALESCE(bk.[Name], d.[Bank]) AS BankName, v.[Name] AS VisitorName,
                   cu.[Name] AS CustomerName, cu.[Code] AS CustomerCode
            FROM dbo.[tblChequeD] d
            LEFT JOIN dbo.[tblFactorF] fx ON fx.[ID] = d.[FactorRef]
            LEFT JOIN dbo.[tblVisitor] v ON v.[ID] = fx.[VisitorRef] AND NOT {VISITOR_LEFT}
            OUTER APPLY (SELECT TOP (1) c.[Name], c.[Code] FROM dbo.[tblCustomer] c WHERE c.[DLRef] = d.[DLRef] ORDER BY c.[ID]) cu
            OUTER APPLY (SELECT TOP (1) s.[Name] FROM dbo.[tblChequeDStatus] s WHERE s.[Code] = d.[StatusRef]) st
            OUTER APPLY (SELECT TOP (1) b.[Name] FROM dbo.[tblBankList] b WHERE b.[Code] = d.[BankIDRef]) bk
            WHERE d.[StatusRef] IN ({statuses}) AND {cheque_scope}
            ORDER BY d.[DueDate]
            """
        ), {"scope_id": scope_id}).mappings().all()

        today = date.today()
        cheques = []
        for r in rows:
            due = _as_date(r["DueDate"])
            booked = _as_date(r["BookDate"])
            cheques.append({
                "cheque_id": int(r["inx"]),
                "cheque_number": _text(r["Serial"]),
                "sayad_number": _text(r["InquiryCode"]),
                "amount_rial": _num(r["Price"]),
                "registration_date_jalali": format_jalali_date(r["BookDate"]),
                "due_date_jalali": format_jalali_date(due),
                "days_until_due": (due - today).days if due else None,
                "receipt_to_due_days": (due - booked).days if due and booked else None,
                "cheque_status": _text(r["StatusName"]),
                "bank": _text(r["BankName"]),
                "visitor_name": _text(r["VisitorName"]),
                "customer_name": _text(r["CustomerName"]),
                "customer_code": _text(r["CustomerCode"]),
                "_dl_ref": r["DLRef"],
            })

        # Bounce base rate per customer from their full history (the open list has no collected cheques).
        dl_refs = sorted({int(c["_dl_ref"]) for c in cheques if c["_dl_ref"] is not None})
        history: dict[int, dict[str, Any]] = {}
        if dl_refs:
            returned = ",".join(str(s) for s in RETURNED_CHEQUE_STATUSES)
            for h in connection.execute(text(
                f"""
                SELECT d.[DLRef],
                       SUM(CASE WHEN d.[StatusRef] = {COLLECTED_CHEQUE_STATUS} THEN 1 ELSE 0 END) AS collected_count,
                       SUM(CASE WHEN d.[StatusRef] IN ({returned}) THEN 1 ELSE 0 END) AS returned_count,
                       AVG(CASE WHEN d.[StatusRef] IN ({COLLECTED_CHEQUE_STATUS},{returned}) THEN d.[Price] END) AS average_amount_rial
                FROM dbo.[tblChequeD] d WHERE d.[DLRef] IN :dls GROUP BY d.[DLRef]
                """
            ).bindparams(bindparam("dls", expanding=True)), {"dls": dl_refs}).mappings():
                history[int(h["DLRef"])] = {
                    "collected_count": int(h["collected_count"] or 0),
                    "returned_count": int(h["returned_count"] or 0),
                    "average_amount_rial": float(h["average_amount_rial"] or 0),
                }
        groups: dict[Any, list[dict[str, Any]]] = {}
        for c in cheques:
            groups.setdefault(c["_dl_ref"], []).append(c)
        for dl, group in groups.items():
            attach_return_risk(group, history.get(int(dl)) if dl is not None else None)
        for c in cheques:
            c.pop("_dl_ref", None)  # never expose which customer a cheque belongs to

        def bucket(pred) -> dict[str, Any]:
            items = [c for c in cheques if pred(c.get("return_risk") or {})]
            return {"count": len(items), "amount_rial": _num(sum(c["amount_rial"] for c in items))}

        return {
            "rows": cheques,
            "summary": {
                "open": bucket(lambda r: r.get("state") == "open"),
                "high": bucket(lambda r: r.get("level") == "high"),
                "medium": bucket(lambda r: r.get("level") == "medium"),
                "low": bucket(lambda r: r.get("level") == "low"),
                "returned": bucket(lambda r: r.get("state") == "returned"),
            },
        }


def warm_up() -> None:
    """Fill the ledger and overview caches in the background at startup, so the first
    person opening «هیبرید من‌ها» does not wait ~20s for the cold ledger query."""
    def run():
        try:
            KaramadSalesNetworkService().overview()
        except Exception:
            pass  # Karamad server unreachable at startup: the page loads it on demand.
    threading.Thread(target=run, name="karamad-sales-network-warmup", daemon=True).start()
