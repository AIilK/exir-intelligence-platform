from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any
import unicodedata

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.database.sqlserver import get_sqlserver_engine
from app.services.received_cheque_current_status import (
    current_received_holding_label,
    current_received_state_expr,
    current_received_status_apply,
    received_cheque_open_expression,
    received_cheque_open_predicate,
    received_cheque_is_approved_open_holding,
)
from app.services.treasury_common import (  # noqa: F401 — moved to treasury_common.py, re-exported for existing imports
    _as_datetime,
    _as_jalali_date,
    _as_number,
    _engine,
)
from app.services.treasury_diagnostics import (  # noqa: F401 — moved to treasury_diagnostics.py, re-exported for existing imports
    analyze_received_cheque_official_discrepancies,
    compare_received_open_sql_with_rahkaran_excel,
    trace_received_cheque_mapping,
)
from app.services.treasury_accounts import (  # noqa: F401 — moved to treasury_accounts.py, re-exported for existing imports
    _PERSIAN_SEARCH_TRANSLATION,
    _account_payload,
    _currency_name,
    _get_account_by_id,
    _normalize_account_search,
    _resolve_account,
    get_account_transactions,
    search_accounts,
)
from app.services.treasury_cheque_settlement import (  # noqa: F401 — moved to treasury_cheque_settlement.py, re-exported for existing imports
    _build_customer_cheque_settlement_payload,
    _cheque_state_label,
    _owner_name_matches_debtor,
    _settlement_remaining,
    get_customer_cheque_settlement,
)
from app.services.treasury_company_payments import (  # noqa: F401 — moved to treasury_company_payments.py, re-exported for existing imports
    _KARAMAD_BANK_NAMES,
    _KARAMAD_FEE_TOKENS,
    _company_payment_response,
    _karamad_payment_category,
    _payment_order_category,
    get_company_payment_orders,
    get_company_payment_orders_karamad,
)


DURATION_CHANGE_STATUS_PREFIX = "تغییر مدت به روز"
# FIN3.DL «سهامداران»: cheques moving money between the shareholders and the company.
# Their text often says «جاری شرکا» rather than «سهامدار», so match the counterpart too.
SHAREHOLDERS_DL_CODE = "950031"


def _issued_status_link_apply(note_alias: str) -> str:
    """OUTER APPLY ``status_link``: the approved document that posted an issued cheque.

    Rahkaran posts a paid issued cheque in one of two ways while PayableNote.State stays 11:
    - a PayableNoteTransaction whose line text says «تعیین وضعیت چک / وصول چک / ...»;
    - an approved «DurationChange» document (long-term to current, credited to
      «موجودی نزد بانکها»). Its text («وصول چک», «کارمزد بانکی», ...) is on the header
      only and the transaction line is blank, so the keyword check alone missed ~6,000
      paid cheques. Same rule as liquidity/issued_cheques.py.
    """

    return f"""
        OUTER APPLY (
            SELECT TOP (1)
                posting.[StatusDocumentID], posting.[StatusDocumentNumber],
                posting.[StatusDocumentDate], posting.[StatusDocumentDescription]
            FROM (
                SELECT
                    pnt.[DocumentRef] AS [StatusDocumentID],
                    pnt.[DocumentNumber] AS [StatusDocumentNumber],
                    COALESCE(pnt.[DocumentDate], pnt.[Date]) AS [StatusDocumentDate],
                    pnt.[Description] AS [StatusDocumentDescription]
                FROM RPA3.[PayableNoteTransaction] AS pnt
                WHERE pnt.[PayableNoteRef] = {note_alias}.[PayableNoteID]
                  AND pnt.[State] = 11
                  AND pnt.[DocumentItemType] IN (24, 26)
                  AND pnt.[DocumentState] = 3
                  AND (
                        ISNULL(pnt.[Description], N'') LIKE N'%تعیین وضعیت چک%'
                     OR ISNULL(pnt.[Description], N'') LIKE N'%تعین وضعیت چک%'
                     OR ISNULL(pnt.[Description], N'') LIKE N'%وصول چ%'
                     OR ISNULL(pnt.[Description], N'') LIKE N'%پرداخت چک%'
                     OR ISNULL(pnt.[Description], N'') LIKE N'%برداشت وجه چک%'
                  )
                UNION ALL
                SELECT
                    dc.[DurationChangeID],
                    dc.[Number],
                    dc.[Date],
                    N'{DURATION_CHANGE_STATUS_PREFIX}'
                        + CASE WHEN ISNULL(dc.[Description], N'') = N'' THEN N''
                               ELSE N' - ' + dc.[Description] END
                FROM RPA3.[DurationChangePayableNote] AS dcp
                INNER JOIN RPA3.[DurationChange] AS dc
                    ON dc.[DurationChangeID] = dcp.[DurationChangeRef]
                WHERE dcp.[PayableNoteRef] = {note_alias}.[PayableNoteID]
                  AND dc.[ApproveState] = 3
                  AND CAST(dcp.[DueDate] AS date) = CAST({note_alias}.[DueDate] AS date)
            ) AS posting
            ORDER BY posting.[StatusDocumentDate] DESC, posting.[StatusDocumentID] DESC
        ) AS status_link"""


def _issued_posting_status(state: Any, status_document_description: Any = None) -> tuple[bool, str]:
    """Return the Finance-approved accounting meaning of an issued cheque state.

    State 11 is still an open long-term obligation. A move to a configured
    cleared state (currently State=28) means the bank withdrawal happened and
    the cheque has been posted/accounted for; it must not remain in future
    cash-flow obligations.
    """

    status_text = str(status_document_description or "").strip()
    normalized_status_text = status_text.replace("ي", "ی").replace("ك", "ک")
    if normalized_status_text.startswith(DURATION_CHANGE_STATUS_PREFIX) or any(
        marker in normalized_status_text
        for marker in ("تعیین وضعیت چک", "تعین وضعیت چک", "وصول چ", "پرداخت چک", "برداشت وجه چک")
    ):
        return True, "سند خورده / برداشت‌شده"

    try:
        code = int(state)
    except (TypeError, ValueError):
        return False, "وضعیت نامشخص"
    paid_states = {
        int(value.strip())
        for value in settings.treasury_issued_paid_states.split(",")
        if value.strip().lstrip("-").isdigit()
    }
    if code in paid_states:
        return True, "سند خورده / برداشت‌شده"
    if code == 11:
        return False, "باز / سند نخورده"
    if code == 15:
        return False, "ابطال / اعاده"
    if code in {-27, -12}:
        return False, "برگشت عملیات"
    return False, "وضعیت نامشخص"

def _master_cheque_payload(row: Any, cheque_type: str) -> dict[str, Any]:
    state = row["ChequeState"]
    current_status_description = row.get("CurrentStatusDescription")
    is_posted, posting_status = _issued_posting_status(state) if cheque_type == "issued" else (False, None)
    received_status_label = (
        current_received_holding_label(state, current_status_description)
        if cheque_type == "received"
        else None
    )
    return {
        "cheque_id": row["ChequeID"],
        "document_id": row.get("DocumentID"),
        "document_number": row.get("DocumentNumber"),
        "document_date": _as_datetime(row.get("DocumentDate")),
        "document_date_jalali": _as_jalali_date(row.get("DocumentDate")),
        "cheque_type": cheque_type,
        "state_code": state,
        "master_state_code": row.get("MasterChequeState", state),
        "state": _cheque_state_label(cheque_type, state),
        "state_label": posting_status if cheque_type == "issued" else received_status_label,
        "current_status_description": current_status_description,
        "current_status_date": _as_datetime(row.get("CurrentStatusDate")),
        "current_status_date_jalali": _as_jalali_date(row.get("CurrentStatusDate")),
        "current_status_document_date": _as_datetime(row.get("CurrentStatusDocumentDate")),
        "current_status_document_date_jalali": _as_jalali_date(row.get("CurrentStatusDocumentDate")),
        "current_status_transaction_id": row.get("CurrentStatusTransactionID"),
        "status_source": (
            "latest_receivable_note_transaction"
            if cheque_type == "received" and row.get("CurrentStatusTransactionID") is not None
            else "receivable_note_master" if cheque_type == "received" else None
        ),
        "is_posted": is_posted if cheque_type == "issued" else None,
        "cashflow_open": (not is_posted and state == 11) if cheque_type == "issued" else None,
        "status_document_id": row.get("StatusDocumentID"),
        "status_document_number": row.get("StatusDocumentNumber"),
        "status_document_date": _as_datetime(row.get("StatusDocumentDate")),
        "status_document_date_jalali": _as_jalali_date(row.get("StatusDocumentDate")),
        "status_document_description": row.get("StatusDocumentDescription"),
        "amount": _as_number(row["Amount"]),
        "due_date": _as_datetime(row["DueDate"]),
        "due_date_jalali": _as_jalali_date(row["DueDate"]),
        "days_until_due": row["DaysUntilDue"],
        "serial_number": row["SerialNumber"],
        "series": row["Series"],
        "sayad_number": row["SayadNumber"],
        "account_number": row["AccountNumber"],
        "bank_ref": row["BankRef"],
        "bank_name": row["BankName"],
        "bank_branch_name": row["BankBranchName"],
        "bank_branch_code": row["BankBranchCode"],
        "counterpart_ref": row["CounterPartRef"],
        "counterpart_code": row["CounterPartCode"],
        "counterpart_name": row["CounterPartName"],
        "account_ref": row["AccountRef"],
        "currency_ref": row["CurrencyRef"],
        "currency_name": _currency_name(row["CurrencyRef"]),
        "normal_or_guarantee": row["NormalORGuarantee"],
        "description": row["Description"],
        "source_system": "rahkaran",
        "source_label": "راهکاران",
    }


