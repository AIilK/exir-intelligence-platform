from app.agents.customer_behavior_agent import CustomerBehaviorAgent
from app.core.config import settings


def test_agent_rules_fallback_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    dashboard = {
        "as_of_date": "2026-08-23",
        "policy": {"maximum_cheque_term_days": 90},
        "summary": {"customer_count": 1},
        "human_analysis": {"headline": "قاعده", "human_summary": "خلاصه"},
        "customers": [],
        "limitations": [],
    }
    result = CustomerBehaviorAgent().analyze(dashboard, trigger="test")
    assert result["metadata"]["agent_mode"] == "rules_only"
    assert result["metadata"]["fallback_used"] is True
    assert result["analysis"]["headline"] == "قاعده"


def test_agent_context_is_reduced(monkeypatch):
    monkeypatch.setattr(settings, "customer_behavior_agent_max_customers", 1)
    dashboard = {
        "as_of_date": "2026-08-23", "policy": {}, "summary": {},
        "human_analysis": {}, "limitations": [],
        "customers": [
            {"counterpart_ref": 1, "counterpart_name": "الف", "open_exposure": 10, "secret": "no"},
            {"counterpart_ref": 2, "counterpart_name": "ب", "open_exposure": 20},
        ],
    }
    context = CustomerBehaviorAgent._safe_context(dashboard)
    assert len(context["top_customers"]) == 1
    assert "secret" not in context["top_customers"][0]
