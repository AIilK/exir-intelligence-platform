from io import BytesIO

from openpyxl import load_workbook

from app.services.reconciliation_export_service import build_reconciliation_workbook
from app.utils.jalali import format_jalali_date


def test_gregorian_date_is_rendered_as_jalali():
    assert format_jalali_date("2026-09-01") == "1405/06/10"
    assert format_jalali_date("2025-03-20") == "1403/12/30"
    assert format_jalali_date("1405/6/1") == "1405/06/01"


def test_reconciliation_excel_uses_jalali_bank_and_document_dates():
    report = {
        "reconciliation_id": "test-id",
        "created_at": "2026-09-01T08:30:00+00:00",
        "file": {
            "filename": "bank.xlsx",
            "statement_period": "2026-09-01",
            "statement_period_jalali": "1405/06/10 تا 1405/06/10",
        },
        "bank_account": {"display_label": "حساب آزمون"},
        "summary": {
            "bank_row_count": 1,
            "bank_total_amount": 1000,
            "business_counts": {"posted": 1},
            "business_amounts": {"posted": 1000},
        },
        "rows": [
            {
                "row_number": 2,
                "bank_date": "2026-09-01",
                "bank_date_jalali": "1405/06/10",
                "direction": "deposit",
                "amount": 1000,
                "business_status": "posted",
                "business_status_fa": "سندخورده",
                "matched_transaction": {
                    "document_number": "123",
                    "booking_date": "2026-09-01",
                    "booking_date_jalali": "1405/06/10",
                    "amount": 1000,
                    "transaction_type": "receipt",
                },
            }
        ],
        "unmatched_erp_transactions": [],
    }
    output = build_reconciliation_workbook(report)
    workbook = load_workbook(BytesIO(output.getvalue()), data_only=True)
    posted = workbook["سندخورده"]
    assert posted["B1"].value == "تاریخ شمسی بانک"
    assert posted["B2"].value == "1405/06/10"
    assert posted["R1"].value == "تاریخ شمسی سند راهکاران"
    assert posted["R2"].value == "1405/06/10"

