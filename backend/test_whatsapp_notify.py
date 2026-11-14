"""تست ارسال واتساپ (app/services/whatsapp) با داده ساختگی و WAHA ساختگی — بدون SQL Server و بدون ارسال واقعی.

اجرا: pytest test_whatsapp_notify.py   یا   python test_whatsapp_notify.py
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

from app.core.config import settings
from app.services.whatsapp import runner, store
from app.services.whatsapp.composer import Composer
from app.services.whatsapp.waha_client import WahaError, normalize_mobile


class FakeSource:
    def customers(self):
        return [
            {"id": 1, "dl_ref": 101, "name": "فروشگاه الف", "code": "C1", "mobile": "09121234567", "branch_ref": 1, "branch": "تهران"},
            {"id": 2, "dl_ref": 102, "name": "فروشگاه ب", "code": "C2", "mobile": "", "branch_ref": 1, "branch": "تهران"},
            {"id": 3, "dl_ref": 103, "name": "فروشگاه ج", "code": "C3", "mobile": "۰۹۳۵۱۱۱۲۲۳۳", "branch_ref": 2, "branch": "اصفهان"},
        ]

    def positions(self):
        return {101: {"balance_rial": 250_000_000}, 102: {"balance_rial": 90_000_000}, 103: {"balance_rial": -5_000}}

    def upcoming_cheques(self, days_ahead):
        return [
            {"id": 1, "number": "123456", "due_date": date(2026, 11, 12), "amount_rial": 40_000_000, "dl_ref": 999, "dl2_ref": 103, "dl3_ref": None, "bank": "ملت", "status": "نزد صندوق"},
            {"id": 2, "number": "777", "due_date": date(2026, 11, 11), "amount_rial": 10_000_000, "dl_ref": 101, "dl2_ref": None, "dl3_ref": None, "bank": None, "status": "غیرقطعی"},
        ]

    def visitors(self):
        return [{"id": 7, "name": "ویزیتور یک", "code": "V7", "mobile": "9120000001", "branch_ref": 1, "branch": "تهران"},
                {"id": 8, "name": "ویزیتور بی‌مشتری", "code": "V8", "mobile": "09120000002", "branch_ref": 1, "branch": "تهران"}]

    def customer_visitor(self):
        return {101: 7, 102: 7, 103: 7}

    def branches(self):
        return [{"id": 1, "name": "تهران"}, {"id": 2, "name": "اصفهان"}]


class FakeWaha:
    def __init__(self, file_fails=False):
        self.sent: list[tuple] = []
        self.file_fails = file_fails

    def session_info(self):
        return {"status": "WORKING"}

    def check_exists(self, phone):
        return None if phone.endswith("0000") else f"{phone}@c.us"

    def send_text(self, chat, text):
        self.sent.append(("text", chat, text))

    def send_file(self, chat, content, filename, caption=""):
        if self.file_fails:
            raise WahaError("WAHA 422: plus only", 422)
        self.sent.append(("file", chat, filename, caption, len(content)))


def _fresh_db():
    tmp = Path(tempfile.mkdtemp())
    settings.whatsapp_db = str(tmp / "wa.db")
    store._ready = False
    return tmp


def _rule(kind):
    return next(r for r in store.list_rules() if r["kind"] == kind)


def test_normalize_mobile():
    assert normalize_mobile("09121234567") == "989121234567"
    assert normalize_mobile("۰۹۱۲ ۱۲۳ ۴۵۶۷") == "989121234567"
    assert normalize_mobile("+98 912 123 4567") == "989121234567"
    assert normalize_mobile("00989121234567") == "989121234567"
    assert normalize_mobile("9121234567") == "989121234567"
    assert normalize_mobile("02188776655") is None
    assert normalize_mobile("") is None


def test_clean_name_and_mobile_in_name():
    from app.services.whatsapp.composer import clean_name, mobile_in_name
    assert clean_name("مرادي سعيد/09120000003") == "مرادی سعید"
    assert clean_name("علی رضایی - ۰۹۱۲ ۱۲۳ ۴۵۶۷") == "علی رضایی"
    assert clean_name("فروشگاه الف (41)") == "فروشگاه الف (41)"
    assert mobile_in_name("مرادي سعيد/09120000003") == "989120000003"
    assert mobile_in_name("فروشگاه بدون شماره") is None


def test_default_rules_seeded_disabled():
    _fresh_db()
    rules = store.list_rules()
    assert {r["kind"] for r in rules} == set(store.KINDS)
    assert not any(r["enabled"] or r["auto_send"] for r in rules)


def test_customer_debt_compose_and_dedupe():
    _fresh_db()
    rule = store.update_rule(_rule("customer_debt")["id"], {"params": {"min_debt_toman": 5_000_000}})
    comp = Composer(FakeSource(), today=date(2026, 11, 10))
    res = comp.compose(rule)
    assert res["stats"]["candidates"] == 2          # 101 و 102 بدهکار؛ 103 بستانکار
    assert res["stats"]["no_phone"] == 1 and res["stats"]["no_phone_names"] == ["فروشگاه ب"]
    [item] = res["items"]
    assert item["phone"] == "989121234567"
    assert "۲۵٬۰۰۰٬۰۰۰ تومان" in item["message"] and "فروشگاه الف" in item["message"]
    assert store.enqueue(res["items"], "pending") == {"added": 1, "duplicates": 0}
    assert store.enqueue(comp.compose(rule)["items"], "pending") == {"added": 0, "duplicates": 1}


def test_overrides_phone_and_opt_out():
    _fresh_db()
    store.upsert_recipient("customer", "102", "فروشگاه ب", "989351234567", False, None)
    store.upsert_recipient("customer", "101", "فروشگاه الف", None, True, "درخواست مشتری")
    res = Composer(FakeSource()).compose(_rule("customer_debt"))
    assert [i["recipient_ref"] for i in res["items"]] == [102]
    assert res["items"][0]["phone"] == "989351234567"
    assert res["stats"]["opted_out"] == 1


def test_cheques_match_any_dl_level_and_branch_filter():
    _fresh_db()
    rule = _rule("customer_cheques")
    items = Composer(FakeSource()).compose(rule)["items"]
    assert sorted(i["recipient_ref"] for i in items) == [101, 103]   # 103 از DL2Ref
    c = next(i for i in items if i["recipient_ref"] == 103)
    assert "۱۲۳۴۵۶" in c["message"] and "(ملت)" in c["message"] and "۴٬۰۰۰٬۰۰۰" in c["message"]
    rule = store.update_rule(rule["id"], {"params": {"days_ahead": 3, "branch_ids": [2]}})
    assert [i["recipient_ref"] for i in Composer(FakeSource()).compose(rule)["items"]] == [103]


def test_visitor_report_with_excel():
    _fresh_db()
    res = Composer(FakeSource(), today=date(2026, 11, 10)).compose(_rule("visitor_report"))
    [item] = res["items"]                       # ویزیتور ۸ مشتری ندارد
    assert item["recipient_ref"] == 7 and item["phone"] == "989120000001"
    assert "۲ مشتری بدهکار" in item["message"] and "۲ چک" in item["message"]
    from openpyxl import load_workbook
    wb = load_workbook(item["file_path"])
    assert wb.sheetnames == ["بدهی مشتریان", "چک‌های پیش‌رو"]
    assert wb["بدهی مشتریان"].max_row == 2 + 2 + 1      # عنوان + سرستون + ۲ مشتری + جمع
    assert wb["بدهی مشتریان"].cell(5, 5).value == 34_000_000


def test_bad_template_rejected():
    _fresh_db()
    rule = store.update_rule(_rule("customer_debt")["id"], {"template": "سلام {name"})
    try:
        Composer(FakeSource()).compose(rule)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_due_rules_window():
    _fresh_db()
    rule = store.update_rule(_rule("customer_cheques")["id"], {"enabled": True, "days": ["tue"], "hour": 9, "minute": 0})
    tue = datetime(2026, 11, 10, tzinfo=runner.TZ)  # سه‌شنبه
    assert not runner.due_rules(tue.replace(hour=8, minute=59))
    assert [r["id"] for r in runner.due_rules(tue.replace(hour=9, minute=0))] == [rule["id"]]
    assert not runner.due_rules(tue.replace(hour=12, minute=1))   # بعد از ۳ ساعت جبران نمی‌شود
    store.mark_rule_run(rule["id"], "2026-11-10", {})
    assert not runner.due_rules(tue.replace(hour=9, minute=30))   # امروز اجرا شده
    assert not runner.due_rules(datetime(2026, 11, 11, 9, 0, tzinfo=runner.TZ))  # چهارشنبه


def test_run_rule_queue_modes():
    _fresh_db()
    rid = _rule("customer_debt")["id"]
    res = runner.run_rule(rid, trigger="manual", composer=Composer(FakeSource()))
    assert res["queued_as"] == "pending" and res["added"] == 1
    store.update_rule(rid, {"auto_send": True})
    old = settings.whatsapp_enabled
    settings.whatsapp_enabled = False   # ارسال واقعی شروع نشود
    try:
        res = runner.run_rule(rid, trigger="scheduled", force=True, composer=Composer(FakeSource()))
    finally:
        settings.whatsapp_enabled = old
    assert res["queued_as"] == "approved" and store.outbox_counts() == {"pending": 1, "approved": 1}


def test_send_item_test_mode_and_file_fallback():
    _fresh_db()
    item = Composer(FakeSource()).compose(_rule("visitor_report"))["items"][0]
    waha = FakeWaha()
    old = settings.whatsapp_test_phone
    try:
        settings.whatsapp_test_phone = "09350000099"
        assert runner.send_item(item, waha) == ("sent", None)
        kind, chat, fname, caption, size = waha.sent[0]
        assert kind == "file" and chat == "989350000099@c.us" and caption.startswith("[آزمایشی") and size > 0
        settings.whatsapp_test_phone = ""
        waha2 = FakeWaha(file_fails=True)
        status, err = runner.send_item(item, waha2)
        assert status == "sent" and "فایل" in err and waha2.sent[0][0] == "text" and waha2.sent[0][1] == "989120000001@c.us"
        assert runner.send_item({**item, "phone": "989120000000", "file_path": None}, waha)[0] == "no_whatsapp"
    finally:
        settings.whatsapp_test_phone = old


def test_approve_skip_and_stuck_reset():
    _fresh_db()
    store.enqueue(Composer(FakeSource()).compose(_rule("customer_cheques"))["items"], "pending")
    ids = [i["id"] for i in store.list_outbox()]
    assert store.set_status(ids[:1], "skipped", ("pending",)) == 1
    assert store.approve_all_pending("tester") == 1
    item = store.next_approved()
    assert item and store.get_item(item["id"])["status"] == "sending"
    store.reset_stuck_sending()
    assert store.get_item(item["id"])["status"] == "approved"


if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
    sys.exit(1 if fails else 0)
