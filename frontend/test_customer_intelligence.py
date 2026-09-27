from app.services.customer_intelligence_service import CustomerIntelligenceService


def test_customer_enrichment_is_explainable():
    service = object.__new__(CustomerIntelligenceService)
    service.forecast_days = 30
    service.allowed_term_days = 90
    row = {
        "counterpart_ref": 1, "counterpart_name": "مشتری تست", "open_exposure": 1_000_000,
        "overdue_open_amount": 500_000, "current_overdue_open_ratio_percent": 50,
        "late_payment_risk": {"value": 70, "label": "high", "reasons": ["نسبت معوق بالاست."]},
        "cheque_return_probability": {"value": 30, "label": "medium"},
        "collection_forecast": {"expected_collection_amount": 400_000},
    }
    result = service._enrich(row, None)
    assert result["risk_level"] == "high"
    assert result["human_explanation"]
    assert result["recommended_actions"]
    alert = service._alert(result)
    assert alert["why"] and alert["future"] and alert["recommendations"]


def test_over_90_day_policy_forces_warning_or_critical():
    service = object.__new__(CustomerIntelligenceService)
    service.forecast_days = 30
    service.allowed_term_days = 90
    row = {
        "counterpart_ref": 2, "counterpart_name": "مشتری خارج از سیاست",
        "open_exposure": 2_000_000, "overdue_open_amount": 1_000_000,
        "current_overdue_open_ratio_percent": 10, "over_policy_count": 6,
        "late_payment_risk": {"value": 10, "reasons": []},
        "cheque_return_probability": {"value": 5},
        "collection_forecast": {"expected_collection_amount": 500_000},
    }
    result = service._enrich(row, None)
    assert result["risk_level"] == "high"
    assert result["over_policy_count"] == 6
