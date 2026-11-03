from __future__ import annotations

from typing import Any


class ExplainableAlertService:
    """Turns raw finance signals into explainable management alerts."""

    @staticmethod
    def build(
        *,
        daily: dict[str, Any],
        cheque_risk: dict[str, Any],
        anomalies: dict[str, Any],
        customer_predictions: dict[str, Any],
        cash_shortage: dict[str, Any],
        collection_priorities: dict[str, Any],
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        cheque_summary = cheque_risk.get("summary", {})

        overdue_issued_count = int(cheque_summary.get("issued_overdue_count", 0) or 0)
        overdue_issued_total = cheque_summary.get("issued_overdue_total", 0) or 0
        if overdue_issued_count:
            alerts.append({
                "level": "critical",
                "type": "issued_cheques_overdue",
                "title": "چک‌های صادره سررسیدگذشته نیازمند اقدام هستند",
                "message": f"{overdue_issued_count} فقره چک صادره از موعد عبور کرده است.",
                "metric": overdue_issued_total,
                "calculation_type": "actual",
                "why": [
                    "چک صادره فعال با تاریخ سررسید گذشته در SQL شناسایی شده است.",
                    "این وضعیت می‌تواند نشان‌دهنده تعهد پرداختی حل‌نشده یا نیازمند بررسی ثبت/تسویه باشد.",
                ],
                "evidence": [
                    {"label": "تعداد", "value": overdue_issued_count},
                    {"label": "مبلغ", "value": overdue_issued_total},
                    {"label": "دامنه", "value": cheque_summary.get("overdue_scope")},
                ],
                "impact": "ریسک فشار نقدینگی و اختلال در برنامه پرداخت افزایش می‌یابد.",
                "recommendations": [
                    "فهرست چک‌های سررسیدگذشته به تفکیک مبلغ و طرف حساب بازبینی شود.",
                    "وضعیت تسویه/ثبت هر مورد قبل از صدور تعهد جدید بررسی شود.",
                ],
                "priority": 1,
            })

        protested_count = int(cheque_summary.get("protested_received_count", 0) or 0)
        protested_total = cheque_summary.get("protested_received_total", 0) or 0
        if protested_count:
            alerts.append({
                "level": "high",
                "type": "protested_received_cheques",
                "title": "چک‌های دریافتی واخواست‌شده وجود دارد",
                "message": f"{protested_count} فقره چک دریافتی در وضعیت واخواست‌شده قرار دارد.",
                "metric": protested_total,
                "calculation_type": "actual",
                "why": [
                    "وضعیت قطعی ReceivableNote برای این موارد protested است.",
                    "وجود واخواست می‌تواند کیفیت وصول و اعتبار مشتری را تحت تاثیر قرار دهد.",
                ],
                "evidence": [
                    {"label": "تعداد", "value": protested_count},
                    {"label": "مبلغ", "value": protested_total},
                    {"label": "دامنه", "value": cheque_summary.get("protested_scope")},
                ],
                "impact": "ریسک وصول مطالبات و نیاز به پیگیری اعتباری افزایش می‌یابد.",
                "recommendations": [
                    "مشتریان مرتبط با واخواست‌ها در اولویت پیگیری وصول قرار گیرند.",
                    "قبل از افزایش سقف اعتبار، سابقه واخواست بررسی شود.",
                ],
                "priority": 2,
            })

        if cash_shortage.get("absolute_shortage_available"):
            shortage_date = cash_shortage.get("first_predicted_shortage_date")
            if shortage_date:
                alerts.append({
                    "level": "critical",
                    "type": "predicted_cash_shortage",
                    "title": "کسری نقدینگی در افق پیش‌بینی مشاهده شده است",
                    "message": f"اولین کسری احتمالی در {shortage_date} پیش‌بینی شده است.",
                    "metric": cash_shortage.get("worst_projected_cash"),
                    "calculation_type": "forecast",
                    "why": [
                        "مانده افتتاحیه با جریان روزانه برآوردی و سررسید چک‌ها ترکیب شده است.",
                        "در سناریوی محتمل، مانده پیش‌بینی‌شده در بخشی از افق زیر صفر می‌رود.",
                    ],
                    "evidence": [
                        {"label": "اولین روز کسری", "value": shortage_date},
                        {"label": "بدترین مانده", "value": cash_shortage.get("worst_projected_cash")},
                        {"label": "افق", "value": cash_shortage.get("forecast_days")},
                    ],
                    "impact": "احتمال کمبود منابع برای پوشش تعهدات سررسیدشونده وجود دارد.",
                    "recommendations": [
                        "وصول مشتریان با اولویت بالا جلو انداخته شود.",
                        "پرداخت‌های کم‌اولویت یا قابل مذاکره بازبینی شوند.",
                    ],
                    "priority": 1,
                })
        else:
            pressure_days = int(cash_shortage.get("negative_cash_pressure_days", 0) or 0)
            if pressure_days:
                alerts.append({
                    "level": "warning",
                    "type": "cash_pressure_without_opening_balance",
                    "title": "روزهای فشار نقدی شناسایی شده، اما مانده افتتاحیه موجود نیست",
                    "message": f"در {pressure_days} روز از افق، تغییر خالص روزانه منفی است.",
                    "metric": pressure_days,
                    "calculation_type": "forecast",
                    "why": [
                        "پیش‌بینی روزانه خروجی را بیشتر از ورودی برآورد کرده است.",
                        "بدون opening_cash نمی‌توان کسری مطلق را با اطمینان اعلام کرد.",
                    ],
                    "evidence": [{"label": "روزهای فشار", "value": pressure_days}],
                    "impact": "ممکن است در بعضی روزها نیاز به جابه‌جایی زمان وصول یا پرداخت ایجاد شود.",
                    "recommendations": ["مانده نقد/بانک معتبر به Forecast اضافه شود تا کسری مطلق محاسبه شود."],
                    "priority": 3,
                })

        finding_count = int(anomalies.get("finding_count", 0) or 0)
        if finding_count:
            alerts.append({
                "level": "warning",
                "type": "anomaly_candidates",
                "title": "موارد مالی غیرعادی برای بررسی انسانی شناسایی شد",
                "message": f"{finding_count} مورد توسط کنترل‌های خودکار علامت‌گذاری شده است.",
                "metric": finding_count,
                "calculation_type": "calculated",
                "why": ["کنترل‌های مبلغ بزرگ/الگوی غیرعادی، مواردی را خارج از رفتار متعارف علامت زده‌اند."],
                "evidence": [
                    {"label": "تعداد یافته", "value": finding_count},
                    {"label": "اسناد بررسی‌شده", "value": anomalies.get("scanned_document_count")},
                ],
                "impact": "ممکن است خطای ثبت، دوباره‌کاری یا مورد نیازمند کنترل وجود داشته باشد؛ این نتیجه اثبات تخلف نیست.",
                "recommendations": ["موارد علامت‌خورده قبل از بستن کنترل روزانه بازبینی شوند."],
                "priority": 4,
            })

        for customer in customer_predictions.get("customers", [])[:50]:
            late = customer["late_payment_risk"]
            ret = customer["cheque_return_probability"]
            if late["label"] == "low" and ret["label"] == "low":
                continue
            level = "critical" if late["label"] == "high" or ret["label"] == "high" else "warning"
            alerts.append({
                "level": level,
                "type": "customer_collection_risk",
                "title": f"ریسک وصول مشتری: {customer['counterpart_name']}",
                "message": (
                    f"ریسک دیرکرد {late['value']}٪ و ریسک برگشت چک {ret['value']}٪ "
                    "در مدل توضیح‌پذیر برآورد شده است."
                ),
                "metric": max(late["value"], ret["value"]),
                "counterpart_ref": customer["counterpart_ref"],
                "calculation_type": "forecast",
                "why": customer.get("late_payment_risk", {}).get("reasons", []),
                "evidence": [
                    {"label": "چک‌های دریافتی باز", "value": customer.get("open_exposure")},
                    {"label": "چک‌های باز سررسیدگذشته", "value": customer.get("overdue_open_amount")},
                    {"label": "نسبت معوق باز", "value": customer.get("current_overdue_open_ratio_percent")},
                    {"label": "وصول مورد انتظار", "value": customer.get("collection_forecast", {}).get("expected_collection_amount")},
                ],
                "impact": "احتمال تاخیر در تبدیل چک‌های باز به نقد افزایش یافته است.",
                "recommendations": [
                    "شرایط چک جدید با سقف اعتباری و سیاست سررسید تطبیق داده شود.",
                    "در صورت بالا بودن اولویت وصول، پیگیری مشتری جلو انداخته شود.",
                ],
                "priority": 2 if level == "critical" else 5,
            })

        top_collection = collection_priorities.get("customers", [])[:3]
        for row in top_collection:
            if row.get("priority_level") != "high":
                continue
            alerts.append({
                "level": "high",
                "type": "collection_priority",
                "title": f"اولویت بالای وصول: {row['counterpart_name']}",
                "message": f"امتیاز اولویت وصول {row['priority_score']} از ۱۰۰ است.",
                "metric": row.get("open_exposure"),
                "counterpart_ref": row.get("counterpart_ref"),
                "calculation_type": "recommendation",
                "why": row.get("reasons", []),
                "evidence": [
                    {"label": "چک‌های دریافتی باز", "value": row.get("open_exposure")},
                    {"label": "چک‌های باز سررسیدگذشته", "value": row.get("overdue_open_amount")},
                ],
                "impact": "پیگیری زودتر این مشتری می‌تواند فشار نقدی کوتاه‌مدت را کاهش دهد.",
                "recommendations": [row.get("recommendation")],
                "priority": 3,
            })

        severity = {"critical": 4, "high": 3, "warning": 2, "info": 1}
        alerts.sort(key=lambda x: (severity.get(x.get("level", ""), 0), -int(x.get("priority", 99))), reverse=True)
        return alerts[:60]
