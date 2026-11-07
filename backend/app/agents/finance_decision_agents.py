from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings


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


class DecisionAgent:
    name = "Finance Decision Agent"
    role_fa = "تصمیم‌یار مالی"
    specialized_prompt_fa = ""
    prompt_profile = "generic_finance_decision_v1"

    def finish(self, context: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        metadata = {
            "agent_name": self.name, "role": self.role_fa,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "rules", "model": settings.customer_behavior_agent_model or settings.openai_model,
            "fallback_used": not bool(settings.openai_api_key),
            "prompt_profile": self.prompt_profile,
        }
        if not settings.openai_api_key:
            return {"metadata": metadata, "analysis": fallback}
        try:
            from openai import OpenAI
            prompt = f"""
تو {self.name} شرکت اکسیر کادوس هستی. نقش: {self.role_fa}.
دستور تخصصی این Agent:
{self.specialized_prompt_fa or "از قواعد عمومی تصمیم‌یار مالی پیروی کن."}

فقط اعداد و سناریوهای JSON ورودی را توضیح بده؛ عدد، درصد، نام یا رویداد جدید نساز.
پیش‌بینی قطعی نیست. راهکارها باید عملیاتی و دارای مسئول، اولویت، مهلت، دلیل و اثر مورد انتظار باشند.
مخاطب مدیرعامل و مدیر مالی است. هیچ نام فیلد انگلیسی، نام جدول، کد State، کد دیتابیس،
عدد خام ریالی یا اعشار طولانی در متن مدیریتی ننویس. مبالغ را به تومان خوانا و درصدها را
حداکثر با یک رقم اعشار نمایش بده. اقدام پیشنهادی باید یک کار اجرایی قابل فهم باشد، نه دستور فنی.
فقط JSON معتبر با ساختار زیر برگردان و همه کلیدها را نگه دار:
headline, summary, management_status, good_signals, risks, prediction,
scenarios, recommended_actions, next_best_action.
prediction شامل next_7_days, end_of_month, confidence, drivers, limitations است.
scenarios شامل optimistic, base, pessimistic است و اعداد آن را از ورودی تغییر نده.
داده محاسبه‌شده و fallback مجاز:
{json.dumps({"context": context, "allowed_output": fallback}, ensure_ascii=False, default=str)}
"""
            request_args = {"model": metadata["model"], "input": prompt}
            if self.specialized_prompt_fa:
                request_args["instructions"] = self.specialized_prompt_fa
            raw = OpenAI(api_key=settings.openai_api_key).responses.create(**request_args).output_text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(raw)
            required = {"headline", "summary", "prediction", "scenarios", "recommended_actions"}
            if not isinstance(result, dict) or not required.issubset(result):
                raise ValueError("decision agent JSON is incomplete")
            # Machine-calculated structures are authoritative. The LLM may
            # explain them, but it must never remove, rename or alter numbers.
            result["prediction"] = fallback.get("prediction") or {}
            result["scenarios"] = fallback.get("scenarios") or {}
            metadata["mode"] = "llm"; metadata["fallback_used"] = False
            return {"metadata": metadata, "analysis": result}
        except Exception as exc:
            metadata["fallback_used"] = True
            metadata["fallback_reason"] = f"{type(exc).__name__}: {str(exc)[:180]}"
            return {"metadata": metadata, "analysis": fallback}


class FinanceManagerDecisionAgent(DecisionAgent):
    name = "Finance Manager Agent"
    role_fa = "هماهنگ‌کننده Agentها و پیشنهاد تصمیم نهایی"

    def run(self, agents: dict[str, Any], cheque_portfolio: dict[str, Any] | None = None, *, actual_report: dict[str, Any] | None = None, cashflow_report: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.agents.management_report import build_management_report
        return build_management_report(agents, cheque_portfolio or {}, actual_report, cashflow_report)

