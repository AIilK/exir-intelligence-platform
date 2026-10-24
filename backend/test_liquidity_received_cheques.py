from datetime import date, timedelta

import pytest

from app.services import finance_prediction_service as fps
from app.services.customer_cheque_behavior_engine import CustomerChequeBehaviorEngine
from app.services.finance_prediction_service import cheque_reliance_rules
from app.services.liquidity import received_cheques
from app.services.liquidity.received_cheques import ReceivedChequeService

TODAY = date(2026, 9, 30)


@pytest.fixture(autouse=True)
def _fresh_cache():
    received_cheques.clear_cache()
    yield
    received_cheques.clear_cache()


def _prediction(cheque_id, days, amount, reliance, name="مشتری B2B", holding="نزد بانک", ref=1):
    return {"cheque_id": cheque_id, "counterpart_ref": ref, "counterpart_code": str(ref), "counterpart_name": name,
            "serial_number": str(cheque_id), "amount": amount, "due_date": (TODAY + timedelta(days=days)).isoformat(),
            "recommended_reliance_percent": reliance, "customer_base_reliance_percent": reliance,
            "reliance_breakdown": {"deductions": []}, "reliance_reasons": [], "holding_label": holding}


def _k(cheque_id, days, amount, status, customer=100, name="گالری الف", branch="هیبرید تهران", visitor="ویزیتور ۱",
       received_days_before=30, sl="حسابهای دریافتنی"):
    due = TODAY + timedelta(days=days)
    return {"ChequeID": cheque_id, "Amount": amount, "DueDate": due, "ReceiptDate": due - timedelta(days=received_days_before),
            "StatusRef": status, "Serial": str(cheque_id), "CustomerRef": customer, "CustomerCode": str(customer),
            "CustomerName": name, "BranchRef": 1, "BranchName": branch, "VisitorName": visitor, "SLName": sl}


RAHKARAN = [
    _prediction(1, 5, 1000, 80),
    _prediction(2, 0, 500, 60, holding="نزد صندوق"),
    _prediction(3, -10, 300, 50),                                    # overdue: own card, not in totals
    _prediction(4, 40, 9000, 90),                                    # outside a 30-day horizon
    _prediction(5, 3, 700, 70, name="هیبرید غرب (پادینا)- تهران", ref=9),  # hybrid stock settlement
]
RAHKARAN_RETURNED = [
    {"ChequeID": 50, "Amount": 400, "DueDate": TODAY - timedelta(days=100), "State": 4, "CustomerName": "مشتری ب"},
    {"ChequeID": 51, "Amount": 600, "DueDate": TODAY - timedelta(days=900), "State": 4, "CustomerName": "مشتری ج"},
]
KARAMAD = (
    # Customer 100: 9 collected + 1 banked long ago (counts as collected) → strong history.
    [_k(1000 + i, -200 - i, 100, 4) for i in range(9)]
    + [_k(1100, -60, 100, 3)]
    # Customer 200: 5 returned (8 = returned then collected, 6 = returned at cashbox).
    + [_k(2000 + i, -150 - i, 100, 8, customer=200, name="گالری ب") for i in range(4)]
    + [_k(2010, -140, 100, 6, customer=200, name="گالری ب")]
    # Open cheques.
    + [_k(3000, 10, 1000, 3), _k(3001, 12, 1000, 2, customer=200, name="گالری ب", branch="هیبرید اصفهان"),
       _k(3002, -5, 200, 3), _k(3003, 20, 400, 1, customer=100)]
    + [_k(3004, 15, 5000, 2, sl="اسناد تضمینی")]   # guarantee: never counted
)


def _service(rahkaran=RAHKARAN, returned=RAHKARAN_RETURNED, karamad=KARAMAD, failing=()):
    def fetch(name, rows):
        def run():
            if name in failing:
                raise ConnectionError("down")
            return list(rows)
        return run
    return ReceivedChequeService(today=TODAY, fetchers={
        "rahkaran": fetch("rahkaran", rahkaran), "rahkaran_returned": fetch("rahkaran", returned),
        "karamad": fetch("karamad", karamad)})


def test_rahkaran_history_counts_every_collected_and_returned_state():
    assert fps._COLLECTED == "3, 30, 32, 33"
    assert fps._RETURNED == "4, 10, 17, 26"
    assert fps._OPEN == "1, 2, 16, 29"


def test_cheque_reliance_rules_keep_the_existing_deductions():
    customer = {"cheque_return_probability": {"value": 10.0}, "historical_average_cheque_amount": 100,
                "current_overdue_open_ratio_percent": 30, "credit_decision": {"recommended_reliance_percent": 80}}
    rules = cheque_reliance_rules(customer, 210, 30, 90)
    # 80 − 15 (≥2× average) − 10 (overdue exposure ≥25%) = 55; probability cap 100 − 26 = 74.
    assert rules["cheque_reliance"] == 55
    assert [d["code"] for d in rules["deductions"]] == ["unusual_amount", "overdue_exposure"]
    assert round(rules["probability"], 2) == 0.26


