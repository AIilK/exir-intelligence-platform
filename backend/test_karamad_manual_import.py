from datetime import date
from pathlib import Path

from openpyxl import Workbook

from app.services.karamad_manual_import_service import KaramadManualImportService


HEADERS = ["ردیف", "شناسه حواله", "شماره حواله", "شعبه", "شماره سند", "تاریخ ثبت", "مبلغ", "کارمزد", "بانک", "بابت", "توضیحات"]


def workbook(path: Path, rows: list[list[object]]) -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    book.save(path)


def service(tmp_path: Path) -> KaramadManualImportService:
    return KaramadManualImportService(tmp_path / "inbox", tmp_path / "archive", tmp_path / "state.json")


def test_four_sources_deduplicate_by_direction_and_transfer_id(tmp_path):
    received_cheque = tmp_path / "چک دریافتی.xlsx"
    received_transfer = tmp_path / "حواله دریافت.xlsx"
    workbook(received_cheque, [[1, 10, 1, "مرکز", 1, "1405/06/10", 1_000, 0, "ملت", "فاکتور 1", ""]])
    workbook(received_transfer, [
        [1, 10, 1, "مرکز", 1, "1405/06/10", 1_000, 0, "ملت", "فاکتور 1", ""],
        [2, 11, 2, "مرکز", 2, "1405/06/11", 2_000, 0, "ملت", "فاکتور 2", ""],
    ])
    importer = service(tmp_path)
    first = importer.import_workbook(received_cheque, received_cheque.name)
    second = importer.import_workbook(received_transfer, received_transfer.name)
    summary = importer.summary()
    assert first["import"]["inserted_count"] == 1
    assert second["import"]["overlap_count"] == 1
    assert summary["unique_record_count"] == 2
    assert summary["operational_inflow_rial"] == 3_000


def test_transfer_and_petty_cash_are_excluded_from_operational_totals(tmp_path):
    source = tmp_path / "حواله پرداخت.xlsx"
    workbook(source, [
        [1, 20, 1, "مرکز", 1, "1405/06/10", 4_000, 0, "ملت", "بابت انتقال از ملت به سپه", ""],
        [2, 21, 2, "مرکز", 2, "1405/06/10", 5_000, 0, "ملت", "تامین تنخواه", ""],
        [3, 22, 3, "مرکز", 3, "1405/06/10", 6_000, 0, "ملت", "خرید مواد اولیه", ""],
    ])
    importer = service(tmp_path)
    result = importer.import_workbook(source, source.name)
    assert result["summary"]["operational_outflow_rial"] == 6_000
    assert result["summary"]["bank_transfer_rial"] == 4_000
    assert result["summary"]["petty_cash_rial"] == 5_000


def test_files_named_cheque_use_transfer_or_registration_date(tmp_path):
    source = tmp_path / "چک پرداختی.xlsx"
    workbook(source, [[1, 30, 1, "مرکز", 1, "1405/06/10", 7_000, 0, "ملت", "هزینه", ""]])
    importer = service(tmp_path)
    result = importer.import_workbook(source, source.name)
    assert any("تاریخ حواله/ثبت" in warning for warning in result["warnings"])
    rows = importer.cheque_rows("issued_cheques")
    assert rows[0]["registration_date_jalali"] == "1405/06/10"
    assert rows[0]["due_date_jalali"] == "1405/06/10"
    assert rows[0]["transfer_number"] == "1"
    assert rows[0]["source_label"] == "کارآمد"


def test_actual_movements_respects_gregorian_report_range(tmp_path):
    source = tmp_path / "حواله دریافت.xlsx"
    workbook(source, [
        [1, 40, 1, "مرکز", 1, "1405/06/10", 8_000, 0, "ملت", "فاکتور", ""],
        [2, 41, 2, "مرکز", 2, "1405/05/10", 9_000, 0, "ملت", "فاکتور", ""],
    ])
    importer = service(tmp_path)
    importer.import_workbook(source, source.name)
    report = importer.actual_movements(date(2026, 8, 31), date(2026, 9, 5))
    assert report["date_from_jalali"] == "1405/06/09"
    assert [row["transfer_id"] for row in report["movements"]] == ["40"]
