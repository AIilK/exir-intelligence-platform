"""پروفایل تاریخچه برای تحلیل هوشمند (app/services/file_history_service.py): جمع روزانه چک‌ها ← ماه شمسی."""
from datetime import date

from app.services.file_history_service import _roll_up, mt


def _row(key, day, n=1, amount=0, collected=0, returned=0, open_=0, term_sum=0, term_n=0):
    return {"Key": key, "Day": day, "n": n, "amount": amount, "collected": collected, "returned": returned,
            "open": open_, "term_sum": term_sum, "term_n": term_n}


def test_days_roll_up_into_jalali_months_per_key():
    rows = [
        _row(7, date(2026, 10, 22), n=2, amount=20_000_000, collected=10_000_000, open_=10_000_000, term_sum=120, term_n=2),  # 1405/07/30
        _row(7, date(2026, 10, 23), n=1, amount=5_000_000, returned=5_000_000, term_sum=30, term_n=1),                         # 1405/08/01
        _row(7, date(2026, 11, 7), n=1, amount=1_000_000, open_=1_000_000),                                                    # 1405/08/16
        _row(9, date(2026, 10, 23), n=3, amount=30_000_000, collected=30_000_000, term_sum=90, term_n=3),
    ]
    out = _roll_up(rows, "Key")
    assert [m["month"] for m in out[7]] == ["1405/07", "1405/08"]
    oct_, nov = out[7]
    assert oct_ == {"month": "1405/07", "cheques": 2, "amount_mt": 2.0, "collected_mt": 1.0, "returned_mt": 0.0,
                    "still_open_mt": 1.0, "avg_term_days": 60}
    assert nov["cheques"] == 2 and nov["returned_mt"] == 0.5 and nov["still_open_mt"] == 0.1
    assert nov["avg_term_days"] == 30  # the cheque without a due date does not count in the average
    assert out[9][0]["collected_mt"] == 3.0


def test_rows_without_key_or_date_are_skipped():
    out = _roll_up([_row(None, date(2026, 10, 1)), _row(5, None)], "Key")
    assert out == {}


def test_mt_is_million_toman():
    assert mt(10_000_000) == 1.0 and mt(None) == 0.0 and mt("x") == 0.0
