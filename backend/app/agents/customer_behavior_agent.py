from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class CustomerBehaviorAgent:
    """Agent مدیریتی روی خروجی قطعی موتورهای رفتار مشتری.

    این Agent اجازه محاسبه یا تغییر اعداد مالی را ندارد. ابزار آن، Dashboard
    محاسبه‌شده CustomerIntelligenceService است و خروجی‌اش فقط تفسیر مدیریتی است.
    """

    REQUIRED_KEYS = (
        "headline",
        "human_summary",
        "good_signals",
        "bad_signals",
        "future_outlook",
        "recommended_actions",
        "next_best_action",
    )

    def analyze(self, dashboard: dict[str, Any], *, trigger: str) -> dict[str, Any]:
        rule_analysis = dashboard.get("human_analysis") or {}
        metadata = {
            "agent_name": "Customer Behavior Agent",
            "agent_mode": "rules_only",
            "llm_enabled": False,
            "llm_configured": bool(settings.openai_api_key),
            "model": settings.customer_behavior_agent_model or settings.openai_model,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "trigger": trigger,
            "fallback_used": False,
            "fallback_reason": None,
        }

        if not settings.customer_behavior_agent_enabled:
            metadata["agent_mode"] = "disabled"
            metadata["fallback_reason"] = "customer_behavior_agent_disabled"
            return {"metadata": metadata, "analysis": rule_analysis, "rule_analysis": rule_analysis}

        if not settings.openai_api_key:
            metadata["fallback_used"] = True
            metadata["fallback_reason"] = "OPENAI_API_KEY_not_configured"
            return {"metadata": metadata, "analysis": rule_analysis, "rule_analysis": rule_analysis}

        try:
            analysis = self._run_llm(self._safe_context(dashboard))
            metadata["agent_mode"] = "llm"
            metadata["llm_enabled"] = True
            return {"metadata": metadata, "analysis": analysis, "rule_analysis": rule_analysis}
        except Exception as exc:
            logger.exception("Customer Behavior Agent LLM execution failed")
            metadata["fallback_used"] = True
            metadata["fallback_reason"] = f"{type(exc).__name__}: {str(exc)[:240]}"
            return {"metadata": metadata, "analysis": rule_analysis, "rule_analysis": rule_analysis}

    def _run_llm(self, context: dict[str, Any]) -> dict[str, Any]:
        from openai import OpenAI

        prompt = f"""
تو Customer Behavior Agent شرکت اکسیر کادوس هستی و برای مدیر مالی گزارش فارسی می‌نویسی.

قواعد قطعی:
- فقط بر اساس JSON ورودی تحلیل کن.
- هیچ عدد، مبلغ، درصد، نام مشتری یا رویدادی تولید یا تغییر نده.
- محاسبات ورودی را دوباره محاسبه نکن.
- پیش‌بینی را قطعی معرفی نکن.
- هشدار کاندید بررسی است، نه اثبات تخلف.
- برای اقدام‌های محدودکننده اعتبار، تأیید مدیر مالی را لازم بدان.
- خوب‌ها، بدها، چشم‌انداز آینده و اقدام مشخص را کوتاه و انسانی توضیح بده.

فقط یک JSON معتبر با این کلیدها برگردان:
headline: string
human_summary: string
good_signals: string[]
bad_signals: string[]
future_outlook: string
recommended_actions: array of objects with action, why, owner
next_best_action: string

داده ورودی:
{json.dumps(context, ensure_ascii=False, default=str)}
"""
        response = OpenAI(api_key=settings.openai_api_key).responses.create(
            model=settings.customer_behavior_agent_model or settings.openai_model,
            input=prompt,
        )
        payload = self._extract_json(response.output_text)
        missing = [key for key in self.REQUIRED_KEYS if key not in payload]
        if missing:
            raise ValueError("Agent JSON missing keys: " + ", ".join(missing))
        for key in ("good_signals", "bad_signals", "recommended_actions"):
            if not isinstance(payload[key], list):
                raise ValueError(f"Agent field {key} must be a list")
        return payload

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Agent response must be a JSON object")
        return payload

    @staticmethod
    def _safe_context(dashboard: dict[str, Any]) -> dict[str, Any]:
        """کاهش داده پیش از ارسال؛ بدون SQL خام، اطلاعات بانکی یا کل دیتابیس."""
        customer_fields = (
            "counterpart_ref", "counterpart_name", "risk_score", "risk_level",
            "outlook", "open_received_cheque_amount", "open_exposure",
            "overdue_open_received_cheque_amount", "overdue_open_amount",
            "over_policy_count", "expected_collection_amount", "collection_gap",
            "reasons", "recommended_actions",
        )
        customers = [
            {key: item.get(key) for key in customer_fields}
            for item in (dashboard.get("customers") or [])[: settings.customer_behavior_agent_max_customers]
        ]
        return {
            "as_of_date": dashboard.get("as_of_date"),
            "policy": dashboard.get("policy"),
            "summary": dashboard.get("summary"),
            "rule_analysis": dashboard.get("human_analysis"),
            "top_customers": customers,
            "limitations": dashboard.get("limitations"),
        }
