"""تسویه چک‌های مشتری: مانده و وضعیت هر چک در برابر بدهی (از treasury_service.py جدا شده)."""

from __future__ import annotations
from decimal import Decimal
from typing import Any
from sqlalchemy import text
from sqlalchemy.engine import Engine
from app.core.config import settings
from app.services.treasury_common import (
    _as_datetime,
    _as_jalali_date,
    _as_number,
    _engine,
)
from app.services.treasury_accounts import _currency_name, _normalize_account_search


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
            11: "issued_open_unposted",
            15: "restored_or_cancelled",
            # Business rule confirmed by Finance: when the payable cheque is
            # withdrawn from the bank, Rahkaran moves it out of the long-term
            # bucket into the daily/cleared state. In this installation that
            # finalized state is 28 and it means the cheque has been posted.
            28: "posted_withdrawn",
            -27: "clearing_reversed",
            -12: "issue_reversed",
        },
    }
    return labels.get(cheque_type, {}).get(state, "unknown")


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
