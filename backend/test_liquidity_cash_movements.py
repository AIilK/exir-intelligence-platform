from datetime import date, timedelta

import pytest

from app.services.liquidity import cash_movements
from app.services.liquidity.cash_movements import CashMovementService, Movement

# 1405/07/08 (Tuesday). Base window of 7 days = 2026-09-23 .. 2026-09-29.
TODAY = date(2026, 9, 30)


def _m(day, system, direction, code, amount, method="bank", counterpart=None, count=1, name=None, note=None):
    return Movement(day=day, system=system, direction=direction, method=method, account_code=code,
                    account_name=None, counterpart_code=counterpart, amount_rial=amount, count=count,
                    counterpart_name=name, note=note)


@pytest.fixture(autouse=True)
def _fresh_cache():
    cash_movements.clear_cache()
    yield
    cash_movements.clear_cache()


def _service(rahkaran=(), karamad=(), failing=()):
    def fetcher(system, rows):
        def fetch(_start, _end):
            if system in failing:
                raise ConnectionError("down")
            return list(rows)
        return fetch
    return CashMovementService(today=TODAY, fetchers={
        "rahkaran": fetcher("rahkaran", rahkaran),
        "karamad": fetcher("karamad", karamad),
    })


def test_inflow_average_uses_only_customer_collections_and_working_days():
    d = TODAY - timedelta(days=1)  # Tuesday 2026-09-29
    friday = date(2026, 9, 25)
    rahkaran = [
        _m(d, "rahkaran", "inflow", "123003", 600),
        _m(friday, "rahkaran", "inflow", "123003", 100),          # counted in total, not in working-day stats
        _m(d, "rahkaran", "inflow", "512029", 10_000, counterpart="950031"),  # shareholders
        _m(d, "rahkaran", "inflow", "512029", 5_000, counterpart="950028"),   # inter-bank
        _m(d, "rahkaran", "inflow", "412001", 7_000),                          # loan
        _m(TODAY, "rahkaran", "inflow", "123003", 9_999),         # today is incomplete: outside base
    ]
    karamad = [_m(d, "karamad", "inflow", "1313", 300, method="cash")]
    result = _service(rahkaran, karamad).inflows(base_days=7)
    stats = result["data"]["customer_collection"]
    assert stats["total_rial"] == 1000
    assert stats["working_days"] == 6
    # Working days: five zero days and one 900 day -> median 0, mean 150.
    assert stats["median_daily_rial"] == 0
    assert stats["mean_daily_rial"] == 150
    methods = {c["method"]: c["amount_rial"] for c in result["data"]["by_method"]}
    assert methods == {"bank": 700, "cash": 300}
    channels = {c["channel"]: c["amount_rial"] for c in result["data"]["by_channel"]}
    assert channels == {"b2b": 700, "hybrid": 300}
    assert result["sources"] == ["rahkaran", "karamad"]
    assert result["warnings"] == []


def test_channel_filter_reads_only_that_system():
    d = TODAY - timedelta(days=1)
    result = _service([_m(d, "rahkaran", "inflow", "123003", 500)],
                      [_m(d, "karamad", "inflow", "1313", 300)]).inflows(base_days=7, channel="hybrid")
    assert result["data"]["customer_collection"]["total_rial"] == 300
    assert result["sources"] == ["karamad"]


def test_outflow_categories_net_import_blocking_and_exclusions():
    d = TODAY - timedelta(days=2)
    rahkaran = [
        _m(d, "rahkaran", "outflow", "116001", 1_000),
        _m(d, "rahkaran", "inflow", "116001", 300),       # returned block reduces imports
        _m(d, "rahkaran", "outflow", "511002", 500),
        _m(d, "rahkaran", "outflow", "512002", 4_000),    # payroll: section 5
        _m(d, "rahkaran", "outflow", "512029", 2_000),    # shareholders: financing
        _m(d, "rahkaran", "outflow", "999999", 50),       # unmapped: review only
    ]
    karamad = [
        _m(d, "karamad", "outflow", "3112", 200),                      # stock settlement: internal
        _m(d, "karamad", "outflow", "3112", 150, note="fx_purchase"),  # FX bought for the company
        _m(d, "karamad", "outflow", "1113", 9_000),       # inter-bank
        _m(d, "karamad", "outflow", "3220", 800),         # Karamad payroll ignored
    ]
    result = _service(rahkaran, karamad).outflows(base_days=7)
    categories = {c["category"]: c["total_rial"] for c in result["data"]["categories"]}
    assert categories == {"imports": 850, "suppliers": 500}
    assert result["data"]["total"]["total_rial"] == 1350


