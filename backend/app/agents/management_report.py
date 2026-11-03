"""Management report built exclusively from canonical calculated reports.

Specialist prose and LLM predictions are never evidence for financial amounts.
"""
from datetime import datetime, timezone
from math import isfinite


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None



def _ratio(numerator, denominator):
    numerator = number(numerator)
    denominator = number(denominator)
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator * 100, 1)


def _future_window(timeline, days_count):
    rows = (timeline or [])[:days_count]
    if not rows:
        return {"days": days_count, "available": False}
    inflow = sum(float(x.get("projected_inflow") or 0) for x in rows)
    outflow = sum(float(x.get("projected_outflow") or 0) for x in rows)
    projected = [number(x.get("projected_cash")) for x in rows]
    projected = [x for x in projected if x is not None]
    return {
        "days": days_count,
        "available": True,
        "inflow_rial": round(inflow, 2),
        "outflow_rial": round(outflow, 2),
        "net_rial": round(inflow - outflow, 2),
        "minimum_cash_rial": min(projected) if projected else None,
        "shortage": any(x < 0 for x in projected),
    }


def _build_manager_alarms(portfolio, forecast, opening, shortage):
    alarms = []
    def add(level, code, title, message, evidence, impact, owner, deadline, agent, priority):
        alarms.append({
            "level": level, "code": code, "title": title, "message": message,
            "evidence": evidence, "impact": impact, "owner": owner, "deadline": deadline,
            "agent": agent, "priority": priority,
        })

    issued_overdue = number(portfolio.get("issued_overdue_amount_rial")) or 0
    issued_overdue_count = int(portfolio.get("issued_overdue_count") or 0)
    received_overdue = number(portfolio.get("received_overdue_amount_rial")) or 0
    received_overdue_count = int(portfolio.get("received_overdue_count") or 0)
    received_future = number(portfolio.get("received_future_open_amount_rial")) or 0
    issued_future = number(portfolio.get("issued_future_open_amount_rial")) or 0

    if opening is not None and shortage:
        add("critical", "cash_shortage", "کسری نقدینگی پیش‌بینی شده است",
            f"اولین روز کسری احتمالی {shortage} است.",
            [{"label":"اولین روز کسری","value":shortage}],
            "ریسک عدم پوشش تعهدات سررسیدشونده.", "مدیر خزانه", shortage,
            "Cash Flow Agent", 1)
    if issued_overdue_count:
        add("critical", "issued_overdue", "چک پرداختی سررسیدگذشته باز وجود دارد",
            f"{issued_overdue_count} فقره چک پرداختی معوق هنوز باز است.",
            [{"label":"تعداد","value":issued_overdue_count},{"label":"مبلغ ریال","value":issued_overdue}],
            "ریسک تعهد پرداخت حل‌نشده و فشار نقدینگی.", "مدیر خزانه", "امروز",
            "Cheque Payment Agent", 2)
    if received_overdue_count:
        ratio = _ratio(received_overdue, received_future + received_overdue)
        level = "high" if ratio is None or ratio >= 20 else "warning"
        add(level, "received_overdue", "وصول معوق نیازمند پیگیری است",
            f"{received_overdue_count} فقره چک دریافتی از سررسید گذشته است.",
            [{"label":"تعداد","value":received_overdue_count},{"label":"مبلغ ریال","value":received_overdue},{"label":"سهم معوق از سبد","value":ratio}],
            "تاخیر در تبدیل مطالبات به نقد می‌تواند برنامه پرداخت را تحت فشار قرار دهد.", "واحد وصول", "تا ۴۸ ساعت",
            "Collection Agent", 3)
    if opening is None:
        add("warning", "opening_cash_missing", "موجودی شروع معتبر در دسترس نیست",
            "بدون مانده شروع تأییدشده، کسری مطلق و مانده پایان دوره قابل اتکا نیست.",
            [], "کیفیت تصمیم Cash Flow کاهش می‌یابد.", "خزانه‌داری", "پیش از تأیید برنامه پرداخت",
            "Cash Flow Agent", 4)
    if issued_future:
        add("info", "future_issued_visibility", "تعهدات پرداختی آینده زیر نظر است",
            "چک‌های پرداختی باز امروز و آینده باید با تقویم منابع پوشش داده شوند.",
            [{"label":"مبلغ ریال","value":issued_future}],
            "کنترل پوشش تعهدات آتی.", "مدیر خزانه", "روزانه",
            "Cheque Payment Agent", 8)
    severity = {"critical":4,"high":3,"warning":2,"info":1}
    alarms.sort(key=lambda x: (severity.get(x["level"],0), -x["priority"]), reverse=True)
    return alarms