def _karamad_cheques(source_kind: str) -> list[dict[str, Any]]:
    # V157: received cheques now come from the live Karamad SQL Server tables
    # (dbo.tblChequeD) instead of the manually-uploaded Excel snapshot. If the
    # live source is unreachable (e.g. credentials not configured yet), fall
    # back to the manual snapshot rather than breaking the report.
    if source_kind == "received_cheques":
        try:
            from app.services.karamad_live_received_cheque_service import KaramadLiveReceivedChequeService
            return KaramadLiveReceivedChequeService().report().get("cheques", [])
        except Exception:
            pass
    # V171: چک‌های پرداختی هم از جدول زنده کارآمد (vwChequePLinesFull، وضعیت نهایی «عادی»)؛
    # Snapshot اکسل هیچ چک آینده‌ای نداشت و تعهدات واقعی از گزارش و پیش‌بینی جا می‌ماند.
    if source_kind == "issued_cheques":
        try:
            from app.services.karamad_issued_cheque_sql_service import KaramadIssuedChequeSQLService
            return KaramadIssuedChequeSQLService().fetch_all()
        except Exception:
            pass
    from app.services.karamad_manual_import_service import KaramadManualImportService
    return KaramadManualImportService().cheque_rows(source_kind)


def _karamad_received_period(rows: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    horizon = {"1m": 30, "3m": 90, "6m": 180, "12m": 365}
    if period == "all":
        return rows
    if period == "overdue":
        return [row for row in rows if row.get("days_until_due") is not None and row["days_until_due"] < 0]
    days = horizon[period]
    return [row for row in rows if row.get("days_until_due") is not None and 0 <= row["days_until_due"] < days]


def get_account_balance(
    account_name: str | None = None,
    account_id: int | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """مانده ذخیره‌شده یک حساب را از FIN3.Account برمی‌گرداند."""

    resolved = _resolve_account(account_name, account_id, engine=engine)
    if resolved["status"] != "success":
        return resolved

    return {
        "status": "success",
        **resolved["account"],
    }


def _get_latest_treasury_documents(
    *,
    table_name: str,
    id_column: str,
    document_type: str,
    limit: int,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """آخرین هدرهای تأییدشده دریافت یا پرداخت را برمی‌گرداند."""

    allowed_sources = {
        ("Receipt", "ReceiptID", "receipt"),
        ("Payment", "PaymentID", "payment"),
    }
    if (table_name, id_column, document_type) not in allowed_sources:
        raise ValueError("Unsupported treasury document source")

    safe_limit = max(1, min(int(limit), 1000))
    query = text(
        f"""
        SELECT TOP ({safe_limit})
            [{id_column}] AS [DocumentID],
            [Number] AS [DocumentNumber],
            [Date] AS [DocumentDate],
            [ApproveState],
            [CounterPartRef],
            [TotalOperationalCurrencyAmount] AS [TotalAmount],
            [ItemType],
            [IsDeployment],
            [FiscalYearRef],
            [Description]
        FROM RPA3.[{table_name}]
        WHERE [ApproveState] = 3
        ORDER BY [Date] DESC, [{id_column}] DESC
        """
    )

    with _engine(engine).connect() as connection:
        rows = connection.execute(query).mappings().all()

    documents = [
        {
            "document_id": row["DocumentID"],
            "number": row["DocumentNumber"],
            "date": _as_datetime(row["DocumentDate"]),
            "date_jalali": _as_jalali_date(row["DocumentDate"]),
            "approve_state": row["ApproveState"],
            "counterpart_ref": row["CounterPartRef"],
            "total_amount": _as_number(row["TotalAmount"]),
            "item_type": row["ItemType"],
            "is_deployment": bool(row["IsDeployment"]),
            "fiscal_year_ref": row["FiscalYearRef"],
            "description": row["Description"],
        }
        for row in rows
    ]

    return {
        "status": "success",
        "document_type": document_type,
        "approve_state_filter": 3,
        "currency_name": settings.treasury_operational_currency_name,
        "documents": documents,
        "returned_count": len(documents),
        "returned_total_amount": sum(
            document["total_amount"]
            for document in documents
        ),
    }


def get_latest_receipts(
    limit: int = 10,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """آخرین اسناد دریافت تأییدشده خزانه را می‌گیرد."""

    return _get_latest_treasury_documents(
        table_name="Receipt",
        id_column="ReceiptID",
        document_type="receipt",
        limit=limit,
        engine=engine,
    )


def get_latest_payments(
    limit: int = 10,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """آخرین اسناد پرداخت تأییدشده خزانه را می‌گیرد."""

    return _get_latest_treasury_documents(
        table_name="Payment",
        id_column="PaymentID",
        document_type="payment",
        limit=limit,
        engine=engine,
    )


def get_latest_received_cheques(
    limit: int = 10,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """آخرین چک‌های ثبت‌شده در اسناد دریافت تأییدشده را برمی‌گرداند."""

    safe_limit = max(1, min(int(limit), 100))
    query = text(
        f"""
        SELECT TOP ({safe_limit})
            note.[ReceiptReceivableNoteID] AS [ChequeItemID],
            receipt.[ReceiptID] AS [DocumentID],
            receipt.[Number] AS [DocumentNumber],
            receipt.[Date] AS [DocumentDate],
            note.[Amount],
            note.[DueDate],
            note.[SerialNumber],
            note.[Series],
            note.[SayadNumber],
            note.[AccountNumber],
            note.[BankRef],
            note.[BankBranchRef],
            note.[BankBranchName],
            note.[BankBranchCode],
            note.[CounterPartRef],
            note.[AccountRef],
            note.[NoteType],
            note.[NormalORGuarantee],
            note.[CurrencyRef],
            master_note.[State] AS [ChequeState],
            bank.[Name] AS [BankName],
            counterpart.[Code] AS [CounterPartCode],
            counterpart.[Title] AS [CounterPartName],
            note.[Description] AS [ChequeDescription],
            receipt.[Description] AS [DocumentDescription]
        FROM RPA3.[ReceiptReceivableNote] AS note
        INNER JOIN RPA3.[Receipt] AS receipt
            ON receipt.[ReceiptID] = note.[ReceiptRef]
        LEFT JOIN RPA3.[ReceivableNote] AS master_note
            ON master_note.[ReceivableNoteID] = note.[ReceivableNoteRef]
        LEFT JOIN RPA3.[Bank] AS bank
            ON bank.[BankID] = note.[BankRef]
        LEFT JOIN FIN3.[DL] AS counterpart
            ON counterpart.[DLID] = note.[CounterPartRef]
        WHERE receipt.[ApproveState] = 3
          AND receipt.[ItemType] = 1
          AND COALESCE(
                master_note.[NormalORGuarantee],
                note.[NormalORGuarantee]
              ) = 1
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
        ORDER BY
            receipt.[Date] DESC,
            note.[ReceiptReceivableNoteID] DESC
        """
    )

    with _engine(engine).connect() as connection:
        rows = connection.execute(query).mappings().all()

    cheques = [
        {
            "cheque_item_id": row["ChequeItemID"],
            "document_id": row["DocumentID"],
            "document_number": row["DocumentNumber"],
            "document_date": _as_datetime(row["DocumentDate"]),
            "document_date_jalali": _as_jalali_date(row["DocumentDate"]),
            "amount": _as_number(row["Amount"]),
            "due_date": _as_datetime(row["DueDate"]),
            "due_date_jalali": _as_jalali_date(row["DueDate"]),
            "serial_number": row["SerialNumber"],
            "series": row["Series"],
            "sayad_number": row["SayadNumber"],
            "account_number": row["AccountNumber"],
            "bank_ref": row["BankRef"],
            "bank_branch_ref": row["BankBranchRef"],
            "bank_branch_name": row["BankBranchName"],
            "bank_branch_code": row["BankBranchCode"],
            "counterpart_ref": row["CounterPartRef"],
            "account_ref": row["AccountRef"],
            "note_type": row["NoteType"],
            "normal_or_guarantee": row["NormalORGuarantee"],
            "currency_ref": row["CurrencyRef"],
            "currency_name": _currency_name(row["CurrencyRef"]),
            "state_code": row["ChequeState"],
            "state": _cheque_state_label(
                "received",
                row["ChequeState"],
            ),
            "bank_name": row["BankName"],
            "counterpart_code": row["CounterPartCode"],
            "counterpart_name": row["CounterPartName"],
            "description": (
                row["ChequeDescription"]
                or row["DocumentDescription"]
            ),
        }
        for row in rows
    ]

    return {
        "status": "success",
        "cheque_type": "received",
        "approve_state_filter": 3,
        "item_type_filter": 1,
        "normal_or_guarantee_filter": 1,
        "guarantee_cheques_excluded": True,
        "guarantee_detection_rules": [
            "NormalORGuarantee must equal 1",
            "Description must not contain ضمانت, تضمین or حسن انجام",
        ],
        "cheques": cheques,
        "returned_count": len(cheques),
        "returned_total_amount": sum(
            cheque["amount"] for cheque in cheques
        ),
    }


EXCLUDED_RECEIVED_CHEQUES_FILE = "./data/excluded_received_cheques.json"


def _excluded_received_cheque_keys() -> set[tuple[str, str, str]]:
    """چک‌هایی که مدیریت از گزارش‌های داشبورد کنار گذاشته (منبع، شماره سند، سریال)."""
    import json
    from pathlib import Path

    path = Path(EXCLUDED_RECEIVED_CHEQUES_FILE)
    if not path.exists():
        return set()
    try:
        items = json.loads(path.read_text(encoding="utf-8")).get("cheques") or []
    except (OSError, ValueError):
        return set()
    return {(str(i.get("source_system") or "").lower(), str(i.get("document_number") or ""),
             str(i.get("serial_number") or "")) for i in items}


def _is_excluded_received_cheque(cheque: dict[str, Any], keys: set[tuple[str, str, str]]) -> bool:
    return (str(cheque.get("source_system") or "").lower(), str(cheque.get("document_number") or ""),
            str(cheque.get("serial_number") or "")) in keys


def get_open_received_cheques(
    period: str = "all",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """All non-guarantee open received cheques, optionally filtered by due horizon."""

    filters = {
        "all": "",
        "overdue": "AND note.[DueDate] < CAST(GETDATE() AS date)",
        "1m": "AND note.[DueDate] >= CAST(GETDATE() AS date) AND note.[DueDate] < DATEADD(month, 1, CAST(GETDATE() AS date))",
        "3m": "AND note.[DueDate] >= CAST(GETDATE() AS date) AND note.[DueDate] < DATEADD(month, 3, CAST(GETDATE() AS date))",
        "6m": "AND note.[DueDate] >= CAST(GETDATE() AS date) AND note.[DueDate] < DATEADD(month, 6, CAST(GETDATE() AS date))",
        "12m": "AND note.[DueDate] >= CAST(GETDATE() AS date) AND note.[DueDate] < DATEADD(month, 12, CAST(GETDATE() AS date))",
    }
    normalized_period = period.strip().lower()
    if normalized_period not in filters:
        raise ValueError("period must be all, overdue, 1m, 3m, 6m or 12m")

    current_status_apply = current_received_status_apply("note", "current_status")
    open_predicate = received_cheque_open_predicate("note", "current_status")
    effective_state = current_received_state_expr("note", "current_status")

    query = text(
        f"""
        SELECT
            note.[ReceivableNoteID] AS [ChequeID],
            note.[State] AS [MasterChequeState],
            {effective_state} AS [ChequeState],
            current_status.[CurrentStatusDescription],
            current_status.[CurrentStatusDate],
            current_status.[CurrentStatusDocumentDate],
            current_status.[CurrentStatusTransactionID],
            note.[Amount], note.[DueDate],
            DATEDIFF(day, CAST(GETDATE() AS date), CAST(note.[DueDate] AS date)) AS [DaysUntilDue],
            note.[SerialNumber], note.[Series], note.[SayadNumber], note.[AccountNumber],
            note.[BankRef], bank.[Name] AS [BankName], note.[BankBranchName], note.[BankBranchCode],
            note.[CounterPartRef], counterpart.[Code] AS [CounterPartCode],
            counterpart.[Title] AS [CounterPartName], note.[AccountRef], note.[CurrencyRef],
            note.[NormalORGuarantee], note.[Description],
            document_link.[DocumentID], document_link.[DocumentNumber], document_link.[DocumentDate]
        FROM RPA3.[ReceivableNote] AS note
        LEFT JOIN RPA3.[Bank] AS bank ON bank.[BankID] = note.[BankRef]
        LEFT JOIN FIN3.[DL] AS counterpart ON counterpart.[DLID] = note.[CounterPartRef]
        {current_status_apply}
        OUTER APPLY (
            SELECT TOP (1)
                receipt.[ReceiptID] AS [DocumentID],
                receipt.[Number] AS [DocumentNumber],
                receipt.[Date] AS [DocumentDate]
            FROM RPA3.[ReceiptReceivableNote] AS receipt_note
            INNER JOIN RPA3.[Receipt] AS receipt ON receipt.[ReceiptID] = receipt_note.[ReceiptRef]
            WHERE receipt_note.[ReceivableNoteRef] = note.[ReceivableNoteID]
              AND receipt.[ApproveState] = 3
            ORDER BY receipt.[Date] DESC, receipt.[ReceiptID] DESC
        ) AS document_link
        WHERE note.[NoteType] = 1
          {open_predicate}
          AND note.[NormalORGuarantee] = 1
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          -- چک‌های راهکاران با سررسید پیش از ۱۴۰۵ کنار گذاشته می‌شوند
          AND (note.[DueDate] IS NULL OR note.[DueDate] >= :rahkaran_from)
          {filters[normalized_period]}
        ORDER BY CASE WHEN note.[DueDate] IS NULL THEN 1 ELSE 0 END,
                 note.[DueDate] ASC, note.[ReceivableNoteID] DESC
        """
    )
    from app.services.liquidity.received_cheques import rahkaran_from_date
    with _engine(engine).connect() as connection:
        rows = connection.execute(query, {"rahkaran_from": rahkaran_from_date()}).mappings().all()
    rahkaran_cheques = [_master_cheque_payload(row, "received") for row in rows]
    karamad_cheques = _karamad_received_period(
        [row for row in _karamad_cheques("received_cheques") if received_cheque_is_approved_open_holding(row)],
        normalized_period,
    )
    excluded_keys = _excluded_received_cheque_keys()
    merged = rahkaran_cheques + karamad_cheques
    excluded = [c for c in merged if _is_excluded_received_cheque(c, excluded_keys)]
    cheques = sorted(
        [c for c in merged if not _is_excluded_received_cheque(c, excluded_keys)],
        key=lambda item: (item.get("due_date") or "9999-12-31", str(item.get("cheque_id") or "")),
    )
    return {
        "excluded_by_management_count": len(excluded),
        "excluded_by_management_amount": sum(float(c.get("amount") or 0) for c in excluded),
        "status": "success",
        "report_type": "open_received_cheques",
        "state_filter": "approved_open_holding_only",
        "allowed_open_holdings": ["نزد مأمور وصول", "نزد بانک", "نزد صندوق", "واگذار شده", "برگشتی نزد صندوق", "برگشتی نزد مشتری", "غیرقطعی"],
        "legacy_master_state_filter": [1, 2],
        "current_status_basis": "برای راهکاران فقط سه محل باز مصوب (نزد مأمور وصول/نزد بانک/نزد صندوق)؛ برای کارآمد این سه به‌علاوه واگذار شده و چک‌های برگشتی هنوز‌تسویه‌نشده (V157)",
        "period_filter": normalized_period,
        "sql_due_date_horizon": "unbounded" if normalized_period == "all" else normalized_period,
        "row_limit": None,
        "guarantee_cheques_excluded": True,
        "data_sources": ["راهکاران", "کارآمد"],
        "guarantee_detection_rules": [
            "NormalORGuarantee must equal 1",
            "Description must not contain ضمانت, تضمین or حسن انجام",
        ],
        "cheques": cheques,
        "returned_count": len(cheques),
        "returned_total_amount": sum(cheque["amount"] for cheque in cheques),
    }


def get_open_issued_cheques(
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Authoritative active issued cheques used by the dashboard.

    State 11 is the finance-confirmed open/active state. Cleared, cancelled,
    reversed, guarantee and shareholder cheques are deliberately excluded.
    """

    query = text(
        f"""
        SELECT
            note.[PayableNoteID] AS [ChequeID],
            note.[State] AS [ChequeState],
            note.[Amount], note.[DueDate],
            DATEDIFF(day, CAST(GETDATE() AS date), CAST(note.[DueDate] AS date)) AS [DaysUntilDue],
            note.[SerialNumber], note.[Series],
            CAST(NULL AS nvarchar(100)) AS [SayadNumber],
            note.[AccountNumber], note.[BankRef],
            bank.[Name] AS [BankName], note.[BankBranchName], note.[BankBranchCode],
            note.[CounterPartRef], counterpart.[Code] AS [CounterPartCode],
            counterpart.[Title] AS [CounterPartName], note.[AccountRef], note.[CurrencyRef],
            note.[NormalORGuarantee], note.[Description],
            document_link.[DocumentID], document_link.[DocumentNumber],
            COALESCE(document_link.[DocumentDate], note.[AgreementDate]) AS [DocumentDate],
            status_link.[StatusDocumentID], status_link.[StatusDocumentNumber],
            status_link.[StatusDocumentDate], status_link.[StatusDocumentDescription]
        FROM RPA3.[PayableNote] AS note
        LEFT JOIN RPA3.[Bank] AS bank ON bank.[BankID] = note.[BankRef]
        LEFT JOIN FIN3.[DL] AS counterpart ON counterpart.[DLID] = note.[CounterPartRef]
        OUTER APPLY (
            SELECT TOP (1)
                payment.[PaymentID] AS [DocumentID],
                payment.[Number] AS [DocumentNumber],
                payment.[Date] AS [DocumentDate]
            FROM RPA3.[PaymentPayableNote] AS payment_note
            INNER JOIN RPA3.[Payment] AS payment
                ON payment.[PaymentID] = payment_note.[PaymentRef]
            WHERE payment_note.[PayableNoteRef] = note.[PayableNoteID]
              AND payment.[ApproveState] = 3
            ORDER BY payment.[Date] DESC, payment.[PaymentID] DESC
        ) AS document_link
        {_issued_status_link_apply("note")}
        WHERE note.[NoteType] = 1
          AND note.[State] = 11
          AND status_link.[StatusDocumentID] IS NULL
          AND note.[NormalORGuarantee] = 1
          AND note.[DueDate] >= DATEADD(day, -20, CAST(GETDATE() AS date))
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%سهامدار%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%سود سهام%'
          AND ISNULL(counterpart.[Code], N'') <> N'{SHAREHOLDERS_DL_CODE}'
        ORDER BY CASE WHEN note.[DueDate] IS NULL THEN 1 ELSE 0 END,
                 note.[DueDate] ASC, note.[PayableNoteID] DESC
        """
    )
    with _engine(engine).connect() as connection:
        rows = connection.execute(query).mappings().all()
    rahkaran_cheques = [_master_cheque_payload(row, "issued") for row in rows]
    # KarAmand issued-cheque file is a snapshot of all registered cheques, not a complete
    # open-commitment feed. Keep the full snapshot visible in the KarAmand source page;
    # Rahkaran retains the 20-day overdue policy for open commitments.
    karamad_cheques = _karamad_cheques("issued_cheques")
    cheques = sorted(
        rahkaran_cheques + karamad_cheques,
        key=lambda item: (item.get("due_date") or "9999-12-31", str(item.get("cheque_id") or "")),
    )
    return {
        "status": "success",
        "report_type": "open_issued_cheques",
        "data_source": "RPA3.PayableNote + KarAmand Live SQL (vwChequePLinesFull)",
        "data_sources": ["راهکاران", "کارآمد"],
        "state_filter": [11],
        "paid_state_excluded": 28,
        "posting_business_rule": "وجود سند تأییدشده تعیین وضعیت/وصول چک در PayableNoteTransaction، سند تأییدشده تغییر مدت به روز (DurationChange) یا State پرداخت‌شده = سند خورده و برداشت‌شده؛ از تعهدات باز و Cash Flow آینده حذف می‌شود",
        "due_policy": "Rahkaran: from 20 days overdue through all future due dates; KarAmand: all live cheques whose final status is عادی (not yet cleared)",
        "row_limit": None,
        "guarantee_cheques_excluded": True,
        "shareholder_cheques_excluded": True,
        "cheques": cheques,
        "returned_count": len(cheques),
        "returned_total_amount": sum(cheque["amount"] for cheque in cheques),
    }


def get_latest_issued_cheques(
    limit: int = 10,
    engine: Engine | None = None,
    upcoming_only: bool = False,
    sort_by_due: bool = False,
) -> dict[str, Any]:
    """آخرین چک‌های ثبت‌شده در اسناد پرداخت تأییدشده را برمی‌گرداند."""

    safe_limit = max(1, min(int(limit), 1000))
    primary_future_filter = (
        "AND note.[DueDate] >= CAST(GETDATE() AS date) AND master_note.[State] = 11"
        if upcoming_only else ""
    )
    primary_order = (
        "CASE WHEN note.[DueDate] IS NULL THEN 1 ELSE 0 END, note.[DueDate] ASC, note.[PaymentPayableNoteID] DESC"
        if sort_by_due else "payment.[Date] DESC, note.[PaymentPayableNoteID] DESC"
    )
    query = text(
        f"""
        SELECT TOP ({safe_limit})
            note.[PaymentPayableNoteID] AS [ChequeItemID],
            payment.[PaymentID] AS [DocumentID],
            payment.[Number] AS [DocumentNumber],
            payment.[Date] AS [DocumentDate],
            note.[Amount],
            note.[DueDate],
            note.[SerialNumber],
            note.[Series],
            note.[AccountNumber],
            note.[BankRef],
            note.[BankAccountRef],
            note.[BankBranchName],
            note.[BankBranchCode],
            note.[CounterPartRef],
            note.[AccountRef],
            note.[ApproveState] AS [ChequeApproveState],
            note.[NoteType],
            note.[NormalORGuarantee],
            note.[CurrencyRef],
            master_note.[State] AS [ChequeState],
            bank.[Name] AS [BankName],
            counterpart.[Code] AS [CounterPartCode],
            counterpart.[Title] AS [CounterPartName],
            note.[Description] AS [ChequeDescription],
            payment.[Description] AS [DocumentDescription],
            status_link.[StatusDocumentID], status_link.[StatusDocumentNumber],
            status_link.[StatusDocumentDate], status_link.[StatusDocumentDescription]
        FROM RPA3.[PaymentPayableNote] AS note
        INNER JOIN RPA3.[Payment] AS payment
            ON payment.[PaymentID] = note.[PaymentRef]
        LEFT JOIN RPA3.[PayableNote] AS master_note
            ON master_note.[PayableNoteID] = note.[PayableNoteRef]
        LEFT JOIN RPA3.[Bank] AS bank
            ON bank.[BankID] = note.[BankRef]
        LEFT JOIN FIN3.[DL] AS counterpart
            ON counterpart.[DLID] = note.[CounterPartRef]
        {_issued_status_link_apply("master_note")}
        WHERE payment.[ApproveState] = 3
          AND note.[NoteType] = 1
          AND COALESCE(
                master_note.[NormalORGuarantee],
                note.[NormalORGuarantee]
              ) = 1
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%سهامدار%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%سود سهام%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%سهامدار%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%سود سهام%'
          AND ISNULL(counterpart.[Code], N'') <> N'{SHAREHOLDERS_DL_CODE}'
          AND note.[DueDate] >= DATEADD(day, -20, CAST(GETDATE() AS date))
          {primary_future_filter}
        ORDER BY {primary_order}
        """
    )

    primary_error: str | None = None
    with _engine(engine).connect() as connection:
        try:
            rows = connection.execute(query).mappings().all()
        except Exception as exc:
            # Some Rahkaran installations do not retain every issued cheque in
            # PaymentPayableNote, while the authoritative master PayableNote
            # still contains it. Keep the dashboard available through the
            # master-table fallback and expose the source in the response.
            primary_error = str(exc)
            rows = []

        source = "payment_document"
        if not rows:
            source = "payable_note_master_fallback"
            fallback_future_filter = (
                "AND master_note.[DueDate] >= CAST(GETDATE() AS date)"
                if upcoming_only else ""
            )
            fallback_query = text(
                f"""
                SELECT TOP ({safe_limit})
                    master_note.[PayableNoteID] AS [ChequeItemID],
                    CAST(NULL AS bigint) AS [DocumentID],
                    CAST(NULL AS bigint) AS [DocumentNumber],
                    master_note.[AgreementDate] AS [DocumentDate],
                    master_note.[Amount],
                    master_note.[DueDate],
                    master_note.[SerialNumber],
                    master_note.[Series],
                    master_note.[AccountNumber],
                    master_note.[BankRef],
                    master_note.[BankAccountRef],
                    master_note.[BankBranchName],
                    master_note.[BankBranchCode],
                    master_note.[CounterPartRef],
                    master_note.[AccountRef],
                    CAST(NULL AS int) AS [ChequeApproveState],
                    master_note.[NoteType],
                    master_note.[NormalORGuarantee],
                    master_note.[CurrencyRef],
                    master_note.[State] AS [ChequeState],
                    bank.[Name] AS [BankName],
                    counterpart.[Code] AS [CounterPartCode],
                    counterpart.[Title] AS [CounterPartName],
                    master_note.[Description] AS [ChequeDescription],
                    CAST(NULL AS nvarchar(1024)) AS [DocumentDescription],
                    status_link.[StatusDocumentID], status_link.[StatusDocumentNumber],
                    status_link.[StatusDocumentDate], status_link.[StatusDocumentDescription]
                FROM RPA3.[PayableNote] AS master_note
                LEFT JOIN RPA3.[Bank] AS bank
                    ON bank.[BankID] = master_note.[BankRef]
                LEFT JOIN FIN3.[DL] AS counterpart
                    ON counterpart.[DLID] = master_note.[CounterPartRef]
                {_issued_status_link_apply("master_note")}
                WHERE master_note.[NoteType] = 1
                  AND master_note.[NormalORGuarantee] = 1
                  AND ISNULL(master_note.[Description], N'') NOT LIKE N'%ضمانت%'
                  AND ISNULL(master_note.[Description], N'') NOT LIKE N'%تضمین%'
                  AND ISNULL(master_note.[Description], N'') NOT LIKE N'%حسن انجام%'
                  AND ISNULL(master_note.[Description], N'') NOT LIKE N'%سهامدار%'
                  AND ISNULL(master_note.[Description], N'') NOT LIKE N'%سود سهام%'
                  AND ISNULL(counterpart.[Code], N'') <> N'{SHAREHOLDERS_DL_CODE}'
                  AND master_note.[State] = 11
                  AND master_note.[DueDate] >= DATEADD(day, -20, CAST(GETDATE() AS date))
                  {fallback_future_filter}
                ORDER BY
                    CASE WHEN master_note.[DueDate] IS NULL THEN 1 ELSE 0 END,
                    master_note.[DueDate] ASC,
                    master_note.[PayableNoteID] DESC
                """
            )
            rows = connection.execute(fallback_query).mappings().all()

    cheques = [
        {
            "cheque_item_id": row["ChequeItemID"],
            "document_id": row["DocumentID"],
            "document_number": row["DocumentNumber"],
            "document_date": _as_datetime(row["DocumentDate"]),
            "document_date_jalali": _as_jalali_date(row["DocumentDate"]),
            "amount": _as_number(row["Amount"]),
            "due_date": _as_datetime(row["DueDate"]),
            "due_date_jalali": _as_jalali_date(row["DueDate"]),
            "serial_number": row["SerialNumber"],
            "series": row["Series"],
            "account_number": row["AccountNumber"],
            "bank_ref": row["BankRef"],
            "bank_account_ref": row["BankAccountRef"],
            "bank_branch_name": row["BankBranchName"],
            "bank_branch_code": row["BankBranchCode"],
            "counterpart_ref": row["CounterPartRef"],
            "account_ref": row["AccountRef"],
            "cheque_approve_state": row["ChequeApproveState"],
            "note_type": row["NoteType"],
            "normal_or_guarantee": row["NormalORGuarantee"],
            "currency_ref": row["CurrencyRef"],
            "currency_name": _currency_name(row["CurrencyRef"]),
            "state_code": row["ChequeState"],
            "state": _cheque_state_label(
                "issued",
                row["ChequeState"],
            ),
            "state_label": _issued_posting_status(row["ChequeState"], row.get("StatusDocumentDescription"))[1],
            "is_posted": _issued_posting_status(row["ChequeState"], row.get("StatusDocumentDescription"))[0],
            "cashflow_open": (not _issued_posting_status(row["ChequeState"], row.get("StatusDocumentDescription"))[0] and row["ChequeState"] == 11),
            "status_document_id": row.get("StatusDocumentID"),
            "status_document_number": row.get("StatusDocumentNumber"),
            "status_document_date": _as_datetime(row.get("StatusDocumentDate")),
            "status_document_date_jalali": _as_jalali_date(row.get("StatusDocumentDate")),
            "status_document_description": row.get("StatusDocumentDescription"),
            "bank_name": row["BankName"],
            "counterpart_code": row["CounterPartCode"],
            "counterpart_name": row["CounterPartName"],
            "description": (
                row["ChequeDescription"]
                or row["DocumentDescription"]
            ),
        }
        for row in rows
    ]

    return {
        "status": "success",
        "cheque_type": "issued",
        "approve_state_filter": 3,
        "note_type_filter": 1,
        "normal_or_guarantee_filter": 1,
        "guarantee_cheques_excluded": True,
        "shareholder_paid_cheques_excluded": True,
        "shareholder_exclusion_rules": [
            "Description does not contain سهامدار or سود سهام",
            f"Counterpart DL code is not {SHAREHOLDERS_DL_CODE} (سهامداران)",
        ],
        "data_source": source,
        "fallback_used": source != "payment_document",
        "primary_query_error": primary_error,
        "cheques": cheques,
        "returned_count": len(cheques),
        "returned_total_amount": sum(
            cheque["amount"] for cheque in cheques
        ),
    }


def get_received_cheque_sql_scope(engine: Engine | None = None) -> dict[str, Any]:
    """Read-only SQL coverage check for Rahkaran received cheques.

    This endpoint intentionally applies NO due-date horizon so Finance can see
    whether SQL itself contains cheques beyond the dates currently visible in UI.
    """
    current_status_apply = current_received_status_apply("note", "current_status")
    open_expression = received_cheque_open_expression("note", "current_status")
    query = text(
        f"""
        SELECT
            MIN(CAST(note.[DueDate] AS date)) AS [MinDueDate],
            MAX(CAST(note.[DueDate] AS date)) AS [MaxDueDate],
            COUNT_BIG(*) AS [AllNormalChequeCount],
            COALESCE(SUM(note.[Amount]), 0) AS [AllNormalChequeAmount],
            SUM(CASE WHEN {open_expression} THEN 1 ELSE 0 END) AS [OpenChequeCount],
            COALESCE(SUM(CASE WHEN {open_expression} THEN note.[Amount] ELSE 0 END), 0) AS [OpenChequeAmount]
        FROM RPA3.[ReceivableNote] AS note
        {current_status_apply}
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
        """
    )
    monthly_query = text(
        f"""
        SELECT
            YEAR(note.[DueDate]) AS [DueYear],
            MONTH(note.[DueDate]) AS [DueMonth],
            COUNT_BIG(*) AS [OpenChequeCount],
            COALESCE(SUM(note.[Amount]), 0) AS [OpenChequeAmount]
        FROM RPA3.[ReceivableNote] AS note
        {current_status_apply}
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND note.[DueDate] IS NOT NULL
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND {open_expression}
        GROUP BY YEAR(note.[DueDate]), MONTH(note.[DueDate])
        ORDER BY YEAR(note.[DueDate]), MONTH(note.[DueDate])
        """
    )
    with _engine(engine).connect() as connection:
        summary = connection.execute(query).mappings().one()
        monthly = connection.execute(monthly_query).mappings().all()
    return {
        "status": "success",
        "source_system": "rahkaran_sql",
        "date_horizon": "unbounded",
        "min_due_date": _as_datetime(summary["MinDueDate"]),
        "max_due_date": _as_datetime(summary["MaxDueDate"]),
        "all_normal_cheque_count": int(summary["AllNormalChequeCount"] or 0),
        "all_normal_cheque_amount": _as_number(summary["AllNormalChequeAmount"]),
        "open_cheque_count": int(summary["OpenChequeCount"] or 0),
        "open_cheque_amount": _as_number(summary["OpenChequeAmount"]),
        "open_due_months": [
            {
                "year": int(row["DueYear"]),
                "month": int(row["DueMonth"]),
                "count": int(row["OpenChequeCount"] or 0),
                "amount": _as_number(row["OpenChequeAmount"]),
            }
            for row in monthly
        ],
    }

def get_received_cheque_current_state_quality(engine: Engine | None = None) -> dict[str, Any]:
    """Compare legacy master-state filtering with Rahkaran's latest operation state.

    This is intentionally read-only and exists so Finance can audit exactly why
    a cheque entered or left the open portfolio after V115.
    """

    current_status_apply = current_received_status_apply("note", "current_status")
    effective_state = current_received_state_expr("note", "current_status")
    open_expression = received_cheque_open_expression("note", "current_status")
    query = text(
        f"""
        WITH CurrentRows AS (
            SELECT
                note.[ReceivableNoteID] AS [ChequeID],
                note.[SerialNumber],
                note.[SayadNumber],
                note.[Amount],
                note.[DueDate],
                note.[State] AS [MasterState],
                {effective_state} AS [EffectiveState],
                current_status.[CurrentStatusDescription],
                current_status.[CurrentStatusDate],
                current_status.[CurrentStatusDocumentDate],
                current_status.[CurrentStatusTransactionID],
                CASE WHEN note.[State] IN (1, 2) THEN 1 ELSE 0 END AS [LegacyOpen],
                CASE WHEN {open_expression} THEN 1 ELSE 0 END AS [BusinessOpen]
            FROM RPA3.[ReceivableNote] AS note
            {current_status_apply}
            WHERE note.[NoteType] = 1
              AND note.[NormalORGuarantee] = 1
              AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
              AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
              AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
        )
        SELECT
            COUNT_BIG(*) AS [TotalNormalChequeCount],
            SUM(CASE WHEN [LegacyOpen] = 1 THEN 1 ELSE 0 END) AS [LegacyOpenCount],
            COALESCE(SUM(CASE WHEN [LegacyOpen] = 1 THEN [Amount] ELSE 0 END), 0) AS [LegacyOpenAmount],
            SUM(CASE WHEN [BusinessOpen] = 1 THEN 1 ELSE 0 END) AS [BusinessOpenCount],
            COALESCE(SUM(CASE WHEN [BusinessOpen] = 1 THEN [Amount] ELSE 0 END), 0) AS [BusinessOpenAmount],
            SUM(CASE WHEN [LegacyOpen] = 1 AND [BusinessOpen] = 0 THEN 1 ELSE 0 END) AS [LegacyOnlyCount],
            COALESCE(SUM(CASE WHEN [LegacyOpen] = 1 AND [BusinessOpen] = 0 THEN [Amount] ELSE 0 END), 0) AS [LegacyOnlyAmount],
            SUM(CASE WHEN [LegacyOpen] = 0 AND [BusinessOpen] = 1 THEN 1 ELSE 0 END) AS [BusinessOnlyCount],
            COALESCE(SUM(CASE WHEN [LegacyOpen] = 0 AND [BusinessOpen] = 1 THEN [Amount] ELSE 0 END), 0) AS [BusinessOnlyAmount]
        FROM CurrentRows
        """
    )
    mismatch_query = text(
        f"""
        SELECT TOP (200)
            note.[ReceivableNoteID] AS [ChequeID],
            note.[SerialNumber],
            note.[SayadNumber],
            note.[Amount],
            note.[DueDate],
            note.[State] AS [MasterState],
            {effective_state} AS [EffectiveState],
            current_status.[CurrentStatusDescription],
            current_status.[CurrentStatusDate],
            current_status.[CurrentStatusDocumentDate],
            current_status.[CurrentStatusTransactionID],
            CASE WHEN note.[State] IN (1, 2) THEN 1 ELSE 0 END AS [LegacyOpen],
            CASE WHEN {open_expression} THEN 1 ELSE 0 END AS [BusinessOpen]
        FROM RPA3.[ReceivableNote] AS note
        {current_status_apply}
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND (
                (note.[State] IN (1, 2) AND NOT {open_expression})
                OR
                (note.[State] NOT IN (1, 2) AND {open_expression})
              )
        ORDER BY
            COALESCE(current_status.[CurrentStatusDate], current_status.[CurrentStatusDocumentDate], note.[DueDate]) DESC,
            note.[ReceivableNoteID] DESC
        """
    )
    with _engine(engine).connect() as connection:
        summary = connection.execute(query).mappings().one()
        mismatches = connection.execute(mismatch_query).mappings().all()

    def money(value: Any) -> float:
        return _as_number(value)

    return {
        "status": "success",
        "definition": "سبد باز = State اصلی ۱/۲؛ آخرین عملیات تأییدشده فقط برای حذف وصول/مسترد/واخواست/واگذاری به غیر",
        "legacy_definition": "ReceivableNote.State IN (1,2)",
        "total_normal_cheque_count": int(summary["TotalNormalChequeCount"] or 0),
        "legacy_open": {
            "count": int(summary["LegacyOpenCount"] or 0),
            "amount": money(summary["LegacyOpenAmount"]),
        },
        "business_open": {
            "count": int(summary["BusinessOpenCount"] or 0),
            "amount": money(summary["BusinessOpenAmount"]),
        },
        "legacy_only": {
            "count": int(summary["LegacyOnlyCount"] or 0),
            "amount": money(summary["LegacyOnlyAmount"]),
        },
        "business_only": {
            "count": int(summary["BusinessOnlyCount"] or 0),
            "amount": money(summary["BusinessOnlyAmount"]),
        },
        "mismatches": [
            {
                "cheque_id": row["ChequeID"],
                "serial_number": row["SerialNumber"],
                "sayad_number": row["SayadNumber"],
                "amount": money(row["Amount"]),
                "due_date": _as_datetime(row["DueDate"]),
                "due_date_jalali": _as_jalali_date(row["DueDate"]),
                "master_state": row["MasterState"],
                "effective_state": row["EffectiveState"],
                "current_status_description": row["CurrentStatusDescription"],
                "current_status_date": _as_datetime(row["CurrentStatusDate"]),
                "current_status_date_jalali": _as_jalali_date(row["CurrentStatusDate"]),
                "legacy_open": bool(row["LegacyOpen"]),
                "business_open": bool(row["BusinessOpen"]),
            }
            for row in mismatches
        ],
        "mismatch_count_returned": len(mismatches),
    }

def get_cheque_state_quality(engine: Engine | None = None) -> dict[str, Any]:
    """Return auditable cheque-state counts and the verified received pass rate.

    Issued-state business meanings vary by Rahkaran configuration. We therefore
    expose their distribution without silently treating unknown states as paid.
    """
    received_query = text(
        """
        SELECT
            COUNT_BIG(*) AS [TotalCount],
            SUM(CASE WHEN [State] = 3 THEN 1 ELSE 0 END) AS [CollectedCount],
            SUM(CASE WHEN [State] = 3 THEN [Amount] ELSE 0 END) AS [CollectedAmount],
            SUM([Amount]) AS [TotalAmount]
        FROM RPA3.[ReceivableNote]
        WHERE [NoteType] = 1
          AND [NormalORGuarantee] = 1
          AND ISNULL([Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL([Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL([Description], N'') NOT LIKE N'%حسن انجام%'
        """
    )
    issued_query = text(
        """
        SELECT
            [State] AS [StateCode],
            COUNT_BIG(*) AS [ChequeCount],
            SUM([Amount]) AS [ChequeAmount],
            SUM(CASE WHEN [DueDate] < CAST(GETDATE() AS date) THEN 1 ELSE 0 END) AS [PastDueCount],
            SUM(CASE WHEN [DueDate] < CAST(GETDATE() AS date) THEN [Amount] ELSE 0 END) AS [PastDueAmount]
        FROM RPA3.[PayableNote]
        WHERE [NoteType] = 1
          AND [NormalORGuarantee] = 1
          AND ISNULL([Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL([Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL([Description], N'') NOT LIKE N'%حسن انجام%'
        GROUP BY [State]
        ORDER BY [State]
        """
    )
    with _engine(engine).connect() as connection:
        received = connection.execute(received_query).mappings().one()
        issued = connection.execute(issued_query).mappings().all()
    total_count = int(received["TotalCount"] or 0)
    total_amount = _as_number(received["TotalAmount"])
    collected_count = int(received["CollectedCount"] or 0)
    collected_amount = _as_number(received["CollectedAmount"])
    issued_rows = [
        {
            "state_code": row["StateCode"],
            "cheque_count": int(row["ChequeCount"] or 0),
            "cheque_amount": _as_number(row["ChequeAmount"]),
            "past_due_count": int(row["PastDueCount"] or 0),
            "past_due_amount": _as_number(row["PastDueAmount"]),
            "verified_business_label": _cheque_state_label("issued", row["StateCode"]),
            "posting_status_fa": _issued_posting_status(row["StateCode"])[1],
            "means_accounting_posted": _issued_posting_status(row["StateCode"])[0],
        }
        for row in issued
    ]
    paid_states = {
        int(value.strip())
        for value in settings.treasury_issued_paid_states.split(",")
        if value.strip().lstrip("-").isdigit()
    }
    # Denominator contains only valid matured cheques: still active (11) plus
    # finance-confirmed cleared states. Restored/cancelled and reversal states
    # must not dilute the real payment rate.
    eligible_states = {11} | paid_states
    due_count = sum(item["past_due_count"] for item in issued_rows if item["state_code"] in eligible_states)
    due_amount = sum(item["past_due_amount"] for item in issued_rows if item["state_code"] in eligible_states)
    paid_count = sum(item["past_due_count"] for item in issued_rows if item["state_code"] in paid_states)
    paid_amount = sum(item["past_due_amount"] for item in issued_rows if item["state_code"] in paid_states)
    issued_actual_rate = None
    if paid_states:
        issued_actual_rate = {
            "definition": "سندخورده/برداشت‌شده (بلندمدت → روز؛ configured cleared states) / چک‌های سررسیدشده معتبر",
            "configured_paid_states": sorted(paid_states),
            "eligible_denominator_states": sorted(eligible_states),
            "due_count": due_count,
            "paid_count": paid_count,
            "count_rate_percent": paid_count / due_count * 100 if due_count else 0,
            "due_amount": due_amount,
            "paid_amount": paid_amount,
            "amount_rate_percent": paid_amount / due_amount * 100 if due_amount else 0,
        }
    return {
        "status": "success",
        "received_verified": {
            "definition": "RPA3.ReceivableNote State=3 / normal received cheque notes; guarantee cheques excluded",
            "total_count": total_count,
            "collected_count": collected_count,
            "count_rate_percent": collected_count / total_count * 100 if total_count else 0,
            "total_amount": total_amount,
            "collected_amount": collected_amount,
            "amount_rate_percent": collected_amount / total_amount * 100 if total_amount else 0,
        },
        "issued_state_distribution": issued_rows,
        "issued_actual_payment_rate": issued_actual_rate,
        "issued_rate_limitation": None if paid_states else "کد وضعیت تسویه‌شده را پس از تأیید مالی در TREASURY_ISSUED_PAID_STATES فایل .env وارد کنید.",
    }


def get_cheque_due_report(
    cheque_type: str,
    days: int = 30,
    overdue: bool = False,
    limit: int = 100,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """گزارش چک‌های فعال سررسیدشونده یا سررسیدگذشته."""

    normalized_type = cheque_type.strip().lower()
    configurations = {
        "received": {
            "table": "ReceivableNote",
            "id_column": "ReceivableNoteID",
            "sayad_sql": "note.[SayadNumber]",
            "active_states": (1, 2),
        },
        "issued": {
            "table": "PayableNote",
            "id_column": "PayableNoteID",
            "sayad_sql": "CAST(NULL AS nvarchar(32))",
            "active_states": (11,),
        },
    }
    configuration = configurations.get(normalized_type)
    if configuration is None:
        raise ValueError("cheque_type must be received or issued")

    safe_days = max(1, min(int(days), 365))
    safe_limit = max(1, min(int(limit), 500))
    state_sql = ", ".join(
        str(state) for state in configuration["active_states"]
    )
    if normalized_type == "received":
        current_status_apply = current_received_status_apply("note", "current_status")
        effective_state = current_received_state_expr("note", "current_status")
        state_select_sql = f"""
            note.[State] AS [MasterChequeState],
            {effective_state} AS [ChequeState],
            current_status.[CurrentStatusDescription],
            current_status.[CurrentStatusDate],
            current_status.[CurrentStatusDocumentDate],
            current_status.[CurrentStatusTransactionID],
        """
        active_state_predicate = received_cheque_open_predicate("note", "current_status")
    else:
        current_status_apply = ""
        state_select_sql = "note.[State] AS [ChequeState],"
        active_state_predicate = f"AND note.[State] IN ({state_sql})"
    if overdue:
        due_filter = """
            CAST(note.[DueDate] AS date) >=
                DATEADD(day, -:days, CAST(GETDATE() AS date))
            AND CAST(note.[DueDate] AS date) < CAST(GETDATE() AS date)
        """
    else:
        due_filter = """
            CAST(note.[DueDate] AS date) >= CAST(GETDATE() AS date)
            AND CAST(note.[DueDate] AS date) <=
                DATEADD(day, :days, CAST(GETDATE() AS date))
        """

    query = text(
        f"""
        SELECT TOP ({safe_limit})
            note.[{configuration['id_column']}] AS [ChequeID],
            {state_select_sql}
            note.[Amount],
            note.[DueDate],
            DATEDIFF(
                day,
                CAST(GETDATE() AS date),
                CAST(note.[DueDate] AS date)
            ) AS [DaysUntilDue],
            note.[SerialNumber],
            note.[Series],
            {configuration['sayad_sql']} AS [SayadNumber],
            note.[AccountNumber],
            note.[BankRef],
            bank.[Name] AS [BankName],
            note.[BankBranchName],
            note.[BankBranchCode],
            note.[CounterPartRef],
            counterpart.[Code] AS [CounterPartCode],
            counterpart.[Title] AS [CounterPartName],
            note.[AccountRef],
            note.[CurrencyRef],
            note.[NormalORGuarantee],
            note.[Description]
        FROM RPA3.[{configuration['table']}] AS note
        LEFT JOIN RPA3.[Bank] AS bank
            ON bank.[BankID] = note.[BankRef]
        LEFT JOIN FIN3.[DL] AS counterpart
            ON counterpart.[DLID] = note.[CounterPartRef]
        {current_status_apply}
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          {active_state_predicate}
          AND note.[DueDate] IS NOT NULL
          AND {due_filter}
        ORDER BY note.[DueDate], note.[{configuration['id_column']}]
        """
    )

    aggregate_query = text(
        f"""
        SELECT
            COUNT_BIG(*) AS [TotalCount],
            COALESCE(SUM(note.[Amount]), 0) AS [TotalAmount]
        FROM RPA3.[{configuration['table']}] AS note
        {current_status_apply}
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          {active_state_predicate}
          AND note.[DueDate] IS NOT NULL
          AND {due_filter}
        """
    )

    parameters = {"days": safe_days}
    with _engine(engine).connect() as connection:
        rows = connection.execute(query, parameters).mappings().all()
        aggregate = connection.execute(
            aggregate_query,
            parameters,
        ).mappings().one()

    cheques = [
        _master_cheque_payload(row, normalized_type)
        for row in rows
    ]
    total_count = int(aggregate["TotalCount"] or 0)
    total_amount = _as_number(aggregate["TotalAmount"])
    return {
        "status": "success",
        "report_type": "overdue" if overdue else "upcoming",
        "cheque_type": normalized_type,
        "as_of_date": date.today().isoformat(),
        "as_of_date_jalali": _as_jalali_date(date.today()),
        "days": safe_days,
        "date_window": (
            f"previous_{safe_days}_days"
            if overdue
            else f"next_{safe_days}_days"
        ),
        "active_state_filter": (
            "latest_positive_receivable_note_transaction_business_open"
            if normalized_type == "received"
            else list(configuration["active_states"])
        ),
        "normal_or_guarantee_filter": 1,
        "cheques": cheques,
        "returned_count": len(cheques),
        "returned_total_amount": sum(
            cheque["amount"] for cheque in cheques
        ),
        "total_count": total_count,
        "total_amount": total_amount,
        "is_truncated": total_count > len(cheques),
    }


def get_received_cheques_by_status(
    cheque_status: str,
    limit: int = 100,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """چک‌های دریافتی با وضعیت قطعی وصول‌شده یا واخواست‌شده."""

    normalized_status = cheque_status.strip().lower()
    state_by_status = {"collected": 3, "protested": 4}
    state_code = state_by_status.get(normalized_status)
    if state_code is None:
        raise ValueError("cheque_status must be collected or protested")

    safe_limit = max(1, min(int(limit), 500))
    query = text(
        f"""
        SELECT TOP ({safe_limit})
            note.[ReceivableNoteID] AS [ChequeID],
            note.[State] AS [ChequeState],
            note.[Amount],
            note.[DueDate],
            DATEDIFF(
                day,
                CAST(GETDATE() AS date),
                CAST(note.[DueDate] AS date)
            ) AS [DaysUntilDue],
            note.[SerialNumber],
            note.[Series],
            note.[SayadNumber],
            note.[AccountNumber],
            note.[BankRef],
            bank.[Name] AS [BankName],
            note.[BankBranchName],
            note.[BankBranchCode],
            note.[CounterPartRef],
            counterpart.[Code] AS [CounterPartCode],
            counterpart.[Title] AS [CounterPartName],
            note.[AccountRef],
            note.[CurrencyRef],
            note.[NormalORGuarantee],
            note.[Description]
        FROM RPA3.[ReceivableNote] AS note
        LEFT JOIN RPA3.[Bank] AS bank
            ON bank.[BankID] = note.[BankRef]
        LEFT JOIN FIN3.[DL] AS counterpart
            ON counterpart.[DLID] = note.[CounterPartRef]
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND note.[State] = :state_code
        ORDER BY note.[DueDate] DESC, note.[ReceivableNoteID] DESC
        """
    )

    with _engine(engine).connect() as connection:
        rows = connection.execute(
            query,
            {"state_code": state_code},
        ).mappings().all()

    cheques = [
        _master_cheque_payload(row, "received")
        for row in rows
    ]
    return {
        "status": "success",
        "report_type": "received_cheque_status",
        "cheque_status": normalized_status,
        "state_filter": state_code,
        "normal_or_guarantee_filter": 1,
        "guarantee_cheques_excluded": True,
        "cheques": cheques,
        "returned_count": len(cheques),
        "returned_total_amount": sum(
            cheque["amount"] for cheque in cheques
        ),
    }


def search_received_cheque_debtors(
    name: str,
    limit: int = 20,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Search explicit cheque debtors/deliverers, not cheque account owners."""

    search_term = _normalize_account_search(name)
    if not search_term:
        return {"status": "success", "debtors": []}
    safe_limit = max(1, min(int(limit), 50))
    tokens = search_term.split()[:8]
    conditions = []
    parameters: dict[str, Any] = {}
    normalized_title_sql = """
        REPLACE(REPLACE(REPLACE(REPLACE(dl.[Title], N'آ', N'ا'),
        N'ي', N'ی'), N'ك', N'ک'), NCHAR(8204), N' ')
    """
    for index, token in enumerate(tokens):
        key = f"token_{index}"
        conditions.append(f"{normalized_title_sql} LIKE :{key}")
        parameters[key] = f"%{token}%"

    query = text(
        f"""
        SELECT TOP ({safe_limit})
            dl.[DLID] AS [CounterPartRef],
            dl.[Code] AS [CounterPartCode],
            dl.[Title] AS [CounterPartName],
            COUNT_BIG(*) AS [ChequeCount],
            SUM(note.[Amount]) AS [ChequeTotalAmount]
        FROM RPA3.[ReceiptReceivableNote] AS note
        INNER JOIN RPA3.[Receipt] AS receipt
            ON receipt.[ReceiptID] = note.[ReceiptRef]
        LEFT JOIN RPA3.[ReceivableNote] AS master_note
            ON master_note.[ReceivableNoteID] = note.[ReceivableNoteRef]
        INNER JOIN FIN3.[DL] AS dl
            ON dl.[DLID] = COALESCE(
                note.[CounterPartRef], receipt.[CounterPartRef]
            )
        WHERE receipt.[ApproveState] = 3
          AND receipt.[ItemType] = 1
          AND COALESCE(
                master_note.[NormalORGuarantee],
                note.[NormalORGuarantee]
              ) = 1
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND {' AND '.join(conditions)}
        GROUP BY dl.[DLID], dl.[Code], dl.[Title]
        ORDER BY COUNT_BIG(*) DESC, dl.[Title]
        """
    )
    with _engine(engine).connect() as connection:
        rows = connection.execute(query, parameters).mappings().all()
    return {
        "status": "success",
        "debtors": [
            {
                "counterpart_ref": row["CounterPartRef"],
                "code": row["CounterPartCode"],
                "name": row["CounterPartName"],
                "cheque_count": row["ChequeCount"],
                "cheque_total_amount": _as_number(row["ChequeTotalAmount"]),
            }
            for row in rows
        ],
        "returned_count": len(rows),
    }


def get_receivable_report() -> dict[str, Any]:
    """تا زمان تأیید تعریف تجاری دریافتنی، عدد احتمالی تولید نمی‌کند."""

    return {
        "status": "not_ready",
        "message": (
            "تعریف و Query گزارش دریافتنی هنوز توسط واحد خزانه تأیید نشده است."
        ),
    }


def get_received_cheque_status_signatures(engine: Engine | None = None) -> dict[str, Any]:
    """SQL-only audit of Rahkaran current-status signatures.

    This does not use Excel as a data source. It exposes the fields that Rahkaran
    uses around the latest approved ReceivableNoteTransaction so the official
    report's «وضعیت فعلی» can be calibrated without guessing from master State.
    """
    current_status_apply = current_received_status_apply("note", "current_status")
    query = text(
        f"""
        SELECT
            note.[State] AS [MasterState],
            current_status.[CurrentChequeState],
            current_status.[CurrentDocumentItemType],
            CASE WHEN current_status.[CurrentBankAccountRef] IS NULL THEN 0 ELSE 1 END AS [HasBankAccount],
            CASE
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%مأمور وصول%'
                  OR ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%مامور وصول%' THEN N'collector_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%واخواست%' THEN N'protested_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%مسترد%'
                  OR ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%استرداد%' THEN N'returned_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%وصول%'
                  OR ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%نقد%' THEN N'collected_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%واگذار%'
                  AND ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%غیر%' THEN N'transferred_to_third_party_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%برگ دریافت چک%'
                  OR ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%برگه دریافت چک%' THEN N'receipt_sheet_text'
                WHEN NULLIF(LTRIM(RTRIM(ISNULL(current_status.[CurrentStatusDescription], N''))), N'') IS NULL THEN N'empty_text'
                ELSE N'other_text'
            END AS [DescriptionClass],
            COUNT_BIG(*) AS [ChequeCount],
            COALESCE(SUM(note.[Amount]), 0) AS [ChequeAmount],
            MIN(CAST(note.[DueDate] AS date)) AS [MinDueDate],
            MAX(CAST(note.[DueDate] AS date)) AS [MaxDueDate]
        FROM RPA3.[ReceivableNote] AS note
        {current_status_apply}
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
        GROUP BY
            note.[State],
            current_status.[CurrentChequeState],
            current_status.[CurrentDocumentItemType],
            CASE WHEN current_status.[CurrentBankAccountRef] IS NULL THEN 0 ELSE 1 END,
            CASE
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%مأمور وصول%'
                  OR ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%مامور وصول%' THEN N'collector_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%واخواست%' THEN N'protested_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%مسترد%'
                  OR ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%استرداد%' THEN N'returned_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%وصول%'
                  OR ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%نقد%' THEN N'collected_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%واگذار%'
                  AND ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%غیر%' THEN N'transferred_to_third_party_text'
                WHEN ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%برگ دریافت چک%'
                  OR ISNULL(current_status.[CurrentStatusDescription], N'') LIKE N'%برگه دریافت چک%' THEN N'receipt_sheet_text'
                WHEN NULLIF(LTRIM(RTRIM(ISNULL(current_status.[CurrentStatusDescription], N''))), N'') IS NULL THEN N'empty_text'
                ELSE N'other_text'
            END
        ORDER BY [ChequeCount] DESC
        """
    )
    with _engine(engine).connect() as connection:
        rows = connection.execute(query).mappings().all()
    return {
        "status": "success",
        "source_system": "rahkaran_sql",
        "excel_used_as_data_source": False,
        "purpose": "calibrate_official_current_status",
        "signatures": [
            {
                "master_state": row["MasterState"],
                "transaction_state": row["CurrentChequeState"],
                "document_item_type": row["CurrentDocumentItemType"],
                "has_bank_account": bool(row["HasBankAccount"]),
                "description_class": row["DescriptionClass"],
                "count": int(row["ChequeCount"] or 0),
                "amount": _as_number(row["ChequeAmount"]),
                "min_due_date": _as_datetime(row["MinDueDate"]),
                "max_due_date": _as_datetime(row["MaxDueDate"]),
            }
            for row in rows
        ],
    }


# V125 diagnostic: discover the SQL scope rule behind the 26 rows that are absent
# from Rahkaran's official ListData report. Excel is validation only.
def analyze_received_cheque_official_scope_rule(excel_bytes: bytes, engine: Engine | None = None) -> dict[str, Any]:
    comparison = compare_received_open_sql_with_rahkaran_excel(excel_bytes, engine=engine)
    sql_only = comparison.get("sql_only", {}).get("rows", [])
    ids = [int(x["cheque_id"]) for x in sql_only if x.get("cheque_id") is not None]
    if not ids:
        return {"status":"success", "version":"V125", "sql_only_count":0, "message":"هیچ رکورد SQL-only وجود ندارد."}

    bind_names = ",".join(f":id{i}" for i in range(len(ids)))
    params = {f"id{i}": v for i, v in enumerate(ids)}
    # Return every master field for the 26 rows. This avoids guessing which
    # Rahkaran master column controls the report scope.
    q_master = text(f"SELECT * FROM RPA3.[ReceivableNote] WHERE [ReceivableNoteID] IN ({bind_names}) ORDER BY [ReceivableNoteID]")
    # Also inspect the receipt/creation document and all transaction signatures.
    q_tx = text(f"""
        SELECT rnt.[ReceivableNoteRef] AS [ChequeID], rnt.*
        FROM RPA3.[ReceivableNoteTransaction] rnt
        WHERE rnt.[ReceivableNoteRef] IN ({bind_names})
        ORDER BY rnt.[ReceivableNoteRef], rnt.[Date], rnt.[DocumentDate], rnt.[ReceivableNoteTransactionID]
    """)
    with _engine(engine).connect() as c:
        masters = [dict(r) for r in c.execute(q_master, params).mappings().all()]
        txs = [dict(r) for r in c.execute(q_tx, params).mappings().all()]

    def safe(v: Any):
        if v is None or isinstance(v, (str, int, float, bool)): return v
        if isinstance(v, Decimal): return float(v)
        if hasattr(v, "isoformat"): return v.isoformat()
        return str(v)
    masters = [{k:safe(v) for k,v in r.items()} for r in masters]
    txs = [{k:safe(v) for k,v in r.items()} for r in txs]

    # Profile master columns across the 26 rows. Constant/low-cardinality fields
    # are the strongest candidates for the hidden official-report scope filter.
    profile=[]
    if masters:
        for col in masters[0].keys():
            vals=[r.get(col) for r in masters]
            counts={}
            for v in vals:
                key="<NULL>" if v is None else str(v)
                counts[key]=counts.get(key,0)+1
            if len(counts) <= 12:
                profile.append({"column":col,"distinct_count":len(counts),"values":dict(sorted(counts.items(), key=lambda kv:(-kv[1],kv[0]))[:12])})
        profile.sort(key=lambda x:(x["distinct_count"], x["column"]))

    tx_profile={}
    for r in txs:
        sig=f"state={r.get('State')}|doc_state={r.get('DocumentState')}|item={r.get('DocumentItemType')}|bank={'yes' if r.get('BankAccountRef') is not None else 'no'}"
        tx_profile[sig]=tx_profile.get(sig,0)+1

    return {
        "status":"success",
        "version":"V125",
        "purpose":"discover_rahkaran_official_report_scope_rule",
        "dashboard_source_changed":False,
        "excel_runtime_source":False,
        "control_target":{"count":comparison.get("excel_open",{}).get("count"),"amount":comparison.get("excel_open",{}).get("amount")},
        "sql_only":{"count":len(ids),"amount":comparison.get("sql_only",{}).get("amount"),"ids":ids},
        "master_low_cardinality_profile":profile,
        "transaction_signature_counts":dict(sorted(tx_profile.items(), key=lambda kv:-kv[1])),
        "master_rows":masters,
        "transaction_rows":txs,
        "next_step":"V126 will turn the discovered general SQL scope rule into the shared received-cheque predicate and validate 795 / 757785104980 without using Excel at runtime."
    }


_B2B_INTERNAL_TOKENS = ("جاری شرکا", "جاري شرکا", "بابت انتقال", "انتقال از", "انتقال بین", "انتقال بانکی")
_B2B_REVERSE_TOKENS = ("بازگشت اعلامیه پرداخت", "بازگشت پرداخت", "برگشت اعلامیه پرداخت")
_B2B_CHEQUE_CASHOUT_TOKENS = ("نقد کردن چک", "نقدکردن چک")
_B2B_RETURNED_CHEQUE_TOKENS = ("چک برگشتی", "چک عودتی", "برگشتی", "واخواست")


def _b2b_remittance_category(description: Any) -> tuple[str, bool]:
    value = str(description or "").strip()
    if any(t in value for t in _B2B_INTERNAL_TOKENS):
        return "انتقال داخلی / جاری شرکا", False
    if any(t in value for t in _B2B_REVERSE_TOKENS):
        return "بازگشت پرداخت", False
    if any(t in value for t in _B2B_CHEQUE_CASHOUT_TOKENS):
        return "نقد کردن چک", False
    if any(t in value for t in _B2B_RETURNED_CHEQUE_TOKENS):
        return "تسویه چک برگشتی", True
    if "تامین موجودی" in value or "تأمین موجودی" in value:
        return "تأمین موجودی B2B", True
    if "فروش مواد اولیه" in value or "بابت فروش" in value or "فاکتور" in value:
        return "فروش / فاکتور B2B", True
    if "واریز" in value or "واریزی" in value or "دریافت از" in value:
        return "واریز مستقیم مشتری", True
    return "سایر دریافت بانکی", False




def get_customer_b2b_remittances(
    limit: int = 20000,
    counterpart_ref: int | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """واریزهای بانکی مشتریان از ReceiptDeposit با طبقه‌بندی قابل توضیح B2B."""
    safe_limit = max(1, min(int(limit), 20000))
    customer_where = "AND COALESCE(rd.[CounterPartRef], r.[CounterPartRef]) = :counterpart_ref" if counterpart_ref else ""
    query = text(f"""
        SELECT TOP ({safe_limit})
            r.[ReceiptID], r.[Number] AS [ReceiptNumber], r.[Date] AS [ReceiptDate],
            r.[ApproveDate], r.[ApproveState], r.[ReceiptType], r.[ItemType],
            COALESCE(rd.[CounterPartRef], r.[CounterPartRef]) AS [CounterPartRef],
            cp.[Code] AS [CustomerCode], cp.[Title] AS [CustomerName],
            rd.[ReceiptDepositID], rd.[Number] AS [DepositNumber], rd.[Date] AS [DepositDate],
            rd.[Amount] AS [AmountRial], rd.[CurrencyAmount], rd.[BankAccountRef], rd.[BankRef],
            rd.[BankBranchCode], rd.[BankBranchName], r.[BranchRef], r.[FiscalYearRef],
            r.[Description] AS [ReceiptDescription], rd.[Description] AS [DepositDescription]
        FROM RPA3.[Receipt] r
        INNER JOIN RPA3.[ReceiptDeposit] rd ON rd.[ReceiptRef] = r.[ReceiptID]
        LEFT JOIN FIN3.[DL] cp ON cp.[DLID] = COALESCE(rd.[CounterPartRef], r.[CounterPartRef])
        WHERE r.[ApproveState] IN (2, 3)
          AND COALESCE(rd.[CounterPartRef], r.[CounterPartRef]) IS NOT NULL
          {customer_where}
        ORDER BY rd.[Date] DESC, rd.[ReceiptDepositID] DESC
    """)
    params = {"counterpart_ref": counterpart_ref} if counterpart_ref else {}
    with _engine(engine).connect() as connection:
        db_rows = connection.execute(query, params).mappings().all()

    rows: list[dict[str, Any]] = []
    for row in db_rows:
        description = row["DepositDescription"] or row["ReceiptDescription"] or ""
        category, eligible = _b2b_remittance_category(description)
        rows.append({
            "receipt_deposit_id": row["ReceiptDepositID"], "receipt_id": row["ReceiptID"],
            "receipt_number": row["ReceiptNumber"], "receipt_date": _as_datetime(row["ReceiptDate"]),
            "deposit_number": row["DepositNumber"], "deposit_date": _as_datetime(row["DepositDate"]),
            "deposit_date_jalali": _as_jalali_date(row["DepositDate"]),
            "approve_date": _as_datetime(row["ApproveDate"]), "approve_state": row["ApproveState"],
            "approve_state_label": "تأیید نهایی" if row["ApproveState"] == 3 else "تأییدشده",
            "receipt_type": row["ReceiptType"], "item_type": row["ItemType"],
            "counterpart_ref": row["CounterPartRef"], "customer_code": row["CustomerCode"],
            "customer_name": row["CustomerName"], "amount_rial": _as_number(row["AmountRial"]),
            "currency_amount": _as_number(row["CurrencyAmount"]), "bank_account_ref": row["BankAccountRef"],
            "bank_ref": row["BankRef"], "bank_branch_code": row["BankBranchCode"],
            "bank_branch_name": row["BankBranchName"], "branch_ref": row["BranchRef"],
            "fiscal_year_ref": row["FiscalYearRef"], "description": description,
            "category": category, "is_b2b_customer_payment": eligible,
            "is_returned_cheque_settlement": category == "تسویه چک برگشتی", "source": "راهکاران",
        })

    eligible_rows = [x for x in rows if x["is_b2b_customer_payment"]]
    direct_rows = [x for x in eligible_rows if not x["is_returned_cheque_settlement"]]
    returned_rows = [x for x in eligible_rows if x["is_returned_cheque_settlement"]]
    customer_refs = {x["counterpart_ref"] for x in eligible_rows if x["counterpart_ref"] is not None}
    return {
        "status": "success", "source": "Rahkaran / RPA3.Receipt + ReceiptDeposit",
        "rows": rows,
        "summary": {
            "all_bank_deposit_count": len(rows),
            "b2b_count": len(eligible_rows),
            "b2b_amount_rial": sum(float(x["amount_rial"] or 0) for x in eligible_rows),
            "direct_count": len(direct_rows),
            "direct_amount_rial": sum(float(x["amount_rial"] or 0) for x in direct_rows),
            "returned_cheque_settlement_count": len(returned_rows),
            "returned_cheque_settlement_amount_rial": sum(float(x["amount_rial"] or 0) for x in returned_rows),
            "customer_count": len(customer_refs),
        },
        "classification_note": "انتقال داخلی/جاری شرکا، بازگشت پرداخت و نقد کردن چک از پرداخت B2B حذف می‌شوند؛ تسویه چک برگشتی جداگانه علامت‌گذاری می‌شود.",
    }


def get_customer_b2b_behavior(counterpart_ref: int, engine: Engine | None = None) -> dict[str, Any]:
    report = get_customer_b2b_remittances(limit=20000, counterpart_ref=counterpart_ref, engine=engine)
    rows = [x for x in report["rows"] if x["is_b2b_customer_payment"]]
    direct = [x for x in rows if not x["is_returned_cheque_settlement"]]
    returned = [x for x in rows if x["is_returned_cheque_settlement"]]
    total = sum(float(x["amount_rial"] or 0) for x in rows)
    direct_total = sum(float(x["amount_rial"] or 0) for x in direct)
    returned_total = sum(float(x["amount_rial"] or 0) for x in returned)
    return {
        "count": len(rows), "amount_rial": total,
        "direct_count": len(direct), "direct_amount_rial": direct_total,
        "returned_cheque_settlement_count": len(returned), "returned_cheque_settlement_amount_rial": returned_total,
        "returned_settlement_ratio_percent": round((returned_total / total * 100), 1) if total else 0,
        "average_amount_rial": round(total / len(rows), 2) if rows else 0,
        "last_payment_date": rows[0]["deposit_date"] if rows else None,
        "rows": rows,
    }