def test_hybrid_settlement_is_shown_per_channel_and_eliminated_from_group():
    d = TODAY - timedelta(days=1)
    rahkaran = [
        _m(d, "rahkaran", "inflow", "123003", 1_000, name="شرکت B2B"),
        _m(d, "rahkaran", "inflow", "123003", 600, name="هیبرید غرب (پادینا)- تهران"),
    ]
    karamad = [
        _m(d, "karamad", "inflow", "1313", 400),
        _m(d, "karamad", "outflow", "3112", 600),
    ]
    service = _service(rahkaran, karamad)

    group = service.inflows(base_days=7)["data"]
    assert group["customer_collection"]["total_rial"] == 1400  # B2B customer + hybrid end customer
    assert group["hybrid_settlement"] == {
        **group["hybrid_settlement"],
        "received_by_company_rial": 600, "paid_by_hybrid_rial": 600, "eliminated_in_group": True}
    assert service.outflows(base_days=7)["data"]["total"]["total_rial"] == 0

    b2b = service.inflows(base_days=7, channel="b2b")["data"]
    assert b2b["customer_collection"]["total_rial"] == 1000
    assert b2b["hybrid_settlement"]["received_by_company_rial"] == 600
    assert b2b["hybrid_settlement"]["paid_by_hybrid_rial"] is None

    hybrid = service.outflows(base_days=7, channel="hybrid")["data"]
    assert hybrid["total"]["total_rial"] == 0
    assert hybrid["hybrid_settlement"]["paid_by_hybrid_rial"] == 600


def test_financing_shows_inflow_outflow_and_net():
    d = TODAY - timedelta(days=3)
    rahkaran = [
        _m(d, "rahkaran", "inflow", "512029", 1_000, counterpart="950031"),
        _m(d, "rahkaran", "outflow", "512029", 400, counterpart="950031"),
        _m(d, "rahkaran", "inflow", "412001", 2_000),
    ]
    data = _service(rahkaran).financing(base_days=7)["data"]
    items = {i["category"]: (i["inflow_rial"], i["outflow_rial"], i["net_rial"]) for i in data["items"]}
    assert items == {"loan": (2000, 0, 2000), "shareholders": (1000, 400, 600)}
    assert data["net_rial"] == 2600
    assert data["in_forecast"] is False


def test_data_quality_lists_review_items_and_excluded_totals():
    d = TODAY - timedelta(days=1)
    rahkaran = [
        _m(d, "rahkaran", "inflow", "512025", 70),
        _m(d, "rahkaran", "outflow", "999999", 30),
        _m(d, "rahkaran", "outflow", "512002", 4_000),
    ]
    data = _service(rahkaran).data_quality(base_days=7)["data"]
    assert {(i["category"], i["account_code"]) for i in data["review_items"]} == {
        ("unknown_deposit", "512025"), ("unmapped", "999999")}
    assert data["review_total_rial"] == 100
    assert {e["category"]: e["amount_rial"] for e in data["excluded_totals"]} == {"payroll_section": 4000}


def test_unavailable_system_returns_warning_instead_of_failing():
    d = TODAY - timedelta(days=1)
    result = _service([_m(d, "rahkaran", "inflow", "123003", 500)], failing=("karamad",)).inflows(base_days=7)
    assert result["data"]["customer_collection"]["total_rial"] == 500
    assert result["sources"] == ["rahkaran"]
    assert result["warnings"][0]["code"] == "karamad_unavailable"


def test_month_comparison_uses_same_number_of_days():
    # 1405/07/01 = 2026-09-23; today is 1405/07/08 -> 7 complete days compared.
    rahkaran = [
        _m(date(2026, 9, 23), "rahkaran", "inflow", "123003", 200),   # 1405/07/01
        _m(date(2026, 8, 23), "rahkaran", "inflow", "123003", 100),   # 1405/06/01
        _m(date(2026, 9, 5), "rahkaran", "inflow", "123003", 999),    # 1405/06/14: outside same period
    ]
    comparison = _service(rahkaran).inflows(base_days=30)["data"]["month_comparison"]
    assert comparison["current_month"] == "1405/07"
    assert comparison["days_compared"] == 7
    assert comparison["current_month_to_date_rial"] == 200
    assert comparison["previous_month_same_period_rial"] == 100
    assert comparison["change_percent"] == 100.0


def test_results_are_cached_until_refresh():
    calls = []

    def fetch(_start, _end):
        calls.append(1)
        return []

    service = CashMovementService(today=TODAY, fetchers={"rahkaran": fetch, "karamad": fetch})
    service.inflows(channel="b2b")
    service.outflows(channel="b2b")
    assert len(calls) == 1
    service.inflows(channel="b2b", refresh=True)
    assert len(calls) == 2
