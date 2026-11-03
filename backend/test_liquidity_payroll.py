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


def _zarin_month(month, headcount, base, commission, net, employee_ins, employer_ins, tax, sales_commission=None):
    return {"Year": 1405, "Month": month, "Employees": headcount, "BasePay": base, "Commission": commission,
            "Gross": net + employee_ins + tax, "NetPay": net, "EmployeeInsurance": employee_ins,
            "EmployerInsurance": employer_ins, "Tax": tax, "SalesEmployees": headcount - 20,
            "SalesCommission": commission if sales_commission is None else sales_commission}


ZARIN = [
    _zarin_month(3, 88, 200, 230, 480, 17, 47, 16),
    _zarin_month(4, 92, 210, 470, 660, 40, 110, 40),
    _zarin_month(5, 103, 240, 180, 400, 33, 90, 13, sales_commission=170),
]


# Zarin settles its payroll on the 28th (1405/03/28, 04/28, 05/28; 1405/06/28 = 2026-09-19).
ZARIN_PAYMENTS = [
    {"Day": date(2026, 6, 18), "Amount": 480},
    {"Day": date(2026, 7, 19), "Amount": 660},
    {"Day": date(2026, 8, 19), "Amount": 400},
    {"Day": date(2026, 8, 20), "Amount": 5},
]


def _service(rows=ROWS, payments=PAYMENTS, zarin=ZARIN, zarin_payments=ZARIN_PAYMENTS):
    def fetch_zarin(_ym):
        if isinstance(zarin, Exception):
            raise zarin
        return list(zarin)
    return PayrollService(today=TODAY, fetch_rows=lambda _ym: list(rows), fetch_payments=lambda _d: list(payments),
                          fetch_zarin=fetch_zarin, fetch_zarin_payments=lambda _d: list(zarin_payments))


def _workshop(rows, workshop):
    return [{**r, "Workshop": workshop} for r in rows]


def test_kpis_use_latest_complete_month_and_total_includes_insurance_and_tax():
    data = _service().report()["data"]
    assert data["latest_month"]["month"] == "1405/05"
    kpis = data["kpis"]
    assert kpis["headcount"] == 143
    assert kpis["net_pay_rial"] == 630
    assert kpis["insurance_and_tax_rial"] == 130 + 115
    assert kpis["total_rial"] == 630 + 130                # employee share (45) and tax (115) excluded
    assert kpis["total_change_percent"] == round((760 - 780) / 780 * 100, 1)
    assert kpis["headcount_change"] == 2
    assert data["in_progress_months"] == [{"month": "1405/06", "headcount": 8}]
    assert [m["month"] for m in data["monthly_trend"]] == ["1405/03", "1405/04", "1405/05"]


def test_pay_day_is_the_median_day_of_the_largest_monthly_payment():
    pay_day = _service().report()["data"]["pay_day"]
    assert pay_day["usual_day_of_month"] == 20
    assert [o["date_jalali"] for o in pay_day["observed"]] == ["1405/03/20", "1405/04/20", "1405/05/20", "1405/06/20"]


def test_forecast_places_last_complete_total_once_per_month_on_pay_day():
    forecast = _service().schedule(horizon_days=60, channel="b2b")
    assert [(f["date_jalali"], f["payroll_month"], f["amount_rial"], f["group"]) for f in forecast] == [
        ("1405/07/20", "1405/06", 760, "rahkaran"),
        ("1405/08/20", "1405/07", 760, "rahkaran"),
    ]


def test_forecast_adds_zarin_last_month_on_its_own_pay_day():
    forecast = _service().schedule(horizon_days=60)
    zarin = [(f["date_jalali"], f["amount_rial"]) for f in forecast if f["group"] == "zarin"]
    assert zarin == [("1405/07/28", 490), ("1405/08/28", 490)]       # 400 + 90
    assert [f["group"] for f in _service().schedule(horizon_days=60, channel="hybrid")] == ["zarin", "zarin"]
    assert [f["date"] for f in forecast] == sorted(f["date"] for f in forecast)


def test_forecast_keeps_rahkaran_when_karamad_is_down():
    forecast = _service(zarin=ConnectionError("down")).schedule(horizon_days=60)
    assert {f["group"] for f in forecast} == {"rahkaran"}


