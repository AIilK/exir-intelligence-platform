from pathlib import Path

from openpyxl import Workbook

from app.services.karamad_payment_transfer_service import (
    HEADER_MAP,
    KaramadPaymentTransferService,
)


def _workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    headers = list(HEADER_MAP)
    sheet.append(headers)
    first = {header: "" for header in headers}
    first.update(
        {
            "ردیف": 1,
            "شناسه حواله": 1001,
            "شماره حواله": 501,
            "تاریخ ثبت": "1405/06/02",
            "مبلغ": 1_500_000,
            "کارمزد": 25_000,
            "بانک": "ملت",
            "بابت": "خرید مواد اولیه",
        }
    )
    second = {header: "" for header in headers}
    second.update(
        {
            "ردیف": 2,
            "شناسه حواله": 1002,
            "شماره حواله": 502,
            "تاریخ ثبت": "1405/05/28",
            "مبلغ": 2_500_000,
            "بانک": "ملی",
            "بابت": "هزینه حمل",
        }
    )
    sheet.append([first[header] for header in headers])
    sheet.append([second[header] for header in headers])
    workbook.save(path)


def test_import_deduplicates_by_transfer_id_and_filters_jalali_month(tmp_path):
    source = tmp_path / "karamad.xlsx"
    _workbook(source)
    service = KaramadPaymentTransferService(tmp_path / "store")

    first = service.import_workbook(source, source.name)
    second = service.import_workbook(source, source.name)
    month = service.report(month="1405/06")

    assert first["import"]["inserted_count"] == 2
    assert second["import"]["inserted_count"] == 0
    assert second["import"]["unchanged_count"] == 2
    assert second["summary"]["record_count"] == 2
    assert second["summary"]["total_amount_rial"] == 4_000_000
    assert month["summary"]["record_count"] == 1
    assert month["summary"]["total_amount_rial"] == 1_500_000
    assert month["summary"]["cashflow_included"] is False

