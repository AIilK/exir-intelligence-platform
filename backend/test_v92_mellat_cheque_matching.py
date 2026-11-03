from decimal import Decimal
from datetime import date
from app.services.bank_reconciliation_service import (
    _is_bank_cheque_event,
    _is_bank_issued_cheque_event,
    _candidate_score,
)


def _bank(direction, description, amount=1000000000):
    return {
        "direction": direction,
        "description": description,
        "operation": "",
        "note": "",
        "payer": "",
        "origin_account": "",
        "reference": "",
        "bank_document_number": "",
        "deposit_id": "",
        "cheque_number": "",
        "date": date(2026, 8, 25),
        "amount": Decimal(str(amount)),
    }


def _tx(effect, tx_type, amount=1000000000):
    return {
        "effect": effect,
        "transaction_type": tx_type,
        "amount": Decimal(str(amount)),
        "booking_date": date(2026, 8, 25),
        "settlement_date": None,
        "description": "",
        "reference_ref": "",
        "item_number": "",
    }


def test_mellat_incoming_cheque_clear_is_explicit_cheque_event():
    row = _bank("deposit", "واریز چک کلر بانک تجارت ۲۸۰۱۹۴۲۲۲")
    assert _is_bank_cheque_event(row)
    assert _candidate_score(row, _tx(1, "received_cheque_status"), 2) is not None


def test_mellat_jam_cheque_deposit_is_explicit_cheque_event():
    row = _bank("deposit", "واریزواگذاری جام به حساب ذینفع کاربر چکاوک")
    assert _is_bank_cheque_event(row)


def test_mellat_issued_cheque_collection_is_explicit_issued_event():
    row = _bank("withdrawal", "وصول چک چکاوک۱۴۸۹۶۶۵۱۹-۱۹۴۹/۴۲۶۸۶۶۲۴")
    assert _is_bank_issued_cheque_event(row)
    assert _candidate_score(row, _tx(2, "issued_cheque_status"), 2) is not None


def test_mellat_transfer_by_cheque_is_explicit_issued_event():
    row = _bank("withdrawal", "برداشت انتقالی طی چک 42686315")
    assert _is_bank_issued_cheque_event(row)


def test_mellat_cheque_assignment_is_bank_fee():
    from app.services.bank_reconciliation_service import _is_fee_text
    assert _is_fee_text("واگذاری چک بانک ملی ایران ۲۸۱۶۲۵۲۸۵")
    assert _is_fee_text("واگذاری چک بانک سپه ۲۸۲۹۱۶۶۳۲")
