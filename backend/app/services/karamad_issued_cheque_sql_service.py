from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.services.karamad_received_cheque_sql_service import get_karamad_sql_engine
from app.utils.jalali import format_jalali_date


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value else None


def _jalali(value: Any) -> str | None:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            return format_jalali_date(value.date())
        if isinstance(value, date):
            return format_jalali_date(value)
    except Exception:
        pass
    return None


class KaramadIssuedChequeSQLService:
    """Authoritative live Karamad issued-cheque source.

    The management portfolio contains only cheques whose FINAL status is
    ``LastStatusRef = 2`` (عادی). Historical/status rows that ended in
    ``LastStatusRef = 3`` (وصول شده) are excluded at SQL level.
    """

    BASE_QUERY = text("""
        SELECT
            [Code], [ChequeRef], [DueDate], [BookDate], [Price], [Behalf],
            [Description], [BranchName], [BankName], [BankRef],
            [DLRef], [DLCode], [DLName], [SLCode], [SLName],
            [StatusName], [StatusRef], [LastStatusRef], [DStatusName],
            [VoucherCode], [VoucherDateE], [FiscalYear], [FiscalYearLines],
            [isSent], [ReceiptDate], [BranchRef], [DL2Name], [DL3Name],
            [inx]
        FROM dbo.[vwChequePLinesFull]
        WHERE [LastStatusRef] = 2
    """)

    def fetch_all(self) -> list[dict[str, Any]]:
        with get_karamad_sql_engine().connect() as conn:
            rows = conn.execute(self.BASE_QUERY).mappings().all()
        today = date.today()
        result: list[dict[str, Any]] = []
        for row in rows:
            due = row.get("DueDate")
            due_date = due.date() if isinstance(due, datetime) else due if isinstance(due, date) else None
            days = (due_date - today).days if due_date else None
            result.append({
                "cheque_id": f"karamad:issued:{row.get('ChequeRef')}",
                "document_id": row.get("ChequeRef"),
                "document_number": row.get("Code"),
                "document_date": _date(row.get("VoucherDateE")),
                "document_date_jalali": _jalali(row.get("VoucherDateE")),
                "registration_date": _date(row.get("BookDate")),
                "registration_date_jalali": _jalali(row.get("BookDate")),
                "due_date": _date(row.get("DueDate")),
                "due_date_jalali": _jalali(row.get("DueDate")),
                "days_until_due": days,
                "days_to_due": days,
                "amount": _num(row.get("Price")),
                "amount_rial": _num(row.get("Price")),
                "serial_number": row.get("inx"),
                "series": None,
                "sayad_number": None,
                "account_number": None,
                "bank_ref": row.get("BankRef"),
                "bank_name": row.get("BankName"),
                "bank_branch_name": row.get("BankName"),
                "bank_branch_code": None,
                "counterpart_ref": row.get("DLRef"),
                "counterpart_code": row.get("DLCode"),
                "counterpart_name": row.get("DLName") or row.get("DL2Name") or row.get("DL3Name") or row.get("Behalf"),
                "description": row.get("Description") or row.get("Behalf"),
                "behalf": row.get("Behalf"),
                "cheque_status": row.get("LastStatusRef"),
                "state_code": row.get("LastStatusRef"),
                "state": row.get("DStatusName") or row.get("StatusName") or "عادی",
                "state_label": row.get("DStatusName") or row.get("StatusName") or "عادی",
                "final_status_ref": row.get("LastStatusRef"),
                "final_status_name": row.get("DStatusName") or row.get("StatusName"),
                "source_status_ref": row.get("StatusRef"),
                "branch": row.get("BranchName"),
                "branch_name": row.get("BranchName"),
                "branch_ref": row.get("BranchRef"),
                "receipt_date": _date(row.get("ReceiptDate")),
                "receipt_date_jalali": _jalali(row.get("ReceiptDate")),
                "source_system": "karamad",
                "source_label": "کارآمد",
                "source": "karamad_sql",
                "source_kind": "issued_cheques",
                "source_kinds": ["issued_cheques"],
            })
        result.sort(key=lambda item: (item.get("due_date") or "9999-12-31", str(item.get("document_id") or "")))
        return result


def get_karamad_issued_cheques() -> list[dict[str, Any]]:
    return KaramadIssuedChequeSQLService().fetch_all()
