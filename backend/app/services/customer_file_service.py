"""پرونده مشتری: آمار فاکتور خرید، ۵ فاکتور آخر سال جاری و شبکه فروش (ویزیتور).

راهکاران (SLS3.Invoice):
- فقط فاکتورهای قطعی (Status = 11) شمرده می‌شوند؛ پیش‌نویس‌ها (Status 1/2)
  جداگانه گزارش می‌شوند.
- راهکاران تسویه به‌ازای هر فاکتور ندارد؛ مانده هر فاکتور با تخصیص مانده
  فعلی حساب مشتری به جدیدترین فاکتورها (FIFO) برآورد و صریحاً اعلام می‌شود.
- ویزیتور در راهکاران ثبت نمی‌شود (BrokerRef/AgentRef همه خالی‌اند).

کارآمد (dbo.tblFactorF):
- مشتری از tblCustomer.DLRef به همان تفصیلی‌های پرونده وصل می‌شود.
- مانده هر فاکتور از vwFactorFRemain.UnPaid و ریز وصول از vwFactorFPayoff.
- هر فاکتور ویزیتور و سرپرست خود را دارد؛ «هیبرید من» هر شعبه از
  tblDL با کلاس «هیبرید من ها» (tblDLClass.ID = 28) خوانده می‌شود.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import bindparam, text

from app.utils.jalali import format_jalali_date

RAHKARAN_FINAL_INVOICE_STATUS = 11
KARAMAD_HYBRID_DL_CLASS_ID = 28
LAST_INVOICE_COUNT = 5
# Placeholder invoices (0 or 1 rial, bonus-only) say nothing about debt or collection.
MIN_LAST_INVOICE_AMOUNT_RIAL = 10_000

KARAMAD_PAYOFF_LABELS = {
    "CashN": "نقد",
    "CashE": "کارت‌خوان",
    "CashT": "سایر نقدی",
    "Draft": "حواله",
    "Cheque": "چک",
    "FactorB": "مرجوعی",
    "SharedFactor": "تسویه اشتراکی",
    "SharedCustomerDebt": "تسویه اشتراکی",
    "SharedReturnCheque": "تسویه چک برگشتی",
    "SharedReturn": "تسویه اشتراکی",
    "Barter": "تهاتر",
}


def _num(value: Any) -> float:
    return round(float(value or 0), 2)


def _date_iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()


def _jalali_year(value: Any) -> str:
    formatted = format_jalali_date(value) or ""
    return formatted[:4]


def _stats(rows: list[dict[str, Any]], current_fy: Any, previous_fy: Any) -> dict[str, Any]:
    def pick(fy: Any) -> list[dict[str, Any]]:
        return [r for r in rows if r["fiscal_year"] == fy]

    current, previous = pick(current_fy), pick(previous_fy)
    return {
        "invoice_count": len(rows),
        "purchase_amount_rial": _num(sum(r["amount_rial"] for r in rows)),
        "current_year_invoice_count": len(current),
        "current_year_amount_rial": _num(sum(r["amount_rial"] for r in current)),
        "previous_year_invoice_count": len(previous),
        "previous_year_amount_rial": _num(sum(r["amount_rial"] for r in previous)),
        "first_invoice_date_jalali": format_jalali_date(min((r["date"] for r in rows), default=None)),
        "last_invoice_date_jalali": format_jalali_date(max((r["date"] for r in rows), default=None)),
    }


def karamad_invoice_settlements(connection, last: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remaining debt and collection breakdown per Karamad invoice (keeps extra keys such as visitor_name)."""
    if not last:
        return []
    ids = [r["invoice_id"] for r in last]
    payoff_columns = ", ".join(f"p.[{c}]" for c in KARAMAD_PAYOFF_LABELS)
    settlement = connection.execute(text(
        f"""
        SELECT r.[ID], r.[Paid], r.[UnPaid], {payoff_columns}
        FROM dbo.[vwFactorFRemain] r
        LEFT JOIN dbo.[vwFactorFPayoff] p ON p.[ID] = r.[ID]
        WHERE r.[ID] IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
    by_id = {int(s["ID"]): s for s in settlement}

    result = []
    for invoice in last:
        s = by_id.get(invoice["invoice_id"], {})
        breakdown: dict[str, float] = {}
        for column, label in KARAMAD_PAYOFF_LABELS.items():
            value = _num(s.get(column))
            if value > 0:
                breakdown[label] = _num(breakdown.get(label, 0) + value)
        amount = invoice["amount_rial"]
        remaining = max(_num(s.get("UnPaid")), 0.0) if s else None
        collected = None if remaining is None else _num(max(amount - remaining, 0.0))
        # vwFactorFPayoff reports each instrument's full amount even when one cheque
        # settled several invoices; show each method's share of this invoice instead.
        instrument_total = sum(breakdown.values())
        if collected is not None and instrument_total > collected > 0:
            breakdown = {k: _num(v * collected / instrument_total) for k, v in breakdown.items()}
        result.append({
            **{k: invoice[k] for k in ("visitor_name",) if k in invoice},
            "invoice_id": invoice["invoice_id"],
            "number": invoice["number"],
            "date": _date_iso(invoice["date"]),
            "date_jalali": format_jalali_date(invoice["date"]),
            "amount_rial": amount,
            "remaining_rial": remaining,
            "collected_rial": collected,
            "collected_percent": None if collected is None or not amount else round(min(collected / amount, 1) * 100, 1),
            "collection_breakdown": [{"method": k, "amount_rial": v} for k, v in breakdown.items()],
        })
    return result


class CustomerFileService:
    def __init__(self, rahkaran_engine=None, karamad_engine=None):
        self._rahkaran_engine = rahkaran_engine
        self._karamad_engine = karamad_engine

    @property
    def rahkaran_engine(self):
        if self._rahkaran_engine is None:
            from app.database.sqlserver import get_sqlserver_engine
            self._rahkaran_engine = get_sqlserver_engine()
        return self._rahkaran_engine

    @property
    def karamad_engine(self):
        if self._karamad_engine is None:
            from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
            self._karamad_engine = get_karamad_sqlserver_engine()
        return self._karamad_engine

    # ------------------------------------------------------------------ Rahkaran
    def rahkaran(self, counterpart_ref: int) -> dict[str, Any]:
        with self.rahkaran_engine.connect() as connection:
            fiscal_years = connection.execute(text(
                """
                SELECT [FiscalYearRef], [StartDate], [EndDate]
                FROM GNR3.[LedgerFiscalYear]
                WHERE [LedgerRef] = 1
                ORDER BY [StartDate] DESC
                """
            )).mappings().all()
            invoices = connection.execute(text(
                """
                SELECT i.[InvoiceID], i.[Number], i.[Date], i.[NetPrice], i.[Status], i.[FiscalYearRef]
                FROM FIN3.[DL] dl
                INNER JOIN SLS3.[Customer] c ON c.[PartyRef] = dl.[ReferenceID]
                INNER JOIN SLS3.[Invoice] i ON i.[CustomerRef] = c.[CustomerID]
                WHERE dl.[DLID] = :counterpart_ref
                ORDER BY i.[Date] DESC, i.[InvoiceID] DESC
                """
            ), {"counterpart_ref": int(counterpart_ref)}).mappings().all()

        today = date.today()
        current = next((fy for fy in fiscal_years if fy["StartDate"].date() <= today <= fy["EndDate"].date()), None)
        previous = next((fy for fy in fiscal_years if current and fy["EndDate"] < current["StartDate"]), None)
        current_ref = current["FiscalYearRef"] if current else None
        previous_ref = previous["FiscalYearRef"] if previous else None

        final = [
            {
                "invoice_id": int(r["InvoiceID"]),
                "number": str(r["Number"] or ""),
                "date": r["Date"],
                "amount_rial": _num(r["NetPrice"]),
                "fiscal_year": r["FiscalYearRef"],
            }
            for r in invoices
            if r["Status"] == RAHKARAN_FINAL_INVOICE_STATUS
        ]

        # FIFO: the customer's current open balance belongs to the newest invoices.
        from app.services.finance_prediction_service import FinancePredictionService
        try:
            account = FinancePredictionService(engine=self.rahkaran_engine).customer_account_position(counterpart_ref)
        except Exception:
            account = {"found": False}
        open_balance = float(account.get("open_account_receivable_rial") or 0) if account.get("found") else None

        last_invoices = []
        remaining_balance = open_balance
        for invoice in final:
            if invoice["fiscal_year"] != current_ref or invoice["amount_rial"] < MIN_LAST_INVOICE_AMOUNT_RIAL:
                continue
            remaining = None
            if remaining_balance is not None:
                remaining = min(invoice["amount_rial"], max(remaining_balance, 0.0))
                remaining_balance -= remaining
            collected = None if remaining is None else invoice["amount_rial"] - remaining
            last_invoices.append({
                "invoice_id": invoice["invoice_id"],
                "number": invoice["number"],
                "date": _date_iso(invoice["date"]),
                "date_jalali": format_jalali_date(invoice["date"]),
                "amount_rial": invoice["amount_rial"],
                "remaining_rial": None if remaining is None else _num(remaining),
                "collected_rial": None if collected is None else _num(collected),
                "collected_percent": None if collected is None or not invoice["amount_rial"] else round(collected / invoice["amount_rial"] * 100, 1),
                "collection_breakdown": [],
            })
            if len(last_invoices) == LAST_INVOICE_COUNT:
                break

        # Every invoice (any year) still carrying part of the balance under the same FIFO rule,
        # newest first; the UI flags the old ones.
        open_invoices = []
        remaining_balance = open_balance
        for invoice in final:
            if remaining_balance is None or remaining_balance <= 0:
                break
            if invoice["amount_rial"] < MIN_LAST_INVOICE_AMOUNT_RIAL:
                continue
            remaining = min(invoice["amount_rial"], remaining_balance)
            remaining_balance -= remaining
            issued = invoice["date"].date() if isinstance(invoice["date"], datetime) else invoice["date"]
            open_invoices.append({
                "invoice_id": invoice["invoice_id"],
                "number": invoice["number"],
                "date_jalali": format_jalali_date(invoice["date"]),
                "age_days": (today - issued).days if issued else None,
                "amount_rial": invoice["amount_rial"],
                "remaining_rial": _num(remaining),
            })

        return {
            "open_invoices": open_invoices,
            "status": "success",
            "source": "rahkaran",
            "counterpart_ref": int(counterpart_ref),
            "current_year_label": _jalali_year(current["StartDate"]) if current else "",
            "previous_year_label": _jalali_year(previous["StartDate"]) if previous else "",
            "purchase_stats": {
                **_stats(final, current_ref, previous_ref),
                "draft_invoice_count": sum(1 for r in invoices if r["Status"] != RAHKARAN_FINAL_INVOICE_STATUS),
            },
            "last_invoices": last_invoices,
            "remaining_method": "fifo_allocation_of_account_balance" if open_balance is not None else "unavailable",
            "remaining_note": (
                "راهکاران تسویه جداگانه برای هر فاکتور ندارد؛ مانده فعلی حساب مشتری "
                "به ترتیب به جدیدترین فاکتورها تخصیص داده شده (FIFO)."
            ),
            "sales_network": {
                "available": False,
                "note": "در راهکاران ویزیتور روی فاکتور ثبت نمی‌شود؛ شبکه فروش فقط برای مشتریان کارآمد نمایش داده می‌شود.",
                "visitors": [],
            },
        }

    # ------------------------------------------------------------------- Karamad
    def karamad(self, dl_refs: list[int]) -> dict[str, Any]:
        dl_refs = sorted({int(x) for x in dl_refs})
        if not dl_refs:
            return {"status": "success", "source": "karamad", "found": False, "dl_refs": []}

        with self.karamad_engine.connect() as connection:
            fiscal_years = connection.execute(text(
                "SELECT [ID], [Name], [DateStart], [DateEnd] FROM dbo.[tblFiscalYear] ORDER BY [DateStart] DESC"
            )).mappings().all()
            invoices = connection.execute(text(
                """
                SELECT f.[ID], f.[Code], f.[DateE], f.[FiscalYear], f.[FactorPriceP],
                       f.[VisitorRef], f.[SupervisorRef], f.[BranchRef]
                FROM dbo.[tblFactorF] f
                INNER JOIN dbo.[tblCustomer] cu ON cu.[ID] = f.[CustomerRef]
                WHERE cu.[DLRef] IN :dl_refs
                ORDER BY f.[DateE] DESC, f.[ID] DESC
                """
            ).bindparams(bindparam("dl_refs", expanding=True)), {"dl_refs": dl_refs}).mappings().all()

            today = date.today()
            current = next((fy for fy in fiscal_years if fy["DateStart"] <= today <= fy["DateEnd"]), None)
            previous = next((fy for fy in fiscal_years if current and fy["DateEnd"] < current["DateStart"]), None)
            current_id = current["ID"] if current else None
            previous_id = previous["ID"] if previous else None

            rows = [
                {
                    "invoice_id": int(r["ID"]),
                    "number": str(r["Code"] or ""),  # tblFactorF.FactorNo is always empty
                    "date": r["DateE"],
                    "amount_rial": _num(r["FactorPriceP"]),
                    "fiscal_year": r["FiscalYear"],
                    "visitor_ref": r["VisitorRef"],
                    "supervisor_ref": r["SupervisorRef"],
                    "branch_ref": r["BranchRef"],
                }
                for r in invoices
            ]
            last = [r for r in rows if r["fiscal_year"] == current_id and r["amount_rial"] >= MIN_LAST_INVOICE_AMOUNT_RIAL][:LAST_INVOICE_COUNT]
            last_invoices = karamad_invoice_settlements(connection, last)
            network = self._karamad_sales_network(connection, rows, current_id, previous_id)

        # Same FIFO rule as Rahkaran: the customer's ledger balance (posted + not yet posted)
        # belongs to the newest invoices, so an old invoice is open only if the balance reaches it.
        from app.services.karamad_sales_network_service import ledger_positions
        positions = ledger_positions()
        remaining_balance = sum(float(positions.get(d, {}).get("balance_rial") or 0) for d in dl_refs)
        open_invoices = []
        for invoice in rows:
            if remaining_balance <= 0:
                break
            if invoice["amount_rial"] < MIN_LAST_INVOICE_AMOUNT_RIAL:
                continue
            remaining = min(invoice["amount_rial"], remaining_balance)
            remaining_balance -= remaining
            issued = invoice["date"].date() if isinstance(invoice["date"], datetime) else invoice["date"]
            open_invoices.append({
                "invoice_id": invoice["invoice_id"],
                "number": invoice["number"],
                "date_jalali": format_jalali_date(invoice["date"]),
                "age_days": (today - issued).days if issued else None,
                "amount_rial": invoice["amount_rial"],
                "remaining_rial": _num(remaining),
            })

        return {
            "status": "success",
            "source": "karamad",
            "open_invoices": open_invoices,
            "found": bool(rows),
            "dl_refs": dl_refs,
            "current_year_label": str(current["Name"]) if current else "",
            "previous_year_label": str(previous["Name"]) if previous else "",
            "purchase_stats": _stats(rows, current_id, previous_id),
            "last_invoices": last_invoices,
            "remaining_method": "karamad_invoice_settlement",
            "remaining_note": "مانده و ریز وصول هر فاکتور مستقیم از تسویه فاکتور در کارآمد (vwFactorFRemain / vwFactorFPayoff) خوانده شده است؛ اگر یک چک چند فاکتور را تسویه کرده باشد، سهم همین فاکتور نمایش داده می‌شود.",
            "sales_network": network,
        }

    def _karamad_sales_network(self, connection, rows: list[dict[str, Any]], current_id: Any, previous_id: Any) -> dict[str, Any]:
        visitor_ids = sorted({int(r["visitor_ref"]) for r in rows if r["visitor_ref"] is not None})
        if not visitor_ids:
            return {"available": True, "note": "برای این مشتری فاکتوری با ویزیتور ثبت نشده است.", "visitors": []}

        visitors = connection.execute(text(
            """
            SELECT v.[ID], v.[Name], v.[Status], v.[BranchRef], b.[Name] AS [BranchName],
                   s.[ID] AS [SupervisorID], s.[Name] AS [SupervisorName]
            FROM dbo.[tblVisitor] v
            LEFT JOIN dbo.[tblBranch] b ON b.[ID] = v.[BranchRef]
            LEFT JOIN dbo.[tblSupervisor] s ON s.[ID] = v.[SupervisorRef]
            WHERE v.[ID] IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True)), {"ids": visitor_ids}).mappings().all()
        sales = connection.execute(text(
            """
            SELECT f.[VisitorRef], f.[FiscalYear], COUNT_BIG(*) AS [InvoiceCount], SUM(f.[FactorPriceP]) AS [Amount]
            FROM dbo.[tblFactorF] f
            WHERE f.[VisitorRef] IN :ids AND f.[FiscalYear] IN :years
            GROUP BY f.[VisitorRef], f.[FiscalYear]
            """
        ).bindparams(bindparam("ids", expanding=True), bindparam("years", expanding=True)),
            {"ids": visitor_ids, "years": [y for y in (current_id, previous_id) if y is not None] or [-1]},
        ).mappings().all()
        # Some visitors have no SupervisorRef; fall back to the supervisor recorded on their latest invoice.
        invoice_supervisor = {}
        for r in rows:  # rows are newest-first
            if r["visitor_ref"] is not None and r["supervisor_ref"] is not None:
                invoice_supervisor.setdefault(int(r["visitor_ref"]), int(r["supervisor_ref"]))
        supervisor_names = {
            int(s["ID"]): str(s["Name"] or "").strip()
            for s in connection.execute(text(
                "SELECT [ID], [Name] FROM dbo.[tblSupervisor] WHERE [ID] IN :ids"
            ).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(set(invoice_supervisor.values())) or [-1]}).mappings()
        }
        branch_ids = sorted({int(v["BranchRef"]) for v in visitors if v["BranchRef"] is not None})
        hybrids = connection.execute(text(
            """
            SELECT dl.[BranchRef], dl.[Name]
            FROM dbo.[tblDL] dl
            WHERE dl.[ClassRef] = :hybrid_class AND dl.[BranchRef] IN :branches
            ORDER BY dl.[Name]
            """
        ).bindparams(bindparam("branches", expanding=True)),
            {"hybrid_class": KARAMAD_HYBRID_DL_CLASS_ID, "branches": branch_ids or [-1]},
        ).mappings().all()

        hybrids_by_branch: dict[int, list[str]] = {}
        for h in hybrids:
            hybrids_by_branch.setdefault(int(h["BranchRef"]), []).append(str(h["Name"] or "").strip())
        sales_by: dict[tuple[int, Any], dict[str, Any]] = {(int(s["VisitorRef"]), s["FiscalYear"]): s for s in sales}

        result = []
        for v in visitors:
            vid = int(v["ID"])
            own = [r for r in rows if r["visitor_ref"] == vid]

            def own_sum(fy: Any) -> float:
                return _num(sum(r["amount_rial"] for r in own if r["fiscal_year"] == fy))

            current_sales = sales_by.get((vid, current_id), {})
            previous_sales = sales_by.get((vid, previous_id), {})
            result.append({
                "visitor_id": vid,
                "visitor_name": str(v["Name"] or "").strip(),
                "active": bool(v["Status"]),
                "branch": str(v["BranchName"] or "").strip(),
                "supervisor": str(v["SupervisorName"] or "").strip() or supervisor_names.get(invoice_supervisor.get(vid, -1), ""),
                "hybrids": hybrids_by_branch.get(int(v["BranchRef"]), []) if v["BranchRef"] is not None else [],
                "last_invoice_date_jalali": format_jalali_date(max((r["date"] for r in own), default=None)),
                "customer_invoice_count": len(own),
                "customer_sales_current_year_rial": own_sum(current_id),
                "customer_sales_previous_year_rial": own_sum(previous_id),
                "visitor_sales_current_year_rial": _num(current_sales.get("Amount")),
                "visitor_invoice_count_current_year": int(current_sales.get("InvoiceCount") or 0),
                "visitor_sales_previous_year_rial": _num(previous_sales.get("Amount")),
                "visitor_invoice_count_previous_year": int(previous_sales.get("InvoiceCount") or 0),
            })
        # The visitor who sold to the customer most recently comes first.
        result.sort(key=lambda x: x["last_invoice_date_jalali"] or "", reverse=True)
        return {"available": True, "note": "", "visitors": result}