def test_definite_reliance_and_risk_in_horizon_for_rahkaran():
    data = _service(karamad=[]).report(horizon_days=30, channel="b2b")["data"]
    k = data["kpis"]["horizon"]
    assert (k["definite_rial"], k["reliance_rial"], k["collection_risk_rial"], k["count"]) == (1500, 1100, 400, 2)
    assert k["reliance_percent"] == round(1100 / 1500 * 100, 1)
    assert data["kpis"]["today"]["definite_rial"] == 500
    assert data["overdue"]["definite_rial"] == 300 and data["overdue"]["in_totals"] is False
    assert data["hybrid_settlement"]["definite_rial"] == 700
    assert {h["holding"]: h["definite_rial"] for h in data["by_holding"]} == {"bank": 1000, "cashbox": 500}


def test_karamad_reliance_comes_from_karamad_history():
    data = _service(rahkaran=[], returned=[]).report(horizon_days=30, channel="hybrid")["data"]
    by_name = {c["customer_name"]: c for c in data["customers"]}
    good, bad = by_name["گالری الف"], by_name["گالری ب"]
    assert good["reliance_percent"] > bad["reliance_percent"]
    assert good["resolved_history_count"] == 10 and bad["resolved_history_count"] == 5

    # The same engine + rules give the same number for the good customer's 1,000 cheque.
    # Customer 100 (guarantee excluded): 9 collected + 1 banked-long-ago + 3 open = 13 cheques.
    engine_row = {"ChequeCount": 13, "CollectedCount": 10, "ReturnedCount": 0, "OpenCount": 3,
                  "OverdueOpenCount": 1, "OverPolicyCount": 0, "OpenAmount": 1600, "OverdueOpenAmount": 200,
                  "UpcomingOpenAmount": 1400, "TotalAmount": 2600, "AverageChequeAmount": 2600 / 13}
    customer = CustomerChequeBehaviorEngine(allowed_term_days=90).evaluate(engine_row)
    customer["historical_average_cheque_amount"] = engine_row["AverageChequeAmount"]
    customer["current_overdue_open_ratio_percent"] = customer["customer_behavior"]["open_overdue_ratio_percent"]
    expected = cheque_reliance_rules(customer, 1000, 30, 90)["cheque_reliance"]
    cheque = _service(rahkaran=[], returned=[]).customer_detail("karamad", "100")["data"]["cheques"]
    assert next(c for c in cheque if c["serial_number"] == "3000")["reliance_percent"] == round(expected, 2)


def test_karamad_open_overdue_banked_rule_guarantee_and_holdings():
    data = _service(rahkaran=[], returned=[]).report(horizon_days=30, channel="hybrid")["data"]
    # Open in horizon: 3000 (bank), 3001 (cashbox), 3003 (pending). 3004 is a guarantee.
    assert data["kpis"]["horizon"]["definite_rial"] == 2400
    assert {h["holding"] for h in data["by_holding"]} == {"bank", "cashbox", "pending"}
    # 3002: banked 5 days overdue → overdue card; 1100: banked 60 days overdue → collected, gone.
    assert data["overdue"]["definite_rial"] == 200 and data["overdue"]["count"] == 1


def test_returned_open_card_is_information_only():
    card = _service().report(horizon_days=30)["data"]["returned_open"]
    # Rahkaran 400 + 600; Karamad status 6 cheque (100). Status 8 was collected after return.
    assert card["amount_rial"] == 1100 and card["count"] == 3
    assert card["last_365_days_rial"] == 500
    assert card["in_totals"] is False


def test_group_view_eliminates_hybrid_settlement_and_splits_channels():
    data = _service().report(horizon_days=30)["data"]
    assert data["kpis"]["horizon"]["definite_rial"] == 1500 + 2400
    assert {c["channel"]: c["definite_rial"] for c in data["by_channel"]} == {"b2b": 1500, "hybrid": 2400}
    assert data["hybrid_settlement"]["eliminated_in_group"] is True


def test_filters():
    service = _service()
    assert service.report(holding="pending")["data"]["kpis"]["horizon"]["definite_rial"] == 400
    assert service.report(branch="اصفهان")["data"]["kpis"]["horizon"]["definite_rial"] == 1000
    assert service.report(search="گالری ب")["data"]["kpis"]["horizon"]["count"] == 1
    high = service.report(reliance_band="high")["data"]["kpis"]["horizon"]
    assert high["definite_rial"] == 1000  # only the 80% Rahkaran cheque


def test_schedule_has_daily_definite_and_reliance_without_overdue_or_settlement():
    schedule = _service(karamad=[]).schedule(horizon_days=30, channel="b2b")
    assert schedule == {
        TODAY.isoformat(): {"definite_rial": 500, "reliance_rial": 300},
        (TODAY + timedelta(days=5)).isoformat(): {"definite_rial": 1000, "reliance_rial": 800},
    }


def test_unavailable_system_returns_warning():
    result = _service(failing=("karamad",)).report()
    assert result["sources"] == ["rahkaran"]
    assert result["warnings"][0]["code"] == "karamad_unavailable"
