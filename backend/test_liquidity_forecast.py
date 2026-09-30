from datetime import date

import pytest

from app.services.liquidity import bank_balances
from app.services.liquidity.bank_balances import BankBalanceService, attach_balances
from app.services.liquidity.forecast import SCENARIOS, ForecastInputs, run_forecast, run_scenario

# 2026-09-30 = 1405/07/08 (Wednesday); 2026-10-02 is a Friday.
TODAY = date(2026, 9, 30)


@pytest.fixture(autouse=True)
def _fresh_cache():
    bank_balances.clear_cache()
    yield
    bank_balances.clear_cache()


def _scenario(key):
    return next(s for s in SCENARIOS if s.key == key)


def _inputs(**overrides):
    values = dict(today=TODAY, horizon_days=5, opening_balance_rial=1000.0,
                  median_inflow_rial=100.0, median_outflow_rial=50.0)
    values.update(overrides)
    return ForecastInputs(**values)


def test_estimated_flows_skip_friday():
    result = run_scenario(_inputs(), _scenario("reliance"))
    friday = next(d for d in result["days"] if d["date"] == "2026-10-02")
    assert friday["estimated_inflow_rial"] == 0 and friday["estimated_outflow_rial"] == 0
    # 4 working days × (100 − 50)
    assert result["closing_rial"] == 1200


def test_scenarios_pick_definite_or_reliance_cheques():
    received = {"2026-10-01": {"definite_rial": 500.0, "reliance_rial": 300.0}}
    inputs = _inputs(received=received, median_inflow_rial=0.0, median_outflow_rial=0.0)
    by_key = {s["key"]: s for s in run_forecast(inputs)["scenarios"]}
    assert by_key["definite"]["closing_rial"] == 1500
    assert by_key["reliance"]["closing_rial"] == 1300
    assert by_key["pessimistic"]["closing_rial"] == 1300


def test_pessimistic_halves_estimated_inflow():
    result = run_scenario(_inputs(median_outflow_rial=0.0), _scenario("pessimistic"))
    assert result["totals"]["estimated_inflow_rial"] == 200


def test_first_shortage_worst_balance_and_runway():
    inputs = _inputs(median_inflow_rial=0.0, median_outflow_rial=0.0,
                     issued={"2026-10-01": 1500.0},
                     received={"2026-10-03": {"definite_rial": 800.0, "reliance_rial": 800.0}},
                     payroll=[{"date": "2026-10-03", "amount_rial": 100.0}])
    result = run_scenario(inputs, _scenario("reliance"))
    assert result["first_shortage"]["date"] == "2026-10-01"
    assert result["runway_days"] == 1
    assert result["worst_balance"]["balance_rial"] == -500
    assert result["financing_need_rial"] == 500
    assert result["closing_rial"] == 200
    # (1000 + 800) / (1500 + 100)
    assert result["coverage_percent"] == 112.5


def test_covered_horizon_has_no_runway_limit():
    result = run_scenario(_inputs(), _scenario("reliance"))
    assert result["first_shortage"] is None and result["runway_days"] is None
    assert result["financing_need_rial"] == 0


RAHKARAN_ROWS = [
    {"SLCode": "126001", "AccountCode": "210210", "AccountName": "بلو بانک  611828288000026601 - اکسیر",
     "Balance": 5000, "LastDate": date(2026, 9, 30)},
    {"SLCode": "126001", "AccountCode": "210008", "AccountName": "سپه  جاری 925800096659 نادر علیزاده",
     "Balance": 9000, "LastDate": date(2026, 9, 29)},
    {"SLCode": "126001", "AccountCode": "210211", "AccountName": "بانک صادرات - 2947 0112779955005 - زرین",
     "Balance": 700, "LastDate": date(2026, 9, 1)},
    {"SLCode": "126001", "AccountCode": "210099", "AccountName": "بانک انصار 556543166820581",
     "Balance": -200, "LastDate": date(2026, 9, 30)},
    {"SLCode": "126002", "AccountCode": "201128", "AccountName": "سپه ارزی یورو 3620008150559",
     "Balance": 80, "LastDate": date(2026, 3, 21)},
    {"SLCode": "126003", "AccountCode": "601160", "AccountName": "غلامرضا دلیلی", "Balance": 300,
     "LastDate": date(2026, 9, 29)},
    {"SLCode": "126004", "AccountCode": "602059", "AccountName": "نادر علیزاده (شخصی)", "Balance": 400,
     "LastDate": date(2026, 9, 22)},
]
KARAMAD_ROWS = [
    {"SLCode": "1113", "AccountCode": "40535", "AccountName": "بانک پارسیان -20100275449603", "Balance": 2000,
     "LastDate": date(2026, 9, 24)},
    {"SLCode": "1113", "AccountCode": "40531", "AccountName": "صادرات 55005", "Balance": 690,
     "LastDate": date(2026, 3, 22)},
    {"SLCode": "1111", "AccountCode": "66662", "AccountName": "صندوق هیبرید اصفهان", "Balance": 50,
     "LastDate": date(2026, 9, 29)},
]


def _service():
    return BankBalanceService(today=TODAY, fetchers={"rahkaran": lambda _: RAHKARAN_ROWS,
                                                     "karamad": lambda _: KARAMAD_ROWS})


def test_balances_exclude_personal_fx_and_duplicate():
    data = _service().report("all")["data"]
    # R banks 5000 + 700 − 200, K bank 2000 (55005 counted once, from Rahkaran)
    assert data["bank_rial"] == 7500
    assert data["cash_rial"] == 350
    reasons = {e["reason"]: e["amount_rial"] for e in data["excluded"]}
    assert reasons == {"shareholder_personal": 9400, "duplicate": 690, "fx": 80}


def test_balances_per_channel_and_posting_lag_warning():
    report = _service().report("hybrid")
    assert report["data"]["bank_rial"] == 2000
    assert report["data"]["by_system"][0]["posting_lag_days"] == 1
    lagging = BankBalanceService(today=date(2026, 10, 5), fetchers={"karamad": lambda _: KARAMAD_ROWS}).report("hybrid")
    assert any(w["code"] == "karamad_posting_lag" for w in lagging["warnings"])


def test_negative_bank_balance_is_flagged():
    warnings = _service().report("b2b")["warnings"]
    assert any(w["code"] == "negative_bank_balance" for w in warnings)


def test_attach_balances_matches_account_number_and_coverage():
    accounts, _, _ = _service().accounts("all")
    table = [
        {"system": "rahkaran", "account_number": "611828288000026601", "overdue_rial": 1000.0, "next_30_days_rial": 1500.0,
         "balance_rial": None, "coverage_percent": None},
        {"system": "karamad", "account_number": None, "overdue_rial": 0.0, "next_30_days_rial": 10.0,
         "balance_rial": None, "coverage_percent": None},
    ]
    attach_balances(table, accounts)
    assert table[0]["balance_rial"] == 5000 and table[0]["coverage_percent"] == 200.0
    assert table[1]["balance_rial"] is None
