from __future__ import annotations

from typing import Any

from app.services.finance_prediction_service import FinancePredictionService
from app.services.treasury_service import get_customer_b2b_behavior, get_customer_b2b_remittances


def _is_hybrid_customer(item: dict[str, Any]) -> bool:
    """True when the customer is a Hybrid sales channel, not a receivable customer.

    Hybrid sales settle directly into company bank accounts, so keeping these rows in
    customer receivables would create a false customer debt/exposure.
    """
    values = (
        item.get("counterpart_name"),
        item.get("customer_name"),
        item.get("name"),
        item.get("title"),
    )
    text = " ".join(str(value or "") for value in values)
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک").replace("‌", " ").lower()
    return "هیبرید" in text or "hybrid" in text


class CustomerIntelligenceService:
    """Customer-only decision layer on top of explainable SQL predictions."""

    def __init__(self, *, history_days: int = 365, forecast_days: int = 30, allowed_term_days: int = 90):
        self.prediction = FinancePredictionService(
            history_days=history_days,
            forecast_days=forecast_days,
            allowed_term_days=allowed_term_days,
        )
        self.history_days = history_days
        self.forecast_days = forecast_days
        self.allowed_term_days = allowed_term_days

    def dashboard(self, limit: int = 200) -> dict[str, Any]:
        report = self.prediction.customer_predictions(limit=limit)
        priorities = self.prediction.collection_priorities(limit=min(limit, 100))
        priority_by_ref = {int(x["counterpart_ref"]): x for x in priorities.get("customers", [])}
        b2b_report = get_customer_b2b_remittances(limit=20000)
        b2b_by_ref: dict[int, dict[str, Any]] = {}
        for remittance in b2b_report.get("rows", []):
            if not remittance.get("is_b2b_customer_payment") or not remittance.get("counterpart_ref"):
                continue
            ref = int(remittance["counterpart_ref"])
            bucket = b2b_by_ref.setdefault(ref, {"count": 0, "amount_rial": 0.0, "direct_count": 0, "direct_amount_rial": 0.0, "returned_cheque_settlement_count": 0, "returned_cheque_settlement_amount_rial": 0.0, "last_payment_date": None})
            amount = float(remittance.get("amount_rial", 0) or 0)
            bucket["count"] += 1; bucket["amount_rial"] += amount
            if remittance.get("is_returned_cheque_settlement"):
                bucket["returned_cheque_settlement_count"] += 1; bucket["returned_cheque_settlement_amount_rial"] += amount
            else:
                bucket["direct_count"] += 1; bucket["direct_amount_rial"] += amount
            if not bucket["last_payment_date"]:
                bucket["last_payment_date"] = remittance.get("deposit_date")
        for bucket in b2b_by_ref.values():
            total = float(bucket["amount_rial"] or 0)
            bucket["average_amount_rial"] = round(total / bucket["count"], 2) if bucket["count"] else 0
            bucket["returned_settlement_ratio_percent"] = round(float(bucket["returned_cheque_settlement_amount_rial"] or 0) / total * 100, 1) if total else 0
        customers = [self._enrich(x, priority_by_ref.get(int(x["counterpart_ref"])), b2b_by_ref.get(int(x["counterpart_ref"]))) for x in report.get("customers", []) if not _is_hybrid_customer(x)]
        customers.sort(key=lambda x: (x["risk_score"], x["open_exposure"]), reverse=True)

        high = [x for x in customers if x["risk_level"] == "high"]
        medium = [x for x in customers if x["risk_level"] == "medium"]
        critical = [
            x for x in customers
            if float(x.get("risk_score", 0) or 0) >= 85
            and (
                int(x.get("over_policy_count", 0) or 0) >= 10
                or float(x.get("current_overdue_open_ratio_percent", 0) or 0) >= 60
            )
        ]
        improving = [x for x in customers if x["outlook"] == "stable_good"]
        total_exposure = sum(float(x.get("open_exposure", 0) or 0) for x in customers)
        expected = sum(float(x.get("expected_collection_amount", 0) or 0) for x in customers)
        alerts = [self._alert(x) for x in customers if x["risk_level"] != "low"][:50]

        return {
            "status": "success",
            "report_type": "customer_intelligence_dashboard",
            "as_of_date": report.get("as_of_date"),
            "source": "SQL Server / Rahkaran",
            "policy": {"maximum_cheque_term_days": self.allowed_term_days},
            "summary": {
                "customer_count": len(customers),
                "high_risk_count": len(high),
                "medium_risk_count": len(medium),
                "healthy_count": len(improving),
                "open_received_cheque_amount": round(total_exposure, 2),
                "open_exposure": round(total_exposure, 2),
                "expected_collection_next_period": round(expected, 2),
                "collection_gap": round(max(total_exposure - expected, 0), 2),
                "overall_status": "critical" if critical else "attention" if high or medium else "good",
            },
            "human_analysis": self._overall_analysis(customers, high, medium, total_exposure, expected),
            "alerts": alerts,
            "customers": customers,
            "collection_priorities": priorities.get("customers", []),
            "method": report.get("method"),
            "limitations": report.get("limitations", []),
        }

    def collection_portfolio(self, limit: int = 300) -> dict[str, Any]:
        """Managerial customer-collection portfolio with account + cheque coverage in one dataset."""
        dashboard = self.dashboard(limit=limit)
        rows: list[dict[str, Any]] = []
        for item in dashboard.get("customers", []):
            # Defensive guard: dashboard already excludes Hybrid customers, but keep
            # the portfolio protected if its upstream source changes later.
            if _is_hybrid_customer(item):
                continue
            ref = item.get("counterpart_ref")
            if ref is None:
                continue
            try:
                account = self.prediction.customer_account_position(int(ref))
            except Exception as exc:
                account = {"found": False, "error": str(exc)}
            balance = float(account.get("balance_rial", 0) or 0) if account.get("found") else 0.0
            open_account = max(balance, 0.0)
            customer_credit = max(-balance, 0.0)
            open_cheques = float(item.get("open_exposure", 0) or 0)
            exposure = round(open_account + open_cheques, 2)
            rows.append({
                **item,
                "account_position": account,
                "collection_position": {
                    "open_account_receivable_rial": round(open_account, 2),
                    "customer_credit_rial": round(customer_credit, 2),
                    "open_cheque_amount_rial": round(open_cheques, 2),
                    "total_collection_exposure_rial": exposure,
                    "cheque_coverage_percent": round(open_cheques / exposure * 100, 1) if exposure else 0.0,
                    "uncovered_percent": round(open_account / exposure * 100, 1) if exposure else 0.0,
                },
            })
        rows.sort(key=lambda x: float(x.get("collection_position", {}).get("total_collection_exposure_rial", 0) or 0), reverse=True)
        return {
            "status": "success",
            "summary": {
                "customer_count": len(rows),
                "open_account_receivable_rial": round(sum(float(x["collection_position"]["open_account_receivable_rial"]) for x in rows), 2),
                "open_cheque_amount_rial": round(sum(float(x["collection_position"]["open_cheque_amount_rial"]) for x in rows), 2),
                "total_collection_exposure_rial": round(sum(float(x["collection_position"]["total_collection_exposure_rial"]) for x in rows), 2),
                "customer_credit_rial": round(sum(float(x["collection_position"]["customer_credit_rial"]) for x in rows), 2),
            },
            "customers": rows,
        }

    def customer(self, counterpart_ref: int) -> dict[str, Any]:
        report = self.prediction.customer_prediction(counterpart_ref)
        if report.get("status") == "not_found":
            return report
        item = report.get("customers", [])[0]
        priorities = self.prediction.collection_priorities(limit=200).get("customers", [])
        priority = next((x for x in priorities if int(x["counterpart_ref"]) == int(counterpart_ref)), None)
        b2b = get_customer_b2b_behavior(counterpart_ref)
        customer = self._enrich(item, priority, b2b)
        customer["b2b_remittances"] = b2b
        customer["latest_invoice"] = self.prediction.customer_latest_invoice(counterpart_ref)
        customer["all_cheques"] = self.prediction.customer_all_cheques(counterpart_ref)
        customer["open_cheques"] = self.prediction.customer_open_cheques(counterpart_ref)
        customer["returned_cheques"] = self.prediction.customer_returned_cheques(counterpart_ref)
        account = self.prediction.customer_account_position(counterpart_ref)
        open_cheque_amount = round(sum(float(x.get("amount", 0) or 0) for x in customer["open_cheques"]), 2)
        open_account = float(account.get("open_account_receivable_rial", 0) or 0)
        total_collection_exposure = round(open_account + open_cheque_amount, 2)
        customer["account_position"] = account
        customer["collection_position"] = {
            "open_account_receivable_rial": round(open_account, 2),
            "customer_credit_rial": round(float(account.get("customer_credit_rial", 0) or 0), 2),
            "open_cheque_amount_rial": open_cheque_amount,
            "total_collection_exposure_rial": total_collection_exposure,
            "cheque_coverage_percent": round(open_cheque_amount / total_collection_exposure * 100, 1) if total_collection_exposure else 0.0,
            "uncovered_percent": round(open_account / total_collection_exposure * 100, 1) if total_collection_exposure else 0.0,
            "accounting_note": "مانده مشتری از گردش سند حسابداری سال مالی روی تفصیلی مشتری و حساب‌های دریافتنی تجاری، برگشتی و اشخاص محاسبه می‌شود؛ انتقال داخلی بین این حساب‌ها در جمع خنثی است.",
        }
        return {"status": "success", "customer": customer, "alert": self._alert(customer)}

    def _enrich(self, item: dict[str, Any], priority: dict[str, Any] | None, b2b: dict[str, Any] | None = None) -> dict[str, Any]:
        late = item.get("late_payment_risk", {})
        returned = item.get("cheque_return_probability", {})
        forecast = item.get("collection_forecast", {})
        late_value = float(late.get("value", 0) or 0)
        return_value = float(returned.get("value", 0) or 0)
        overdue_ratio = float(item.get("current_overdue_open_ratio_percent", 0) or 0)
        over_policy_count = int(item.get("over_policy_count", 0) or 0)
        base_risk_score = 0.45 * late_value + 0.35 * return_value + 0.20 * overdue_ratio
        b2b = b2b or {}
        direct_count = int(b2b.get("direct_count", 0) or 0)
        returned_settlement_ratio = float(b2b.get("returned_settlement_ratio_percent", 0) or 0)
        # حواله مستقیم و تکرارشونده یک سیگنال مثبت محدود است؛ تسویه چک برگشتی سیگنال منفی است.
        remittance_adjustment = min(8.0, direct_count * 0.4) - min(12.0, returned_settlement_ratio * 0.20)
        risk_score = round(max(0, min(100, base_risk_score - remittance_adjustment)), 1)
        # سیاست قطعی شرکت: وجود چک بالاتر از سقف ۹۰ روز حداقل هشدار است.
        # تکرار بالا همراه با مانده معوق، وضعیت را بحرانی می‌کند.
        policy_critical = (
            over_policy_count >= 10
            and overdue_ratio >= 60
            and float(item.get("overdue_open_amount", 0) or 0) > 0
        )
        risk_level = (
            "high" if risk_score >= 70 or policy_critical
            else "medium" if risk_score >= 40 or over_policy_count >= 3
            else "low"
        )
        reasons = list(dict.fromkeys((late.get("reasons") or []) + (priority or {}).get("reasons", [])))
        expected = float(forecast.get("expected_collection_amount", 0) or 0)
        exposure = float(item.get("open_exposure", 0) or 0)
        outlook = "deteriorating" if risk_level == "high" else "needs_attention" if risk_level == "medium" else "stable_good"
        actions = self._actions(risk_level, overdue_ratio, return_value, exposure, priority, over_policy_count)
        explanation = self._human_explanation(item, risk_level, risk_score, reasons, expected, exposure)
        return {
            **item,
            "over_policy_count": over_policy_count,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "outlook": outlook,
            "expected_collection_amount": round(expected, 2),
            "collection_gap": round(max(exposure - expected, 0), 2),
            "reasons": reasons or ["نشانه پرریسک غالب در قواعد فعلی مشاهده نشد."],
            "human_explanation": explanation,
            "recommended_actions": actions,
            "priority": priority,
            "b2b_behavior": b2b,
            "b2b_risk_adjustment": round(-remittance_adjustment, 1),
        }

    def _actions(self, level: str, overdue_ratio: float, return_risk: float, exposure: float, priority: dict | None, over_policy_count: int = 0) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if level == "high":
            result.append({"action": "فروش اعتباری جدید را تا بازبینی پرونده محدود کنید.", "why": "ریسک ترکیبی وصول در سطح بالا قرار دارد.", "owner": "مدیر مالی و فروش"})
        if overdue_ratio >= 25:
            result.append({"action": "پیگیری وصول را حداکثر طی ۲۴ ساعت آغاز کنید.", "why": "سهم مانده سررسیدگذشته از چک‌های باز بالاست.", "owner": "واحد وصول"})
        if over_policy_count > 0:
            result.append({
                "action": f"تا بازبینی پرونده، چک جدید بالاتر از {self.allowed_term_days} روز پذیرفته نشود.",
                "why": f"{over_policy_count} فقره چک خارج از سیاست سررسید شرکت ثبت شده است.",
                "owner": "اعتبارات و فروش",
            })
        if return_risk >= 18:
            result.append({"action": "برای فروش بعدی تضمین معتبرتر یا پیش‌پرداخت دریافت کنید.", "why": "احتمال تجربی برگشت چک از محدوده کم‌ریسک بالاتر است.", "owner": "اعتبارات"})
        if priority and priority.get("priority_level") == "high":
            result.append({"action": priority.get("recommendation") or "مشتری را در ابتدای صف وصول قرار دهید.", "why": "اثر وصول این مشتری بر نقدینگی کوتاه‌مدت بالاست.", "owner": "خزانه"})
        if not result:
            result.append({"action": "شرایط فعلی را حفظ و رفتار مشتری را هفتگی پایش کنید.", "why": "نشانه بحرانی در داده‌های فعلی مشاهده نشده است.", "owner": "اعتبارات"})
        return result

    def _human_explanation(self, item: dict, level: str, score: float, reasons: list[str], expected: float, exposure: float) -> str:
        name = item.get("counterpart_name", "این مشتری")
        level_fa = {"high": "بالا", "medium": "متوسط", "low": "پایین"}[level]
        reason = reasons[0] if reasons else "نشانه منفی غالب دیده نشده است"
        coverage = 0 if exposure <= 0 else round(expected / exposure * 100)
        policy = int(item.get("over_policy_count", 0) or 0)
        policy_text = f" {policy} فقره چک خارج از سقف {self.allowed_term_days} روز ثبت شده است." if policy else ""
        return f"ریسک رفتار مالی {name} {level_fa} و امتیاز آن {score} از ۱۰۰ است. مهم‌ترین علت: {reason}{policy_text} برآورد می‌شود حدود {coverage}٪ از چک‌های دریافتی باز در افق انتخابی وصول شود؛ این برآورد قطعی نیست و باید همراه با وضعیت فروش و تماس وصول بررسی شود."

    def _alert(self, customer: dict[str, Any]) -> dict[str, Any]:
        is_critical = (
            float(customer.get("risk_score", 0) or 0) >= 85
            and (
                int(customer.get("over_policy_count", 0) or 0) >= 10
                or float(customer.get("current_overdue_open_ratio_percent", 0) or 0) >= 60
            )
        )
        return {
            "id": f"customer-{customer['counterpart_ref']}",
            "level": "critical" if is_critical else "warning",
            "title": f"هشدار رفتار مشتری: {customer['counterpart_name']}",
            "message": customer["human_explanation"],
            "why": customer["reasons"],
            "evidence": [
                {"label": "امتیاز ریسک", "value": customer["risk_score"]},
                {"label": "چک‌های دریافتی باز", "value": customer["open_exposure"]},
                {"label": "چک‌های باز سررسیدگذشته", "value": customer["overdue_open_amount"]},
                {"label": "چک خارج از سیاست", "value": customer["over_policy_count"]},
                {"label": "وصول مورد انتظار", "value": customer["expected_collection_amount"]},
            ],
            "future": f"در افق {self.forecast_days} روزه، شکاف وصول برآوردی {customer['collection_gap'] / 10:,.0f} تومان است.",
            "recommendations": customer["recommended_actions"],
            "counterpart_ref": customer["counterpart_ref"],
        }

    @staticmethod
    def _overall_analysis(customers: list[dict], high: list[dict], medium: list[dict], exposure: float, expected: float) -> dict[str, Any]:
        good = [f"{x['counterpart_name']} در محدوده کم‌ریسک قرار دارد." for x in customers if x["risk_level"] == "low"][:3]
        bad = [f"{x['counterpart_name']} با امتیاز {x['risk_score']} نیازمند اقدام است." for x in high[:3]]
        status = "ریسک وصول نیازمند اقدام فوری است." if high else "وضعیت کلی نیازمند توجه است." if medium else "وضعیت رفتار مشتریان پایدار است."
        coverage = 0 if exposure <= 0 else round(expected / exposure * 100, 1)
        return {
            "headline": status,
            "human_summary": f"براساس رفتار چک‌های دریافتی، وصول حدود {coverage}٪ از چک‌های باز در افق پیش‌بینی انتظار می‌رود.",
            "good_signals": good or ["هنوز سیگنال مثبت قابل اتکای کافی برای نمایش وجود ندارد."],
            "bad_signals": bad or ["هشدار بحرانی مشتری مشاهده نشد."],
            "next_best_action": "از سه مشتری اول در فهرست اولویت وصول شروع کنید و شرایط فروش اعتباری آن‌ها را بازبینی کنید." if high else "پایش هفتگی رفتار مشتریان و کنترل سیاست ۹۰ روزه ادامه پیدا کند.",
        }
