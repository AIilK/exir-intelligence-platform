from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services.bank_reconciliation_service import (
    _candidate_score,
    _is_received_cheque_collection_transaction,
    _transaction_type_is_compatible,
)


def _bank_row(dt=date(2026, 9, 3), amount='300000000', description='تعيين وضعيت چک عادي عهده ساير /1864/82439115'):
    return {
        'date': dt,
        'direction': 'deposit',
        'amount': Decimal(amount),
        'description': description,
        'reference': '',
        'operation': '',
        'note': '',
        'bank_document_number': '',
        'deposit_id': '',
        'cheque_number': '',
        'payer': '',
        'origin_account': '',
    }


def _tx(dt=date(2026, 9, 1), amount='300000000', item_number='82439115 1864 1234567890123456'):
    return {
        'transaction_type': 'received_cheque_status',
        'effect': 1,
        'amount': Decimal(amount),
        'booking_date': dt,
        'settlement_date': dt,
        'description': 'وصولی | وصولی',
        'reference_ref': item_number,
        'item_number': item_number,
    }


def test_received_collection_text_is_recognized():
    assert _is_received_cheque_collection_transaction(_tx())


def test_bank_shahr_received_cheque_can_match_by_exact_serial_with_date_gap():
    row = _bank_row(dt=date(2026, 9, 8))
    tx = _tx(dt=date(2026, 9, 1))
    assert _transaction_type_is_compatible(row, tx)
    scored = _candidate_score(row, tx, 2)
    assert scored is not None
    score, reasons = scored
    assert score >= 90
    assert any('سریال چک' in reason for reason in reasons)


def test_bank_shahr_received_collection_can_match_without_serial_within_seven_days():
    row = _bank_row(
        dt=date(2026, 9, 6),
        description='تعيين وضعيت چک عادي عهده ساير - بانک شهر',
    )
    tx = _tx(dt=date(2026, 9, 1), item_number='999999 1111')
    assert _transaction_type_is_compatible(row, tx)
    scored = _candidate_score(row, tx, 2)
    assert scored is not None
    score, reasons = scored
    assert score >= 75
    assert any('وصول / تعیین وضعیت' in reason for reason in reasons)


def test_sql_no_longer_hardcodes_state3_or_itemtype12_for_received_cheque_status():
    text = Path('app/services/bank_reconciliation_service.py').read_text(encoding='utf-8')
    assert 'rnt.State = 3\n                OR rnt.DocumentItemType = 12' in text
    assert "LIKE N'%وصول%'" in text
    assert ':received_cheque_start_date' in text
    assert ':received_cheque_end_date' in text
    assert 'rnt.DocumentState = 3' in text
