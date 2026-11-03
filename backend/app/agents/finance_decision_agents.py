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
        karamad_context = report.get("karamad_context") or {}
        k_received = karamad_context.get("received_cheques") or {}
        k_customer_count = int(karamad_context.get("customer_count") or 0)
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
            "summary": f"نسبت مبلغ سررسیدگذشته به چک‌های باز راهکاران {ratio:.1f}٪ است. Snapshot کارآمد نیز {k_customer_count} مشتری و {int(k_received.get('count') or 0)} چک دریافتی را به پرونده یکپارچه اضافه کرده است.",
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
        return self.finish({"customer_count": len(rows), "critical_count": len(critical), "open_amount": open_amount, "overdue_amount": overdue, "overdue_ratio": ratio, "top_customers": top, "karamad_context": karamad_context}, fallback)


class CustomerChequeBehaviorDecisionAgent(DecisionAgent):
    name = "Customer Cheque Behavior Agent"
    role_fa = "تحلیل خوش‌قولی مشتری و پیشنهاد سیاست پذیرش چک"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        rows = report.get("customers") or []
        karamad_context = report.get("karamad_context") or {}
        k_received = karamad_context.get("received_cheques") or {}
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
            "summary": f"{len(reliable)} مشتری راهکاران امتیاز خوش‌قولی حداقل ۷۰ دارند و وصول مورد انتظار سبد {_toman(expected)} است؛ {int(k_received.get('count') or 0)} چک دریافتی کارآمد نیز در سابقه یکپارچه مشتری نگهداری می‌شود.",
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
        karamad_context = quality.get("karamad_context") or {}
        karamad_registered_count = int(karamad_context.get("count") or 0)
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
            "summary": f"ظرفیت، توان نقدی آینده است؛ نرخ واقعی راهکاران از State=28 محاسبه می‌شود. کارآمد فعلاً {karamad_registered_count} چک پرداختی ثبت‌شده دارد و منبع آینده آن کامل نیست.",
            "management_status": status,
            "good_signals": [f"موجودی آخرین Snapshot برابر {_toman(latest_cash)} است."] if latest_cash else [],
            "risks": [f"تنها {count_rate:.1f}٪ از تعداد چک‌های معتبر سررسیدشده، پرداخت قطعی ثبت‌شده دارند.", "اختلاف زیاد میان موجودی قابل پوشش و پرداخت قطعی نیازمند بررسی چک‌های باز سررسیدگذشته است."],
            "prediction": {"next_7_days": {"payment_capacity_percent": base, "latest_obligations_rial": latest_obligation}, "end_of_month": {"estimated_payment_capacity_percent": capacity, "actual_payment_rate_to_date_percent": actual_rate}, "confidence": forecast.get("confidence") or "low", "drivers": ["موجودی آخرین Snapshot", "چک‌های سررسیدشده", "State=11 فعال", "State=28 پاس‌شده", "چک‌های ثبت‌شده کارآمد"], "limitations": ["ظرفیت پرداخت معادل تضمین پاس‌شدن نیست.", "داده آینده چک پرداختی کارآمد هنوز کامل نیست؛ فقط ثبت‌شده‌های موجود لحاظ می‌شوند."]},
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
        summary = report.get("summary") or {}
        policy = report.get("cashflow_policy") or {}
        management = report.get("management_summary") or {}
        seven = days[:7]
        inflow7 = sum(_num(x.get("projected_inflow")) for x in seven)
        outflow7 = sum(_num(x.get("projected_outflow")) for x in seven)
        inflow = sum(_num(x.get("projected_inflow")) for x in days)
        outflow = sum(_num(x.get("projected_outflow")) for x in days)
        pressure = sum(1 for row in days if row.get("cash_shortage"))
        worst = min(days, key=lambda x: _num(x.get("daily_net_change")), default={})
        base_reliability = max(_num(policy.get("portfolio_reliability_percent")), 1.0)
        def scenario(reliability_percent: float) -> dict[str, Any]:
            adjusted_inflow = inflow * reliability_percent / base_reliability
            return {"collection_reliability_percent": reliability_percent, "projected_inflow": round(adjusted_inflow, 2), "projected_outflow": round(outflow, 2), "net_change": round(adjusted_inflow-outflow, 2)}
        status = management.get("status") or ("critical" if summary.get("first_predicted_shortage_date_jalali") else "attention" if pressure else "healthy")
        management_actions = management.get("recommendations") or []
        fallback = {
            "headline": management.get("headline") or ("کسری نقدینگی پیش‌بینی شده است." if status == "critical" else f"در افق پیش‌بینی {pressure} روز فشار نقدی وجود دارد."),
            "summary": f"خالص هفت‌روزه {_toman(inflow7-outflow7)} و خالص کل افق {_toman(inflow-outflow)} برآورد شده است. وصول چک‌ها با سیاست پایهٔ { _num(policy.get('portfolio_reliability_percent')):.1f}٪ (۲۵٪ برگشت) تعدیل شده است. سایر هزینه‌های تاریخی عمداً در این پیش‌بینی وارد نشده‌اند.",
            "management_status": status,
            "good_signals": [f"ورودی کل پیش‌بینی‌شده {_toman(inflow)} است."],
            "risks": ([f"سخت‌ترین روز {worst.get('date_jalali') or worst.get('date')} با خالص {_toman(_num(worst.get('daily_net_change')))} است."] if worst else []) + (["مانده افتتاحیه ثبت نشده است."] if report.get("opening_cash") is None else []) + (["سایر هزینه‌های تاریخی خارج از Cash Flow و نیازمند برنامهٔ هزینهٔ قطعی هستند."] if not policy.get("historical_other_expenses_included") else []),
            "prediction": {"next_7_days": {"inflow": inflow7, "outflow": outflow7, "net_change": inflow7-outflow7}, "end_of_month": {"inflow": inflow, "outflow": outflow, "net_change": inflow-outflow, "first_shortage": summary.get("first_predicted_shortage_date_jalali")}, "confidence": "medium" if len(days) >= 14 else "low", "drivers": ["موجودی صورت‌حساب", "وصول چک تعدیل‌شده", "چک پرداختی حداکثر ۲۰ روز معوق", "ذخیره حقوق"], "limitations": report.get("limitations") or []},
            "scenarios": {"optimistic": scenario(80), "base": scenario(75), "pessimistic": scenario(70)},
            "recommended_actions": [
                _action(item["action"], item["why"], "کاهش ریسک نقدینگی", item["owner"], item["priority"], item["deadline"])
                for item in management_actions
            ],
            "next_best_action": "موجودی افتتاحیه و مانده واقعی حساب پرداخت امروز ثبت شود؛ سپس وجه چک‌های نزدیک رزرو شود.",
        }
        return self.finish({"forecast": fallback["prediction"], "scenarios": fallback["scenarios"], "worst_day": worst, "management_summary": management}, fallback)


