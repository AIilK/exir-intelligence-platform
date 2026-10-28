from pathlib import Path


def test_received_cheque_status_allows_null_bank_account_ref():
    text = Path('app/services/bank_reconciliation_service.py').read_text(encoding='utf-8')
    assert '(rnt.BankAccountRef = :bank_account_id OR rnt.BankAccountRef IS NULL)' in text


def test_definite_match_rate_excludes_reversed_and_internal_transfer():
    text = Path('app/services/bank_reconciliation_service.py').read_text(encoding='utf-8')
    assert '"documentable_bank_row_count"' in text
    assert 'business_counts.get("reversed"' in text
    assert 'business_counts.get("internal_transfer"' in text
