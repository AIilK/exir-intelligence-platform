from datetime import date, datetime
from decimal import Decimal

from app.services.bank_reconciliation_service import (
    _candidate_score,
    _is_issued_cheque_term_change,
    _transaction_type_is_compatible,
)


def _bank(description: str = "برداشت از حساب", cheque_number: str = "431868"):
    return {
        "date": date(2026, 2, 13),
        "direction": "withdrawal",
        "amount": Decimal("250000000"),
        "description": description,
        "operation": "",
        "note": "",
        "reference": "",
        "bank_document_number": "",
        "deposit_id": "",
        "cheque_number": cheque_number,
        "payer": "",
        "origin_account": "",
    }


def _tx(description: str, item_number: str = "0140 431868"):
    return {
        "transaction_type": "issued_cheque_status",
        "effect": 2,
        "amount": Decimal("250000000"),
        "booking_date": datetime(2026, 2, 13),
        "settlement_date": datetime(2026, 2, 13),
        "description": description,
        "reference_ref": item_number,
        "item_number": item_number,
    }


def test_term_change_phrase_is_detected():
    assert _is_issued_cheque_term_change(
        _tx("تغییر مدت چک از بلند مدت به روز - تعیین وضعیت چک")
    )


def test_generic_tejarat_with_exact_serial_is_compatible():
    bank = _bank("برداشت اینترنتی")
    tx = _tx("تغییر مدت چک از بلندمدت به روز")
    assert _transaction_type_is_compatible(bank, tx)
    scored = _candidate_score(bank, tx, tolerance_days=2)
    assert scored is not None
    score, reasons = scored
    assert score >= 95
    assert any("سریال چک" in reason for reason in reasons)
    assert any("تغییر مدت" in reason for reason in reasons)


def test_generic_with_wrong_serial_is_rejected():
    bank = _bank("برداشت اینترنتی", cheque_number="999999")
    tx = _tx("تغییر مدت چک از بلندمدت به روز", item_number="0140 431868")
    assert not _transaction_type_is_compatible(bank, tx)
