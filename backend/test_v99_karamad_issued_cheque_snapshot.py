from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook

from app.services.karamad_manual_import_service import KaramadManualImportService


def _sample(path: Path, ids=(1, 2)):
    wb = Workbook()
    ws = wb.active
    ws.append(["ردیف","شناسه","شماره چک","شعبه","اسناد پرداختنی","وضعیت","تاریخ ثبت","تاریخ سررسید","مبلغ","بابت","توضیحات","کد معین","کد سطح 4","کد سطح 5","کد سطح 6","معین","تفضیلی","سطح 5","سطح 6","تضمینی","سال مالی","تاریخ وصول","بررسی","شماره درخواست پرداخت","شماره صیادی"])
    for i in ids:
        ws.append([i, 3800+i, f"35{i}", "هیبرید تهران", "بانک ملت ظفر9203348030", "عادی", "1405/06/01", "1405/07/10", 1000000000, "خرید", "", 3112, 1254, "", "", "حساب های پرداختنی", "شرکت تست", "", "", False, "1405", "", False, "", f"123{i}"])
    ws.append([None,None,None,None,None,None,None,"راس: -10",2000000000])
    wb.save(path)


def test_issued_portfolio_skips_total_row_and_marks_incomplete_future():
    with TemporaryDirectory() as d:
        root=Path(d)
        f=root/'issued.xlsx'; _sample(f)
        svc=KaramadManualImportService(inbox=root/'in', archive=root/'archive', state_path=root/'state.json')
        rows,warnings=svc.parse(f,'issued_cheques')
        assert len(rows)==2
        assert sum(r['amount_rial'] for r in rows)==2000000000
        assert all(r['cheque_status']=='ثبت‌شده در کارآمد' for r in rows)
        assert all(r['future_data_complete'] is False for r in rows)
        assert all(r['returns_available'] is False for r in rows)


def test_issued_portfolio_replace_is_snapshot_not_incremental():
    with TemporaryDirectory() as d:
        root=Path(d)
        svc=KaramadManualImportService(inbox=root/'in', archive=root/'archive', state_path=root/'state.json')
        f1=root/'one.xlsx'; _sample(f1,(1,2))
        f2=root/'two.xlsx'; _sample(f2,(3,))
        r1=svc.import_workbook(f1,'one.xlsx','issued_cheques')
        r2=svc.import_workbook(f2,'two.xlsx','issued_cheques')
        assert r1['import']['snapshot_kind']=='issued_cheques'
        assert r2['import']['replaced_previous_count']==2
        rows=svc.cheque_rows('issued_cheques')
        assert len(rows)==1
        assert rows[0]['counterpart_name']=='شرکت تست'
        assert rows[0]['returns_available'] is False


def test_issued_portfolio_excludes_guaranteed_cheques():
    with TemporaryDirectory() as d:
        root=Path(d)
        f=root/'issued-guaranteed.xlsx'
        wb=Workbook(); ws=wb.active
        ws.append(["ردیف","شناسه","شماره چک","شعبه","اسناد پرداختنی","وضعیت","تاریخ ثبت","تاریخ سررسید","مبلغ","بابت","توضیحات","کد معین","کد سطح 4","کد سطح 5","کد سطح 6","معین","تفضیلی","سطح 5","سطح 6","تضمینی","سال مالی","تاریخ وصول","بررسی","شماره درخواست پرداخت","شماره صیادی"])
        ws.append([1,1001,"111","تهران","بانک ملت","عادی","1405/06/01","1405/07/01",1000000000,"خرید","",3112,1,"","","حساب های پرداختنی","شرکت الف","","",False,"1405","",False,"","1"])
        ws.append([2,1002,"222","تهران","بانک ملت","عادی","1405/06/01","1405/07/01",2000000000,"تضمین","",3112,1,"","","اسناد تضمینی بابت تسهیلات مالی دریافتی","","","",True,"1405","",False,"","2"])
        wb.save(f)
        svc=KaramadManualImportService(inbox=root/'in', archive=root/'archive', state_path=root/'state.json')
        rows,_=svc.parse(f,'issued_cheques')
        assert len(rows)==1
        assert rows[0]['transfer_id']=='1001'
