from pathlib import Path
from tempfile import TemporaryDirectory
from openpyxl import Workbook
from app.services.karamad_manual_import_service import KaramadManualImportService


def _book(path: Path, rows):
    wb=Workbook(); ws=wb.active
    ws.append(["ردیف","شناسه","شماره چک","شعبه","وضعیت","تاریخ ثبت","تاریخ سررسید","مبلغ","نام بانک","محل چک","تفضیلی"])
    for row in rows: ws.append(row)
    ws.append([None,None,None,None,None,None,None,999,None,None,None])
    wb.save(path)


def test_received_snapshot_replaces_previous_and_keeps_real_status():
    with TemporaryDirectory() as d:
        root=Path(d)
        svc=KaramadManualImportService(inbox=root/'in', archive=root/'arc', state_path=root/'state.json')
        f1=root/'a.xlsx'; f2=root/'b.xlsx'
        _book(f1, [[1,101,'C1','تهران','نزد صندوق','1405/06/01','1405/07/01',1000,'ملت','صندوق تهران','مشتری الف'],[2,102,'C2','مشهد','واگذار شده','1405/06/01','1405/08/01',2000,'تجارت','صندوق مشهد','مشتری ب']])
        _book(f2, [[1,101,'C1','تهران','واگذار شده','1405/06/01','1405/07/01',1000,'ملت','صندوق تهران','مشتری الف']])
        r1=svc.import_workbook(f1,f1.name,'received_cheques')
        assert r1['import']['snapshot_replace'] is True
        assert len(svc.cheque_rows('received_cheques'))==2
        r2=svc.import_workbook(f2,f2.name,'received_cheques')
        rows=svc.cheque_rows('received_cheques')
        assert len(rows)==1
        assert rows[0]['state_label']=='واگذار شده'
        assert rows[0]['cheque_location']=='صندوق تهران'
        assert r2['import']['replaced_previous_count']==2


def test_received_blank_status_is_normalized_to_cashbox():
    from app.services.received_cheque_current_status import received_cheque_is_approved_open_holding
    with TemporaryDirectory() as d:
        root=Path(d)
        svc=KaramadManualImportService(inbox=root/'in', archive=root/'arc', state_path=root/'state.json')
        f=root/'blank.xlsx'
        _book(f, [
            [1,201,'B1','تهران',None,'1405/06/01','1405/07/01',1000,'ملت','صندوق تهران','مشتری الف'],
            [2,202,'B2','تهران','نزد صندوق','1405/06/01','1405/07/02',2000,'ملت','صندوق تهران','مشتری ب'],
            [3,203,'B3','تهران','واگذار شده','1405/06/01','1405/07/03',3000,'ملت','صندوق تهران','مشتری ج'],
        ])
        svc.import_workbook(f,f.name,'received_cheques')
        rows=svc.cheque_rows('received_cheques')
        assert len(rows)==3
        by_doc={str(x['document_id']):x for x in rows}
        assert by_doc['201']['cheque_status']=='نزد صندوق'
        assert by_doc['201']['state_label']=='نزد صندوق'
        assert received_cheque_is_approved_open_holding(by_doc['201']) is True
        assert received_cheque_is_approved_open_holding(by_doc['202']) is True
        assert received_cheque_is_approved_open_holding(by_doc['203']) is True
