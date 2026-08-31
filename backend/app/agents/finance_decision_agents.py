from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.agents.cash_bank_movement_prompts import CASH_BANK_MOVEMENT_SYSTEM_PROMPT_FA


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _maybe_num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _manager_sentence(value: Any) -> str:
    """Convert specialist evidence to board-level Persian without losing the number."""
    text = str(value or "").strip()
    text = re.sub(
        r"(?<![\d.])([\d,]+(?:\.\d+)?)\s*ریال",
        lambda match: _toman(_num(match.group(1).replace(",", ""))),
        text,
    )
    replacements = {
        "upcoming": "در انتظار سررسید",
        "days_overdue": "روز تأخیر",
        "State=11": "باز و تعیین‌تکلیف‌نشده",
        "State=28": "پرداخت‌شده قطعی",
        "CounterPartRef": "شناسه مشتری",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _action(action: str, reason: str, effect: str, owner: str, priority: str, deadline: str) -> dict[str, str]:
    return {"action": action, "why": reason, "expected_effect": effect, "owner": owner, "priority": priority, "deadline": deadline}


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


class CustomerRiskDecisionAgent(DecisionAgent):
    name = "Customer Risk Decision Agent"
    role_fa = "پیش‌بینی ریسک مشتری و پیشنهاد سیاست اعتبار"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        rows = report.get("customers") or []
        critical = [x for x in rows if _num(x.get("risk_score")) >= 85]
        requiring_attention = [
            x for x in rows
            if str(x.get("risk_level") or "").lower() in {"high", "critical"}
            or _num(x.get("risk_score")) >= 70
        ]
        open_amount = sum(_num(x.get("open_exposure") or x.get("open_received_cheque_amount")) for x in rows)
        overdue = sum(_num(x.get("overdue_open_amount") or x.get("overdue_open_received_cheque_amount")) for x in rows)
        ratio = overdue / open_amount * 100 if open_amount else 0
        top = sorted(rows, key=lambda x: (_num(x.get("risk_score")), _num(x.get("open_exposure"))), reverse=True)[:5]
        status = "critical" if ratio >= 75 or len(critical) >= 20 else "attention" if ratio >= 30 or requiring_attention else "healthy"
        fallback = {
            "headline": f"{len(critical)} مشتری در سطح پرریسک قرار دارد.",
            "summary": f"نسبت مبلغ سررسیدگذشته به چک‌های باز {ratio:.1f}٪ است و سیاست اعتبار باید بر مشتریان اولویت‌دار متمرکز شود.",
            "management_status": status,
            "good_signals": [f"برای {len(rows)} مشتری پرونده عددی قابل مقایسه وجود دارد."],
            "risks": [f"مبلغ چک‌های باز سررسیدگذشته {_toman(overdue)} است."] if overdue else [],
            "prediction": {"next_7_days": {"customers_requiring_review": len(critical)}, "end_of_month": {"risk_direction": "افزایشی" if ratio >= 30 else "باثبات"}, "confidence": "medium" if len(rows) >= 20 else "low", "drivers": ["مانده باز", "سررسیدگذشته", "سابقه برگشت", "مدت چک"], "limitations": ["نتیجه تماس و قول پرداخت باید روزانه ثبت شود."]},
            "scenarios": {"optimistic": {"assumption": "پیگیری پنج مشتری اول و تحقق قول‌ها", "overdue_pressure": "کاهشی"}, "base": {"assumption": "ادامه روند فعلی", "overdue_pressure": "باثبات"}, "pessimistic": {"assumption": "عدم تحقق قول‌های پرداخت", "overdue_pressure": "افزایشی"}},
            "recommended_actions": [
                _action("بازبینی اعتبار پنج مشتری اول", "بالاترین ترکیب ریسک و مانده باز", "کاهش پذیرش ریسک جدید", "مدیر مالی و فروش", "high", "امروز"),
                _action("ثبت نتیجه تماس و قول پرداخت", "بهبود دقت پیش‌بینی رفتار", "تبدیل ریسک به برنامه وصول قابل سنجش", "وصول", "high", "تا ۲۴ ساعت"),
            ],
            "next_best_action": "پرونده پنج مشتری پرریسک اول امروز تعیین تکلیف شود.",
        }
        return self.finish({"customer_count": len(rows), "critical_count": len(critical), "open_amount": open_amount, "overdue_amount": overdue, "overdue_ratio": ratio, "top_customers": top}, fallback)


class CustomerChequeBehaviorDecisionAgent(DecisionAgent):
    name = "Customer Cheque Behavior Agent"
    role_fa = "تحلیل خوش‌قولی مشتری و پیشنهاد سیاست پذیرش چک"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        rows = report.get("customers") or []
        ranked = sorted(
            rows,
            key=lambda item: (
                _num((item.get("customer_behavior") or {}).get("reliability_score")),
                -_num(item.get("open_exposure")),
            ),
        )
        review = [
            item for item in ranked
            if (item.get("credit_decision") or {}).get("requires_human_approval")
        ]
        weak = [
            item for item in ranked
            if _num((item.get("customer_behavior") or {}).get("reliability_score")) < 50
        ]
        reliable = [
            item for item in ranked
            if _num((item.get("customer_behavior") or {}).get("reliability_score")) >= 70
        ]
        top_review = review[:10]
        expected = sum(
            _num((item.get("collection_forecast") or {}).get("expected_collection_amount"))
            for item in rows
        )
        fallback = {
            "headline": f"رفتار چکی {len(rows)} مشتری بررسی شد؛ {len(review)} پرونده نیازمند تأیید انسانی است.",
            "summary": f"{len(reliable)} مشتری امتیاز خوش‌قولی حداقل ۷۰ دارند و وصول مورد انتظار سبد {_toman(expected)} است.",
            "management_status": "attention" if review else "healthy",
            "good_signals": [f"{len(reliable)} مشتری سابقه وصول مناسب و امتیاز خوش‌قولی حداقل ۷۰ دارند."],
            "risks": [f"{len(weak)} مشتری امتیاز خوش‌قولی کمتر از ۵۰ دارند."] if weak else [],
            "prediction": {
                "next_7_days": {"customers_requiring_credit_review": len(review)},
                "end_of_month": {"expected_collection_amount": expected},
                "confidence": "medium" if rows else "low",
                "drivers": ["نرخ وصول تاریخی", "سابقه واخواست", "چک باز سررسیدگذشته", "مدت چک"],
                "limitations": ["امتیازها تصمیم‌یار هستند و پذیرش یا رد اعتبار نیازمند تأیید مدیر مالی است."],
            },
            "scenarios": {
                "optimistic": {"assumption": "تحقق وصول مورد انتظار مشتریان خوش‌قول", "direction": "بهبود"},
                "base": {"assumption": "تداوم رفتار تاریخی ثبت‌شده", "direction": "باثبات"},
                "pessimistic": {"assumption": "عدم تحقق وصول مشتریان نیازمند بازبینی", "direction": "افزایش ریسک"},
            },
            "recommended_actions": [
                _action("بازبینی پرونده مشتریان نیازمند تأیید", "امتیاز خوش‌قولی و تعهد باز آن‌ها نیازمند کنترل است", "کاهش پذیرش ریسک جدید", "مدیر اعتبارات", "high", "امروز"),
                _action("ثبت نتیجه وصول و واخواست هر چک", "دقت امتیاز خوش‌قولی به نتیجه واقعی وابسته است", "افزایش دقت پیش‌بینی", "واحد وصول", "high", "روزانه"),
            ],
            "next_best_action": "مشتریان نیازمند تأیید انسانی، پیش از پذیرش چک جدید بازبینی شوند.",
        }
        context = {
            "customer_count": len(rows),
            "reliable_count": len(reliable),
            "weak_count": len(weak),
            "human_review_count": len(review),
            "expected_collection_amount": expected,
            "top_review_customers": top_review,
        }
        return self.finish(context, fallback)


class ChequePaymentDecisionAgent(DecisionAgent):
    name = "Cheque Payment Decision Agent"
    role_fa = "پیش‌بینی پوشش و پاس‌شدن چک‌های پرداختی"

    def run(self, quality: dict[str, Any], monthly: dict[str, Any] | None) -> dict[str, Any]:
        actual = quality.get("issued_actual_payment_rate") or {}
        actual_rate = _num(actual.get("amount_rate_percent"))
        count_rate = _num(actual.get("count_rate_percent"))
        forecast = (monthly or {}).get("forecast") or {}
        summary = (monthly or {}).get("summary") or {}
        has_monthly_data = bool(monthly and monthly.get("status") == "success")
        capacity_value = _maybe_num(forecast.get("estimated_payment_capacity_percent")) if has_monthly_data else None
        capacity = capacity_value if capacity_value is not None else 0.0
        latest_cash = _num(summary.get("latest_liquidity_rial"))
        latest_obligation = _num(summary.get("latest_obligations_rial"))
        base = capacity_value
        optimistic = _pct(latest_cash * 1.10 / latest_obligation * 100) if has_monthly_data and latest_obligation else None
        pessimistic = _pct(latest_cash * .80 / latest_obligation * 100) if has_monthly_data and latest_obligation else None
        status = "critical" if capacity < 80 else "attention" if capacity < 100 else "healthy"
        fallback = {
            "headline": (f"توان پوشش چک‌ها {capacity:.0f}٪ است؛ اما تاکنون {actual_rate:.1f}٪ از مبلغ چک‌های سررسیدشده به‌صورت قطعی پاس شده است." if capacity_value is not None else "برای محاسبه توان پوشش چک‌ها Snapshot معتبر Cash Flow کافی نیست."),
            "summary": "ظرفیت، توان نقدی آینده است؛ نرخ واقعی از State=28 چک‌های معتبر سررسیدشده SQL محاسبه می‌شود.",
            "management_status": status,
            "good_signals": [f"موجودی آخرین Snapshot برابر {_toman(latest_cash)} است."] if latest_cash else [],
            "risks": [f"تنها {count_rate:.1f}٪ از تعداد چک‌های معتبر سررسیدشده، پرداخت قطعی ثبت‌شده دارند.", "اختلاف زیاد میان موجودی قابل پوشش و پرداخت قطعی نیازمند بررسی چک‌های باز سررسیدگذشته است."],
            "prediction": {"next_7_days": {"payment_capacity_percent": base, "latest_obligations_rial": latest_obligation}, "end_of_month": {"estimated_payment_capacity_percent": capacity, "actual_payment_rate_to_date_percent": actual_rate}, "confidence": forecast.get("confidence") or "low", "drivers": ["موجودی آخرین Snapshot", "چک‌های سررسیدشده", "State=11 فعال", "State=28 پاس‌شده"], "limitations": ["ظرفیت پرداخت معادل تضمین پاس‌شدن نیست."]},
            "scenarios": {"optimistic": {"assumption": "۱۰٪ افزایش موجودی قابل استفاده", "payment_capacity_percent": optimistic, "available": optimistic is not None}, "base": {"assumption": "ادامه موجودی فعلی", "payment_capacity_percent": base, "available": base is not None}, "pessimistic": {"assumption": "۲۰٪ افت موجودی قابل استفاده", "payment_capacity_percent": pessimistic, "available": pessimistic is not None}},
            "recommended_actions": [
                _action("بررسی چک‌های پرداختی سررسیدگذشته که هنوز در سیستم باز هستند", "با وجود موجودی کافی، بخشی از چک‌های سررسیدشده هنوز پرداخت قطعی ثبت‌شده ندارند", "تفکیک چک واقعاً پرداخت‌نشده از سندی که وضعیت آن به‌روزرسانی نشده است", "مدیر خزانه", "critical", "امروز"),
                _action("رزرو وجه روزهای پرتراکم", "جلوگیری از کسری لحظه‌ای حساب صادرکننده", "افزایش احتمال پاس‌شدن چک", "مدیر خزانه", "high", "۳ روز قبل از سررسید"),
            ],
            "next_best_action": "مدیر خزانه امروز فهرست چک‌های پرداختی سررسیدگذشته و باز را با گردش بانک تطبیق دهد و نتیجه هر چک را مشخص کند.",
        }
        return self.finish({"actual_payment": actual, "monthly_cashflow_summary": summary, "monthly_forecast": forecast, "computed_scenarios": fallback["scenarios"]}, fallback)


class CashFlowDecisionAgent(DecisionAgent):
    name = "Cash Flow Prediction Agent"
    role_fa = "پیش‌بینی نقدینگی و پیشنهاد جلوگیری از کسری"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        days = report.get("timeline") or []
        reliance = report.get("reliance_summary") or {}
        seven = days[:7]
        inflow7 = sum(_num(x.get("projected_inflow")) for x in seven)
        outflow7 = sum(_num(x.get("projected_outflow")) for x in seven)
        inflow = sum(_num(x.get("projected_inflow")) for x in days)
        outflow = sum(_num(x.get("projected_outflow")) for x in days)
        pressure = int(report.get("negative_cash_pressure_days") or 0)
        worst = min(days, key=lambda x: _num(x.get("daily_net_change")), default={})
        def scenario(rate: float) -> dict[str, Any]:
            adjusted_inflow = inflow * rate
            return {"collection_multiplier": rate, "projected_inflow": round(adjusted_inflow, 2), "projected_outflow": round(outflow, 2), "net_change": round(adjusted_inflow-outflow, 2)}
        status = "critical" if report.get("first_predicted_shortage_date_jalali") else "attention" if pressure else "healthy"
        fallback = {
            "headline": "کسری نقدینگی پیش‌بینی شده است." if status == "critical" else f"در افق پیش‌بینی {pressure} روز فشار نقدی وجود دارد.",
            "summary": f"خالص هفت‌روزه {_toman(inflow7-outflow7)} و خالص کل افق {_toman(inflow-outflow)} برآورد شده است. از چک‌های دریافتی این افق، { _num(reliance.get('portfolio_reliance_percent')):.1f}٪ مبلغ اسمی در سناریوی پایه قابل اتکا در نظر گرفته شده است.",
            "management_status": status,
            "good_signals": [f"ورودی کل پیش‌بینی‌شده {_toman(inflow)} است."],
            "risks": ([f"سخت‌ترین روز {worst.get('date_jalali') or worst.get('date')} با خالص {_toman(_num(worst.get('daily_net_change')))} است."] if worst else []) + (["مانده افتتاحیه ثبت نشده است."] if not report.get("absolute_shortage_available") else []) + ([f"برای احتیاط، {_toman(_num(reliance.get('risk_reduction_rial')))} از مبلغ اسمی چک‌های دریافتی وارد سناریوی پایه نشده است."] if _num(reliance.get("risk_reduction_rial")) else []),
            "prediction": {"next_7_days": {"inflow": inflow7, "outflow": outflow7, "net_change": inflow7-outflow7}, "end_of_month": {"inflow": inflow, "outflow": outflow, "net_change": inflow-outflow, "first_shortage": report.get("first_predicted_shortage_date_jalali")}, "confidence": "medium" if len(days) >= 14 else "low", "drivers": ["وصول چک دریافتی", "چک پرداختی", "میانگین دریافت و پرداخت عملیاتی"], "limitations": report.get("limitations") or []},
            "scenarios": {"optimistic": scenario(1.10), "base": scenario(1.0), "pessimistic": scenario(.75)},
            "recommended_actions": [
                _action("رزرو بافر نقدی پیش از سخت‌ترین روز", "پوشش تمرکز خروجی", "کاهش احتمال کسری", "خزانه", "critical" if status == "critical" else "high", "۲ روز قبل"),
                _action("جلو انداختن وصول مشتریان اولویت‌دار", "تقویت ورودی قبل از پرداخت‌ها و افزایش تحقق مبلغ قابل اتکا", "بهبود خالص نقدینگی", "وصول", "high", "تا ۴۸ ساعت"),
                _action("بازچینی پرداخت غیرضروری", "انتقال خروجی از روز منفی", "کاهش فشار روزانه", "مدیر مالی", "medium", "این هفته"),
            ],
            "next_best_action": "موجودی افتتاحیه و مانده واقعی حساب پرداخت امروز ثبت شود.",
        }
        return self.finish({"forecast": fallback["prediction"], "scenarios": fallback["scenarios"], "worst_day": worst, "reliance_summary": reliance}, fallback)


class CollectionDecisionAgent(DecisionAgent):
    name = "Collection Decision Agent"
    role_fa = "پیش‌بینی وصول و تعیین اقدام بعدی مشتریان"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        rows = report.get("priorities") or report.get("customers") or []
        top = rows[:10]
        expected = sum(_num(x.get("expected_collection_amount") or x.get("collection_forecast")) for x in rows)
        exposure = sum(_num(x.get("open_exposure") or x.get("open_amount")) for x in rows)
        fallback = {
            "headline": f"{len(rows)} مشتری در صف وصول قرار دارند.", "summary": f"وصول مورد انتظار ثبت‌شده {_toman(expected)} از مانده {_toman(exposure)} است.", "management_status": "attention" if rows else "healthy",
            "good_signals": ["صف وصول بر اساس اثر مالی اولویت‌بندی شده است."], "risks": ["عدم ثبت نتیجه تماس و قول پرداخت، پیش‌بینی را کم‌دقت می‌کند."],
            "prediction": {"next_7_days": {"top_customer_count": min(10, len(rows)), "expected_collection_amount": expected}, "end_of_month": {"open_exposure": exposure}, "confidence": "medium" if expected else "low", "drivers": ["مانده باز", "دیرکرد", "ریسک برگشت", "قول پرداخت"], "limitations": ["نتایج تماس باید ثبت شود."]},
            "scenarios": {"optimistic": {"assumption": "تحقق کامل وصول مورد انتظار", "collection_amount": expected}, "base": {"assumption": "تحقق ۷۵٪ وصول مورد انتظار", "collection_amount": expected*.75}, "pessimistic": {"assumption": "تحقق ۵۰٪ وصول مورد انتظار", "collection_amount": expected*.5}},
            "recommended_actions": [_action("تماس با پنج اولویت نخست", "بیشترین اثر نقدی", "تسریع وصول", "کارشناس وصول", "high", "امروز"), _action("ثبت قول پرداخت با مبلغ و تاریخ", "قابل سنجش‌شدن Forecast", "افزایش دقت پیش‌بینی", "وصول", "high", "پس از هر تماس")],
            "next_best_action": "برای پنج مشتری اول مسئول، مهلت و نتیجه تماس ثبت شود.",
        }
        return self.finish({"priority_count": len(rows), "expected_collection": expected, "open_exposure": exposure, "top_priorities": top, "scenarios": fallback["scenarios"]}, fallback)


class ScenarioDecisionAgent(DecisionAgent):
    name = "Finance Scenario Agent"
    role_fa = "مقایسه سناریوها و انتخاب مسیر کم‌ریسک"

    def run(self, cash_analysis: dict[str, Any], cheque_analysis: dict[str, Any]) -> dict[str, Any]:
        cash_s = cash_analysis.get("scenarios") or {}; cheque_s = cheque_analysis.get("scenarios") or {}
        base_cash = _num((cash_s.get("base") or {}).get("net_change")); bad_cash = _num((cash_s.get("pessimistic") or {}).get("net_change"))
        fallback = {
            "headline": "سه مسیر آینده برای تصمیم مالی آماده است.", "summary": "مسیر پیشنهادی، سناریوی پایه همراه کنترل‌های سناریوی بدبینانه است.", "management_status": "critical" if bad_cash < 0 else "attention" if base_cash < 0 else "healthy",
            "good_signals": ["اثر تغییر وصول و موجودی به‌صورت جدا محاسبه شده است."], "risks": ["سناریوی بدبینانه ممکن است خالص نقدینگی را منفی کند."] if bad_cash < 0 else [],
            "prediction": {"next_7_days": {"selected_path": "base_with_pessimistic_controls"}, "end_of_month": {"base_net_change": base_cash, "pessimistic_net_change": bad_cash}, "confidence": "medium", "drivers": ["نرخ وصول", "موجودی قابل استفاده", "زمان پرداخت"], "limitations": ["سناریو تصمیم‌یار است و پرداخت اجرا نمی‌کند."]},
            "scenarios": {"optimistic": {"cashflow": cash_s.get("optimistic"), "cheque": cheque_s.get("optimistic")}, "base": {"cashflow": cash_s.get("base"), "cheque": cheque_s.get("base")}, "pessimistic": {"cashflow": cash_s.get("pessimistic"), "cheque": cheque_s.get("pessimistic")}},
            "recommended_actions": [_action("اجرای مسیر پایه با بافر بدبینانه", "پرهیز از خوش‌بینی در وصول", "حفظ پوشش پرداخت", "مدیر مالی", "high", "امروز"), _action("بازمحاسبه سناریو بعد از هر فایل روزانه", "ورود Snapshot جدید", "تصمیم بر مبنای داده تازه", "Finance Agent", "medium", "روزانه")],
            "next_best_action": "سناریوی بدبینانه با مانده واقعی حساب‌ها کنترل شود.",
        }
        return self.finish({"cashflow_scenarios": cash_s, "cheque_scenarios": cheque_s}, fallback)


class CashBankMovementDecisionAgent(DecisionAgent):
    name = "Cash & Bank Movement Agent"
    role_fa = "تحلیل دریافت، پرداخت، حواله و انتقال داخلی"
    specialized_prompt_fa = CASH_BANK_MOVEMENT_SYSTEM_PROMPT_FA
    prompt_profile = "cash_bank_movement_v1"

    def run(self, report: dict[str, Any], transfers: dict[str, Any] | None = None) -> dict[str, Any]:
        summary = report.get("summary") or {}
        inflow = _num(summary.get("inflow_rial"))
        outflow = _num(summary.get("outflow_rial"))
        net = inflow - outflow
        cash_in = _num(summary.get("cash_receipt_rial"))
        bank_in = _num(summary.get("bank_receipt_rial"))
        cash_out = _num(summary.get("cash_payment_rial"))
        bank_out = _num(summary.get("bank_payment_rial"))
        rows = report.get("movements") or []
        top_out = sorted(
            [x for x in rows if x.get("direction") == "outflow"],
            key=lambda x: _num(x.get("amount_rial")), reverse=True,
        )[:5]
        pending = sum(1 for x in rows if int(x.get("approve_state") or 0) in (1, 2))
        transfer_summary = (transfers or {}).get("summary") or {}
        status = "critical" if net < 0 and outflow > inflow * 1.25 else "attention" if net < 0 or pending else "healthy"
        fallback = {
            "headline": f"خالص گردش نقد و بانک در بازه انتخابی {_toman(abs(net))} {'مثبت' if net >= 0 else 'منفی'} است.",
            "summary": f"ورودی قطعی {_toman(inflow)} و خروجی قطعی {_toman(outflow)} است؛ انتقال داخلی {_toman(_num(transfer_summary.get('transfer_amount_rial')))} اثر خالص صفر در کل شرکت دارد.",
            "management_status": status,
            "good_signals": [f"واریز بانکی و نقدی قطعی مجموعاً {_toman(inflow)} است."] if inflow else [],
            "risks": ([f"خروجی از ورودی {_toman(abs(net))} بیشتر است."] if net < 0 else []) + ([f"{pending} ردیف غیرقطعی جدا نگهداری شده است."] if pending else []),
            "prediction": {
                "next_7_days": {"actual_inflow_rial": inflow, "actual_outflow_rial": outflow, "actual_net_rial": net},
                "end_of_month": {"cash_receipt_rial": cash_in, "bank_receipt_rial": bank_in, "cash_payment_rial": cash_out, "bank_payment_rial": bank_out},
                "confidence": "high" if report.get("status") == "success" else "low",
                "drivers": ["دریافت نقدی قطعی", "واریز بانکی قطعی", "پرداخت نقدی قطعی", "برداشت بانکی قطعی"],
                "limitations": ["انتقال داخلی در خالص شرکت صفر است و فقط در سطح حساب اثر دارد.", "چک و عملیات استرداد چک در این گزارش شمرده نمی‌شود."],
            },
            "scenarios": {},
            "recommended_actions": [
                _action("بررسی پنج خروجی بزرگ بازه", "کنترل مقصد، علت و عامل جریان نقد", "کاهش پرداخت غیرضروری و خطای ثبت", "مدیر خزانه", "high", "امروز"),
                _action("تعیین‌تکلیف اسناد غیرقطعی", "اسناد State 1 و 2 وارد نقدینگی قطعی نشده‌اند", "کامل‌شدن تصویر روزانه نقد", "کارشناس خزانه", "medium", "تا پایان روز"),
            ],
            "next_best_action": "مدیر خزانه پنج برداشت بزرگ را با حساب مقصد و علت پرداخت تطبیق دهد.",
        }
        return self.finish({"summary": summary, "top_outflows": top_out, "internal_transfer_summary": transfer_summary}, fallback)


class FinanceManagerDecisionAgent(DecisionAgent):
    name = "Finance Manager Agent"
    role_fa = "هماهنگ‌کننده Agentها و پیشنهاد تصمیم نهایی"

    def run(self, agents: dict[str, Any]) -> dict[str, Any]:
        analyses = {key: value.get("analysis") or {} for key, value in agents.items()}
        risks = [_manager_sentence(x) for a in analyses.values() for x in (a.get("risks") or [])][:10]
        actions = [x for a in analyses.values() for x in (a.get("recommended_actions") or [])]
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        actions = sorted(actions, key=lambda x: order.get(str(x.get("priority", "medium")), 2))[:10]
        statuses = [a.get("management_status") for a in analyses.values()]
        status = "critical" if "critical" in statuses else "attention" if "attention" in statuses else "healthy"
        customer = (
            analyses.get("customer_cheque_behavior", {}).get("prediction")
            or analyses.get("customer_behavior", {}).get("prediction")
            or {}
        )
        payment = analyses.get("cheque_payment", {}).get("prediction") or {}
        cash = analyses.get("cashflow", {}).get("prediction") or {}
        cash_bank = analyses.get("cash_bank_movement", {}).get("prediction") or {}
        collection = analyses.get("collection", {}).get("prediction") or {}
        customer7_data = customer.get("next_7_days") or {}
        customer7 = customer7_data.get("customers_requiring_credit_review")
        if customer7 is None:
            customer7 = customer7_data.get("customers_requiring_review")
        payment7 = payment.get("next_7_days") or {}
        cash7 = cash.get("next_7_days") or {}
        cash_bank_actual = cash_bank.get("next_7_days") or {}
        collection7 = collection.get("next_7_days") or {}
        payment_month = payment.get("end_of_month") or {}
        cash_month = cash.get("end_of_month") or {}
        next_week_lines = []
        if customer7 is not None:
            next_week_lines.append(f"{int(customer7)} مشتری نیازمند بازبینی اعتباری و پیگیری هستند.")
        if payment7:
            next_week_lines.append(f"توان پوشش چک‌های نزدیک { _num(payment7.get('payment_capacity_percent')):.0f}٪ و مبلغ تعهد ثبت‌شده {_toman(_num(payment7.get('latest_obligations_rial')))} است.")
        if cash7:
            next_week_lines.append(f"خالص جریان نقد هفت‌روزه {_toman(_num(cash7.get('net_change')))} مثبت پیش‌بینی می‌شود." if _num(cash7.get("net_change")) >= 0 else f"خالص جریان نقد هفت‌روزه {_toman(abs(_num(cash7.get('net_change'))))} منفی پیش‌بینی می‌شود.")
        if cash_bank_actual:
            actual_net = _num(cash_bank_actual.get("actual_net_rial"))
            next_week_lines.append(f"خالص واقعی نقد و بانک در بازه گزارش {_toman(abs(actual_net))} {'مثبت' if actual_net >= 0 else 'منفی'} است.")
        if collection7.get("expected_collection_amount"):
            next_week_lines.append(f"وصول مورد انتظار مشتریان اولویت‌دار {_toman(_num(collection7.get('expected_collection_amount')))} است.")
        month_lines = []
        if payment_month:
            month_lines.append(f"توان پوشش پایان ماه {_num(payment_month.get('estimated_payment_capacity_percent')):.0f}٪ است و نرخ پرداخت قطعی ثبت‌شده تا امروز {_num(payment_month.get('actual_payment_rate_to_date_percent')):.1f}٪ است.")
        if cash_month:
            month_lines.append(f"خالص جریان نقد پایان دوره {_toman(_num(cash_month.get('net_change')))} مثبت برآورد می‌شود." if _num(cash_month.get("net_change")) >= 0 else f"کسری پایان دوره {_toman(abs(_num(cash_month.get('net_change'))))} برآورد می‌شود.")
        scenario_analysis = analyses.get("scenario", {}).get("scenarios") or {}
        human_scenarios = {}
        for key, title in (("optimistic", "خوش‌بینانه"), ("base", "پایه"), ("pessimistic", "بدبینانه")):
            item = scenario_analysis.get(key) or {}
            cash_item = item.get("cashflow") or {}
            cheque_item = item.get("cheque") or {}
            net = _maybe_num(cash_item.get("net_change"))
            capacity_value = _maybe_num(cheque_item.get("payment_capacity_percent"))
            net_text = (
                f"خالص نقدینگی {_toman(abs(net))} {'مثبت' if net >= 0 else 'منفی'}"
                if net is not None else "خالص نقدینگی در انتظار داده کافی"
            )
            capacity_text = (
                f"توان پوشش چک‌ها {capacity_value:.0f}٪"
                if capacity_value is not None else "توان پوشش در انتظار Snapshot معتبر"
            )
            human_scenarios[key] = {
                "title": title,
                "summary": f"{net_text}؛ {capacity_text}",
                "assumption": cheque_item.get("assumption") or cash_item.get("assumption"),
                "available": net is not None or capacity_value is not None,
            }
        cash7_net = _maybe_num(cash7.get("net_change"))
        payment_capacity = _maybe_num(payment7.get("payment_capacity_percent"))
        expected_collection = _maybe_num(collection7.get("expected_collection_amount"))
        open_exposure = _maybe_num((collection.get("end_of_month") or {}).get("open_exposure"))
        actual_inflow = _maybe_num(cash_bank_actual.get("actual_inflow_rial"))
        actual_outflow = _maybe_num(cash_bank_actual.get("actual_outflow_rial"))
        actual_net = _maybe_num(cash_bank_actual.get("actual_net_rial"))
        executive_kpis = [
            {"label": "دریافت نقدی و بانکی قطعی", "value_rial": actual_inflow, "format": "money", "tone": "teal", "available": actual_inflow is not None},
            {"label": "پرداخت نقدی و بانکی قطعی", "value_rial": actual_outflow, "format": "money", "tone": "red", "available": actual_outflow is not None},
            {"label": "خالص واقعی نقد و بانک", "value_rial": actual_net, "format": "money_signed", "tone": "green" if (actual_net or 0) >= 0 else "red", "available": actual_net is not None},
            {"label": "مانده چک‌های دریافتی باز", "value_rial": open_exposure, "format": "money", "tone": "teal", "available": open_exposure is not None},
            {"label": "وصول مورد انتظار", "value_rial": expected_collection, "format": "money", "tone": "blue", "available": expected_collection is not None},
            {"label": "خالص جریان ۷ روزه", "value_rial": cash7_net, "format": "money_signed", "tone": "green" if (cash7_net or 0) >= 0 else "red", "available": cash7_net is not None},
            {"label": "توان پوشش چک‌های نزدیک", "value": payment_capacity, "format": "percent", "tone": "green" if (payment_capacity or 0) >= 100 else "amber", "available": payment_capacity is not None},
            {"label": "مشتری نیازمند بازبینی", "value": customer7, "format": "count", "tone": "amber", "available": customer7 is not None},
            {"label": "تعداد اقدام فوری و مهم", "value": len([x for x in actions if x.get("priority") in ("critical", "high")]), "format": "count", "tone": "red", "available": True},
        ]
        first_action = actions[0] if actions else None
        if first_action:
            next_best_action = (
                f"{first_action.get('owner') or 'مدیر مالی'} تا {first_action.get('deadline') or 'این هفته'} «{first_action.get('action')}» را انجام دهد؛ "
                f"زیرا {first_action.get('why') or 'این اقدام بالاترین اولویت مالی را دارد'}. "
                f"اثر مورد انتظار: {first_action.get('expected_effect') or 'کاهش ریسک مالی'}."
            )
        else:
            next_best_action = "پس از ورود داده جدید، تیم Agentها دوباره اجرا و برنامه روز به‌روزرسانی شود."
        fallback = {
            "headline": "خلاصه پیش‌بینی و تصمیم تیم Agentهای مالی آماده است.",
            "summary": "خروجی دریافت و پرداخت نقدی و بانکی، رفتار مشتری، چک‌ها، نقدینگی، وصول و سناریو در یک برنامه اجرایی یکپارچه شده است.",
            "management_status": status,
            "good_signals": [_manager_sentence(x) for a in analyses.values() for x in (a.get("good_signals") or [])][:5], "risks": risks,
            "prediction": {"next_7_days": next_week_lines, "end_of_month": month_lines, "confidence": "medium", "drivers": ["گردش واقعی نقد و بانک", "رفتار مشتری", "وضعیت چک", "جریان نقد", "وصول"], "limitations": ["تصمیم‌های اجرایی نیازمند تأیید مدیر مالی است."]},
            "scenarios": human_scenarios,
            "executive_kpis": executive_kpis,
            "recommended_actions": actions,
            "decisions_today": actions[:4],
            "seven_day_plan": actions[:7],
            "next_best_action": next_best_action,
        }
        result = self.finish({"specialist_outputs": analyses, "prioritized_actions": actions, "executive_kpis": executive_kpis}, fallback)
        # Preserve the complete managerial contract even in LLM mode.
        analysis = result.get("analysis") or {}
        analysis["executive_kpis"] = executive_kpis
        analysis["decisions_today"] = actions[:4]
        analysis["seven_day_plan"] = actions[:7]
        result["analysis"] = analysis
        return result
