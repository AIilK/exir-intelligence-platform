"""جستجوی حساب‌ها و گردش حساب راهکاران (از treasury_service.py جدا شده)."""

from __future__ import annotations
import re
from typing import Any
import unicodedata
from sqlalchemy import text
from sqlalchemy.engine import Engine
from app.core.config import settings
from app.services.treasury_common import (
    _as_datetime,
    _as_jalali_date,
    _as_number,
    _engine,
)


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


def _currency_name(currency_ref: Any) -> str | None:
    if currency_ref == settings.treasury_operational_currency_ref:
        return settings.treasury_operational_currency_name
    return None


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
    safe_limit = max(1, min(int(limit), 1000))

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