def test_unavailable_rahkaran_returns_warning():
    def boom(_):
        raise ConnectionError("down")

    result = PayrollService(today=TODAY, fetch_rows=boom, fetch_payments=boom, fetch_zarin=boom,
                            fetch_zarin_payments=boom).report()
    assert result["data"] is None
    assert result["warnings"][0]["code"] == "rahkaran_unavailable"


COMPANY_ROWS = (
    _workshop(_month(140504, 50, 300, 20, 60, 50), "سازمان بیمه تامین اجتماعی شعبه اشتهارد 0040 - اکسیر")
    + _workshop(_month(140504, 30, 200, 10, 40, 30), "سازمان بیمه تامین اجتماعی شعبه اشتهارد0029 - فراز بهداشت")
    + _workshop(_month(140504, 52, 250, 10, 50, 40), "سازمان تأمین اجتماعی شعبه شمیران - کادوس")
    + _month(140504, 9, 60, 0, 0, 0)                     # no insurance workshop
    + _workshop(_month(140505, 51, 310, 20, 60, 50), "سازمان بیمه تامین اجتماعی شعبه شمیران0957 - اکسیر")
    + _workshop(_month(140505, 32, 210, 10, 40, 30), "سازمان بیمه تامین اجتماعی شعبه شمیران0027- فراز")
    + _workshop(_month(140505, 52, 260, 10, 50, 40), "سازمان بیمه تامین اجتماعی شعبه اشتهارد 0002- کادوس")
    + _month(140505, 9, 60, 0, 0, 0)
)


def test_rahkaran_is_split_by_insurance_workshop_company_and_group_total_unchanged():
    data = _service(rows=COMPANY_ROWS).report()["data"]
    cards = {c["key"]: c for c in data["companies"]}
    assert [c["key"] for c in data["companies"]] == ["faraz", "exir", "kadus", "uninsured", "zarin"]
    assert cards["exir"]["latest_month"]["total_rial"] == 310 + 60
    assert cards["faraz"]["latest_month"]["headcount"] == 32
    assert cards["uninsured"]["latest_month"]["total_rial"] == 60
    assert cards["kadus"]["monthly_trend"][0]["month"] == "1405/04"
    # the group KPI (and the forecast) still use the Rahkaran total over every workshop
    assert data["kpis"]["headcount"] == 51 + 32 + 52 + 9
    assert data["kpis"]["total_rial"] == sum(cards[k]["latest_month"]["total_rial"] for k in ("exir", "faraz", "kadus", "uninsured"))


def test_zarin_comes_from_karamad_with_monthly_commission():
    service = _service()
    data = service.report()["data"]
    zarin = next(c for c in data["companies"] if c["key"] == "zarin")
    assert (zarin["system"], zarin["channel"]) == ("karamad", "hybrid")
    assert [m["commission_rial"] for m in zarin["monthly_trend"]] == [230, 470, 180]
    latest = zarin["latest_month"]
    assert latest["month"] == "1405/05" and latest["headcount"] == 103
    assert latest["total_rial"] == 400 + 90
    assert latest["base_pay_rial"] == 240 and latest["sales_commission_rial"] == 170
    month = next(r for r in data["by_company_monthly"] if r["month"] == "1405/05")
    assert month["companies"]["zarin"] == 490 and month["total_rial"] == 760 + 490


def test_karamad_down_keeps_rahkaran_payroll_with_warning():
    result = _service(zarin=ConnectionError("down")).report()
    assert result["data"]["kpis"]["total_rial"] == 760
    assert [c["key"] for c in result["data"]["companies"]] == ["uninsured"]
    assert result["warnings"][0]["code"] == "karamad_unavailable"
    assert result["sources"] == ["rahkaran"]


def test_only_trailing_months_can_be_in_progress():
    zarin = [_zarin_month(12, 105, 160, 300, 400, 30, 80, 20) | {"Year": 1404},
             _zarin_month(1, 81, 200, 30, 270, 17, 47, 5),     # Nowruz dip: a finished month
             _zarin_month(2, 95, 200, 180, 400, 17, 47, 15),
             _zarin_month(3, 10, 20, 0, 40, 0, 0, 0)]           # still being calculated
    zarin_card = next(c for c in _service(zarin=zarin).report()["data"]["companies"] if c["key"] == "zarin")
    assert [m["month"] for m in zarin_card["monthly_trend"]] == ["1404/12", "1405/01", "1405/02"]
