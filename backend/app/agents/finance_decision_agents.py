from __future__ import annotations

from typing import Any



def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def _toman(value_rial: float) -> str:
    value = value_rial / 10
    if abs(value) >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:,.1f} همت"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.1f} میلیارد تومان"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.1f} میلیون تومان"
    return f"{value:,.0f} تومان"


class FinanceManagerDecisionAgent:
    name = "Finance Manager Agent"
    role_fa = "هماهنگ‌کننده Agentها و پیشنهاد تصمیم نهایی"

    def run(self, agents: dict[str, Any], cheque_portfolio: dict[str, Any] | None = None, *, actual_report: dict[str, Any] | None = None, cashflow_report: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.agents.management_report import build_management_report
        return build_management_report(agents, cheque_portfolio or {}, actual_report, cashflow_report)

