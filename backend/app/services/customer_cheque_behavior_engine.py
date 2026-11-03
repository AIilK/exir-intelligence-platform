from __future__ import annotations

from typing import Any


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _percent(value: float) -> float:
    return round(_clamp(value) * 100, 2)


class CustomerChequeBehaviorEngine:
    """Deterministic and auditable customer cheque-behaviour scoring.

    The engine receives one SQL aggregate row for a customer. It owns every
    financial calculation; an LLM may explain this output but must not change
    its scores, probabilities or recommended limits.
    """

    def __init__(self, *, allowed_term_days: int = 90, forecast_days: int = 30):
        self.allowed_term_days = max(1, int(allowed_term_days))
        self.forecast_days = max(1, int(forecast_days))

    def evaluate(self, row: dict[str, Any]) -> dict[str, Any]:
        cheque_count = int(row.get("ChequeCount") or 0)
        collected_count = int(row.get("CollectedCount") or 0)
        returned_count = int(row.get("ReturnedCount") or 0)
        open_count = int(row.get("OpenCount") or 0)
        overdue_open_count = int(row.get("OverdueOpenCount") or 0)
        over_policy_count = int(row.get("OverPolicyCount") or 0)
        resolved_count = collected_count + returned_count

        # Bayesian smoothing prevents one very small history from producing
        # an unrealistically certain 0% or 100% return probability.
        return_probability = (returned_count + 1.0) / (resolved_count + 10.0)
        collection_probability = 1.0 - return_probability
        overdue_open_ratio = overdue_open_count / max(open_count, 1)
        over_policy_ratio = over_policy_count / max(cheque_count, 1)

        late_risk = _clamp(
            0.50 * overdue_open_ratio
            + 0.25 * over_policy_ratio
            + 0.25 * return_probability,
            0.02,
            0.95,
        )
        expected_collection_rate = _clamp(
            collection_probability * (1.0 - 0.35 * late_risk),
            0.05,
            0.98,
        )

        resolved_collection_rate = collected_count / max(resolved_count, 1)
        resolved_return_rate = returned_count / max(resolved_count, 1)
        history_confidence_value = _clamp(resolved_count / 20.0, 0.20, 1.0)

        reliability_score = 100 * _clamp(
            0.55 * resolved_collection_rate
            + 0.20 * (1.0 - resolved_return_rate)
            + 0.15 * (1.0 - overdue_open_ratio)
            + 0.10 * (1.0 - over_policy_ratio)
        )
        reliability_score = 50 + (
            reliability_score - 50
        ) * history_confidence_value

        behavior_level = (
            "excellent" if reliability_score >= 85
            else "good" if reliability_score >= 70
            else "review" if reliability_score >= 50
            else "weak" if reliability_score >= 30
            else "high_risk"
        )

        # Customer-level reliance is shared by all open cheques. Cheque-specific
        # term and amount adjustments are applied later by ChequeRiskRuleEngine.
        recommended_reliance = _clamp(
            expected_collection_rate * (0.65 + 0.35 * history_confidence_value),
            0.10,
            0.95,
        )

        reliability_components = [
            {
                "title": "نرخ وصول چک‌های تعیین‌تکلیف‌شده",
                "weight_percent": 55,
                "observed_percent": _percent(resolved_collection_rate),
                "score_contribution": round(55 * resolved_collection_rate, 2),
            },
            {
                "title": "نداشتن سابقه واخواست",
                "weight_percent": 20,
                "observed_percent": _percent(1.0 - resolved_return_rate),
                "score_contribution": round(20 * (1.0 - resolved_return_rate), 2),
            },
            {
                "title": "نداشتن چک باز سررسیدگذشته",
                "weight_percent": 15,
                "observed_percent": _percent(1.0 - overdue_open_ratio),
                "score_contribution": round(15 * (1.0 - overdue_open_ratio), 2),
            },
            {
                "title": f"رعایت سقف سررسید {self.allowed_term_days} روز",
                "weight_percent": 10,
                "observed_percent": _percent(1.0 - over_policy_ratio),
                "score_contribution": round(10 * (1.0 - over_policy_ratio), 2),
            },
        ]

        improvement_actions: list[dict[str, str]] = []
        if resolved_count < 8:
            improvement_actions.append({
                "action": "نتیجه قطعی وصول یا واخواست چک‌ها منظم ثبت شود.",
                "why": "سابقه تعیین‌تکلیف‌شده کم است و ضریب اطمینان امتیاز را کاهش می‌دهد.",
                "expected_improvement": "افزایش اطمینان محاسبه پس از ثبت سابقه بیشتر",
            })
        if returned_count > 0:
            improvement_actions.append({
                "action": "چک‌های بعدی پس از تسویه موارد واخواست‌شده و تأیید مدیر مالی پذیرفته شود.",
                "why": f"{returned_count} سابقه واخواست در داده قطعی مشتری ثبت شده است.",
                "expected_improvement": "کاهش نرخ برگشت تاریخی در صورت وصول منظم چک‌های بعدی",
            })
        if overdue_open_ratio > 0:
            improvement_actions.append({
                "action": "چک‌های باز سررسیدگذشته فعلی تعیین‌تکلیف و نتیجه پیگیری ثبت شود.",
                "why": f"{overdue_open_count} فقره از {open_count} چک باز سررسیدگذشته است.",
                "expected_improvement": "کاهش نسبت معوق باز و افزایش امتیاز خوش‌قولی",
            })
        if over_policy_count > 0:
            improvement_actions.append({
                "action": f"چک جدید با سررسید حداکثر {self.allowed_term_days} روز دریافت شود.",
                "why": f"{over_policy_count} چک خارج از سیاست مدت شرکت ثبت شده است.",
                "expected_improvement": "کاهش ریسک مدت و افزایش قابلیت اتکای وصول",
            })
        if not improvement_actions:
            improvement_actions.append({
                "action": "رفتار وصول فعلی حفظ و نتایج چک‌ها بدون وقفه ثبت شود.",
                "why": "عامل منفی غالب در سابقه فعلی مشاهده نشده است.",
                "expected_improvement": "حفظ یا افزایش تدریجی سطح اطمینان",
            })

        credit_policy = (
            "accept_normal"
            if reliability_score >= 80 and overdue_open_ratio < 0.10
            else "accept_with_monitoring"
            if reliability_score >= 65 and overdue_open_ratio < 0.25
            else "accept_with_guarantee"
            if reliability_score >= 45
            else "manual_approval_required"
        )

        upcoming_amount = _number(row.get("UpcomingOpenAmount"))
        overdue_amount = _number(row.get("OverdueOpenAmount"))
        open_amount = _number(row.get("OpenAmount"))
        expected_collection_amount = (
            upcoming_amount * expected_collection_rate
            + overdue_amount * expected_collection_rate * 0.60
        )

        priority_score = (
            40 * (open_amount > 0)
            + 30 * overdue_open_ratio
            + 20 * late_risk
            + 10 * return_probability
        )

        confidence = (
            "high" if resolved_count >= 20
            else "medium" if resolved_count >= 8
            else "low"
        )
        evidence = [
            f"{collected_count} فقره وصول‌شده و {returned_count} فقره واخواست‌شده در سوابق تعیین‌تکلیف‌شده.",
            f"{overdue_open_count} فقره از {open_count} چک باز فعلی سررسیدگذشته است.",
            f"{over_policy_count} فقره خارج از سقف {self.allowed_term_days} روز ثبت شده است.",
        ]
        late_reasons: list[str] = []
        if overdue_open_ratio >= 0.25:
            late_reasons.append("نسبت چک‌های باز سررسیدگذشته بالاست.")
        if over_policy_ratio >= 0.20:
            late_reasons.append("تعداد قابل توجهی از چک‌ها خارج از سیاست سررسید هستند.")
        if return_probability >= 0.20:
            late_reasons.append("سابقه واخواست، ریسک دیرکرد یا عدم وصول را افزایش می‌دهد.")
        if not late_reasons:
            late_reasons.append("عامل پرریسک غالب در قواعد فعلی مشاهده نشد.")

        average_amount = _number(row.get("AverageChequeAmount"))
        return {
            "customer_behavior": {
                "reliability_score": round(reliability_score, 1),
                "behavior_level": behavior_level,
                "historical_collection_rate_percent": _percent(resolved_collection_rate),
                "historical_return_rate_percent": _percent(resolved_return_rate),
                "resolved_cheque_count": resolved_count,
                "open_overdue_ratio_percent": _percent(overdue_open_ratio),
                "history_confidence": confidence,
                "calculation_source": "customer_cheque_behavior_engine",
                "score_breakdown": reliability_components,
                "score_explanation": (
                    "امتیاز خوش‌قولی از نرخ وصول، سابقه واخواست، نسبت چک‌های "
                    "باز سررسیدگذشته و رعایت سقف مدت چک ساخته و سپس براساس "
                    "حجم سابقه تعدیل شده است."
                ),
            },
            "credit_decision": {
                "policy": credit_policy,
                "recommended_reliance_percent": _percent(recommended_reliance),
                "recommended_max_new_cheque_amount_rial": round(
                    average_amount
                    * (1.5 if reliability_score >= 80 else 1.0 if reliability_score >= 65 else 0.5),
                    2,
                ),
                "reasons": evidence,
                "reliance_calculation": {
                    "expected_collection_rate_percent": _percent(expected_collection_rate),
                    "history_confidence_factor_percent": round(
                        (0.65 + 0.35 * history_confidence_value) * 100,
                        2,
                    ),
                    "final_reliance_percent": _percent(recommended_reliance),
                    "formula_fa": "نرخ وصول مورد انتظار × ضریب اطمینان سابقه",
                },
                "improvement_actions": improvement_actions,
                "requires_human_approval": credit_policy
                in {"accept_with_guarantee", "manual_approval_required"},
            },
            "collection_forecast": {
                "forecast_days": self.forecast_days,
                "amount_due_or_overdue_in_scope": round(upcoming_amount + overdue_amount, 2),
                "expected_collection_rate_percent": _percent(expected_collection_rate),
                "expected_collection_amount": round(expected_collection_amount, 2),
                "confidence": "medium" if resolved_count >= 10 else "low",
                "calculation_type": "forecast",
            },
            "late_payment_risk": {
                "value": _percent(late_risk),
                "label": "high" if late_risk >= 0.55 else "medium" if late_risk >= 0.30 else "low",
                "reasons": late_reasons,
                "calculation_type": "forecast",
            },
            "cheque_return_probability": {
                "value": _percent(return_probability),
                "label": "high" if return_probability >= 0.35 else "medium" if return_probability >= 0.18 else "low",
                "calculation_type": "forecast",
            },
            "evidence": evidence,
            "collection_priority_base_score": round(priority_score, 2),
            "method": "transparent_customer_cheque_behavior_engine",
        }
