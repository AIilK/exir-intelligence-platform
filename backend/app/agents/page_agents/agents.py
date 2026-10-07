"""Page Agentهای هر صفحه داشبورد (V171).

دو نوع Agent:
- جدید (روی داده زنده، متن با OpenAI): چک دریافتی، چک پرداختی، حواله‌های پرداختی شرکت، B2B،
  توزیع بار، Cash Flow روزانه، مغایرت‌گیری.
- Wrap شده (منطق و LLM همان Agent قبلی؛ هشدار/پیش‌بینی ساختاریافته و حافظه اضافه می‌شود):
  مشتری، نقدینگی، نقد و حواله، وصول، نمایندگان، سناریو، مدیر مالی.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.agents.page_agents.base import (
    PageAgent, action, alert, change_phrase, fa_number, prediction, toman,
)
from app.agents.page_agents.context import _days, cheque_buckets


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _iso_day(value: Any) -> str:
    return str(value or "")[:10]


def _days_back(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _top_by(rows: list[dict[str, Any]], key: str, amount_key: str, limit: int = 5) -> list[dict[str, Any]]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        name = str(row.get(key) or "نامشخص").strip() or "نامشخص"
        totals[name] += _f(row.get(amount_key))
        counts[name] += 1
    ranked = sorted(totals.items(), key=lambda item: -item[1])[:limit]
    return [{"name": name, "amount_rial": amount, "count": counts[name]} for name, amount in ranked]


# =============================================================== new agents
class ReceivedChequesAgent(PageAgent):
    key = "received_cheques"
    page = "چک‌های دریافتی"
    name = "Received Cheques Agent"
    role_fa = "پایش سررسید، تمرکز و سررسیدگذشته چک‌های دریافتی باز (راهکاران + کارآمد)"
    tracked_metrics = {
        "future_amount": "چک دریافتی باز آینده", "overdue_amount": "چک دریافتی سررسیدگذشته",
        "next_7_amount": "سررسید ۷ روز آینده", "overdue_count": "تعداد سررسیدگذشته",
    }
    primary_metric = "overdue_amount"

    def collect(self) -> dict[str, Any]:
        rows = self.ctx.received_open().get("cheques") or []
        buckets = cheque_buckets(rows)
        future = [r for r in rows if (_days(r) is not None and _days(r) >= 0)]
        overdue = [r for r in rows if (_days(r) is not None and _days(r) < 0)]
        top_drawers = _top_by(future, "counterpart_name", "amount")
        top_overdue = _top_by(overdue, "counterpart_name", "amount")
        metrics = {
            "count": buckets["all"]["count"], "future_amount": buckets["future"]["amount_rial"],
            "future_count": buckets["future"]["count"], "overdue_amount": buckets["overdue"]["amount_rial"],
            "overdue_count": buckets["overdue"]["count"], "today_amount": buckets["today"]["amount_rial"],
            "next_7_amount": buckets["next_7"]["amount_rial"], "next_7_count": buckets["next_7"]["count"],
            "next_30_amount": buckets["next_30"]["amount_rial"],
            "karamad_future_amount": buckets["future"]["sources"].get("karamad", {}).get("amount_rial", 0),
            "top_drawer_share_percent": round(top_drawers[0]["amount_rial"] / buckets["future"]["amount_rial"] * 100, 1)
            if top_drawers and buckets["future"]["amount_rial"] else 0,
        }
        return {"metrics": metrics, "top_drawers": top_drawers, "top_overdue": top_overdue}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        alerts, actions = [], []
        if m["overdue_count"]:
            level = "critical" if m["overdue_amount"] >= 0.15 * max(m["future_amount"], 1) else "high"
            alerts.append(alert(
                "received_overdue", level, f"{fa_number(m['overdue_count'])} چک دریافتی سررسیدگذشته و هنوز باز",
                [f"مبلغ {toman(m['overdue_amount'])} از موعد گذشته ولی در محل‌های باز (نزد بانک/صندوق/مأمور وصول) مانده است.",
                 change_phrase(deltas.get("overdue_amount"))],
                "وضعیت هر چک سررسیدگذشته در بانک استعلام و برگشتی‌ها تعیین تکلیف شوند.",
                evidence=[{"label": x["name"], "value": toman(x["amount_rial"])} for x in data["top_overdue"][:3]],
                metric=m["overdue_amount"]))
        if m["top_drawer_share_percent"] >= 15:
            top = data["top_drawers"][0]
            alerts.append(alert(
                "drawer_concentration", "medium",
                f"{fa_number(m['top_drawer_share_percent'])}٪ چک‌های آینده از یک مشتری است",
                [f"{top['name']} با {fa_number(top['count'])} چک و {toman(top['amount_rial'])}."],
                "سقف اعتبار این مشتری بازبینی و از تمرکز بیشتر جلوگیری شود.", entity_ref=top["name"]))
        if m["next_7_count"]:
            actions.append(action("هماهنگی واگذاری چک‌های ۷ روز آینده به بانک",
                                  f"{fa_number(m['next_7_count'])} چک به مبلغ {toman(m['next_7_amount'])} در هفته آینده سررسید می‌شود.",
                                  "خزانه", "high", "امروز", "وصول به‌موقع و پیش‌بینی دقیق‌تر نقدینگی"))
        if m["overdue_count"]:
            actions.append(action("تعیین تکلیف چک‌های سررسیدگذشته", "چک‌های گذشته‌موعد هنوز باز هستند.",
                                  "وصول", "high", "تا ۲۴ ساعت"))
        return {
            "headline": f"{toman(m['future_amount'])} چک دریافتی باز آینده؛ {toman(m['next_7_amount'])} تا ۷ روز آینده سررسید می‌شود.",
            "summary": f"{fa_number(m['count'])} چک دریافتی باز است؛ {fa_number(m['overdue_count'])} فقره به مبلغ {toman(m['overdue_amount'])} سررسیدگذشته است. "
                       + (change_phrase(deltas.get("future_amount")) and f"مانده آینده {change_phrase(deltas.get('future_amount'))}."),
            "good_signals": [f"{toman(m['next_30_amount'])} ورودی چکی تا ۳۰ روز آینده برنامه‌ریزی‌پذیر است."] if m["next_30_amount"] else [],
            "risks": [a["title"] for a in alerts],
            "recommended_actions": actions,
            "next_best_action": actions[0]["action"] if actions else "پایش روزانه سررسیدها ادامه یابد.",
            "alerts": alerts,
            "predictions": [
                prediction("next_7_amount", "سررسید چک دریافتی ۷ روز آینده", "۷ روز", m["next_7_amount"], "high",
                           "جمع اسمی چک‌های باز با سررسید امروز تا ۷ روز بعد"),
                prediction("next_30_amount", "سررسید چک دریافتی ۳۰ روز آینده", "۳۰ روز", m["next_30_amount"], "medium",
                           "جمع اسمی؛ بخشی ممکن است برگشت بخورد"),
            ],
        }


class IssuedChequesAgent(PageAgent):
    key = "issued_cheques"
    page = "چک‌های پرداختی"
    name = "Issued Cheques Agent"
    role_fa = "پایش تعهد چک‌های پرداختی و پوشش آن با نقدینگی"
    tracked_metrics = {"future_amount": "چک پرداختی باز آینده", "next_7_amount": "سررسید ۷ روز آینده",
                       "overdue_amount": "چک پرداختی سررسیدگذشته"}
    primary_metric = "next_7_amount"
    narrate_with_llm = True

    def collect(self):
        rows = self.ctx.issued_open().get("cheques") or []
        buckets = cheque_buckets(rows)
        liquidity = self.ctx.opening_cash()
        latest = self.ctx.excel_latest() or {}
        metrics = {
            "count": buckets["all"]["count"], "future_amount": buckets["future"]["amount_rial"],
            "overdue_amount": buckets["overdue"]["amount_rial"], "overdue_count": buckets["overdue"]["count"],
            "next_7_amount": buckets["next_7"]["amount_rial"], "next_7_count": buckets["next_7"]["count"],
            "next_30_amount": buckets["next_30"]["amount_rial"], "liquidity": liquidity,
            "coverage_7_percent": round(liquidity / buckets["next_7"]["amount_rial"] * 100, 1)
            if liquidity is not None and buckets["next_7"]["amount_rial"] else None,
        }
        return {"metrics": metrics, "liquidity_date": latest.get("jalali_date"),
                "top_payees": _top_by([r for r in rows if (_days(r) or 0) >= 0], "counterpart_name", "amount")}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        alerts = []
        if m["overdue_count"]:
            alerts.append(alert("issued_overdue", "critical",
                                f"{fa_number(m['overdue_count'])} چک پرداختی سررسیدگذشته هنوز پاس‌نشده ثبت است",
                                [f"مبلغ {toman(m['overdue_amount'])}؛ یا موجودی کافی نبوده یا وضعیت چک در سیستم ثبت نشده است."],
                                "وضعیت هر چک با بانک تطبیق و سند تعیین وضعیت ثبت شود.", metric=m["overdue_amount"]))
        cov = m["coverage_7_percent"]
        if cov is not None and cov < 120:
            alerts.append(alert("weak_cheque_coverage", "critical" if cov < 100 else "high",
                                f"پوشش چک‌های ۷ روز آینده با موجودی فقط {fa_number(cov)}٪ است",
                                [f"موجودی آخرین Excel ({data['liquidity_date'] or '—'}): {toman(m['liquidity'])}؛ سررسید ۷ روز: {toman(m['next_7_amount'])}."],
                                "تأمین منابع یا جابه‌جایی پرداخت‌های غیرضروری قبل از سررسید.", metric=cov))
        return {
            "headline": f"{toman(m['next_7_amount'])} چک پرداختی تا ۷ روز آینده سررسید می‌شود.",
            "summary": f"{fa_number(m['count'])} چک پرداختی باز به مبلغ آینده {toman(m['future_amount'])}؛ "
                       f"{toman(m['next_30_amount'])} در ۳۰ روز آینده. " + (f"پوشش ۷ روز با موجودی {fa_number(cov)}٪." if cov is not None else ""),
            "good_signals": ["چک پرداختی سررسیدگذشته‌ای ثبت نشده است."] if not m["overdue_count"] else [],
            "risks": [a["title"] for a in alerts],
            "recommended_actions": [action("تهیه برنامه پرداخت چک‌های هفته آینده", "تعهدات قطعی بانکی", "مدیر مالی",
                                           "high" if alerts else "medium", "این هفته", "جلوگیری از برگشت چک شرکت")],
            "next_best_action": "برنامه تأمین وجه چک‌های هفته آینده تأیید شود.",
            "alerts": alerts,
            "predictions": [
                prediction("next_7_amount", "خروجی چک پرداختی ۷ روز آینده", "۷ روز", m["next_7_amount"], "high", "سررسید چک‌های ثبت‌شده"),
                prediction("next_30_amount", "خروجی چک پرداختی ۳۰ روز آینده", "۳۰ روز", m["next_30_amount"], "high",
                           "سررسید چک‌های ثبت‌شده؛ چک‌های آینده کارآمد ممکن است کامل نباشد"),
            ],
        }


class CompanyPaymentsAgent(PageAgent):
    key = "company_payments"
    page = "حواله‌های پرداختی شرکت"
    name = "Company Payments Agent"
    role_fa = "تحلیل پرداخت‌های شرکت به تفکیک دسته و پیگیری پرداخت‌های بدون تأیید/سند"
    tracked_metrics = {"spend_30": "پرداخت ۳۰ روز اخیر (بدون انتقال داخلی)", "waiting_amount": "پرداخت بدون تأیید/سند",
                       "internal_30": "انتقال داخلی ۳۰ روز"}
    primary_metric = "spend_30"

    def collect(self):
        rows = self.ctx.company_payments()
        since30, since60 = _days_back(30), _days_back(60)
        internal = "انتقال بین حساب‌های شرکت"
        last30 = [r for r in rows if _iso_day(r.get("order_date")) >= since30]
        prev30 = [r for r in rows if since60 <= _iso_day(r.get("order_date")) < since30]
        spend = [r for r in last30 if r.get("category") != internal]
        spend_prev = [r for r in prev30 if r.get("category") != internal]
        waiting = [r for r in last30 if not r.get("is_approved")]
        by_category = _top_by(spend, "category", "calculated_amount", limit=10)
        prev_by_category = {x["name"]: x["amount_rial"] for x in _top_by(spend_prev, "category", "calculated_amount", limit=20)}
        large = sorted(spend, key=lambda r: -_f(r.get("calculated_amount")))[:5]
        metrics = {
            "spend_30": sum(_f(r.get("calculated_amount")) for r in spend),
            "spend_prev_30": sum(_f(r.get("calculated_amount")) for r in spend_prev),
            "count_30": len(spend),
            "internal_30": sum(_f(r.get("calculated_amount")) for r in last30 if r.get("category") == internal),
            "waiting_amount": sum(_f(r.get("calculated_amount")) for r in waiting),
            "waiting_count": len(waiting),
            "karamad_share_percent": round(sum(_f(r.get("calculated_amount")) for r in spend if r.get("source") == "karamad")
                                           / max(sum(_f(r.get("calculated_amount")) for r in spend), 1) * 100, 1),
        }
        return {"metrics": metrics, "by_category": by_category, "prev_by_category": prev_by_category,
                "large": [{"number": r.get("payment_order_number"), "name": r.get("counterpart_name"),
                           "amount_rial": _f(r.get("calculated_amount")), "source": r.get("source_label"),
                           "date": r.get("order_date_jalali"), "category": r.get("category")} for r in large]}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        alerts = []
        if m["spend_prev_30"] and m["spend_30"] > m["spend_prev_30"] * 1.25:
            growth = (m["spend_30"] / m["spend_prev_30"] - 1) * 100
            alerts.append(alert("spend_jump", "high", f"پرداخت‌های ۳۰ روز اخیر {fa_number(growth)}٪ بیشتر از ۳۰ روز قبل",
                                [f"{toman(m['spend_30'])} در برابر {toman(m['spend_prev_30'])} (بدون انتقال داخلی)."],
                                "دسته‌هایی که بیشترین رشد را داشته‌اند بازبینی شوند.", metric=growth))
        for cat in data["by_category"]:
            before = data["prev_by_category"].get(cat["name"], 0)
            if before and cat["amount_rial"] > before * 1.6 and cat["amount_rial"] > 0.1 * max(m["spend_30"], 1):
                alerts.append(alert("category_jump", "medium", f"رشد پرداخت دسته «{cat['name']}»",
                                    [f"{toman(cat['amount_rial'])} در ۳۰ روز اخیر در برابر {toman(before)} در ۳۰ روز قبل."],
                                    "علت رشد این دسته با مسئول مربوط بررسی شود.", entity_ref=cat["name"]))
        if m["waiting_count"]:
            alerts.append(alert("payments_waiting", "medium", f"{fa_number(m['waiting_count'])} پرداخت ۳۰ روز اخیر بدون تأیید/سند حسابداری",
                                [f"مبلغ {toman(m['waiting_amount'])}؛ در راهکاران تأیید نشده یا در کارآمد سند حسابداری نخورده است."],
                                "تأیید یا صدور سند این پرداخت‌ها پیگیری شود."))
        daily = m["spend_30"] / 30
        return {
            "headline": f"پرداخت ۳۰ روز اخیر شرکت {toman(m['spend_30'])} بوده است.",
            "summary": "بیشترین دسته‌ها: " + "، ".join(f"{c['name']} {toman(c['amount_rial'])}" for c in data["by_category"][:3])
                       + f". سهم کارآمد {fa_number(m['karamad_share_percent'])}٪.",
            "good_signals": [], "risks": [a["title"] for a in alerts],
            "recommended_actions": [action("بازبینی پنج پرداخت بزرگ ماه", "؛ ".join(f"{x['name']} {toman(x['amount_rial'])}" for x in data["large"][:3]),
                                           "مدیر مالی", "medium", "این هفته", "کنترل هزینه")],
            "next_best_action": "پرداخت‌های بدون تأیید/سند تعیین تکلیف شوند." if m["waiting_count"] else "پایش هزینه دسته‌ها ادامه یابد.",
            "alerts": alerts,
            "predictions": [prediction("spend_next_30", "پرداخت ۳۰ روز آینده با روند فعلی", "۳۰ روز", daily * 30, "low",
                                       "میانگین روزانه ۳۰ روز اخیر؛ پرداخت‌های غیرتکراری را شامل می‌شود")],
            "evidence": {"by_category": data["by_category"], "large": data["large"]},
        }


class B2BRemittancesAgent(PageAgent):
    key = "b2b_remittances"
    page = "حواله‌های مشتریان B2B"
    name = "B2B Remittances Agent"
    role_fa = "روند واریز مستقیم مشتریان B2B و تسویه چک‌های برگشتی"
    tracked_metrics = {"b2b_30": "واریز B2B ۳۰ روز اخیر", "returned_30": "تسویه چک برگشتی ۳۰ روز"}
    primary_metric = "b2b_30"

    def collect(self):
        rows = [r for r in self.ctx.b2b() if r.get("is_b2b_customer_payment")]
        since30, since60 = _days_back(30), _days_back(60)
        day = lambda r: _iso_day(r.get("deposit_date"))  # noqa: E731
        last30 = [r for r in rows if day(r) >= since30]
        prev30 = [r for r in rows if since60 <= day(r) < since30]
        metrics = {
            "b2b_30": sum(_f(r.get("amount_rial")) for r in last30),
            "b2b_prev_30": sum(_f(r.get("amount_rial")) for r in prev30),
            "returned_30": sum(_f(r.get("amount_rial")) for r in last30 if r.get("is_returned_cheque_settlement")),
            "customers_30": len({r.get("counterpart_ref") or r.get("customer_name") for r in last30}),
            "customers_prev_30": len({r.get("counterpart_ref") or r.get("customer_name") for r in prev30}),
        }
        return {"metrics": metrics, "top_customers": _top_by(last30, "customer_name", "amount_rial")}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        alerts = []
        if m["b2b_prev_30"] and m["b2b_30"] < m["b2b_prev_30"] * 0.75:
            drop = (1 - m["b2b_30"] / m["b2b_prev_30"]) * 100
            alerts.append(alert("b2b_drop", "high", f"واریز B2B {fa_number(drop)}٪ کمتر از ۳۰ روز قبل",
                                [f"{toman(m['b2b_30'])} در برابر {toman(m['b2b_prev_30'])}؛ مشتریان فعال {fa_number(m['customers_30'])} (قبل {fa_number(m['customers_prev_30'])})."],
                                "مشتریان B2B که واریزشان قطع شده پیگیری شوند."))
        top = data["top_customers"]
        if top and m["b2b_30"] and top[0]["amount_rial"] / m["b2b_30"] > 0.3:
            alerts.append(alert("b2b_concentration", "medium", f"{top[0]['name']} بیش از ۳۰٪ واریز B2B ماه است",
                                [f"{toman(top[0]['amount_rial'])} از {toman(m['b2b_30'])}."], "وابستگی به یک مشتری پایش شود.",
                                entity_ref=top[0]["name"]))
        return {
            "headline": f"واریز مستقیم مشتریان B2B در ۳۰ روز اخیر {toman(m['b2b_30'])}.",
            "summary": f"{fa_number(m['customers_30'])} مشتری واریز داشته‌اند؛ تسویه چک برگشتی {toman(m['returned_30'])}. "
                       f"۳۰ روز قبل: {toman(m['b2b_prev_30'])}.",
            "good_signals": ["روند واریز نسبت به ماه قبل رو به رشد است."] if m["b2b_30"] > m["b2b_prev_30"] else [],
            "risks": [a["title"] for a in alerts],
            "recommended_actions": [action("پیگیری مشتریان B2B بدون واریز اخیر", "حفظ جریان نقد مستقیم", "فروش B2B", "medium", "این هفته")],
            "next_best_action": "مشتریان B2B با کاهش واریز تماس گرفته شوند." if alerts else "روند واریز B2B پایش شود.",
            "alerts": alerts,
            "predictions": [prediction("b2b_next_30", "واریز B2B ۳۰ روز آینده", "۳۰ روز",
                                       (m["b2b_30"] + m["b2b_prev_30"]) / 2 if m["b2b_prev_30"] else m["b2b_30"], "low",
                                       "میانگین دو بازه ۳۰ روزه اخیر")],
        }


class DistributionAgent(PageAgent):
    key = "distribution"
    page = "توزیع بار"
    name = "Distribution Agent"
    role_fa = "پایش فاکتورهای توزیع‌نشده، سرعت ثبت حواله خروج و حواله‌های باز"
    tracked_metrics = {"undistributed_amount": "فاکتور توزیع‌نشده", "stale_count": "توزیع‌نشده بیش از ۱۴ روز",
                       "median_hours_to_exit": "میانه ثبت فاکتور تا حواله (ساعت)"}
    primary_metric = "undistributed_amount"

    def collect(self):
        overview = self.ctx.distribution_overview()
        timeline = self.ctx.distribution_timeline().get("invoices") or []
        rows = overview.get("undistributed") or []
        stale = [r for r in rows if (r.get("days_waiting") or 0) > 14]
        hours = sorted(x["hours_to_exit_registration"] for x in timeline if x.get("hours_to_exit_registration") is not None)
        exited = [x for x in timeline if x.get("exit_id")]
        same_day = [x for x in exited if (x.get("invoice_created") or {}).get("date_jalali") == (x.get("exit_registered") or {}).get("date_jalali")]
        branch_stale = _top_by(stale, "branch_name", "amount_rial")
        slow = sorted((overview.get("lead_time") or []), key=lambda x: -_f(x.get("average_days")))[:3]
        metrics = {
            "undistributed_count": len(rows), "undistributed_amount": sum(_f(r.get("amount_rial")) for r in rows),
            "stale_count": len(stale), "stale_amount": sum(_f(r.get("amount_rial")) for r in stale),
            "open_exit_count": len(overview.get("open_exits") or []),
            "median_hours_to_exit": hours[len(hours) // 2] if hours else None,
            "same_day_exit_percent": round(len(same_day) / len(exited) * 100, 1) if exited else None,
            "late_registered_count": sum(1 for x in timeline if (x.get("registration_delay_days") or 0) > 0),
            "invoice_count_14d": len(timeline),
        }
        return {"metrics": metrics, "branch_stale": branch_stale, "slow_branches": slow,
                "oldest": sorted(rows, key=lambda r: -(r.get("days_waiting") or 0))[:5]}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        alerts = []
        if m["stale_count"]:
            alerts.append(alert("stale_undistributed", "high", f"{fa_number(m['stale_count'])} فاکتور بیش از ۱۴ روز بدون حواله خروج",
                                [f"مبلغ {toman(m['stale_amount'])}؛ این فاکتورها در فروش و بدهی مشتری حساب شده‌اند ولی بار نرفته است.",
                                 "بیشترین در: " + "، ".join(f"{b['name']} ({fa_number(b['count'])})" for b in data["branch_stale"][:3])],
                                "با شعب مربوط علت عدم ارسال بررسی و فاکتورهای غیرقابل ارسال اصلاح/مرجوع شوند.",
                                evidence=[{"label": f"فاکتور {r.get('number')} — {r.get('customer_name')}",
                                           "value": f"{fa_number(r.get('days_waiting'))} روز"} for r in data["oldest"][:3]]))
        for branch in data["slow_branches"]:
            if _f(branch.get("average_days")) > 7:
                alerts.append(alert("slow_branch", "medium", f"خروج بار {branch.get('branch_name')} به‌طور میانگین {fa_number(branch.get('average_days'))} روز طول می‌کشد",
                                    [f"{fa_number(branch.get('over_7_days'))} از {fa_number(branch.get('invoice_count'))} فاکتور بیش از ۷ روز."],
                                    "ظرفیت توزیع و زمان‌بندی خروج این شعبه بازبینی شود.", entity_ref=branch.get("branch_name")))
        if m["late_registered_count"] and m["invoice_count_14d"] and m["late_registered_count"] / m["invoice_count_14d"] > 0.3:
            alerts.append(alert("late_invoice_registration", "medium",
                                f"{fa_number(m['late_registered_count'])} فاکتور ۱۴ روز اخیر دیرتر از تاریخ خودش ثبت شده",
                                ["ساعت ثبت فاکتور در کارآمد بعد از روز تاریخ فاکتور است؛ گزارش روزانه فروش دیر کامل می‌شود."],
                                "ثبت فاکتور در همان روز صدور الزامی شود."))
        median = m["median_hours_to_exit"]
        return {
            "headline": f"{fa_number(m['undistributed_count'])} فاکتور به مبلغ {toman(m['undistributed_amount'])} هنوز حواله خروج ندارد.",
            "summary": (f"میانه فاصله ثبت فاکتور تا ثبت حواله در ۱۴ روز اخیر {fa_number(median)} ساعت است؛ "
                        f"{fa_number(m['same_day_exit_percent'])}٪ همان روز حواله شده‌اند.") if median is not None else "",
            "good_signals": [], "risks": [a["title"] for a in alerts],
            "recommended_actions": [action("پیگیری قدیمی‌ترین فاکتورهای توزیع‌نشده با شعب", "بار نرفته ولی بدهی مشتری ثبت شده",
                                           "مدیر توزیع", "high" if m["stale_count"] else "medium", "امروز")],
            "next_best_action": "قدیمی‌ترین فاکتورهای بدون حواله تعیین تکلیف شوند.",
            "alerts": alerts,
            "predictions": [prediction("median_hours_to_exit", "زمان معمول ثبت فاکتور تا حواله", "۱۴ روز اخیر",
                                       median, "medium", "میانه ۱۴ روز اخیر", unit="hours",
                                       display=f"{fa_number(median)} ساعت" if median is not None else "—")],
        }


class DailyCashExcelAgent(PageAgent):
    key = "daily_cash_excel"
    page = "Cash Flow روزانه"
    name = "Daily Cash Report Agent"
    role_fa = "پایش گزارش روزانه نقدینگی (Excel): موجودی، تعهدات، فشار و کسری"
    tracked_metrics = {"liquidity": "موجودی نقد", "obligations": "تعهدات", "pressure_percent": "فشار نقدینگی ٪"}
    primary_metric = "liquidity"

    def collect(self):
        latest = self.ctx.excel_latest()
        if not latest:
            raise ValueError("هنوز هیچ Excel روزانه نقدینگی بارگذاری نشده است.")
        import jdatetime
        y, mo, d = (int(x) for x in str(latest["jalali_date"]).split("/"))
        age = (date.today() - jdatetime.date(y, mo, d).togregorian()).days
        metrics = {"liquidity": _f(latest.get("liquidity_rial")), "obligations": _f(latest.get("obligations_rial")),
                   "pressure_percent": _f(latest.get("pressure_percent")), "shortfall": _f(latest.get("shortfall_rial")),
                   "overdue_cheques": _f(latest.get("overdue_cheques_rial")), "upcoming_cheques": _f(latest.get("upcoming_cheques_rial")),
                   "snapshot_age_days": age}
        return {"metrics": metrics, "snapshot_date": latest["jalali_date"], "monthly": self.ctx.excel_monthly() or {}}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        alerts = []
        if m["snapshot_age_days"] > 3:
            alerts.append(alert("stale_snapshot", "high", f"آخرین گزارش روزانه نقدینگی {fa_number(m['snapshot_age_days'])} روز پیش است",
                                [f"آخرین فایل: {data['snapshot_date']}؛ پیش‌بینی نقدینگی و پوشش چک‌ها روی موجودی قدیمی حساب می‌شود."],
                                "فایل Excel روزانه نقدینگی امروز بارگذاری شود."))
        if m["shortfall"] > 0:
            alerts.append(alert("cash_shortfall", "critical", f"کسری {toman(m['shortfall'])} در گزارش روزانه",
                                ["تعهدات از موجودی بیشتر است."], "تأمین منابع یا جابه‌جایی پرداخت‌ها فوری بررسی شود."))
        elif m["pressure_percent"] >= 70:
            alerts.append(alert("cash_pressure", "high", f"فشار نقدینگی {fa_number(m['pressure_percent'])}٪",
                                ["بیش از ۷۰٪ موجودی صرف تعهدات می‌شود."], "پرداخت‌های غیرضروری به تعویق بیفتد."))
        return {
            "headline": f"موجودی {toman(m['liquidity'])} و تعهدات {toman(m['obligations'])} (گزارش {data['snapshot_date']}).",
            "summary": f"فشار نقدینگی {fa_number(m['pressure_percent'])}٪؛ چک سررسیدگذشته {toman(m['overdue_cheques'])} و آینده {toman(m['upcoming_cheques'])}. "
                       + (change_phrase(deltas.get("liquidity")) and f"موجودی {change_phrase(deltas.get('liquidity'))}."),
            "good_signals": ["کسری نقدینگی گزارش نشده است."] if not m["shortfall"] else [],
            "risks": [a["title"] for a in alerts],
            "recommended_actions": [action("بارگذاری روزانه Excel نقدینگی", "مبنای همه پیش‌بینی‌های نقدینگی", "خزانه",
                                           "high" if m["snapshot_age_days"] > 3 else "medium", "هر روز ساعت ۱۰")],
            "next_best_action": alerts[0]["action"] if alerts else "گزارش روزانه به‌موقع بارگذاری شود.",
            "alerts": alerts,
            "predictions": [prediction("remaining_cash", "موجودی پس از تعهدات فعلی", "گزارش جاری",
                                       m["liquidity"] - m["obligations"], "medium", "موجودی منهای تعهدات همان گزارش")],
        }


class ReconciliationAgent(PageAgent):
    key = "reconciliation"
    page = "مغایرت‌گیری بانک"
    name = "Bank Reconciliation Agent"
    role_fa = "پایش نتیجه مغایرت‌گیری صورت‌حساب‌ها: بدون سند، نیازمند بررسی و اختلاف مانده"
    tracked_metrics = {"unposted_rows": "ردیف بدون سند", "needs_review_rows": "ردیف نیازمند بررسی"}
    primary_metric = "unposted_rows"

    def collect(self):
        reports = self.ctx.reconciliation_reports()
        if not reports:
            raise ValueError("هنوز هیچ مغایرت‌گیری ثبت نشده است.")
        latest_by_account: dict[str, dict[str, Any]] = {}
        for report in reports:
            key = str((report["account"] or {}).get("account_id") or report["filename"])
            latest_by_account.setdefault(key, report)
        accounts = []
        for report in latest_by_account.values():
            counts = report["summary"].get("business_counts") or {}
            amounts = report["summary"].get("business_amounts") or {}
            accounts.append({
                "label": report["account"].get("display_label") or report["filename"],
                "period": report["file"].get("statement_period_jalali"), "created_at": report["created_at"],
                "unposted": int(counts.get("unposted") or 0), "unposted_amount": _f(amounts.get("unposted")),
                "needs_review": int(counts.get("needs_review") or 0),
                "first_unmatched": report["book_balance"].get("first_unmatched_date_jalali"),
                "last_matched": report["book_balance"].get("last_matched_date_jalali"),
            })
        metrics = {"accounts": len(accounts), "unposted_rows": sum(a["unposted"] for a in accounts),
                   "unposted_amount": sum(a["unposted_amount"] for a in accounts),
                   "needs_review_rows": sum(a["needs_review"] for a in accounts),
                   "balance_mismatch_accounts": sum(1 for a in accounts if a["first_unmatched"])}
        return {"metrics": metrics, "accounts": accounts}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        alerts = []
        for acc in data["accounts"]:
            if acc["unposted"]:
                alerts.append(alert("unposted_rows", "high" if acc["unposted_amount"] > 1e10 else "medium",
                                    f"{acc['label']}: {fa_number(acc['unposted'])} گردش بانکی بدون سند",
                                    [f"دوره {acc['period'] or '—'}؛ مبلغ {toman(acc['unposted_amount'])}.",
                                     f"مانده بانک و دفتر تا {acc['last_matched'] or '—'} برابر است." if acc["last_matched"] else ""],
                                    "گردش‌های بدون سند در خزانه ثبت یا علت بررسی شود.", entity_ref=acc["label"]))
        return {
            "headline": f"{fa_number(m['unposted_rows'])} گردش بدون سند در آخرین مغایرت‌گیری {fa_number(m['accounts'])} حساب.",
            "summary": f"مبلغ بدون سند {toman(m['unposted_amount'])}؛ {fa_number(m['needs_review_rows'])} ردیف نیازمند بررسی؛ "
                       f"{fa_number(m['balance_mismatch_accounts'])} حساب اختلاف مانده روزانه دارد.",
            "good_signals": [], "risks": [a["title"] for a in alerts],
            "recommended_actions": [action("ثبت اسناد گردش‌های بدون سند", "تطبیق دفتر با بانک", "حسابداری خزانه", "medium", "این هفته")],
            "next_best_action": "مغایرت‌گیری حساب‌ها هر هفته با فایل جدید بانک تکرار شود.",
            "alerts": alerts, "predictions": [],
        }


# ============================================================= wrapped agents
class LegacyWrappedAgent(PageAgent):
    """Wraps an existing decision agent: its analysis text stays, structured alerts/predictions are added."""

    narrate_with_llm = False

    def legacy_result(self) -> dict[str, Any]:
        raise NotImplementedError

    def legacy_metrics(self) -> dict[str, Any]:
        return {}

    def collect(self):
        legacy = self.ctx.legacy(self.key, self.legacy_result)
        return {"metrics": self.legacy_metrics(), "legacy": legacy, "mode": (legacy.get("metadata") or {}).get("mode", "rules")}

    def extra(self, data, memory, deltas) -> dict[str, Any]:
        return {"alerts": [], "predictions": []}

    def rules(self, data, memory, deltas):
        analysis = dict(data["legacy"].get("analysis") or {})
        extra = self.extra(data, memory, deltas)
        analysis.setdefault("summary", analysis.get("human_summary"))
        analysis["alerts"] = extra["alerts"]
        analysis["predictions"] = extra["predictions"]
        return analysis


class CustomerRiskAgent(LegacyWrappedAgent):
    key = "customer_behavior"
    page = "پرونده مشتری"
    name = "Customer Risk Agent"
    role_fa = "پیش‌بینی ریسک مشتری و پیشنهاد سیاست اعتبار"
    tracked_metrics = {"open_exposure": "مانده باز مشتریان", "collection_gap": "شکاف وصول", "high_risk_count": "مشتری پرریسک"}
    primary_metric = "collection_gap"

    def legacy_result(self):
        from app.agents.finance_decision_agents import CustomerRiskDecisionAgent
        return CustomerRiskDecisionAgent().run(self.ctx.customer())

    def legacy_metrics(self):
        s = self.ctx.customer().get("summary") or {}
        return {k: _f(s.get(k)) for k in ("customer_count", "high_risk_count", "medium_risk_count", "open_exposure",
                                          "expected_collection_next_period", "collection_gap")}

    def extra(self, data, memory, deltas):
        m = data["metrics"]
        alerts = []
        for a in (self.ctx.customer().get("alerts") or [])[:8]:
            if a.get("level") in {"critical", "high"}:
                alerts.append(alert("customer_risk", a["level"], a.get("title") or "ریسک مشتری",
                                    [str(x) for x in (a.get("why") or [])][:3] or [a.get("message") or ""],
                                    "؛ ".join(str(x) for x in (a.get("recommendations") or [])[:1]) or "پرونده مشتری بازبینی شود.",
                                    entity_ref=a.get("counterpart_ref")))
        ratio = m["expected_collection_next_period"] / m["open_exposure"] * 100 if m["open_exposure"] else 0
        return {"alerts": alerts, "predictions": [
            prediction("expected_collection_next_period", "وصول مورد انتظار دوره آینده", "دوره پیش‌بینی",
                       m["expected_collection_next_period"], "medium",
                       f"رفتار تاریخی چک‌های هر مشتری؛ {fa_number(ratio)}٪ مانده باز")]}


class CashflowAgent(LegacyWrappedAgent):
    key = "cashflow"
    page = "پیش‌بینی نقدینگی"
    name = "Cash Flow Prediction Agent"
    role_fa = "پیش‌بینی نقدینگی و پیشنهاد جلوگیری از کسری"
    tracked_metrics = {"net_cash_change": "تغییر خالص نقد ۳۰ روز", "lowest_projected_cash": "کمترین موجودی پیش‌بینی"}
    primary_metric = "lowest_projected_cash"

    def legacy_result(self):
        from app.agents.finance_decision_agents import CashFlowDecisionAgent
        return CashFlowDecisionAgent().run(self.ctx.cash())

    def legacy_metrics(self):
        cash = self.ctx.cash()
        timeline = cash.get("timeline") or []
        projected = [(_f(x.get("projected_cash")), x.get("date_jalali")) for x in timeline if x.get("projected_cash") is not None]
        lowest = min(projected) if projected else (None, None)
        first_short = next((x.get("date_jalali") for x in timeline if x.get("cash_shortage")), None)
        ms = cash.get("management_summary") or {}
        return {"opening_cash": _f(cash.get("opening_cash")), "net_cash_change": _f(ms.get("net_cash_change_rial")),
                "coverage_percent": _f(ms.get("coverage_percent")), "lowest_projected_cash": lowest[0],
                "lowest_date": lowest[1], "first_shortage_date": first_short}

    def extra(self, data, memory, deltas):
        m = data["metrics"]
        alerts = []
        if m["first_shortage_date"]:
            alerts.append(alert("projected_shortage", "critical", f"کسری نقدینگی از {m['first_shortage_date']} پیش‌بینی می‌شود",
                                [f"کمترین موجودی پیش‌بینی {toman(m['lowest_projected_cash'])} در {m['lowest_date']}."],
                                "وصول مشتریان اولویت‌دار جلو بیفتد و پرداخت‌های غیرضروری جابه‌جا شود."))
        return {"alerts": alerts, "predictions": [
            prediction("lowest_projected_cash", "کمترین موجودی ۳۰ روز آینده", m["lowest_date"] or "۳۰ روز",
                       m["lowest_projected_cash"], "medium", "موجودی Excel + ۷۵٪ چک دریافتی − چک پرداختی − ذخیره حقوق"),
            prediction("net_cash_change", "تغییر خالص نقد ۳۰ روز", "۳۰ روز", m["net_cash_change"], "medium", "همان مدل نقدینگی")]}


class CashBankAgent(LegacyWrappedAgent):
    key = "cash_bank_movement"
    page = "نقد و حواله"
    name = "Cash & Bank Movement Agent"
    role_fa = "تحلیل دریافت، پرداخت، حواله و انتقال داخلی"
    tracked_metrics = {"inflow": "ورودی ماه", "outflow": "خروجی ماه", "net": "خالص ماه"}
    primary_metric = "net"

    def legacy_result(self):
        from app.agents.finance_decision_agents import CashBankMovementDecisionAgent
        return CashBankMovementDecisionAgent().run(self.ctx.cash_bank(), self.ctx.internal_transfers(), self.ctx.payment_commitments())

    def legacy_metrics(self):
        s = self.ctx.cash_bank().get("summary") or {}
        f = self.ctx.cash_bank().get("filters") or {}
        return {"inflow": _f(s.get("inflow_rial")), "outflow": _f(s.get("outflow_rial")), "net": _f(s.get("net_rial")),
                "internal_transfer": _f(s.get("bank_payment_internal_transfer_rial")),
                "date_from": f.get("date_from"), "date_to": f.get("date_to")}

    def extra(self, data, memory, deltas):
        m = data["metrics"]
        alerts = []
        if m["net"] < 0:
            alerts.append(alert("negative_net_month", "high", f"خالص نقد ۳۰ روز اخیر منفی است ({toman(m['net'])})",
                                [f"ورودی {toman(m['inflow'])} در برابر خروجی {toman(m['outflow'])}."],
                                "خروجی‌های بزرگ ماه بازبینی و وصول تسریع شود."))
        return {"alerts": alerts, "predictions": [
            prediction("net_next_30", "خالص نقد ۳۰ روز آینده با روند فعلی", "۳۰ روز", m["net"], "low", "تکرار خالص ۳۰ روز اخیر")]}


class CollectionAgent(LegacyWrappedAgent):
    key = "collection"
    page = "مرکز عملیات وصول"
    name = "Collection Decision Agent"
    role_fa = "پیش‌بینی وصول و تعیین اقدام بعدی مشتریان"
    tracked_metrics = {"overdue_total": "سررسیدگذشته ۱۰۰ مشتری اول", "expected_total": "وصول مورد انتظار"}
    primary_metric = "overdue_total"

    def legacy_result(self):
        from app.agents.finance_decision_agents import CollectionDecisionAgent
        return CollectionDecisionAgent().run(self.ctx.collections())

    def legacy_metrics(self):
        rows = self.ctx.collections().get("customers") or []
        return {"customers": len(rows), "overdue_total": sum(_f(r.get("overdue_open_amount")) for r in rows),
                "expected_total": sum(_f(r.get("expected_collection_amount")) for r in rows),
                "critical_count": sum(1 for r in rows if r.get("priority_level") in {"critical", "high"})}

    def extra(self, data, memory, deltas):
        rows = self.ctx.collections().get("customers") or []
        alerts = [alert("collection_priority", "high", f"اولویت وصول: {r.get('counterpart_name')}",
                        [f"سررسیدگذشته {toman(r.get('overdue_open_amount'))} از مانده {toman(r.get('open_exposure'))}."]
                        + [str(x) for x in (r.get("reasons") or [])[:2]],
                        str(r.get("recommendation") or "تماس و ثبت قول پرداخت"), entity_ref=r.get("counterpart_ref"))
                  for r in rows[:5] if r.get("priority_level") in {"critical", "high"} and _f(r.get("overdue_open_amount")) > 0]
        return {"alerts": alerts, "predictions": [
            prediction("expected_total", "وصول مورد انتظار ۱۰۰ مشتری اولویت‌دار", "دوره پیش‌بینی",
                       data["metrics"]["expected_total"], "medium", "احتمال وصول هر مشتری از سابقه چک")]}


class RepresentativeAgentPage(LegacyWrappedAgent):
    key = "representative"
    page = "تحلیل نمایندگان"
    name = "Representative Performance Agent"
    role_fa = "تحلیل کیفیت پرتفوی و وصول نمایندگان"
    tracked_metrics = {"critical_count": "نماینده بحرانی"}
    primary_metric = "critical_count"
    primary_unit = "count"

    def legacy_result(self):
        from app.agents.finance_specialist_agents import RepresentativeAgent
        return RepresentativeAgent().run(self.ctx.representatives())

    def legacy_metrics(self):
        reps = self.ctx.representatives()
        rows = reps.get("representatives") or []
        return {"representatives": len(rows), "critical_count": sum(1 for x in rows if x.get("status") == "critical"),
                "mapping_ready": reps.get("status") != "not_ready"}

    def extra(self, data, memory, deltas):
        if data["metrics"]["mapping_ready"]:
            return {"alerts": [], "predictions": []}
        return {"alerts": [alert("mapping_missing", "medium", "ارتباط مشتری و نماینده تنظیم نشده است",
                                 ["فایل نگاشت مشتری به نماینده در سیستم نیست؛ تحلیل نمایندگان ممکن نیست."],
                                 "فایل customer_representative_mapping.csv تکمیل شود.")], "predictions": []}


class ScenarioAgent(LegacyWrappedAgent):
    key = "scenario"
    page = "سناریوساز نقدینگی"
    name = "Finance Scenario Agent"
    role_fa = "مقایسه سناریوها و انتخاب مسیر کم‌ریسک"

    def legacy_result(self):
        from app.agents.finance_decision_agents import ChequePaymentDecisionAgent, ScenarioDecisionAgent
        cash = self.ctx.legacy("cashflow", CashflowAgent(self.store, self.ctx).legacy_result)
        cheque_payment = self.ctx.legacy("cheque_payment", lambda: ChequePaymentDecisionAgent().run(
            self.ctx.cheque_quality(), self.ctx.excel_monthly()))
        return ScenarioDecisionAgent().run(cash.get("analysis") or {}, cheque_payment.get("analysis") or {})


class ManagerAgent(LegacyWrappedAgent):
    key = "management"
    page = "خلاصه مدیریتی"
    name = "Finance Manager Agent"
    role_fa = "هماهنگ‌کننده همه Agentها و پیشنهاد تصمیم نهایی"
    tracked_metrics = {"critical_alerts": "هشدار بحرانی کل", "received_overdue": "چک دریافتی سررسیدگذشته",
                       "issued_future": "چک پرداختی باز آینده"}
    primary_metric = "critical_alerts"
    primary_unit = "count"

    def __init__(self, store=None, context=None, team_results: dict[str, dict[str, Any]] | None = None):
        super().__init__(store, context)
        self.team = team_results or {}

    def legacy_result(self):
        from app.agents.finance_decision_agents import FinanceManagerDecisionAgent
        result = FinanceManagerDecisionAgent().run(
            self.team, cheque_portfolio=self.ctx.cheque_portfolio(),
            actual_report=self.ctx.cash_bank(), cashflow_report=self.ctx.cash())
        analysis = result.setdefault("analysis", {})
        analysis.setdefault("cheque_portfolio", self.ctx.cheque_portfolio())
        return result

    def legacy_metrics(self):
        alerts = [a for r in self.team.values() for a in (r.get("alerts") or [])]
        p = self.ctx.cheque_portfolio()
        return {"critical_alerts": sum(1 for a in alerts if a["level"] == "critical"),
                "high_alerts": sum(1 for a in alerts if a["level"] == "high"),
                "agents_ok": sum(1 for r in self.team.values() if r.get("status") == "success"),
                "agents_total": len(self.team),
                "received_overdue": p.get("received_overdue_amount_rial"), "issued_future": p.get("issued_future_open_amount_rial")}

    def extra(self, data, memory, deltas):
        ranked = sorted(
            ((r.get("page"), a) for r in self.team.values() for a in (r.get("alerts") or [])
             if a["level"] in {"critical", "high"} and a.get("status") != "dismissed"),
            key=lambda item: ({"critical": 0, "high": 1}[item[1]["level"]], -(item[1].get("consecutive_runs") or 1)))
        alerts = [alert(f"team:{a['type']}", a["level"], f"{page}: {a['title']}", a.get("why") or [], a.get("action") or "",
                        entity_ref=a.get("alert_key")) for page, a in ranked[:6]]
        predictions = [{**p, "label": f"{r.get('page')} — {p['label']}"} for r in self.team.values()
                       for p in (r.get("predictions") or [])[:1]]
        return {"alerts": alerts, "predictions": predictions[:8]}


PAGE_AGENT_CLASSES: list[type[PageAgent]] = [
    ReceivedChequesAgent, IssuedChequesAgent, CompanyPaymentsAgent, B2BRemittancesAgent, DistributionAgent,
    DailyCashExcelAgent, ReconciliationAgent, CustomerRiskAgent, CashflowAgent, CashBankAgent, CollectionAgent,
    RepresentativeAgentPage, ScenarioAgent,
]