def build_management_report(agents, portfolio, actual_report=None, cashflow_report=None):
    actual_report = actual_report or {}
    actual = actual_report.get("summary") or {}
    # Compatibility with the deterministic cash/bank specialist only.
    bank_agent = agents.get("cash_bank_movement") or {}
    if not actual and (bank_agent.get("metadata") or {}).get("mode") == "rules":
        period = ((bank_agent.get("analysis") or {}).get("prediction") or {}).get("actual_period") or {}
        actual = {"inflow_rial": period.get("actual_inflow_rial"), "outflow_rial": period.get("actual_outflow_rial"), "net_rial": period.get("actual_net_rial")}
    forecast = cashflow_report or {}
    management = forecast.get("management_summary") or {}
    opening = number(forecast.get("opening_cash"))
    closing = next((number(p.get("amount_rial")) for p in management.get("key_points", []) if p.get("label") == "مانده پایان بازه"), None)
    coverage = number(management.get("coverage_percent")) if opening is not None else None
    shortage = management.get("first_shortage_date_jalali")
    kpis = []

    def metric(group, label, value, tone="blue", fmt="money", note=""):
        value = number(value)
        kpis.append({"group": group, "label": label, "value_rial": value if fmt.startswith("money") else None, "value": value if not fmt.startswith("money") else None, "format": fmt, "tone": tone, "available": value is not None, "note": note})

    for label, key, tone in [
        ("حواله دریافتی", "bank_receipt_rial", "blue"),
        ("حواله پرداختی", "bank_payment_total_rial", "amber"),
        ("حواله پرداختی بدون انتقال بانکی", "bank_payment_excluding_transfer_rial", "red"),
    ]:
        metric("actual", label, actual.get(key), tone)
    for label, key, tone in [
        ("چک‌های دریافتی باز؛ امروز و آینده", "received_future_open_amount_rial", "teal"),
        ("چک‌های دریافتی سررسیدگذشته", "received_overdue_amount_rial", "amber"),
        ("چک‌های پرداختی باز؛ امروز و آینده", "issued_future_open_amount_rial", "blue"),
        ("چک‌های پرداختی سررسیدگذشته", "issued_overdue_amount_rial", "red"),
    ]:
        metric("cheques", label, portfolio.get(key), tone, note="مبلغ اسمی چک؛ نرخ وصول روی این مانده اعمال نشده است")
    metric("forecast", "موجودی شروع از Excel", opening)
    metric("forecast", "وصول قابل برنامه‌ریزی", next((p.get("amount_rial") for p in management.get("key_points", []) if p.get("label") == "وصول قابل برنامه‌ریزی"), None), "teal")
    metric("forecast", "چک پرداختی و ذخیره حقوق در بازه", management.get("fixed_outflows_rial"), "red")
    metric("forecast", "مانده پیش‌بینی‌شده پایان بازه", closing if opening is not None else None, "red" if closing is not None and closing < 0 else "teal", "money_signed")
    metric("forecast", "پوشش چک‌های پرداختی و حقوق", coverage, "teal" if coverage is not None and coverage >= 100 else "amber", "percent")
    days = forecast.get("timeline") or []
    if days:
        seven_net = sum(float(d.get("projected_inflow") or 0) - float(d.get("projected_outflow") or 0) for d in days[:7])
    else:
        seven_net = None
    future_outlook = {
        "7_days": _future_window(days, 7),
        "30_days": _future_window(days, 30),
        "90_days": _future_window(days, 90),
    }
    metric("forecast", "خالص تغییر نقدینگی ۷ روز نخست", seven_net, "blue", "money_signed", "تغییر طی دوره؛ موجودی شروع در این عدد نیست")
    status = "critical" if opening is not None and shortage else "attention" if opening is None or coverage is None or coverage < 100 else "healthy"
    headline = "گزارش مدیریتی نقدینگی و تعهدات"
    conclusion = (
        f"اولین کسری نقدینگی در تاریخ {shortage} پیش‌بینی شده است؛ تأمین وجه پیش از این تاریخ در اولویت قرار دارد."
        if opening is not None and shortage else
        "موجودی شروع تأییدشده در دسترس نیست؛ مانده پایان بازه و کفایت منابع قابل تأیید نیست."
        if opening is None else
        "گزارش پیش‌بینی کامل در دسترس نیست؛ ارزیابی کفایت منابع نیازمند تکمیل محاسبه است."
        if not days or closing is None else
        "در افق محاسبه‌شده کسری مانده گزارش نشده است؛ پوشش پرداخت‌ها با وصول برنامه‌ریزی‌شده ارزیابی شود."
    )
    actions = []
    def action(title, why, owner, deadline, priority="high"):
        actions.append({"action": title, "why": why, "owner": owner, "deadline": deadline, "priority": priority, "expected_effect": "تکمیل مبنای تصمیم و کنترل تعهدات نقدی"})
    if opening is None:
        action("تکمیل و تطبیق موجودی شروع", "مانده حساب‌های بانکی با آخرین Excel موجودی تطبیق داده شود.", "خزانه‌داری", "پیش از تأیید برنامه پرداخت", "critical")
    else:
        action("تأمین وجه پرداخت‌های سررسیددار", f"برنامه تأمین وجه تا تاریخ {shortage} نهایی شود." if shortage else "وجه چک‌ها و حقوق مطابق تقویم پرداخت تخصیص داده شود.", "مدیر خزانه", shortage or "امروز", "critical" if shortage else "high")
    overdue = number(portfolio.get("received_overdue_amount_rial"))
    action("پیگیری وصول چک‌های دریافتی", "فهرست چک‌های سررسیدگذشته و وضعیت آخرین عملیات برای تعیین اقدام وصول بررسی شود." if overdue else "وصول چک‌های نزدیک سررسید با نرخ مصوب سناریوی پایه پیگیری شود.", "واحد وصول", "تا ۴۸ ساعت")
    action("تطبیق حواله‌های پرداختی و انتقال بانکی", "جمع کل حواله‌ها با تفکیک انتقال بانک‌به‌بانک و تنخواه تطبیق داده شود؛ گردش داخلی وارد خالص عملیاتی نشود.", "کارشناس خزانه", "تا پایان روز")
    alarms = _build_manager_alarms(portfolio, forecast, opening, shortage)
    critical_alarm_count = sum(1 for x in alarms if x.get("level") == "critical")
    high_alarm_count = sum(1 for x in alarms if x.get("level") == "high")
    if critical_alarm_count:
        status = "critical"
    elif high_alarm_count and status == "healthy":
        status = "attention"
    agent_requests = [
        {"agent":"Cash & Bank Movement Agent","required":["دریافت عملیاتی","پرداخت عملیاتی","انتقال داخلی","خالص واقعی","تازگی داده"]},
        {"agent":"Cash Flow Agent","required":["موجودی شروع","پیش‌بینی ۷/۳۰/۹۰ روز","اولین کسری","کمترین مانده","سناریو"]},
        {"agent":"Cheque Risk Agent","required":["چک دریافتی باز آینده","معوق دریافتی","ریسک وصول","راهکاران+کارآمد"]},
        {"agent":"Cheque Payment Agent","required":["چک پرداختی باز آینده","معوق پرداختی","تعهد قطعی","کامل بودن داده آینده"]},
        {"agent":"Collection Agent","required":["اولویت وصول","مبلغ قابل وصول","مشتریان معوق","اقدام بعدی"]},
        {"agent":"Customer Behavior Agent","required":["مشتری پرریسک","ارزش پرونده","تغییر رفتار","سابقه چک/حواله"]},
        {"agent":"Scenario Agent","required":["پایه","بدبینانه","خوش‌بینانه","اثر تصمیم"]},
    ]
    data_quality = {
        "sources": ["راهکاران", "کارآمد"],
        "karamad_issued_future_complete": False,
        "opening_cash_available": opening is not None,
        "note": "آینده چک پرداختی کارآمد کامل نیست؛ مانده باز آینده و معوق همیشه جدا گزارش می‌شوند.",
    }
    drilldowns = {
        "cash_movement":"Cash & Bank Movement Agent",
        "cashflow":"Cash Flow Agent",
        "received_cheques":"Cheque Risk Agent / Collection Agent",
        "issued_cheques":"Cheque Payment Agent",
        "customers":"Customer Behavior Agent",
        "scenarios":"Scenario Agent",
    }
    filters = actual_report.get("filters") or {}
    return {"metadata": {"agent_name": "Finance Manager Agent", "role": "گزارش مدیریتی نقدینگی و تعهدات", "generated_at": datetime.now(timezone.utc).isoformat(), "mode": "rules", "model": "executive_finance_manager_v113"}, "analysis": {
        "headline": headline, "summary": conclusion, "management_status": status,
        "executive_kpis": kpis, "cheque_portfolio": portfolio,
        "report_context": {"version": "v113", "actual_from": filters.get("date_from"), "actual_to": filters.get("date_to"), "forecast_from": (days[0].get("date_jalali") or days[0].get("date")) if days else None, "forecast_to": (days[-1].get("date_jalali") or days[-1].get("date")) if days else None, "first_shortage": shortage if opening is not None else None, "opening_available": opening is not None, "generated_at": datetime.now(timezone.utc).isoformat(), "decision_basis": management.get("decision_basis") or "پیش‌بینی معتبر هنوز در دسترس نیست."},
        "recommended_actions": actions, "decisions_today": actions[:3],
        "alarms": alarms,
        "alarm_summary": {"critical": critical_alarm_count, "high": high_alarm_count, "total": len(alarms)},
        "future_outlook": future_outlook,
        "agent_requests": agent_requests,
        "data_quality": data_quality,
        "drilldowns": drilldowns,
        "good_signals": [], "risks": [x.get("title") for x in alarms if x.get("level") in {"critical","high"}], "scenarios": {}, "prediction": future_outlook,
    }}
