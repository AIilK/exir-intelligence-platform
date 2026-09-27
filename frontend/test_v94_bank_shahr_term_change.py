from datetime import date
from decimal import Decimal

from app.services.bank_reconciliation_service import (
    _candidate_score,
    _is_generic_bank_cheque_text,
    _transaction_type_is_compatible,
)


def _tx(amount="125000000", dt=date(2026, 8, 10), desc="تغيير مدت چک عهده ما | تعيين وضعيت چک"):
    return {
        "transaction_type": "issued_cheque_status",
        "effect": 2,
        "amount": Decimal(amount),
        "booking_date": dt,
        "settlement_date": dt,
        "description": desc,
        "reference_ref": "431868",
        "item_number": "431868",
    }


def test_bank_shahr_generic_cheque_text_is_detected_without_serial():
    row = {
        "date": date(2026, 8, 11),
        "direction": "withdrawal",
        "amount": Decimal("125000000"),
        "description": "برداشت بابت چک عهده بانک شهر",
        "reference": "",
        "operation": "",
        "note": "",
        "bank_document_number": "",
        "deposit_id": "",
        "cheque_number": "",
    }
    assert _is_generic_bank_cheque_text(row)
    assert _transaction_type_is_compatible(row, _tx())
    assert _candidate_score(row, _tx(), 2) is not None


def test_bank_shahr_term_change_can_match_within_seven_days_without_serial():
    row = {
        "date": date(2026, 8, 16),
        "direction": "withdrawal",
        "amount": Decimal("125000000"),
        "description": "برداشت چک",
        "reference": "",
        "operation": "",
        "note": "",
        "bank_document_number": "",
        "deposit_id": "",
        "cheque_number": "",
    }
    scored = _candidate_score(row, _tx(dt=date(2026, 8, 10)), 2)
    assert scored is not None
    score, reasons = scored
    assert score >= 75
    assert any("تغییر مدت" in reason or "تعیین وضعیت" in reason for reason in reasons)


def test_non_cheque_generic_with_no_serial_is_rejected():
    row = {
        "date": date(2026, 8, 10),
        "direction": "withdrawal",
        "amount": Decimal("125000000"),
        "description": "برداشت ساتنا بابت خرید مواد اولیه",
        "reference": "",
        "operation": "",
        "note": "",
        "bank_document_number": "",
        "deposit_id": "",
        "cheque_number": "",
    }
    assert not _transaction_type_is_compatible(row, _tx())
    assert _candidate_score(row, _tx(), 2) is None
