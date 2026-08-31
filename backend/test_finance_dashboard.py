from app.services.customer_risk_service import CustomerRiskService


def test_customer_risk_flags_returned_and_long_term_cheques():
    result = CustomerRiskService().analyze(
        counterpart_code="C-1",
        counterpart_name="مشتری تست",
        cheque_count=10,
        total_amount=1_000_000_000,
        returned_count=1,
        returned_amount=150_000_000,
        average_term_days=80,
        max_term_days=140,
        allowed_term_days=90,
    )
    assert result["risk_level"] in {"medium", "high"}
    assert result["metrics"]["returned_amount_rate_percent"] == 15.0
    assert any(item["type"] == "term_over_policy" for item in result["alerts"])
