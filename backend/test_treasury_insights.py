from datetime import date
from decimal import Decimal
import unittest

from app.services.treasury_insight_service import (
    _build_cheque_risk_payload,
    _build_daily_briefing_payload,
    _build_payment_plan_payload,
    _detect_financial_anomalies,
)


def cheque_report(cheques=None, total=0, *, total_count=None, exact_total=None):
    items = cheques or []
    report = {
        "cheques": items,
        "returned_count": len(items),
        "returned_total_amount": total,
    }
    if total_count is not None:
        report["total_count"] = total_count
    if exact_total is not None:
        report["total_amount"] = exact_total
    return report


class TreasuryInsightTests(unittest.TestCase):
    def test_daily_briefing_never_calls_document_net_a_bank_balance(self):
        result = _build_daily_briefing_payload(
            target_date=date(2026, 8, 19),
            aggregate_rows=[
                {"DocumentType": "receipt", "DocumentCount": 2, "TotalAmount": Decimal("300")},
                {"DocumentType": "payment", "DocumentCount": 1, "TotalAmount": Decimal("500")},
            ],
            largest_rows=[],
            issued_upcoming=cheque_report(total=700),
            issued_overdue=cheque_report(),
            received_upcoming=cheque_report(total=200),
            received_overdue=cheque_report(),
        )
        self.assertEqual(result["today"]["document_net_movement"], -200)
        self.assertEqual(result["today"]["net_direction"], "net_payment")
        self.assertIn("مانده بانکی محسوب نمی‌شود", result["today"]["note"])
        self.assertEqual(result["alerts"][0]["code"], "near_term_nominal_outflow_gap")

    def test_anomaly_rules_are_explainable_and_not_fraud_claims(self):
        rows = [
            {
                "DocumentType": "payment",
                "DocumentID": 1,
                "DocumentNumber": "100",
                "DocumentDate": date(2026, 8, 19),
                "CounterPartRef": 10,
                "Amount": Decimal("100"),
                "ItemType": 8,
                "Description": "",
            },
            {
                "DocumentType": "payment",
                "DocumentID": 2,
                "DocumentNumber": "101",
                "DocumentDate": date(2026, 8, 19),
                "CounterPartRef": 10,
                "Amount": Decimal("100"),
                "ItemType": 8,
                "Description": "پرداخت دوم",
            },
            {
                "DocumentType": "receipt",
                "DocumentID": 3,
                "DocumentNumber": "102",
                "DocumentDate": date(2026, 8, 19),
                "CounterPartRef": 11,
                "Amount": Decimal("1000"),
                "ItemType": 8,
                "Description": "دریافت بزرگ",
            },
        ]
        result = _detect_financial_anomalies(
            rows,
            explicit_large_threshold=Decimal("900"),
        )
        self.assertEqual(result["finding_counts"]["possible_duplicate"], 1)
        self.assertEqual(result["finding_counts"]["unusually_large_amount"], 1)
        self.assertEqual(result["finding_counts"]["missing_description"], 1)
        duplicate = next(item for item in result["findings"] if item["finding_type"] == "possible_duplicate")
        self.assertIn("باید انسانی تأیید شود", duplicate["reason"])

    def test_payment_plan_calculates_funding_gap_without_executing_payment(self):
        result = _build_payment_plan_payload(
            days=30,
            overdue_cheques=[{"cheque_id": 1, "amount": 100, "days_until_due": -2, "due_date": "2026-08-17"}],
            upcoming_cheques=[{"cheque_id": 2, "amount": 250, "days_until_due": 3, "due_date": "2026-08-22"}],
            available_cash=Decimal("200"),
        )
        self.assertEqual(result["summary"]["total_required"], 350)
        self.assertEqual(result["summary"]["funding_gap"], 150)
        self.assertEqual(result["items"][0]["priority"], "critical")
        self.assertEqual(result["items"][1]["funding_status"], "unfunded")
        self.assertFalse(result["bank_transaction_execution"])

    def test_cheque_risk_coverage_is_labeled_nominal(self):
        issued = [{"counterpart_ref": 1, "counterpart_name": "الف", "amount": 400}]
        received = [{"counterpart_ref": 2, "counterpart_name": "ب", "amount": 100}]
        result = _build_cheque_risk_payload(
            days=30,
            issued_upcoming=cheque_report(issued, 400),
            issued_overdue=cheque_report(),
            received_upcoming=cheque_report(received, 100),
            received_overdue=cheque_report(),
            protested=cheque_report(),
            issued_concentration=[
                {"counterpart_ref": 1, "counterpart_name": "الف", "count": 9, "amount": 900}
            ],
            received_concentration=[],
        )
        self.assertEqual(result["summary"]["nominal_coverage_percent"], 25)
        self.assertIn("تضمین وصول", result["summary"]["coverage_note"])
        self.assertEqual(result["alerts"][0]["code"], "nominal_coverage_gap")
        self.assertEqual(result["summary"]["overdue_scope"], "previous_30_days")
        self.assertEqual(result["summary"]["protested_scope"], "current_state_all_history")
        self.assertEqual(result["concentration_scope"], "all_upcoming_rows")
        self.assertEqual(result["issued_counterparty_concentration"][0]["count"], 9)

    def test_dashboard_uses_exact_totals_not_limited_detail_rows(self):
        result = _build_daily_briefing_payload(
            target_date=date(2026, 8, 19),
            aggregate_rows=[],
            largest_rows=[],
            issued_upcoming=cheque_report(),
            issued_overdue=cheque_report(
                [{"amount": 10}],
                10,
                total_count=12,
                exact_total=500,
            ),
            received_upcoming=cheque_report(),
            received_overdue=cheque_report(),
        )
        self.assertEqual(result["cheques"]["issued_overdue"]["count"], 12)
        self.assertEqual(result["cheques"]["issued_overdue"]["amount"], 500)


if __name__ == "__main__":
    unittest.main()
