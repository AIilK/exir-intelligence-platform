from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.schemas.cheque_risk_intelligence import (
    ChequeRiskAssessment,
    ChequeRiskRuleOutput,
    CustomerChequePortfolio,
    RiskReason,
)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _level(score: float, high_threshold: float) -> str:
    if score >= max(90, high_threshold + 40):
        return "critical"
    if score >= max(65, high_threshold):
        return "high"
    if score >= max(40, high_threshold * 0.70):
        return "medium"
    return "low"


class ChequeRiskRuleEngine:
    """تمام چک‌ها را با قوانین قطعی شرکت ارزیابی و به تفکیک مشتری گروه‌بندی می‌کند."""

    def __init__(self, allowed_term_days: int = 90, high_threshold: float = 35):
        self.allowed_term_days = max(1, int(allowed_term_days))
        self.high_threshold = max(1, min(float(high_threshold), 100))

    def evaluate(self, report: dict[str, Any]) -> ChequeRiskRuleOutput:
        rows = report.get("cheques") or []
        assessments = [self._evaluate_cheque(row) for row in rows]
        assessments.sort(key=lambda item: (item.risk_score, item.amount), reverse=True)

        grouped: dict[int | None, list[ChequeRiskAssessment]] = defaultdict(list)
        for item in assessments:
            grouped[item.counterpart_ref].append(item)

        portfolios: list[CustomerChequePortfolio] = []
        for counterpart_ref, items in grouped.items():
            highest = max((item.risk_score for item in items), default=0)
            portfolios.append(
                CustomerChequePortfolio(
                    counterpart_ref=counterpart_ref,
                    counterpart_name=items[0].counterpart_name if items else "مشتری نامشخص",
                    cheque_count=len(items),
                    total_open_amount=sum(item.amount for item in items),
                    high_risk_count=sum(item.risk_level in {"high", "critical"} for item in items),
                    critical_risk_count=sum(item.risk_level == "critical" for item in items),
                    highest_risk_score=round(highest, 1),
                    risk_level=_level(highest, self.high_threshold),
                    customer_reliability_score=round(items[0].customer_reliability_score, 1),
                    customer_behavior_level=items[0].customer_behavior_level,
                    historical_collection_rate_percent=round(items[0].historical_collection_rate_percent, 2),
                    historical_return_rate_percent=round(items[0].historical_return_rate_percent, 2),
                    recommended_reliance_percent=round(items[0].recommended_reliance_percent, 2),
                    risk_adjusted_collectible_amount_rial=sum(
                        item.risk_adjusted_collectible_amount_rial for item in items
                    ),
                    recommended_credit_policy=items[0].recommended_credit_policy,
                    cheque_ids=[item.cheque_id for item in items],
                )
            )
        portfolios.sort(
            key=lambda item: (item.highest_risk_score, item.total_open_amount),
            reverse=True,
        )

        risky = [item for item in assessments if item.risk_level in {"high", "critical"}]
        return ChequeRiskRuleOutput(
            processed_cheque_count=len(assessments),
            customer_count=len(portfolios),
            high_risk_count=sum(item.risk_level == "high" for item in assessments),
            critical_risk_count=sum(item.risk_level == "critical" for item in assessments),
            over_policy_count=sum(
                (item.term_days or 0) > self.allowed_term_days for item in assessments
            ),
            total_open_amount=sum(item.amount for item in assessments),
            high_risk_open_amount=sum(item.amount for item in risky),
            assessments=assessments,
            customer_portfolios=portfolios,
            limitations=list(report.get("limitations") or []),
        )

    def _evaluate_cheque(self, row: dict[str, Any]) -> ChequeRiskAssessment:
        score = _number(row.get("estimated_return_probability_percent"))
        term_days = row.get("term_days")
        days_to_due = row.get("days_to_due")
        amount_ratio = _number(row.get("historical_amount_ratio"))
        reliability = _number(row.get("customer_reliability_score") or 50)
        collection_rate = _number(row.get("historical_collection_rate_percent"))
        return_rate = _number(row.get("historical_return_rate_percent"))
        reliance = _number(row.get("recommended_reliance_percent") or (100 - score))
        reasons: list[RiskReason] = []

        for message in row.get("reasons") or []:
            reasons.append(RiskReason(code="source_evidence", message=str(message)))

        if term_days is not None and int(term_days) > self.allowed_term_days:
            reasons.append(
                RiskReason(
                    code="over_term_policy",
                    message=f"مدت چک {int(term_days)} روز و بیشتر از سقف {self.allowed_term_days} روز شرکت است.",
                    weight=15,
                )
            )
        if amount_ratio >= 2:
            reasons.append(
                RiskReason(
                    code="unusual_amount",
                    message="مبلغ چک حداقل دو برابر میانگین تاریخی چک‌های این مشتری است.",
                    weight=8,
                )
            )
        if days_to_due is not None and 0 <= int(days_to_due) <= 7:
            reasons.append(
                RiskReason(
                    code="due_soon",
                    message=f"فقط {int(days_to_due)} روز تا سررسید چک باقی مانده است.",
                    weight=0,
                )
            )

        if reliability < 50:
            reasons.append(
                RiskReason(
                    code="weak_customer_history",
                    message=f"امتیاز خوش‌قولی مشتری {reliability:.1f} از ۱۰۰ است و نیازمند بازبینی اعتباری است.",
                    weight=10,
                )
            )
        elif reliability >= 80:
            reasons.append(
                RiskReason(
                    code="strong_customer_history",
                    message=f"امتیاز خوش‌قولی مشتری {reliability:.1f} از ۱۰۰ و سابقه وصول او مناسب است.",
                    weight=0,
                )
            )

        score = max(1, min(score, 95))
        level = _level(score, self.high_threshold)
        action = (
            "پیش از پذیرش اعتبار یا چک جدید، پرونده مشتری توسط مدیر مالی بررسی شود."
            if level in {"high", "critical"}
            else "چک در سررسید تعیین‌شده پایش شود."
        )
        return ChequeRiskAssessment(
            cheque_id=row.get("cheque_id") or "unknown",
            counterpart_ref=row.get("counterpart_ref"),
            counterpart_name=str(row.get("counterpart_name") or "مشتری نامشخص"),
            amount=_number(row.get("amount")),
            due_date=str(row.get("due_date")) if row.get("due_date") else None,
            due_date_jalali=row.get("due_date_jalali"),
            days_to_due=int(days_to_due) if days_to_due is not None else None,
            term_days=int(term_days) if term_days is not None else None,
            risk_score=round(score, 1),
            risk_level=level,
            customer_reliability_score=round(reliability, 1),
            customer_behavior_level=str(row.get("customer_behavior_level") or "unknown"),
            historical_collection_rate_percent=round(collection_rate, 2),
            historical_return_rate_percent=round(return_rate, 2),
            recommended_reliance_percent=round(max(0, min(reliance, 100)), 2),
            risk_adjusted_collectible_amount_rial=round(
                _number(row.get("amount")) * max(0, min(reliance, 100)) / 100,
                2,
            ),
            recommended_credit_policy=str(row.get("recommended_credit_policy") or "review"),
            reasons=reasons,
            recommended_action=action,
        )
