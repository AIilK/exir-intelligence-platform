from app.services.finance_prediction_service import FinancePredictionService
from app.services.explainable_alert_service import ExplainableAlertService


def _service():
    return FinancePredictionService(
        history_days=365,
        forecast_days=30,
        allowed_term_days=90,
        engine=object(),
    )


def test_customer_prediction_is_bounded_and_explainable():
    result = _service()._build_customer_prediction({
        "CounterPartRef": 1,
        "CounterPartCode": "C1",
        "CounterPartName": "Customer",
        "ChequeCount": 20,
        "TotalAmount": 1_000_000,
        "CollectedCount": 14,
        "ReturnedCount": 2,
        "OpenCount": 4,
        "OpenAmount": 400_000,
        "OverdueOpenCount": 2,
        "OverdueOpenAmount": 200_000,
        "UpcomingOpenAmount": 200_000,
        "ReturnedAmount": 100_000,
        "AverageChequeAmount": 50_000,
        "AverageTermDays": 95,
        "MaxTermDays": 130,
        "OverPolicyCount": 6,
    })
    assert 0 <= result["late_payment_risk"]["value"] <= 100
    assert 0 <= result["cheque_return_probability"]["value"] <= 100
    assert result["collection_forecast"]["expected_collection_amount"] >= 0
    assert result["evidence"]
    assert result["open_received_cheque_amount"] == 400_000
    assert result["overdue_open_received_cheque_amount"] == 200_000
    # Legacy aliases stay equal so existing API consumers do not break.
    assert result["open_received_cheque_amount"] == result["open_exposure"]
    assert result["overdue_open_received_cheque_amount"] == result["overdue_open_amount"]


def test_explainable_alert_contains_why_impact_and_recommendation():
    alerts = ExplainableAlertService.build(
        daily={},
        cheque_risk={"summary": {
            "issued_overdue_count": 2,
            "issued_overdue_total": 500,
            "protested_received_count": 0,
            "protested_received_total": 0,
            "overdue_scope": "previous_60_days",
        }},
        anomalies={"finding_count": 0},
        customer_predictions={"customers": []},
        cash_shortage={"absolute_shortage_available": False, "negative_cash_pressure_days": 0},
        collection_priorities={"customers": []},
    )
    alert = alerts[0]
    assert alert["why"]
    assert alert["impact"]
    assert alert["recommendations"]
