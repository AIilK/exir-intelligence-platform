from datetime import date, timedelta

import pytest

from app.services.liquidity import issued_cheques
from app.services.liquidity.issued_cheques import IssuedChequeService

TODAY = date(2026, 9, 30)


@pytest.fixture(autouse=True)
def _fresh_cache():
    issued_cheques.clear_cache()
    yield
    issued_cheques.clear_cache()


def _row(cheque_id, days, amount, payee="تأمین‌کننده الف", bank="ملت", account="111", sl=None):
    return {"ChequeID": cheque_id, "Amount": amount, "DueDate": TODAY + timedelta(days=days),
            "SerialNumber": str(cheque_id), "AccountNumber": account, "BankName": bank, "BankBranchName": None,
            "PayeeCode": payee, "PayeeName": payee, "Description": None, "SLCode": sl}


RAHKARAN = [
    _row(1, -200, 70),               # «open» for 200 days: needs status review, not counted
    _row(2, -5, 30),                 # overdue within 20 days: counted on today
    _row(3, 0, 100),
    _row(4, 3, 200, bank="سپه", account="222"),
    _row(5, 10, 400, payee="تأمین‌کننده ب"),
    _row(6, 45, 999),                # outside a 30-day horizon
]
KARAMAD = [
    _row(10, 2, 50, bank="ملت ظفر"),
    _row(10, 2, 50, bank="ملت ظفر"),  # same cheque on two view lines: counted once
    _row(11, 4, 600, payee="شرکت پادینا", sl="3112"),  # hybrid stock settlement
]


def _service(rahkaran=RAHKARAN, karamad=KARAMAD, failing=()):
    def fetcher(system, rows):
        def fetch():
            if system in failing:
                raise ConnectionError("down")
            return list(rows)
        return fetch
    return IssuedChequeService(today=TODAY, fetchers={"rahkaran": fetcher("rahkaran", rahkaran),
                                                      "karamad": fetcher("karamad", karamad)})


def test_kpis_count_overdue_up_to_20_days_and_the_horizon():
    kpis = _service().report(horizon_days=30)["data"]["kpis"]
    assert kpis["overdue"] == {"amount_rial": 30, "count": 1}
    assert kpis["horizon"] == {"amount_rial": 750, "count": 4}
    assert kpis["today"] == {"amount_rial": 100, "count": 1}
    assert kpis["next_7_days"] == {"amount_rial": 350, "count": 3}
    assert kpis["total_due_by_horizon_end"] == {"amount_rial": 780, "count": 5}
    assert kpis["peak_day"]["amount_rial"] == 400


def test_overdue_boundary_is_20_days():
    rows = [_row(1, -20, 10), _row(2, -21, 20)]
    data = _service(rahkaran=rows, karamad=[]).report()["data"]
    assert data["kpis"]["overdue"]["amount_rial"] == 10
    assert data["needs_status_review"]["amount_rial"] == 20


def test_old_open_cheques_go_to_status_review_not_forecast():
    card = _service().report()["data"]["needs_status_review"]
    assert card["amount_rial"] == 70 and card["count"] == 1
    assert [b["amount_rial"] for b in card["age_buckets"]] == [0, 70, 0]
    assert card["oldest"]["days_overdue"] == 200
    assert card["in_forecast"] is False
    assert "hybrid_settlement" not in card["cheques"][0]


SHAREHOLDER_ROWS = [
    # Drawn on a shareholder's personal account, payable to the company.
    {**_row(20, 3, 500, payee="سهامداران", account="925800096659"), "PayeeCode": "950031",
     "Description": "پرداخت به جاری شرکا بابت انتقال از 966 نادر علیزاده به 5565 اکسیر"},
    {**_row(22, -10, 300, payee="سهامداران"), "PayeeCode": "950031"},
    {**_row(23, -40, 900, payee="سهامداران"), "PayeeCode": "950031"},
    _row(21, 3, 100),
]


