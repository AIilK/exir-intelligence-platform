from __future__ import annotations

from typing import Any

from app.agents.finance_decision_agents import DecisionAgent
from app.schemas.cheque_risk_intelligence import ChequeRiskRuleOutput


def _toman(value_rial: float) -> str:
    value = value_rial / 10
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.1f} میلیارد تومان"
    if value >= 1_000_000:
        return f"{value / 1_000_000:,.1f} میلیون تومان"
    return f"{value:,.0f} تومان"


class ChequeRiskIntelligenceAgent(DecisionAgent):
    name = "Cheque Risk Intelligence Agent"
    role_fa = "تحلیل ریسک تمام چک‌های باز با استفاده از سابقه کامل مشتری"
    instructions_fa = """
    وضعیت بحرانی فقط زمانی مجاز است که critical_risk_count بزرگ‌تر از صفر باشد.
    چک high را بحرانی معرفی نکن؛ آن را «پرریسک و نیازمند توجه» بنام.
    عبور از سیاست ۹۰ روزه به‌تنهایی بحران نیست و فقط هشدار کنترلی است.
    آستانه‌های Rule Engine را تغییر نده و سطح ریسک را ارتقا نده.
    """

    def run(
        self,
        rule_output: ChequeRiskRuleOutput,
        max_llm_cheques: int = 20,
    ) -> dict[str, Any]:
        top_cheques = rule_output.assessments[:max(1, min(max_llm_cheques, 50))]
        top_customers = rule_output.customer_portfolios[:10]
        risky_count = rule_output.high_risk_count + rule_output.critical_risk_count
        status = (
            "critical" if rule_output.critical_risk_count else
            "attention" if rule_output.high_risk_count else
            "healthy"
        )

        fallback = {
            "headline": f"از {rule_output.processed_cheque_count} چک بررسی‌شده، {risky_count} چک نیازمند توجه فوری است.",
            "summary": (
                f"تمام چک‌ها با قواعد شرکت پردازش شدند. مبلغ چک‌های پرریسک "
                f"{_toman(rule_output.high_risk_open_amount)} و مربوط به "
                f"{rule_output.customer_count} مشتری است. سابقه وصول، برگشت و "
                f"چک‌های باز هر مشتری نیز در تصمیم اعتباری لحاظ شده است."
            ),
            "management_status": status,
            "good_signals": [
                f"{max(rule_output.processed_cheque_count-risky_count, 0)} چک در سطح ریسک بالا یا بحرانی نیستند."
            ],
            "risks": [
                f"چک {item.cheque_id} متعلق به {item.counterpart_name} با امتیاز {item.risk_score:.1f} در سطح {item.risk_level} است؛ "
                + f"امتیاز خوش‌قولی مشتری {item.customer_reliability_score:.1f} و درصد اتکای پیشنهادی {item.recommended_reliance_percent:.1f}٪ است؛ "
                + " ".join(reason.message for reason in item.reasons[:2])
                for item in top_cheques[:5]
            ],
            "prediction": {
                "next_7_days": {
                    "due_soon_risky_cheques": sum(
                        item.risk_level in {"high", "critical"}
                        and item.days_to_due is not None
                        and 0 <= item.days_to_due <= 7
                        for item in rule_output.assessments
                    )
                },
                "end_of_month": {
                    "high_and_critical_cheques": risky_count,
                    "high_risk_open_amount_rial": rule_output.high_risk_open_amount,
                },
                "confidence": "medium",
                "drivers": ["سابقه وصول و برگشت مشتری", "مدت چک", "مبلغ غیرعادی", "مانده باز سررسیدگذشته"],
                "limitations": rule_output.limitations,
            },
            "scenarios": {
                "optimistic": {"assumption": "پیگیری چک‌های اولویت‌دار و تحقق وصول", "risk_direction": "کاهشی"},
                "base": {"assumption": "ادامه رفتار فعلی مشتریان", "risk_direction": "باثبات"},
                "pessimistic": {"assumption": "عدم تحقق وصول چک‌های نزدیک", "risk_direction": "افزایشی"},
            },
            "recommended_actions": [
                {
                    "action": "پیگیری چک‌های پرریسک با سررسید هفت روز آینده",
                    "why": "این چک‌ها نزدیک‌ترین اثر را بر وصول و نقدینگی دارند",
                    "expected_effect": "کاهش احتمال دیرکرد و برگشت",
                    "owner": "کارشناس وصول",
                    "priority": "critical" if rule_output.critical_risk_count else "high",
                    "deadline": "امروز",
                },
                {
                    "action": "بازبینی اعتبار مشتریان دارای چند چک پرریسک",
                    "why": "تصمیم براساس نرخ وصول تاریخی، سابقه برگشت، مبلغ تعهد باز و امتیاز خوش‌قولی هر مشتری ساخته شده است",
                    "expected_effect": "جلوگیری از افزایش مانده پرریسک",
                    "owner": "مدیر مالی و فروش",
                    "priority": "high",
                    "deadline": "تا ۲۴ ساعت",
                },
            ],
            "next_best_action": "چک‌های نزدیک سررسید مشتریان با امتیاز خوش‌قولی پایین و درصد اتکای کم، امروز در اولویت پیگیری وصول قرار گیرند.",
        }

        context = {
            "portfolio_summary": {
                "processed_cheques": rule_output.processed_cheque_count,
                "customers": rule_output.customer_count,
                "high_risk": rule_output.high_risk_count,
                "critical": rule_output.critical_risk_count,
                "over_policy": rule_output.over_policy_count,
                "total_open_amount": rule_output.total_open_amount,
                "high_risk_open_amount": rule_output.high_risk_open_amount,
            },
            "top_risky_cheques": [item.model_dump() for item in top_cheques],
            "top_customer_portfolios": [item.model_dump() for item in top_customers],
            "limitations": rule_output.limitations,
        }
        result = self.finish(context, fallback)
        result["rule_output"] = rule_output.model_dump()
        return result