class CollectionDecisionAgent(DecisionAgent):
    name = "Collection Decision Agent"
    role_fa = "پیش‌بینی وصول و تعیین اقدام بعدی مشتریان"

    def run(self, report: dict[str, Any]) -> dict[str, Any]:
        rows = report.get("priorities") or report.get("customers") or []
        karamad_context = report.get("karamad_context") or {}
        k_received = karamad_context.get("received_cheques") or {}
        k_overdue_amount = _num(k_received.get("overdue_amount_rial"))
        k_overdue_count = int(k_received.get("overdue_count") or 0)
        top = rows[:10]
        expected = sum(_num(x.get("expected_collection_amount") or x.get("collection_forecast")) for x in rows)
        exposure = sum(_num(x.get("open_exposure") or x.get("open_amount")) for x in rows)
        fallback = {
            "headline": f"{len(rows)} مشتری در صف وصول قرار دارند.", "summary": f"وصول مورد انتظار راهکاران {_toman(expected)} از مانده {_toman(exposure)} است؛ کارآمد نیز {k_overdue_count} چک دریافتی سررسیدگذشته به مبلغ {_toman(k_overdue_amount)} دارد.", "management_status": "attention" if rows or k_overdue_count else "healthy",
            "good_signals": ["صف وصول بر اساس اثر مالی اولویت‌بندی شده است."], "risks": ["عدم ثبت نتیجه تماس و قول پرداخت، پیش‌بینی را کم‌دقت می‌کند."],
            "prediction": {"next_7_days": {"top_customer_count": min(10, len(rows)), "expected_collection_amount": expected}, "end_of_month": {"open_exposure": exposure}, "confidence": "medium" if expected else "low", "drivers": ["مانده باز", "دیرکرد", "ریسک برگشت", "قول پرداخت"], "limitations": ["نتایج تماس باید ثبت شود."]},
            "scenarios": {"optimistic": {"assumption": "تحقق کامل وصول مورد انتظار", "collection_amount": expected}, "base": {"assumption": "تحقق ۷۵٪ وصول مورد انتظار", "collection_amount": expected*.75}, "pessimistic": {"assumption": "تحقق ۵۰٪ وصول مورد انتظار", "collection_amount": expected*.5}},
            "recommended_actions": [_action("تماس با پنج اولویت نخست", "بیشترین اثر نقدی", "تسریع وصول", "کارشناس وصول", "high", "امروز"), _action("ثبت قول پرداخت با مبلغ و تاریخ", "قابل سنجش‌شدن Forecast", "افزایش دقت پیش‌بینی", "وصول", "high", "پس از هر تماس")],
            "next_best_action": "برای پنج مشتری اول مسئول، مهلت و نتیجه تماس ثبت شود.",
        }
        return self.finish({"priority_count": len(rows), "expected_collection": expected, "open_exposure": exposure, "top_priorities": top, "karamad_overdue_count": k_overdue_count, "karamad_overdue_amount_rial": k_overdue_amount, "scenarios": fallback["scenarios"]}, fallback)


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

    def run(self, report: dict[str, Any], transfers: dict[str, Any] | None = None, commitments: dict[str, Any] | None = None) -> dict[str, Any]:
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
        commitment_summary = (commitments or {}).get("summary") or {}
        approved_future = commitment_summary.get("approved_future") or {}
        draft_future = commitment_summary.get("draft_future") or {}
        current_overdue = commitment_summary.get("current_year_overdue") or {}
        historical_backlog = commitment_summary.get("historical_backlog") or {}
        approved_future_amount = _num(approved_future.get("amount_rial"))
        overdue_amount = _num(current_overdue.get("amount_rial"))
        status = "critical" if net < 0 and outflow > inflow * 1.25 else "attention" if net < 0 or pending else "healthy"
        fallback = {
            "headline": f"خالص گردش نقد و بانک در بازه انتخابی {_toman(abs(net))} {'مثبت' if net >= 0 else 'منفی'} است.",
            "summary": f"ورودی قطعی {_toman(inflow)} و خروجی قطعی {_toman(outflow)} است؛ انتقال داخلی {_toman(_num(transfer_summary.get('transfer_amount_rial')))} اثر خالص صفر در کل شرکت دارد.",
            "management_status": status,
            "good_signals": [f"واریز بانکی و نقدی قطعی مجموعاً {_toman(inflow)} است."] if inflow else [],
            "risks": ([f"خروجی از ورودی {_toman(abs(net))} بیشتر است."] if net < 0 else []) + ([f"{pending} ردیف غیرقطعی جدا نگهداری شده است."] if pending else []) + ([f"{int(current_overdue.get('payment_order_count') or 0)} دستور پرداخت سال جاری شامل {int(current_overdue.get('installment_count') or 0)} قسط و مبلغ {_toman(overdue_amount)} سررسیدگذشته و تعیین‌تکلیف‌نشده است."] if overdue_amount else []),
            "prediction": {
                # These are confirmed, historical movements in the current
                # 30-day report; they are intentionally not labelled forecast.
                "actual_period": {
                    "operational_inflow_rial": inflow,
                    "operational_outflow_rial": outflow,
                    "operational_net_rial": net,
                    # Stable aliases consumed by the Finance Manager summary.
                    # Keep the operational_* names for backward compatibility.
                    "actual_inflow_rial": inflow,
                    "actual_outflow_rial": outflow,
                    "actual_net_rial": net,
                },
                "confidence": "high" if report.get("status") == "success" else "low",
                "drivers": ["دریافت نقدی قطعی", "واریز بانکی قطعی", "پرداخت نقدی قطعی", "برداشت بانکی قطعی"],
                "limitations": ["انتقال داخلی در خالص شرکت صفر است و فقط در سطح حساب اثر دارد.", "چک و عملیات استرداد چک در این گزارش شمرده نمی‌شود."],
            },
            "scenarios": {},
            "recommended_actions": [
                _action("بررسی پنج خروجی بزرگ بازه", "کنترل مقصد، علت و عامل جریان نقد", "کاهش پرداخت غیرضروری و خطای ثبت", "مدیر خزانه", "high", "امروز"),
                _action("تعیین‌تکلیف اسناد غیرقطعی", "اسناد State 1 و 2 وارد نقدینگی قطعی نشده‌اند", "کامل‌شدن تصویر روزانه نقد", "کارشناس خزانه", "medium", "تا پایان روز"),
                *([_action("بررسی دستورهای پرداخت سررسیدگذشته سال جاری", f"{int(current_overdue.get('payment_order_count') or 0)} دستور شامل {int(current_overdue.get('installment_count') or 0)} قسط هنوز اجرا یا ابطال نشده است", "تعیین تعهد واقعی و اصلاح Cash Flow", "مدیر خزانه", "high", "امروز")] if overdue_amount else []),
            ],
            "next_best_action": "مدیر خزانه پنج برداشت بزرگ را با حساب مقصد و علت پرداخت تطبیق دهد.",
        }
        # This agent is an auditable movement report. Do not let free-form LLM
        # text add a line item or amount that is inconsistent with its totals.
        return {
            "metadata": {
                "agent_name": self.name, "role": self.role_fa,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "mode": "rules", "model": "auditable_cash_bank_rules",
                "fallback_used": False, "prompt_profile": self.prompt_profile,
            },
            "analysis": fallback,
        }


class FinanceManagerDecisionAgent(DecisionAgent):
    name = "Finance Manager Agent"
    role_fa = "هماهنگ‌کننده Agentها و پیشنهاد تصمیم نهایی"

    def run(self, agents: dict[str, Any], cheque_portfolio: dict[str, Any] | None = None, *, actual_report: dict[str, Any] | None = None, cashflow_report: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.agents.management_report import build_management_report
        return build_management_report(agents, cheque_portfolio or {}, actual_report, cashflow_report)

