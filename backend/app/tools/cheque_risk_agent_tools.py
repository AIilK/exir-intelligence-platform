from __future__ import annotations

from typing import Any

from app.agents.cheque_risk_intelligence_agent import ChequeRiskIntelligenceAgent
from app.services.cheque_risk_rule_engine import ChequeRiskRuleEngine


def run_cheque_risk_agent_tool(
    report: dict[str, Any],
    *,
    allowed_term_days: int = 90,
    high_risk_threshold: float = 35,
    max_llm_cheques: int = 20,
) -> dict[str, Any]:
    """Tool قابل استفاده توسط Finance Manager برای اجرای Agent ریسک چک."""
    rule_output = ChequeRiskRuleEngine(
        allowed_term_days=allowed_term_days,
        high_threshold=high_risk_threshold,
    ).evaluate(report)
    return ChequeRiskIntelligenceAgent().run(
        rule_output,
        max_llm_cheques=max_llm_cheques,
    )

