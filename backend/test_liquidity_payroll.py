from datetime import date

import pytest

from app.services.liquidity import payroll
from app.services.liquidity.payroll import PayrollService

# 2026-09-30 = 1405/07/08
TODAY = date(2026, 9, 30)


@pytest.fixture(autouse=True)
def _fresh_cache():
    payroll.clear_cache()
    yield
    payroll.clear_cache()


def _month(ym, headcount, net, employee_ins, employer_ins, tax):
    return [
        {"YearMonth": ym, "Factor": 63, "Employees": headcount, "Amount": net},
        {"YearMonth": ym, "Factor": 46, "Employees": headcount, "Amount": employee_ins},
        {"YearMonth": ym, "Factor": 64, "Employees": headcount, "Amount": employer_ins},
        {"YearMonth": ym, "Factor": 49, "Employees": headcount, "Amount": tax},
    ]


ROWS = (
    _month(140503, 144, 700, 40, 140, 130)
    + _month(140504, 141, 650, 40, 130, 110)
    + _month(140505, 143, 630, 45, 130, 115)
    + _month(140506, 8, 55, 0, 0, 0)          # still being calculated
)

# Largest payroll payment per Jalali month: day 20 of 1405/03, 04, 05, 06.
PAYMENTS = [
    {"Day": date(2026, 6, 10), "Amount": 500},   # 1405/03/20
    {"Day": date(2026, 6, 11), "Amount": 10},
    {"Day": date(2026, 7, 11), "Amount": 500},   # 1405/04/20
    {"Day": date(2026, 8, 11), "Amount": 500},   # 1405/05/20
    {"Day": date(2026, 9, 11), "Amount": 500},   # 1405/06/20
    {"Day": date(2026, 9, 24), "Amount": 900},   # 1405/07/02: current month, ignored
]


def _service(rows=ROWS, payments=PAYMENTS):
    return PayrollService(today=TODAY, fetch_rows=lambda _ym: list(rows), fetch_payments=lambda _d: list(payments))


def test_kpis_use_latest_complete_month_and_total_includes_insurance_and_tax():
    data = _service().report()["data"]
    assert data["latest_month"]["month"] == "1405/05"
    kpis = data["kpis"]
    assert kpis["headcount"] == 143
    assert kpis["net_pay_rial"] == 630
    assert kpis["insurance_and_tax_rial"] == 45 + 130 + 115
    assert kpis["total_rial"] == 630 + 45 + 130 + 115
    assert kpis["total_change_percent"] == round((920 - 930) / 930 * 100, 1)
    assert kpis["headcount_change"] == 2
    assert data["in_progress_months"] == [{"month": "1405/06", "headcount": 8}]
    assert [m["month"] for m in data["monthly_trend"]] == ["1405/03", "1405/04", "1405/05"]


def test_pay_day_is_the_median_day_of_the_largest_monthly_payment():
    pay_day = _service().report()["data"]["pay_day"]
    assert pay_day["usual_day_of_month"] == 20
    assert [o["date_jalali"] for o in pay_day["observed"]] == ["1405/03/20", "1405/04/20", "1405/05/20", "1405/06/20"]


def test_forecast_places_last_complete_total_once_per_month_on_pay_day():
    forecast = _service().schedule(horizon_days=60)
    assert [(f["date_jalali"], f["payroll_month"], f["amount_rial"]) for f in forecast] == [
        ("1405/07/20", "1405/06", 920),
        ("1405/08/20", "1405/07", 920),
    ]


def test_unavailable_rahkaran_returns_warning():
    def boom(_):
        raise ConnectionError("down")

    result = PayrollService(today=TODAY, fetch_rows=boom, fetch_payments=boom).report()
    assert result["data"] is None
    assert result["warnings"][0]["code"] == "rahkaran_unavailable"
