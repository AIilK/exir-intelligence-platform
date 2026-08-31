from decimal import Decimal
import unittest

from app.services.treasury_service import (
    _build_customer_cheque_settlement_payload,
)


def cheque_row(
    cheque_id: int,
    amount: int,
    state: int,
    *,
    account_text: str,
    note_counterpart_ref: int | None = 900001,
):
    return {
        "ChequeID": cheque_id,
        "ChequeItemID": cheque_id + 1000,
        "DocumentID": 2000,
        "DocumentNumber": "22001",
        "DocumentDate": None,
        "Amount": Decimal(amount),
        "DueDate": None,
        "SerialNumber": str(cheque_id),
        "Series": None,
        "SayadNumber": None,
        "AccountNumber": account_text,
        "NoteCounterPartRef": note_counterpart_ref,
        "DocumentCounterPartRef": 900001,
        "ChequeState": state,
        "BankName": "بانک نمونه",
        "CounterPartCode": "130001",
        "CounterPartName": "صابری",
        "ChequeDescription": None,
        "DocumentDescription": "دریافت چک از صابری",
    }


class CustomerChequeSettlementTests(unittest.TestCase):
    def test_many_third_party_cheques_reduce_one_debt_safely(self):
        rows = [
            cheque_row(1, 30_000_000, 1, account_text="رضایی"),
            cheque_row(2, 200_000_000, 2, account_text="احمدی"),
            cheque_row(3, 300_000_000, 3, account_text="صابری"),
            cheque_row(4, 100_000_000, 4, account_text="کاظمی"),
        ]
        payload = _build_customer_cheque_settlement_payload(
            cheque_rows=rows,
            account_rows=[],
            counterpart_ref=900001,
            counterpart_code="130001",
            counterpart_name="صابری",
            opening_debt=Decimal("1000000000"),
        )

        self.assertEqual(payload["summary"]["cheque_count"], 4)
        self.assertEqual(payload["summary"]["collected_total"], 300_000_000)
        self.assertEqual(payload["summary"]["pending_total"], 230_000_000)
        self.assertEqual(
            payload["debt_calculation"]["confirmed_remaining_debt"],
            700_000_000,
        )
        self.assertEqual(
            payload["debt_calculation"]["provisional_remaining_debt"],
            470_000_000,
        )
        self.assertEqual(
            payload["debt_calculation"]["protested_cheques_are_excluded"],
            True,
        )
        self.assertEqual(
            payload["summary"]["third_party_indicator_count"],
            3,
        )
        self.assertTrue(
            all(cheque["allocation_is_explicit"] for cheque in payload["cheques"])
        )

    def test_document_counterpart_is_valid_fallback(self):
        row = cheque_row(
            10,
            50_000_000,
            3,
            account_text="شخص ثالث",
            note_counterpart_ref=None,
        )
        payload = _build_customer_cheque_settlement_payload(
            cheque_rows=[row],
            account_rows=[],
            counterpart_ref=900001,
            counterpart_code="130001",
            counterpart_name="صابری",
            opening_debt=None,
        )

        self.assertEqual(
            payload["cheques"][0]["allocation_source"],
            "receipt_document_counterpart",
        )
        self.assertIsNone(payload["debt_calculation"])


if __name__ == "__main__":
    unittest.main()
