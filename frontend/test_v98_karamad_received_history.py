from pathlib import Path
from tempfile import TemporaryDirectory
from openpyxl import Workbook
from app.services.karamad_manual_import_service import KaramadManualImportService


def _book(path: Path):
    wb=Workbook(); ws=wb.active
    ws.append(['شناسه','شماره چک','شعبه','وضعیت','تاریخ ثبت','تاریخ سررسید','مبلغ','محل چک','نام بانک','تفضیلی','شناسه صیاد'])
    ws.append([1,'111','تهران','نزد صندوق','1405/06/01','1405/06/10',1000,'صندوق تهران','شهر','مشتری الف','991'])
    ws.append([2,'222','تهران','واگذار شده','1405/06/01','1405/07/10',2000,'بانک','تجارت','مشتری الف','992'])
    wb.save(path)


def test_customer_detail_keeps_full_received_cheque_fields_and_timing(monkeypatch):
    with TemporaryDirectory() as td:
        root=Path(td); f=root/'all.xlsx'; _book(f)
        svc=KaramadManualImportService(inbox=root/'inbox',archive=root/'archive',state_path=root/'state.json')
        svc.import_workbook(f,f.name,'received_cheques')
        detail=svc.customer_detail('مشتری الف')
        assert detail['summary']['received_cheque_count']==2
        assert len(detail['received_cheques'])==2
        assert all('days_until_due' in row for row in detail['received_cheques'])
        assert {row['cheque_status'] for row in detail['received_cheques']}=={'نزد صندوق','واگذار شده'}
        assert {row['cheque_location'] for row in detail['received_cheques']}=={'صندوق تهران','بانک'}
