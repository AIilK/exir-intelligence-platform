from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings


def _toman(value_rial: float) -> str:
    value = float(value_rial or 0) / 10
    if abs(value) >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:,.1f} همت"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.1f} میلیارد تومان"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.1f} میلیون تومان"
    return f"{value:,.0f} تومان"


class ExplainableFinanceAgent:
    name = "Finance Specialist Agent"
    role_fa = "تحلیل‌گر مالی"

    def analyze(self, context: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        metadata = {
            "agent_name": self.name,
            "role": self.role_fa,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "rules",
            "model": settings.customer_behavior_agent_model or settings.openai_model,
            "fallback_used": False,
        }
        if not settings.openai_api_key:
            metadata["fallback_used"] = True
            return {"metadata": metadata, "analysis": fallback}
        try:
            from openai import OpenAI
            prompt = f"""
تو {self.name} شرکت اکسیر کادوس هستی. نقش تو: {self.role_fa}.
فقط بر اساس JSON ورودی تحلیل کن. عدد و نام جدید نساز. پیش‌بینی را قطعی معرفی نکن.
هر مبلغ را فقط به تومان خوانا بنویس و هیچ مبلغی را با واحد ریال نمایش نده.
خروجی فقط JSON معتبر با کلیدهای headline, summary, good_signals, risks,
future_outlook, recommended_actions, next_best_action باشد. recommended_actions
آرایه‌ای از آبجکت‌های action, why, owner, priority است.
داده ورودی:
{json.dumps(context, ensure_ascii=False, default=str)}
"""
            raw = OpenAI(api_key=settings.openai_api_key).responses.create(
                model=metadata["model"], input=prompt
            ).output_text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("agent output is not an object")
            metadata["mode"] = "llm"
            return {"metadata": metadata, "analysis": result}
        except Exception as exc:
            metadata["fallback_used"] = True
            metadata["fallback_reason"] = f"{type(exc).__name__}: {str(exc)[:180]}"
            return {"metadata": metadata, "analysis": fallback}


class ChequeRiskAgent(ExplainableFinanceAgent):
    name = "Cheque Risk Agent"
    role_fa = "تحلیل ریسک برگشت، سررسید و قانون ۹۰ روز"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        rows = report.get("cheques") or []
        high = [x for x in rows if x.get("risk_level") == "high"]
        over = [x for x in rows if (x.get("term_days") or 0) > 90]
        top = sorted(rows, key=lambda x: (x.get("estimated_return_probability_percent") or 0, x.get("amount") or 0), reverse=True)[:5]
        fallback = {
            "headline": f"{len(high)} چک با ریسک بالا و {len(over)} چک خارج از سیاست ۹۰ روز شناسایی شد.",
            "summary": "ریسک هر چک از سابقه مشتری، مدت سررسید، مبلغ غیرعادی و چک‌های باز سررسیدگذشته ساخته شده است.",
            "good_signals": [f"{max(len(rows)-len(high), 0)} چک در سطح ریسک بالا نیستند."],
            "risks": [reason for row in top for reason in (row.get("reasons") or [])][:4],
            "future_outlook": "چک‌های نزدیک به سررسید و خارج از سیاست باید پیش از پذیرش چک جدید بررسی شوند.",
            "recommended_actions": [{"action": "پیگیری چک‌های پرریسک", "why": "کاهش احتمال برگشت و فشار نقدی", "owner": "وصول", "priority": "high"}, {"action": "محدودکردن چک بالاتر از ۹۰ روز", "why": "اجرای سیاست اعتباری شرکت", "owner": "مدیر مالی", "priority": "high"}],
            "next_best_action": "فهرست پنج چک با بالاترین احتمال برگشت امروز پیگیری شود.",
        }
        return self.analyze({"summary": {"count": len(rows), "high_risk": len(high), "over_90_days": len(over)}, "top_risky_cheques": top}, fallback)


class CashFlowAgent(ExplainableFinanceAgent):
    name = "Cash Flow Agent"
    role_fa = "تحلیل فشار و کسری نقدینگی و پیشنهاد سناریو"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        days = report.get("timeline") or []
        inflow = sum(float(x.get("projected_inflow") or 0) for x in days)
        outflow = sum(float(x.get("projected_outflow") or 0) for x in days)
        pressure = int(report.get("negative_cash_pressure_days") or 0)
        worst = min(days, key=lambda x: x.get("daily_net_change") or 0, default={})
        fallback = {
            "headline": "نقدینگی نیازمند کنترل است." if pressure else "روند نقدینگی در سناریوی محتمل مناسب است.",
            "summary": f"در افق گزارش، {pressure} روز فشار نقدی منفی شناسایی شده است.",
            "good_signals": [f"ورودی پیش‌بینی‌شده {_toman(inflow)} است."],
            "risks": ([f"سخت‌ترین روز {worst.get('date_jalali') or worst.get('date')} است."] if worst else []) + (["مانده افتتاحیه تنظیم نشده و کسری مطلق قابل اعلام نیست."] if not report.get("absolute_shortage_available") else []),
            "future_outlook": "نتیجه سناریویی است و با نرخ وصول واقعی و تغییر پرداخت‌ها به‌روزرسانی می‌شود.",
            "recommended_actions": [{"action": "ایجاد بافر نقدی", "why": "پوشش روزهای فشار", "owner": "خزانه", "priority": "high"}, {"action": "بازچینی پرداخت‌ها", "why": "انتقال پرداخت غیرضروری از روزهای منفی", "owner": "مدیر مالی", "priority": "medium"}],
            "next_best_action": "موجودی افتتاحیه ثبت و سناریوی وصول ۵۰ درصد اجرا شود.",
        }
        return self.analyze({"forecast_days": report.get("forecast_days"), "total_inflow": inflow, "total_outflow": outflow, "net": inflow-outflow, "pressure_days": pressure, "first_shortage": report.get("first_predicted_shortage_date_jalali"), "worst_day": worst, "limitations": report.get("limitations")}, fallback)


class CollectionAgent(ExplainableFinanceAgent):
    name = "Collection Agent"
    role_fa = "اولویت‌بندی وصول و مدیریت تعهدهای پرداخت"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        rows = report.get("priorities") or report.get("customers") or []
        top = rows[:10]
        fallback = {
            "headline": f"{len(rows)} مشتری در صف اولویت وصول قرار دارند.",
            "summary": "اولویت بر اساس مبلغ چک‌های دریافتی باز، دیرکرد، ریسک برگشت و احتمال وصول تعیین شده است.",
            "good_signals": ["صف پیگیری وصول به‌صورت عددی اولویت‌بندی شده است."],
            "risks": ["قول‌های پرداخت ثبت‌نشده یا پیگیری‌نشده می‌توانند پیش‌بینی را ضعیف کنند."],
            "future_outlook": "ثبت نتیجه هر تماس باعث قابل‌اندازه‌گیری‌شدن عملکرد وصول می‌شود.",
            "recommended_actions": [{"action": "تماس با پنج اولویت نخست", "why": "بیشترین اثر روی چک‌های باز سررسیدگذشته", "owner": "کارشناس وصول", "priority": "high"}],
            "next_best_action": "برای پنج مشتری اول مسئول و مهلت پیگیری تعیین شود.",
        }
        return self.analyze({"count": len(rows), "top_collection_priorities": top}, fallback)


class RepresentativeAgent(ExplainableFinanceAgent):
    name = "Representative Performance Agent"
    role_fa = "تحلیل کیفیت پرتفوی و وصول نمایندگان"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        rows = report.get("representatives") or []
        critical = [x for x in rows if x.get("status") == "critical"]
        fallback = {
            "headline": f"{len(critical)} نماینده دارای پرتفوی بحرانی است.",
            "summary": "نمایندگان بر اساس تعداد مشتری پرریسک، چک‌های باز سررسیدگذشته و کیفیت وصول مقایسه شده‌اند.",
            "good_signals": [f"اطلاعات {len(rows)} نماینده قابل مقایسه است."],
            "risks": [f"{report.get('unmapped_customer_count', 0)} مشتری هنوز به نماینده متصل نشده است."],
            "future_outlook": "تکمیل Mapping مشتری و نماینده کیفیت پاسخ‌گویی را افزایش می‌دهد.",
            "recommended_actions": [{"action": "جلسه با نمایندگان بحرانی", "why": "کاهش ریسک پرتفوی فروش", "owner": "مدیر فروش", "priority": "medium"}],
            "next_best_action": "مشتریان بدون نماینده تعیین تکلیف شوند.",
        }
        return self.analyze({"count": len(rows), "critical_count": len(critical), "unmapped": report.get("unmapped_customer_count"), "representatives": rows[:15]}, fallback)


class FinanceManagerAgent(ExplainableFinanceAgent):
    name = "Finance Manager Agent"
    role_fa = "مدیر هماهنگ‌کننده همه Agentهای مالی و تولید خلاصه مدیریتی"

    def run(self, agents: dict[str, Any]) -> dict[str, Any]:
        analyses = {key: value.get("analysis", {}) for key, value in agents.items()}
        risks = [r for a in analyses.values() for r in (a.get("risks") or a.get("bad_signals") or [])][:7]
        actions = [x for a in analyses.values() for x in (a.get("recommended_actions") or [])][:8]
        fallback = {
            "headline": "گزارش یکپارچه Agentهای مالی آماده است.",
            "summary": "این جمع‌بندی از خروجی Agent رفتار مشتری، چک، نقدینگی، وصول و نمایندگان ساخته شده است.",
            "management_status": "critical" if len(risks) >= 8 else "attention" if risks else "healthy",
            "good_signals": [x for a in analyses.values() for x in (a.get("good_signals") or [])][:4],
            "risks": risks,
            "future_outlook": "ریسک‌ها باید همراه نتیجه پیگیری و عملکرد واقعی روزهای آینده دوباره ارزیابی شوند.",
            "recommended_actions": actions,
            "decisions_today": [x.get("action") for x in actions[:3] if isinstance(x, dict)],
            "seven_day_plan": ["پیگیری مشتریان و چک‌های بحرانی", "ثبت قول‌های پرداخت", "اجرای سناریوی بدبینانه نقدینگی", "بازبینی نتیجه هشدارها"],
            "next_best_action": actions[0].get("action") if actions and isinstance(actions[0], dict) else "اجرای گزارش کامل مالی",
        }
        return self.analyze({"specialist_agent_outputs": analyses}, fallback)
