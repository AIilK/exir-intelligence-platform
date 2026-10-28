from datetime import date, datetime
from decimal import Decimal

from app.services.bank_reconciliation_service import (
    _attach_balances,
    _attach_fee_details,
    _candidate_score,
    _is_fee_text,
    _match_bank_reversal_pairs,
    _match_daily_fee_groups,
)


DAY = date(2026, 7, 26)


def _bank(
    description: str,
    amount: str,
    direction: str = "deposit",
    row_number: int = 1,
    time: str = "",
):
    return {
        "row_number": row_number,
        "date": DAY,
        "direction": direction,
        "amount": Decimal(amount),
        "description": description,
        "operation": "",
        "note": "",
        "reference": "",
        "bank_document_number": "",
        "deposit_id": "",
        "cheque_number": "",
        "payer": "",
        "origin_account": "",
        "branch": "",
        "time": time,
        "balance": None,
    }


def _tx(
    transaction_type: str,
    amount: str,
    description: str,
    item_number: str = "",
    document_id: int = 1,
):
    return {
        "transaction_id": f"{transaction_type}:{document_id}:{item_number}",
        "transaction_type": transaction_type,
        "effect": 1 if transaction_type in {"receipt", "received_cheque_status"} else 2,
        "amount": Decimal(amount),
        "booking_date": datetime(2026, 7, 26),
        "settlement_date": datetime(2026, 7, 26),
        "description": description,
        "reference_ref": item_number,
        "item_number": item_number,
        "document_id": document_id,
        "document_number": str(document_id),
        "reference_component": "RPA3",
        "reference_entity": "",
    }


SEPAH_CHEQUE = (
    "تعين وضعيت چک عادي عهده ساير ، چ ش/0347/780148 "
    "شباIR650150000003001295833656بانک ملي4048"
)


def test_cheque_with_other_serial_is_not_a_candidate():
    # «مشکوک وصول» نام گروه مشتری است و چک سریال دیگری دارد.
    other_cheque = _tx(
        "received_cheque_status",
        "300000000",
        "برگ دریافت چک . احسان نوروزی (جوو) - تهران-مشکوک وصول",
        "278238 403009 4955040149940690",
    )
    assert _candidate_score(_bank(SEPAH_CHEQUE, "300000000"), other_cheque, 2) is None

    receipt = _tx("receipt", "300000000", "وصول چک")
    scored = _candidate_score(_bank(SEPAH_CHEQUE, "300000000"), receipt, 2)
    assert scored is not None and scored[0] >= 90


def test_receipt_listing_bank_serial_gets_serial_evidence():
    bank = _bank(
        "تعين وضعيت چک عادي عهده ساير ، چ ش/6083/806197 شباIR65015",
        "100000000",
    )
    receipt = _tx(
        "receipt",
        "100000000",
        "نقد کردن چکهای 956902-874351-087699-806197-167384",
    )
    score, reasons = _candidate_score(bank, receipt, 2)
    assert score >= 95
    assert any("سریال چک" in reason for reason in reasons)


def test_same_bank_cheque_shown_as_transfer_matches_by_serial():
    bank = _bank(
        "انتقال وجه از سپرده جاري کيميا تجارت پايون به سپرده قرض الحسنه "
        "از 0149 679540,3001436760792,3100050551000",
        "20350000000",
    )
    cheque = _tx(
        "received_cheque_status",
        "20350000000",
        "",
        "679540 0149 9879040042498234",
    )
    score, _ = _candidate_score(bank, cheque, 2)
    assert score >= 90


def test_sepah_assignment_wording_is_fee():
    assert _is_fee_text("دريافت وجه واگذاري  و  واگذاري | طرف بدهکار")


def test_daily_fees_split_across_two_documents_match_together():
    rows = [
        _bank("برداشت کارمزد دستور پرداخت سمت متعهد", "40000", "withdrawal", 1),
        _bank("برداشت کارمزد دريافت کارمزد واگذاري چک عادي", "18000", "withdrawal", 2),
        _bank("برداشت کارمزد دريافت کارمزد واگذاري چک عادي", "18000", "withdrawal", 3),
    ]
    documents = [
        _tx("payment", "58000", "کارمزد بانکی", "521", document_id=33438),
        _tx("payment", "18000", "کارمزد بانکی", "15", document_id=33439),
    ]
    results, used = _match_daily_fee_groups(rows, documents)
    assert {result["business_status"] for result in results.values()} == {"posted"}
    assert len(results) == 3
    assert len(used) == 2
    matched = results[0]["matched_transaction"]
    assert matched["amount"] == 76000
    assert len(matched["member_documents"]) == 2


def test_reversal_of_one_of_two_identical_fees_is_paired():
    rows = [
        _bank("برداشت کارمزد دستور پرداخت سمت متعهد", "5000", "withdrawal", 169),
        _bank("برداشت کارمزد دستور پرداخت سمت متعهد", "5000", "withdrawal", 171),
        _bank(
            "برگشت عمليات  برداشت کارمزد دستور پرداخت سمت متعهد | بازگشت عملیات",
            "5000",
            "deposit",
            173,
        ),
    ]
    results = _match_bank_reversal_pairs(rows)
    assert set(results) == {1, 2}


def test_fee_is_attached_to_same_time_transfer():
    results = [
        {"row_number": 32, "bank_date": "2026-07-25", "time": "12:08:8",
         "direction": "withdrawal", "amount": 816200000.0,
         "description": "دستور پرداخت صادره پايا", "business_status": "posted"},
        {"row_number": 33, "bank_date": "2026-07-25", "time": "12:08:8",
         "direction": "withdrawal", "amount": 75000.0,
         "description": "برداشت کارمزد کارمزد پايا", "business_status": "posted"},
    ]
    summary = _attach_fee_details(results)
    assert results[1]["fee_kind"] == "کارمزد پایا"
    assert results[1]["fee_parent_row_number"] == 32
    assert results[0]["fee_amount"] == 75000.0
    assert summary["total_amount"] == 75000.0


def test_balances_compare_bank_and_book_per_day_and_document():
    results = [
        {"row_number": 1, "bank_date": "2026-07-26", "direction": "deposit",
         "amount": 100.0, "balance": 1100.0, "business_status": "posted",
         "matched_transaction": {"transaction_id": "receipt:1", "amount": 100.0,
                                 "effect": 1, "booking_date": "2026-07-26T00:00:00",
                                 "settlement_date": None}},
        {"row_number": 2, "bank_date": "2026-07-27", "direction": "withdrawal",
         "amount": 50.0, "balance": 1050.0, "business_status": "unposted",
         "matched_transaction": None},
    ]
    ledger = {
        "available": True,
        "dl_code": "210212",
        "dl_title": "سپه 3656",
        "lines": [
            {"date": date(2026, 7, 1), "voucher_number": "1",
             "net": Decimal("1000"), "balance": Decimal("1000")},
            {"date": date(2026, 7, 26), "voucher_number": "7476",
             "net": Decimal("100"), "balance": Decimal("1100")},
        ],
    }
    summary = _attach_balances(results, ledger)
    assert results[0]["book_balance_after_document"] == 1100.0
    assert results[0]["book_voucher_number"] == "7476"
    assert results[0]["day_balance_matched"] is True
    assert results[1]["day_balance_difference"] == -50.0
    assert summary["first_unmatched_date"] == "2026-07-27"
