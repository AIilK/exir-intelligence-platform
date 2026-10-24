from app.services.cheque_risk_rule_engine import ChequeRiskRuleEngine


def test_rule_engine_processes_more_than_300_cheques_and_keeps_customer_history():
    cheques = []
    for index in range(650):
        cheques.append(
            {
                "cheque_id": index + 1,
                "counterpart_ref": (index % 13) + 1,
                "counterpart_name": f"مشتری {(index % 13) + 1}",
                "amount": 100_000_000 + index,
                "days_to_due": index % 45,
                "term_days": 120 if index % 4 == 0 else 60,
                "historical_amount_ratio": 1.2,
                "estimated_return_probability_percent": 12 if index % 10 else 42,
                "customer_reliability_score": 82 if index % 10 else 44,
                "customer_behavior_level": "good" if index % 10 else "weak",
                "historical_collection_rate_percent": 91,
                "historical_return_rate_percent": 9,
                "recommended_reliance_percent": 78 if index % 10 else 35,
                "recommended_credit_policy": "accept_with_monitoring",
                "reasons": [],
            }
        )

    output = ChequeRiskRuleEngine().evaluate({"cheques": cheques})

    assert output.processed_cheque_count == 650
    assert output.customer_count == 13
    assert output.over_policy_count == 163
    assert output.assessments[0].recommended_reliance_percent == 35
    assert output.assessments[0].risk_adjusted_collectible_amount_rial > 0
    assert output.customer_portfolios[0].historical_collection_rate_percent == 91

