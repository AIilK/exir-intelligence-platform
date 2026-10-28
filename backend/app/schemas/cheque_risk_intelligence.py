from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "critical"]


class RiskReason(BaseModel):
    code: str
    message: str
    weight: float = 0


class ChequeRiskAssessment(BaseModel):
    cheque_id: int | str
    counterpart_ref: int | None = None
    counterpart_name: str = "مشتری نامشخص"
    amount: float = Field(default=0, ge=0)
    due_date: str | None = None
    due_date_jalali: str | None = None
    days_to_due: int | None = None
    term_days: int | None = None
    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    customer_reliability_score: float = Field(default=50, ge=0, le=100)
    customer_behavior_level: str = "unknown"
    historical_collection_rate_percent: float = Field(default=0, ge=0, le=100)
    historical_return_rate_percent: float = Field(default=0, ge=0, le=100)
    recommended_reliance_percent: float = Field(default=50, ge=0, le=100)
    risk_adjusted_collectible_amount_rial: float = Field(default=0, ge=0)
    recommended_credit_policy: str = "review"
    reasons: list[RiskReason]
    recommended_action: str


class CustomerChequePortfolio(BaseModel):
    counterpart_ref: int | None = None
    counterpart_name: str = "مشتری نامشخص"
    cheque_count: int = 0
    total_open_amount: float = 0
    high_risk_count: int = 0
    critical_risk_count: int = 0
    highest_risk_score: float = 0
    risk_level: RiskLevel = "low"
    customer_reliability_score: float = Field(default=50, ge=0, le=100)
    customer_behavior_level: str = "unknown"
    historical_collection_rate_percent: float = Field(default=0, ge=0, le=100)
    historical_return_rate_percent: float = Field(default=0, ge=0, le=100)
    recommended_reliance_percent: float = Field(default=50, ge=0, le=100)
    risk_adjusted_collectible_amount_rial: float = Field(default=0, ge=0)
    recommended_credit_policy: str = "review"
    cheque_ids: list[int | str] = []


class ChequeRiskRuleOutput(BaseModel):
    processed_cheque_count: int
    customer_count: int
    high_risk_count: int
    critical_risk_count: int
    over_policy_count: int
    total_open_amount: float
    high_risk_open_amount: float
    assessments: list[ChequeRiskAssessment]
    customer_portfolios: list[CustomerChequePortfolio]
    limitations: list[str] = []