def test_shareholder_cheques_are_intra_company_not_inflow_or_outflow():
    service = _service(rahkaran=SHAREHOLDER_ROWS, karamad=[])
    data = service.report(horizon_days=30)["data"]
    assert data["kpis"]["total_due_by_horizon_end"] == {"amount_rial": 100, "count": 1}
    assert all(p["payee_name"] != "سهامداران" for p in data["top_payees"])
    assert "shareholder_financing_inflow" not in data
    # even old ones are not a treasury status-review item
    assert data["needs_status_review"]["count"] == 0
    assert all(a["open_count"] == 1 for a in data["by_bank_account"])
    assert service.schedule(horizon_days=30) == {(TODAY + timedelta(days=3)).isoformat(): 100}


def test_hybrid_settlement_cheques_are_separate_and_not_in_totals():
    data = _service().report(horizon_days=30)["data"]
    assert data["hybrid_settlement"]["amount_rial"] == 600
    assert data["hybrid_settlement"]["eliminated_in_group"] is True
    assert all(c["payee_name"] != "شرکت پادینا" for c in data["cheques"])
    hybrid = _service().report(horizon_days=30, channel="hybrid")["data"]
    assert hybrid["kpis"]["horizon"] == {"amount_rial": 50, "count": 1}


def test_bank_accounts_payees_and_filters():
    data = _service().report(horizon_days=30)["data"]
    accounts = {a["bank_account_key"]: a for a in data["by_bank_account"]}
    melat = accounts["rahkaran|ملت|111"]
    assert (melat["overdue_rial"], melat["next_7_days_rial"], melat["next_30_days_rial"], melat["next_90_days_rial"]) == (
        30, 100, 500, 1499)
    assert melat["needs_review_rial"] == 70
    assert melat["balance_rial"] is None
    # «الف»: 30 + 100 + 200 + 50 = 380 (its 200-day-old cheque is under review); «ب»: 400.
    assert [(p["payee_name"], p["amount_rial"]) for p in data["top_payees"]] == [
        ("تأمین‌کننده ب", 400), ("تأمین‌کننده الف", 380)]

    only_sepah = _service().report(horizon_days=30, bank_account="rahkaran|سپه|222")["data"]
    assert only_sepah["kpis"]["total_due_by_horizon_end"]["amount_rial"] == 200
    assert _service().report(horizon_days=30, payee="ب")["data"]["kpis"]["horizon"]["amount_rial"] == 400
    assert _service().report(horizon_days=30, min_amount=150)["data"]["kpis"]["horizon"]["count"] == 2


def test_schedule_puts_counted_overdue_on_today_and_skips_settlement_and_review():
    schedule = _service().schedule(horizon_days=30)
    assert schedule[TODAY.isoformat()] == 130  # 30 overdue (≤20 days) + 100 due today
    assert (TODAY + timedelta(days=4)).isoformat() not in schedule  # the settlement cheque
    assert sum(schedule.values()) == 780


def test_calendar_covers_every_day_of_the_horizon():
    calendar = _service().report(horizon_days=14)["data"]["calendar"]
    assert len(calendar) == 14
    assert calendar[3]["amount_rial"] == 200


def test_unavailable_system_returns_warning():
    result = _service(failing=("karamad",)).report()
    assert result["sources"] == ["rahkaran"]
    assert result["warnings"][0]["code"] == "karamad_unavailable"


def test_cheque_to_its_own_drawing_account_is_a_transfer_not_outflow():
    karamad = [
        _row(20, 3, 500, payee="ملت ظفر9203348030", bank="بانک ملت ظفر9203348030", account=None),
        _row(21, -60, 300, payee="بانک پارسیان -20100275449603", bank="بانک پارسیان - 20100275449603", account=None),
        # 8+ digits in a supplier name that is not the drawing account: still a normal payment
        _row(22, 5, 70, payee="erbatur - پرفرم 25102022", bank="سپه", account="925800190125"),
    ]
    service = _service(rahkaran=[], karamad=karamad)
    data = service.report(horizon_days=30)["data"]
    assert data["kpis"]["horizon"] == {"amount_rial": 70, "count": 1}
    assert data["needs_status_review"]["count"] == 0
    assert data["own_account_transfers"]["amount_rial"] == 800
    assert data["own_account_transfers"]["count"] == 2
    assert data["own_account_transfers"]["in_forecast"] is False
    assert [p["payee_name"] for p in data["top_payees"]] == ["erbatur - پرفرم 25102022"]
    assert sum(service.schedule(30).values()) == 70
