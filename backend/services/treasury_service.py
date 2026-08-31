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


_PERSIAN_SEARCH_TRANSLATION = str.maketrans(
    {
        "آ": "ا",
        "أ": "ا",
        "إ": "ا",
        "ٱ": "ا",
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "\u200c": " ",
    }
)


def _normalize_account_search(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    normalized = normalized.translate(_PERSIAN_SEARCH_TRANSLATION)
    normalized = re.sub(r"[^\w\u0600-\u06ff]+", " ", normalized)
    return " ".join(normalized.split())


def _as_number(value: Any) -> int | float:
    if value is None:
        return 0.0
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    if number == number.to_integral_value():
        return int(number)
    return float(number)


def _as_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _as_jalali_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        import jdatetime
    except ImportError:
        return None

    if isinstance(value, datetime):
        gregorian_date = value.date()
    elif isinstance(value, date):
        gregorian_date = value
    else:
        try:
            gregorian_date = datetime.fromisoformat(str(value)).date()
        except ValueError:
            return None

    return jdatetime.date.fromgregorian(date=gregorian_date).isoformat().replace("-", "/")


def _currency_name(currency_ref: Any) -> str | None:
    if currency_ref == settings.treasury_operational_currency_ref:
        return settings.treasury_operational_currency_name
    return None


def _cheque_state_label(cheque_type: str, state: int) -> str:
    """برچسب‌های تأییدشده یا استنباط‌شده از تراکنش‌های واقعی راهکاران."""

    labels = {
        "received": {
            1: "registered",
            2: "in_collection",
            3: "collected",
            4: "protested",
            10: "delivered_to_counterparty",
        },
        "issued": {
            11: "issued_active",
        },
    }
    return labels.get(cheque_type, {}).get(state, "unknown")


def _master_cheque_payload(row: Any, cheque_type: str) -> dict[str, Any]:
    state = row["ChequeState"]
    return {
        "cheque_id": row["ChequeID"],
        "cheque_type": cheque_type,
        "state_code": state,
        "state": _cheque_state_label(cheque_type, state),
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
    }


def _engine(engine: Engine | None) -> Engine:
    return engine or get_sqlserver_engine()


def _account_payload(row: Any) -> dict[str, Any]:
    return {
        "account_id": row["AccountID"],
        "name": row["Name"],
        "number": row["Number"],
        "currency_ref": row["CurrencyRef"],
        "currency_name": _currency_name(row["CurrencyRef"]),
        "account_type_ref": row["AccountTypeRef"],
        "party_ref": row["PartyRef"],
        "status": row["Status"],
        "debit": _as_number(row["DebitBalance"]),
        "credit": _as_number(row["CreditBalance"]),
        "balance": _as_number(row["Balance"]),
    }


def search_accounts(
    account_name: str,
    limit: int = 20,
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    """حساب‌ها را بدون انتخاب خودکار یک نتیجه مبهم جست‌وجو می‌کند."""

    search_term = _normalize_account_search(account_name)
    if not search_term:
        return []

    safe_limit = max(1, min(int(limit), 50))
    tokens = search_term.split()[:8]

    normalized_name_sql = """
        REPLACE(
            REPLACE(
                REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(Name, N'آ', N'ا'),
                            N'أ', N'ا'
                        ),
                        N'إ', N'ا'
                    ),
                    N'ي', N'ی'
                ),
                N'ى', N'ی'
            ),
            N'ك', N'ک'
        )
    """

    token_filters = " AND ".join(
        f"{normalized_name_sql} LIKE :token_{index}"
        for index in range(len(tokens))
    )

    query = text(
        f"""
        SELECT TOP ({safe_limit})
            AccountID,
            Name,
            Number,
            CurrencyRef,
            AccountTypeRef,
            PartyRef,
            Status,
            DebitBalance,
            CreditBalance,
            Balance
        FROM FIN3.Account
        WHERE {token_filters}
        ORDER BY
            CASE
                WHEN LTRIM(RTRIM({normalized_name_sql})) = :exact_name
                THEN 0 ELSE 1
            END,
            Name,
            CurrencyRef
        """
    )

    parameters = {
        f"token_{index}": f"%{token}%"
        for index, token in enumerate(tokens)
    }
    parameters["exact_name"] = search_term

    with _engine(engine).connect() as connection:
        rows = connection.execute(
            query,
            parameters,
        ).mappings().all()

    return [_account_payload(row) for row in rows]


def _get_account_by_id(
    account_id: int,
    engine: Engine | None = None,
) -> dict[str, Any] | None:
    query = text(
        """
        SELECT
            AccountID,
            Name,
            Number,
            CurrencyRef,
            AccountTypeRef,
            PartyRef,
            Status,
            DebitBalance,
            CreditBalance,
            Balance
        FROM FIN3.Account
        WHERE AccountID = :account_id
        """
    )

    with _engine(engine).connect() as connection:
        row = connection.execute(
            query,
            {"account_id": int(account_id)},
        ).mappings().first()

    return _account_payload(row) if row else None


def _resolve_account(
    account_name: str | None,
    account_id: int | None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    if account_id is not None:
        account = _get_account_by_id(account_id, engine=engine)
        if account is None:
            return {
                "status": "not_found",
                "message": "حساب با شناسه داده‌شده پیدا نشد.",
            }
        return {"status": "success", "account": account}

    matches = search_accounts(account_name or "", engine=engine)

    if not matches:
        return {
            "status": "not_found",
            "message": "حساب پیدا نشد.",
        }

    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "message": "چند حساب پیدا شد؛ حساب و ارز موردنظر را مشخص کنید.",
            "matches": matches,
        }

    return {"status": "success", "account": matches[0]}


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


def get_account_transactions(
    account_name: str | None = None,
    limit: int = 10,
    account_id: int | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """گردش عمومی حساب را از هسته FIN3.Transaction دریافت می‌کند."""

    resolved = _resolve_account(account_name, account_id, engine=engine)
    if resolved["status"] != "success":
        return resolved

    account = resolved["account"]
    safe_limit = max(1, min(int(limit), 100))

    transactions_query = text(
        f"""
        SELECT TOP ({safe_limit})
            TransactionID,
            BookingDate,
            SettlementDate,
            Description,
            EntryAmount,
            GLAmount,
            Effect,
            Status,
            ReferenceTypeComponentName,
            ReferenceTypeEntityName,
            ReferenceRef
        FROM FIN3.[Transaction]
        WHERE AccountRef = :account_id
          AND Status = 1
        ORDER BY BookingDate DESC, TransactionID DESC
        """
    )

    summary_query = text(
        """
        SELECT
            COALESCE(SUM(CASE WHEN Effect = 1 THEN EntryAmount ELSE 0 END), 0)
                AS DebitTotal,
            COALESCE(SUM(CASE WHEN Effect = 2 THEN EntryAmount ELSE 0 END), 0)
                AS CreditTotal
        FROM FIN3.[Transaction]
        WHERE AccountRef = :account_id
          AND Status = 1
        """
    )

    with _engine(engine).connect() as connection:
        transaction_rows = connection.execute(
            transactions_query,
            {"account_id": account["account_id"]},
        ).mappings().all()
        summary = connection.execute(
            summary_query,
            {"account_id": account["account_id"]},
        ).mappings().one()

    transactions = []
    for row in transaction_rows:
        effect = row["Effect"]
        transactions.append(
            {
                "transaction_id": row["TransactionID"],
                "booking_date": _as_datetime(row["BookingDate"]),
                "booking_date_jalali": _as_jalali_date(row["BookingDate"]),
                "settlement_date": _as_datetime(row["SettlementDate"]),
                "settlement_date_jalali": _as_jalali_date(row["SettlementDate"]),
                "description": row["Description"],
                "amount": _as_number(row["EntryAmount"]),
                "gl_amount": _as_number(row["GLAmount"]),
                "gl_currency_name": settings.treasury_operational_currency_name,
                "effect": effect,
                "side": (
                    "debit"
                    if effect == 1
                    else "credit"
                    if effect == 2
                    else "unknown"
                ),
                "status": row["Status"],
                "reference_component": row["ReferenceTypeComponentName"],
                "reference_entity": row["ReferenceTypeEntityName"],
                "reference_ref": row["ReferenceRef"],
            }
        )

    debit_total = _as_number(summary["DebitTotal"])
    credit_total = _as_number(summary["CreditTotal"])

    return {
        "status": "success",
        "account": account,
        "summary": {
            "debit_total": debit_total,
            "credit_total": credit_total,
            "calculated_balance": debit_total - credit_total,
            "stored_balance": account["balance"],
            "gl_currency_name": settings.treasury_operational_currency_name,
        },
        "transactions": transactions,
        "returned_count": len(transactions),
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

    safe_limit = max(1, min(int(limit), 100))
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
        "cheques": cheques,
        "returned_count": len(cheques),
        "returned_total_amount": sum(
            cheque["amount"] for cheque in cheques
        ),
    }


def get_latest_issued_cheques(
    limit: int = 10,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """آخرین چک‌های ثبت‌شده در اسناد پرداخت تأییدشده را برمی‌گرداند."""

    safe_limit = max(1, min(int(limit), 100))
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
            payment.[Description] AS [DocumentDescription]
        FROM RPA3.[PaymentPayableNote] AS note
        INNER JOIN RPA3.[Payment] AS payment
            ON payment.[PaymentID] = note.[PaymentRef]
        LEFT JOIN RPA3.[PayableNote] AS master_note
            ON master_note.[PayableNoteID] = note.[PayableNoteRef]
        LEFT JOIN RPA3.[Bank] AS bank
            ON bank.[BankID] = note.[BankRef]
        LEFT JOIN FIN3.[DL] AS counterpart
            ON counterpart.[DLID] = note.[CounterPartRef]
        WHERE payment.[ApproveState] = 3
          AND note.[NoteType] = 1
        ORDER BY
            payment.[Date] DESC,
            note.[PaymentPayableNoteID] DESC
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
        "cheques": cheques,
        "returned_count": len(cheques),
        "returned_total_amount": sum(
            cheque["amount"] for cheque in cheques
        ),
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
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND note.[State] IN ({state_sql})
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
        WHERE note.[NoteType] = 1
          AND note.[NormalORGuarantee] = 1
          AND note.[State] IN ({state_sql})
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
        "active_state_filter": list(configuration["active_states"]),
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
        "cheques": cheques,
        "returned_count": len(cheques),
        "returned_total_amount": sum(
            cheque["amount"] for cheque in cheques
        ),
    }


def _owner_name_matches_debtor(
    debtor_name: str | None,
    cheque_account_text: str | None,
) -> bool | None:
    """Informational only; allocation never depends on this fuzzy comparison."""

    account_text = _normalize_account_search(cheque_account_text or "")
    debtor_text = _normalize_account_search(debtor_name or "")
    if not account_text or not debtor_text:
        return None
    ignored = {
        "شرکت",
        "بازرگانی",
        "دریافتنی",
        "ریال",
        "اشخاص",
        "تجاری",
    }
    debtor_tokens = {
        token
        for token in debtor_text.split()
        if len(token) >= 3 and token not in ignored
    }
    if not debtor_tokens:
        return None
    return any(token in account_text for token in debtor_tokens)


def _settlement_remaining(
    opening_debt: Decimal,
    settlement_amount: Decimal,
) -> tuple[Decimal, Decimal]:
    difference = opening_debt - settlement_amount
    return max(difference, Decimal("0")), max(-difference, Decimal("0"))


def _build_customer_cheque_settlement_payload(
    *,
    cheque_rows: list[Any],
    account_rows: list[Any],
    counterpart_ref: int,
    counterpart_code: str | None,
    counterpart_name: str | None,
    opening_debt: Decimal | None,
) -> dict[str, Any]:
    """Build safe many-cheques-to-one-debtor totals from explicit ERP refs."""

    cheques: list[dict[str, Any]] = []
    state_amounts: dict[str, Decimal] = {
        "registered": Decimal("0"),
        "in_collection": Decimal("0"),
        "collected": Decimal("0"),
        "protested": Decimal("0"),
        "delivered_to_counterparty": Decimal("0"),
        "unknown": Decimal("0"),
    }
    state_counts = {state: 0 for state in state_amounts}

    for row in cheque_rows:
        state_code = row["ChequeState"]
        state = _cheque_state_label("received", state_code)
        amount = Decimal(str(row["Amount"] or 0))
        state_amounts.setdefault(state, Decimal("0"))
        state_counts.setdefault(state, 0)
        state_amounts[state] += amount
        state_counts[state] += 1
        allocation_source = (
            "receipt_note_counterpart"
            if row["NoteCounterPartRef"] is not None
            else "receipt_document_counterpart"
        )
        owner_matches = _owner_name_matches_debtor(
            counterpart_name,
            row["AccountNumber"],
        )
        cheques.append(
            {
                "cheque_id": row["ChequeID"],
                "cheque_item_id": row["ChequeItemID"],
                "document_id": row["DocumentID"],
                "document_number": row["DocumentNumber"],
                "document_date": _as_datetime(row["DocumentDate"]),
                "document_date_jalali": _as_jalali_date(row["DocumentDate"]),
                "amount": _as_number(amount),
                "due_date": _as_datetime(row["DueDate"]),
                "due_date_jalali": _as_jalali_date(row["DueDate"]),
                "serial_number": row["SerialNumber"],
                "series": row["Series"],
                "sayad_number": row["SayadNumber"],
                "cheque_account_text": row["AccountNumber"],
                "bank_name": row["BankName"],
                "state_code": state_code,
                "state": state,
                "allocated_debtor_ref": counterpart_ref,
                "allocated_debtor_name": counterpart_name,
                "allocation_source": allocation_source,
                "allocation_is_explicit": True,
                "owner_name_matches_debtor": owner_matches,
                "third_party_indicator": owner_matches is False,
                "description": (
                    row["ChequeDescription"]
                    or row["DocumentDescription"]
                ),
            }
        )

    received_total = sum(state_amounts.values(), Decimal("0"))
    collected_total = state_amounts.get("collected", Decimal("0"))
    pending_total = (
        state_amounts.get("registered", Decimal("0"))
        + state_amounts.get("in_collection", Decimal("0"))
    )
    provisional_settlement = collected_total + pending_total
    third_party_count = sum(
        1 for cheque in cheques if cheque["third_party_indicator"]
    )
    current_book_balance = sum(
        (Decimal(str(row["Balance"] or 0)) for row in account_rows),
        Decimal("0"),
    )

    debt_calculation: dict[str, Any] | None = None
    if opening_debt is not None:
        confirmed_remaining, confirmed_overpayment = _settlement_remaining(
            opening_debt,
            collected_total,
        )
        provisional_remaining, provisional_overpayment = _settlement_remaining(
            opening_debt,
            provisional_settlement,
        )
        debt_calculation = {
            "opening_debt": _as_number(opening_debt),
            "confirmed_settlement_collected_only": _as_number(collected_total),
            "confirmed_remaining_debt": _as_number(confirmed_remaining),
            "confirmed_overpayment": _as_number(confirmed_overpayment),
            "provisional_settlement_collected_and_pending": _as_number(
                provisional_settlement
            ),
            "provisional_remaining_debt": _as_number(provisional_remaining),
            "provisional_overpayment": _as_number(provisional_overpayment),
            "protested_cheques_are_excluded": True,
        }

    return {
        "status": "success",
        "report_type": "customer_cheque_settlement",
        "debtor": {
            "counterpart_ref": counterpart_ref,
            "code": counterpart_code,
            "name": counterpart_name,
        },
        "allocation_rule": (
            "CounterPartRef ردیف چک؛ در نبود آن CounterPartRef سند دریافت"
        ),
        "owner_name_is_not_used_for_allocation": True,
        "current_receivable_accounts": [
            {
                "account_id": row["AccountID"],
                "name": row["AccountName"],
                "number": row["AccountNumber"],
                "balance": _as_number(row["Balance"]),
                "currency_ref": row["CurrencyRef"],
                "currency_name": _currency_name(row["CurrencyRef"]),
            }
            for row in account_rows
        ],
        "current_book_balance_total": _as_number(current_book_balance),
        "summary": {
            "cheque_count": len(cheques),
            "received_cheque_total": _as_number(received_total),
            "collected_total": _as_number(collected_total),
            "pending_total": _as_number(pending_total),
            "protested_total": _as_number(
                state_amounts.get("protested", Decimal("0"))
            ),
            "third_party_indicator_count": third_party_count,
            "state_counts": state_counts,
            "state_amounts": {
                key: _as_number(value) for key, value in state_amounts.items()
            },
        },
        "debt_calculation": debt_calculation,
        "cheques": cheques,
        "returned_count": len(cheques),
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
        INNER JOIN FIN3.[DL] AS dl
            ON dl.[DLID] = COALESCE(
                note.[CounterPartRef], receipt.[CounterPartRef]
            )
        WHERE receipt.[ApproveState] = 3
          AND receipt.[ItemType] = 1
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


def get_customer_cheque_settlement(
    *,
    counterpart_ref: int,
    opening_debt: str | int | float | Decimal | None = None,
    limit: int = 500,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Report multiple own/third-party cheques allocated to one debtor."""

    safe_limit = max(1, min(int(limit), 1000))
    parsed_opening_debt: Decimal | None = None
    if opening_debt not in (None, ""):
        try:
            parsed_opening_debt = Decimal(str(opening_debt))
        except Exception as exc:
            raise ValueError("opening_debt must be a valid number") from exc
        if parsed_opening_debt < 0:
            raise ValueError("opening_debt cannot be negative")

    cheque_query = text(
        f"""
        SELECT TOP ({safe_limit})
            note.[ReceiptReceivableNoteID] AS [ChequeItemID],
            note.[ReceivableNoteRef] AS [ChequeID],
            receipt.[ReceiptID] AS [DocumentID],
            receipt.[Number] AS [DocumentNumber],
            receipt.[Date] AS [DocumentDate],
            note.[Amount], note.[DueDate], note.[SerialNumber], note.[Series],
            note.[SayadNumber], note.[AccountNumber],
            note.[CounterPartRef] AS [NoteCounterPartRef],
            receipt.[CounterPartRef] AS [DocumentCounterPartRef],
            master_note.[State] AS [ChequeState],
            bank.[Name] AS [BankName],
            dl.[Code] AS [CounterPartCode],
            dl.[Title] AS [CounterPartName],
            note.[Description] AS [ChequeDescription],
            receipt.[Description] AS [DocumentDescription]
        FROM RPA3.[ReceiptReceivableNote] AS note
        INNER JOIN RPA3.[Receipt] AS receipt
            ON receipt.[ReceiptID] = note.[ReceiptRef]
        LEFT JOIN RPA3.[ReceivableNote] AS master_note
            ON master_note.[ReceivableNoteID] = note.[ReceivableNoteRef]
        LEFT JOIN RPA3.[Bank] AS bank ON bank.[BankID] = note.[BankRef]
        INNER JOIN FIN3.[DL] AS dl
            ON dl.[DLID] = COALESCE(
                note.[CounterPartRef], receipt.[CounterPartRef]
            )
        WHERE receipt.[ApproveState] = 3
          AND receipt.[ItemType] = 1
          AND COALESCE(note.[CounterPartRef], receipt.[CounterPartRef])
              = :counterpart_ref
          AND note.[CurrencyRef] = :currency_ref
        ORDER BY receipt.[Date] DESC, note.[ReceiptReceivableNoteID] DESC
        """
    )
    account_query = text(
        """
        SELECT
            account.[AccountID], account.[Name] AS [AccountName],
            account.[Number] AS [AccountNumber], account.[Balance],
            account.[CurrencyRef]
        FROM FIN3.[Account] AS account
        INNER JOIN FIN3.[DL] AS dl
            ON dl.[ReferenceID] = account.[PartyRef]
        WHERE dl.[DLID] = :counterpart_ref
          AND account.[CurrencyRef] = :currency_ref
          AND account.[Status] = 2
        ORDER BY account.[AccountID]
        """
    )
    parameters = {
        "counterpart_ref": int(counterpart_ref),
        "currency_ref": settings.treasury_operational_currency_ref,
    }
    with _engine(engine).connect() as connection:
        cheque_rows = connection.execute(
            cheque_query, parameters
        ).mappings().all()
        account_rows = connection.execute(
            account_query, parameters
        ).mappings().all()

    if not cheque_rows:
        return {
            "status": "not_found",
            "message": "برای این طرف حساب چک دریافتی تخصیص‌یافته پیدا نشد.",
            "counterpart_ref": int(counterpart_ref),
        }
    first = cheque_rows[0]
    return _build_customer_cheque_settlement_payload(
        cheque_rows=cheque_rows,
        account_rows=account_rows,
        counterpart_ref=int(counterpart_ref),
        counterpart_code=first["CounterPartCode"],
        counterpart_name=first["CounterPartName"],
        opening_debt=parsed_opening_debt,
    )


def get_receivable_report() -> dict[str, Any]:
    """تا زمان تأیید تعریف تجاری دریافتنی، عدد احتمالی تولید نمی‌کند."""

    return {
        "status": "not_ready",
        "message": (
            "تعریف و Query گزارش دریافتنی هنوز توسط واحد خزانه تأیید نشده است."
        ),
    }
