"""Page Agentهای فروش (هیبریدها) روی همان چارچوب V171: هشدار، پیش‌بینی، اقدام و حافظه.

منبع فروش: API داشبورد فروش (sales-dashboard، پیش‌فرض http://127.0.0.1:8000؛ متغیر SALES_API_URL)
که همان اعداد صفحات فروش را می‌دهد. منبع مالی: سرویس‌های همین پروژه (شبکه فروش کارآمد، چک‌ها).
همه فقط خواندنی‌اند. تارگت فروش عمداً در این Agentها نیست (تا درست شدن تارگت‌گذاری).

Agentها:
- sales_pace            سرعت فروش هیبریدها: ماه جاری در برابر همین بازه ماه قبل و پارسال، افت نسبی و توقف فروش
- sales_requests        تبدیل درخواست (سفارش) به فاکتور: افت نرخ تبدیل، سفارش‌های معطل، فروشنده‌های کم‌تبدیل
- sales_finance_bridge  پل فروش و مالی: فروش به مشتری دارای چک برگشتی، رشد فروش با وصول ضعیف، ویزیتور پربدهی
- sales_manager         مدیر فروش: تیم بالا را اجرا و جمع‌بندی و سه اقدام اولویت‌دار را می‌سازد
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import text

from app.agents.page_agents.base import LEVEL_ORDER, PageAgent, action, alert, fa_number, prediction, toman

SALES_API = os.environ.get("SALES_API_URL", "http://127.0.0.1:8000").rstrip("/")
SALES_TIMEOUT_SECONDS = 240
JALALI_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
# Months that were not normal for sales (internal events, internet shutdown, war, Nowruz): a comparison
# against them is reported with a caution and lower confidence.
ABNORMAL_MONTHS = {"1404/10", "1404/11", "1404/12", "1405/01"}

MIN_BASE_RIAL = 5e9          # 500M toman: below this a growth percent says nothing
SILENT_DAYS = 5              # a branch without any invoice for this many days while it sold last month
REL_DROP_PTS = 20            # branch growth this many points below the company is "underperforming"
BRANCH_CONV_DROP_PTS = 15    # a hybrid this many points below the company's conversion this month
OPEN_REQUEST_SHARE = 40      # % of the month's requests still not invoiced
SELLER_MIN_REQ_RIAL = 2e9    # 200M toman of requests before a seller's conversion is judged
SELLER_LOW_CONV = 40
DSO_HIGH = 120               # days of sales outstanding
VISITOR_DEBT_RIAL = 1e10     # 1B toman
VISITOR_DEBT_RATIO = 40      # % of the visitor's yearly sales
BRIDGE_TOP_BRANCHES = 6      # visitor-level check on the branches with the most receivables
OPEN_RETURNED_STATUSES = (6, 7, 10)  # Karamad: returned and not yet settled


# ------------------------------------------------------------------ helpers
def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _growth(cur: Any, prev: Any) -> float | None:
    c, p = _f(cur), _f(prev)
    return (c - p) / p * 100 if p > 0 else None


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{fa_number(round(value, 1))}٪"


def _signed(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{'+' if value >= 0 else '−'}{fa_number(abs(round(value, 1)))}٪"


def _fa_digits(value: Any) -> str:
    """Digits only (years, dates): «1405» → «۱۴۰۵», no thousands separator."""
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _month_name(ym: str) -> str:
    try:
        return JALALI_MONTHS[int(str(ym)[5:7]) - 1]
    except (ValueError, IndexError):
        return str(ym)


def _prev_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{y - 1}/12" if m == 1 else f"{y}/{m - 1:02d}"


def _jordinal(date_text: str) -> float:
    """Monotonic day number of a Jalali date «1405/07/21» (exact within a year; enough for gaps)."""
    y, m, d = (int(x) for x in str(date_text)[:10].split("/"))
    day_of_year = (m - 1) * 31 + d if m <= 7 else 186 + (m - 7) * 30 + d
    return y * 365.25 + day_of_year


def _day_of_year(date_text: str) -> int:
    _, m, d = (int(x) for x in str(date_text)[:10].split("/"))
    return (m - 1) * 31 + d if m <= 7 else 186 + (m - 7) * 30 + d


def _norm(name: Any) -> str:
    return " ".join(str(name or "").split("/")[0].replace("ي", "ی").replace("ك", "ک").replace("‌", " ").split())


# ------------------------------------------------------------------ sales data (shared per run)
class SalesData:
    """Sales-dashboard API reads, cached in the run context so the team reads each URL once."""

    def __init__(self, ctx: Any):
        self.ctx = ctx

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        query = urlencode([(k, v) for k, v in params.items() if v not in (None, "")], doseq=True)
        url = f"{SALES_API}{path}{'?' + query if query else ''}"

        def load() -> dict[str, Any]:
            with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=SALES_TIMEOUT_SECONDS) as r:
                return json.loads(r.read().decode("utf-8"))
        return self.ctx.legacy(f"sales:{url}", load)

    def meta(self) -> dict[str, Any]:
        return self.get("/api/meta")

    def periods(self) -> dict[str, Any]:
        f = self.meta()["file"]
        month, today = f["month"], f["today"]
        day = int(today[8:10])
        pm = _prev_month(month)
        pm_len = next((int(m["to"][8:10]) for m in f.get("months", []) if m.get("month") == pm), 30)
        md = today[5:]
        y = int(today[:4])
        return {
            "month": month, "today": today, "day": day, "prev_month": pm,
            "month_len": next((int(m["to"][8:10]) for m in f.get("months", []) if m.get("month") == month), 30),
            "prev": {"date_from": f"{pm}/01", "date_to": f"{pm}/{min(day, pm_len):02d}"},
            "ytd": {"date_from": f"{y}/01/01", "date_to": today},
            "ytd_prev": {"date_from": f"{y - 1}/01/01", "date_to": f"{y - 1}/{'12/29' if md == '12/30' else md}"},
            "year": y,
        }

    def hybrid(self, period: dict[str, str] | None = None) -> dict[str, Any]:
        # no dates = current month start → today (carries the month-end forecast)
        return self.get("/api/hybrid", vat=1, **(period or {}))

    def team(self, period: dict[str, str] | None = None) -> dict[str, Any]:
        return self.get("/api/team", vat=1, **(period or {}))

    def customers(self) -> dict[str, Any]:
        return self.get("/api/customers", vat=1)

    def monthly(self) -> dict[str, Any]:
        return self.get("/api/monthly", vat=1)


def _by_branch(resp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_norm(b.get("key")): b for b in (resp or {}).get("branches") or []}


class SalesPageAgent(PageAgent):
    """Base for the sales agents: the sales API context and the comparison-month caution."""

    @property
    def sales(self) -> SalesData:
        return SalesData(self.ctx)

    @staticmethod
    def abnormal_note(month: str) -> str:
        if month in ABNORMAL_MONTHS or month.endswith("/01"):
            return f"ماه مقایسه ({_month_name(month)} {month[:4]}) ماه عادی فروش نبوده؛ مقایسه با احتیاط خوانده شود."
        return ""


# ================================================================== 1) sales pace
class SalesPaceAgent(SalesPageAgent):
    key = "sales_pace"
    page = "عملکرد هیبرید"
    name = "Sales Pace Agent"
    role_fa = "پایش سرعت فروش هیبریدها: ماه جاری در برابر همین بازه ماه قبل و پارسال، افت نسبی و توقف فروش"
    prompt_fa = "روی افت یا رشد نسبت به کل شرکت و هیبریدهایی که فروششان متوقف شده تمرکز کن."
    tracked_metrics = {"month_net": "فروش خالص ماه تا امروز", "forecast": "پیش‌بینی پایان ماه",
                       "growth_pct": "رشد نسبت به همین بازه ماه قبل ٪", "silent_branches": "هیبرید بدون فروش"}
    primary_metric = "month_net"

    def collect(self) -> dict[str, Any]:
        s = self.sales
        p = s.periods()
        cur, prev = s.hybrid(), s.hybrid(p["prev"])
        ytd, ytd_prev = s.hybrid(p["ytd"]), s.hybrid(p["ytd_prev"])
        months = {m["month"]: m for m in s.monthly().get("months") or []}
        prev_full = _f((months.get(p["prev_month"]) or {}).get("net"))
        overall = _growth(cur["kpis"]["net"], prev["kpis"]["net"])
        cur_b, prev_b = _by_branch(cur), _by_branch(prev)
        today_ord = _jordinal(p["today"])
        rows, silent = [], []
        for key in sorted(set(cur_b) | set(prev_b)):
            c, pv = cur_b.get(key) or {}, prev_b.get(key) or {}
            name = c.get("label") or pv.get("label") or key
            g = _growth(c.get("net"), pv.get("net")) if _f(pv.get("net")) >= MIN_BASE_RIAL else None
            last = c.get("last_date")
            gap = int(today_ord - _jordinal(last)) if last else None
            rows.append({"name": name, "net": _f(c.get("net")), "prev": _f(pv.get("net")), "growth": g,
                         "rel": None if g is None or overall is None else g - overall,
                         "forecast": _f(c.get("forecast")), "last_date": last, "gap_days": gap,
                         "supervisor": c.get("supervisor") or pv.get("supervisor")})
            if _f(pv.get("net")) >= MIN_BASE_RIAL and (gap is None or gap >= SILENT_DAYS):
                silent.append(rows[-1])
        k = cur["kpis"]
        metrics = {
            "month": p["month"], "prev_month": p["prev_month"], "today": p["today"],
            "month_net": _f(k.get("net")), "prev_net": _f(prev["kpis"].get("net")), "growth_pct": overall,
            "forecast": _f(k.get("forecast")), "prev_month_full": prev_full,
            "ytd_net": _f(ytd["kpis"].get("net")), "ytd_prev_net": _f(ytd_prev["kpis"].get("net")),
            "ytd_growth_pct": _growth(ytd["kpis"].get("net"), ytd_prev["kpis"].get("net")),
            "active_branches": sum(1 for r in rows if r["net"] > 0), "silent_branches": len(silent),
            "year": p["year"],
        }
        return {"metrics": metrics, "branches": rows, "silent": silent}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        month, prev_name = _month_name(m["month"]), _month_name(m["prev_month"])
        caution = self.abnormal_note(m["prev_month"])
        g = m["growth_pct"]
        rows = data["branches"]
        alerts, actions, good = [], [], []

        if g is not None and g <= -15:
            drops = sorted((r for r in rows if r["prev"] > 0), key=lambda r: r["net"] - r["prev"])[:3]
            alerts.append(alert(
                "sales_month_drop", "critical" if g <= -30 else "high",
                f"فروش {month} تا امروز {_pct(abs(g))} کمتر از همین بازه {prev_name} است",
                [f"{toman(m['month_net'])} در برابر {toman(m['prev_net'])} در همین تعداد روز.", caution],
                "علت افت (موجودی، قیمت، اعتبار مشتری، فصل) با مدیر فروش و سرپرست‌ها بررسی شود.",
                evidence=[{"label": r["name"], "value": f"{toman(r['net'])} از {toman(r['prev'])}"} for r in drops],
                metric=m["month_net"]))
            actions.append(action("جلسه بررسی افت فروش ماه با سرپرست‌ها",
                                  f"فروش کل {_pct(abs(g))} کمتر از همین بازه {prev_name}.", "مدیر فروش", "high", "این هفته",
                                  "پیدا شدن علت افت قبل از پایان ماه"))

        for r in data["silent"][:3]:
            alerts.append(alert(
                "branch_silent", "high", f"{r['name']}: {fa_number(r['gap_days']) + ' روز' if r['gap_days'] is not None else 'این ماه'} بدون فاکتور فروش",
                [f"در همین بازه {prev_name} {toman(r['prev'])} فروش داشته است.",
                 f"آخرین فاکتور: {r['last_date'] or 'این ماه فاکتوری ندارد'}."],
                "با سرپرست هیبرید تماس گرفته و علت توقف (موجودی، مشکل سیستم، اعتبار) روشن شود.",
                entity_ref=r["name"], metric=r["prev"]))
            actions.append(action(f"پیگیری توقف فروش {r['name']}", "هیبرید با سابقه فروش، چند روز فاکتور نزده است.",
                                  r.get("supervisor") or "سرپرست هیبرید", "high", "امروز"))

        silent_names = {r["name"] for r in data["silent"]}
        # returns larger than sales: a different problem than a slowdown
        for r in [r for r in rows if r["net"] < 0 and r["name"] not in silent_names][:2]:
            alerts.append(alert(
                "branch_net_negative", "high", f"{r['name']}: برگشت از فروش بیشتر از فروش این ماه",
                [f"فروش خالص {month} تا امروز {toman(r['net'])} (منفی)؛ در همین بازه {prev_name} {toman(r['prev'])}."],
                "علت برگشتی‌ها (کیفیت، تاریخ انقضا، اختلاف قیمت، فاکتور اشتباه) با سرپرست بررسی شود.",
                entity_ref=r["name"], metric=r["net"]))
            silent_names.add(r["name"])
        under = sorted((r for r in rows if r["rel"] is not None and r["rel"] <= -REL_DROP_PTS and r["name"] not in silent_names),
                       key=lambda r: r["rel"])[:3]
        for r in under:
            alerts.append(alert(
                "branch_underperform", "high" if r["rel"] <= -40 else "medium",
                f"{r['name']}: فروش {_signed(r['growth'])} در حالی که کل شرکت {_signed(g)}",
                [f"{toman(r['net'])} در برابر {toman(r['prev'])} در همین بازه {prev_name}.", caution],
                "عملکرد ویزیتورها و مشتریان اصلی این هیبرید بررسی شود.",
                entity_ref=r["name"], evidence=[{"label": "پیش‌بینی پایان ماه", "value": toman(r["forecast"])}],
                metric=r["net"]))
        if under:
            actions.append(action(f"بررسی افت نسبی {under[0]['name']}", "افتش از روند کل شرکت بیشتر است.",
                                  "مدیر فروش", "medium", "این هفته"))

        if m["ytd_growth_pct"] is not None and m["ytd_growth_pct"] <= -10:
            alerts.append(alert("ytd_decline", "high", f"فروش {_fa_digits(m['year'])} تا امروز {_pct(abs(m['ytd_growth_pct']))} کمتر از همین بازه پارسال",
                                [f"{toman(m['ytd_net'])} در برابر {toman(m['ytd_prev_net'])}."],
                                "روند سالانه در جلسه مدیریت بررسی شود.", metric=m["ytd_net"]))
        elif m["ytd_growth_pct"] is not None and m["ytd_growth_pct"] > 0:
            good.append(f"فروش امسال تا امروز {_signed(m['ytd_growth_pct'])} نسبت به همین بازه پارسال ({toman(m['ytd_net'])}).")
        for r in sorted((r for r in rows if r["rel"] is not None and r["rel"] >= 15 and r["net"] >= MIN_BASE_RIAL),
                        key=lambda r: -r["rel"])[:2]:
            good.append(f"{r['name']} {_signed(r['growth'])} نسبت به همین بازه {prev_name}، جلوتر از روند کل شرکت.")

        vs_last_month = _growth(m["forecast"], m["prev_month_full"])
        return {
            "headline": f"فروش {month} تا امروز {toman(m['month_net'])}؛ {_signed(g)} نسبت به همین بازه {prev_name}.",
            "summary": (f"پیش‌بینی پایان ماه {toman(m['forecast'])}"
                        + (f" ({_signed(vs_last_month)} نسبت به کل {prev_name})" if vs_last_month is not None else "")
                        + f". فروش {_fa_digits(m['year'])} تا امروز {toman(m['ytd_net'])} ({_signed(m['ytd_growth_pct'])} نسبت به همین بازه پارسال). "
                        + f"{fa_number(m['active_branches'])} هیبرید این ماه فروش داشته‌اند"
                        + (f" و {fa_number(m['silent_branches'])} هیبرید فروششان متوقف شده است." if m["silent_branches"] else ".")),
            "good_signals": good,
            "risks": [a["title"] for a in alerts],
            "recommended_actions": actions,
            "next_best_action": actions[0]["action"] if actions else "روند روزانه فروش هیبریدها پایش شود.",
            "alerts": alerts,
            "predictions": [
                prediction("forecast", f"فروش خالص پایان {month}", "پایان ماه", m["forecast"], "low" if caution else "medium",
                           "میانگین فروش روزانه همین ماه × روزهای کاری ماه (داشبورد فروش)"),
                prediction("forecast_vs_last_month", f"پیش‌بینی پایان {month} نسبت به کل {prev_name}", "پایان ماه",
                           vs_last_month, "low", "پیش‌بینی پایان ماه تقسیم بر فروش کل ماه قبل",
                           unit="percent", display=_signed(vs_last_month)),
            ],
        }


# ================================================================== 2) request → invoice conversion
class RequestConversionAgent(SalesPageAgent):
    key = "sales_requests"
    page = "تبدیل درخواست به فاکتور"
    name = "Request Conversion Agent"
    role_fa = "پایش تبدیل درخواست (سفارش) به فاکتور: افت نرخ تبدیل، سفارش‌های معطل و فروشنده‌های کم‌تبدیل"
    prompt_fa = "روی سفارش‌هایی که فاکتور نشده‌اند و افت نرخ تبدیل تمرکز کن؛ این‌ها فروش ازدست‌رفته یا معطل هستند."
    tracked_metrics = {"conversion_pct": "نرخ تبدیل درخواست ٪", "open_amount": "درخواست فاکتورنشده",
                       "requests": "درخواست ماه"}
    primary_metric = "conversion_pct"
    primary_unit = "percent"

    def collect(self) -> dict[str, Any]:
        s = self.sales
        p = s.periods()
        cur, prev = s.hybrid(), s.hybrid(p["prev"])
        sellers = s.team().get("sellers") or []
        k, kp = cur["kpis"], prev["kpis"]
        conv = _f(k.get("req_conv")) * 100 if k.get("req_conv") is not None else None
        conv_prev = _f(kp.get("req_conv")) * 100 if kp.get("req_conv") is not None else None
        open_amount = max(0.0, _f(k.get("req_net")) - _f(k.get("req_net_done")))
        prev_b = _by_branch(prev)
        branches = []
        for b in cur.get("branches") or []:
            pb = prev_b.get(_norm(b.get("key"))) or {}
            c = _f(b.get("req_conv")) * 100 if b.get("req_conv") is not None else None
            cp = _f(pb.get("req_conv")) * 100 if pb.get("req_conv") is not None else None
            branches.append({"name": b.get("label") or b.get("key"), "requests": _f(b.get("req_net")), "conv": c, "conv_prev": cp,
                             "open": _f(b.get("req_net")) * (1 - (c or 0) / 100) if c is not None else 0.0,
                             "supervisor": b.get("supervisor")})
        low_sellers = sorted(
            ({"name": x.get("label"), "branch": x.get("branch"), "requests": _f(x.get("req_net")),
              "conv": _f(x.get("req_conv")) * 100} for x in sellers
             if _f(x.get("req_net")) >= SELLER_MIN_REQ_RIAL and x.get("req_conv") is not None
             and _f(x.get("req_conv")) * 100 < SELLER_LOW_CONV),
            key=lambda x: -x["requests"])
        metrics = {
            "month": p["month"], "prev_month": p["prev_month"], "requests": _f(k.get("req_net")),
            "requests_count": int(_f(k.get("req_docs"))), "done_count": int(_f(k.get("req_docs_done"))),
            "conversion_pct": conv, "prev_conversion_pct": conv_prev,
            "conversion_change_pts": None if conv is None or conv_prev is None else conv - conv_prev,
            "open_amount": open_amount, "open_share_pct": open_amount / _f(k.get("req_net")) * 100 if _f(k.get("req_net")) else 0.0,
            "request_forecast": _f(k.get("req_forecast")), "low_conversion_sellers": len(low_sellers),
        }
        return {"metrics": metrics, "branches": branches, "low_sellers": low_sellers}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        month, prev_name = _month_name(m["month"]), _month_name(m["prev_month"])
        alerts, actions, good = [], [], []
        # Requests of past months have all been settled by now (their conversion reads ~100%), so this
        # month is NOT compared with last month; each hybrid is compared with the company this month,
        # and the run-to-run change shows in the agent's memory (tracked conversion_pct).
        company = m["conversion_pct"]
        lagging = sorted((b for b in data["branches"] if b["requests"] >= MIN_BASE_RIAL and b["conv"] is not None
                          and company is not None and b["conv"] <= company - BRANCH_CONV_DROP_PTS),
                         key=lambda b: -b["open"])[:3]
        for b in lagging:
            alerts.append(alert(
                "branch_low_conversion", "high" if b["conv"] <= company - 30 else "medium",
                f"{b['name']}: نرخ تبدیل {_pct(b['conv'])} در برابر {_pct(company)} کل شرکت",
                [f"درخواست این ماه {toman(b['requests'])}؛ حدود {toman(b['open'])} هنوز فاکتور نشده."],
                "سفارش‌های باز این هیبرید یکی‌یکی بررسی و علت معطل‌ماندن (موجودی، اعتبار، تأیید) ثبت شود.",
                entity_ref=b["name"], metric=b["conv"]))
        if lagging:
            actions.append(action(f"بررسی سفارش‌های معطل {lagging[0]['name']}",
                                  f"نرخ تبدیلش {_pct(lagging[0]['conv'])} است، خیلی کمتر از کل شرکت.",
                                  lagging[0].get("supervisor") or "سرپرست هیبرید", "high", "این هفته"))
        for b in sorted((b for b in data["branches"] if b["requests"] >= MIN_BASE_RIAL and b["conv"] is not None and b["conv"] >= 90),
                        key=lambda b: -b["requests"])[:2]:
            good.append(f"{b['name']}: {_pct(b['conv'])} درخواست‌های این ماه فاکتور شده است.")

        if m["open_share_pct"] >= OPEN_REQUEST_SHARE and m["open_amount"] >= 1e10:
            top = sorted(data["branches"], key=lambda b: -b["open"])[:3]
            alerts.append(alert(
                "open_requests", "medium", f"{toman(m['open_amount'])} از درخواست‌های {month} هنوز فاکتور نشده",
                [f"{_pct(m['open_share_pct'])} درخواست‌های ماه؛ {fa_number(m['requests_count'] - m['done_count'])} سند درخواست باز."],
                "سفارش‌های باز با انبار و مالی تعیین تکلیف شوند تا فروش ماه از دست نرود.",
                evidence=[{"label": b["name"], "value": toman(b["open"])} for b in top], metric=m["open_amount"]))
            actions.append(action("تعیین تکلیف سفارش‌های فاکتورنشده", f"{toman(m['open_amount'])} سفارش معطل است.",
                                  "مدیر فروش + انبار", "high", "تا پایان هفته", "تبدیل سفارش معطل به فروش همین ماه"))

        if data["low_sellers"]:
            alerts.append(alert(
                "seller_low_conversion", "medium",
                f"{fa_number(len(data['low_sellers']))} فروشنده با درخواست زیاد و نرخ تبدیل زیر {fa_number(SELLER_LOW_CONV)}٪",
                ["درخواست زیاد ولی فاکتور کم: یا سفارش‌ها بی‌پشتوانه‌اند یا گرفتار موجودی/اعتبار شده‌اند."],
                "با سرپرست هر فروشنده علت بررسی شود.",
                evidence=[{"label": f"{x['name']} ({x['branch']})", "value": f"{toman(x['requests'])} · {_pct(x['conv'])}"}
                          for x in data["low_sellers"][:5]]))
            actions.append(action("بررسی فروشنده‌های کم‌تبدیل با سرپرست‌ها", "درخواست زیاد ولی فاکتور کم.",
                                  "سرپرست‌ها", "medium", "این هفته"))

        # last month's requests ended up this converted, so the open ones are expected to follow
        expected = m["open_amount"] * ((m["prev_conversion_pct"] or m["conversion_pct"] or 0) / 100)
        return {
            "headline": f"نرخ تبدیل درخواست به فاکتور در {month} تا امروز: {_pct(m['conversion_pct'])}؛ "
                        f"{toman(m['open_amount'])} سفارش هنوز فاکتور نشده.",
            "summary": f"{toman(m['requests'])} درخواست در {fa_number(m['requests_count'])} سند ثبت شده؛ "
                       f"{toman(m['open_amount'])} ({_pct(m['open_share_pct'])}) هنوز فاکتور نشده است.",
            "good_signals": good,
            "risks": [a["title"] for a in alerts],
            "recommended_actions": actions,
            "next_best_action": actions[0]["action"] if actions else "نرخ تبدیل روزانه پایش شود.",
            "alerts": alerts,
            "predictions": [
                prediction("expected_from_open", "فاکتور قابل انتظار از درخواست‌های باز", "چند روز آینده", expected, "low",
                           f"مبلغ درخواست‌های باز × سهمی از درخواست‌های {prev_name} که در نهایت فاکتور شد ({_pct(m['prev_conversion_pct'])})"),
                prediction("request_forecast", f"درخواست پیش‌بینی‌شده پایان {month}", "پایان ماه", m["request_forecast"],
                           "medium", "میانگین درخواست روزانه همین ماه (داشبورد فروش)"),
            ],
        }


# ================================================================== 3) sales ↔ finance bridge
class SalesFinanceBridgeAgent(SalesPageAgent):
    key = "sales_finance_bridge"
    page = "پرونده هیبریدها"
    name = "Sales–Finance Bridge Agent"
    role_fa = "پل فروش و مالی: فروش به مشتری دارای چک برگشتی، رشد فروش با وصول ضعیف و ویزیتورهای پربدهی"
    prompt_fa = "فروشی که پولش برنمی‌گردد را برجسته کن؛ مخاطب هم مدیر فروش است هم مدیر مالی."
    tracked_metrics = {"risky_customers": "مشتری دارای چک برگشتی با خرید/سفارش این ماه",
                       "risky_month_amount": "خرید و سفارش این ماه مشتریان دارای چک برگشتی",
                       "dso_days": "دوره وصول هیبریدها (روز)", "hybrid_debt": "مطالبات باز هیبریدها"}
    primary_metric = "risky_month_amount"

    def _returned_by_customer(self) -> dict[str, dict[str, Any]]:
        def load():
            from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
            statuses = ",".join(str(s) for s in OPEN_RETURNED_STATUSES)
            with get_karamad_sqlserver_engine().connect() as c:
                rows = c.execute(text(f"""
                    SELECT cu.[Code] AS code, MIN(cu.[Name]) AS name, COUNT(*) AS n, SUM(d.[Price]) AS amount, MIN(d.[DueDate]) AS oldest
                    FROM dbo.[tblChequeD] d
                    OUTER APPLY (SELECT TOP (1) c.[Code], c.[Name] FROM dbo.[tblCustomer] c WHERE c.[DLRef] = d.[DLRef] ORDER BY c.[ID]) cu
                    WHERE d.[StatusRef] IN ({statuses}) AND cu.[Code] IS NOT NULL
                    GROUP BY cu.[Code]""")).mappings().all()
            return {str(r["code"]).strip(): {"name": str(r["name"] or "").strip(), "count": int(r["n"] or 0),
                                             "amount": _f(r["amount"]), "oldest": r["oldest"]} for r in rows}
        return self.ctx.legacy("sales:returned_by_customer", load)

    def collect(self) -> dict[str, Any]:
        from app.services.karamad_sales_network_service import KaramadSalesNetworkService

        s = self.sales
        p = s.periods()
        network = self.ctx.legacy("sales:network", lambda: KaramadSalesNetworkService().overview())
        cur, ytd, ytd_prev = s.hybrid(), s.hybrid(p["ytd"]), s.hybrid(p["ytd_prev"])
        cur_b, ytd_b, ytdp_b = _by_branch(cur), _by_branch(ytd), _by_branch(ytd_prev)
        doy = _day_of_year(p["today"])

        # 1) customers with unsettled returned cheques who bought or ordered this month
        returned = self._returned_by_customer()
        risky = []
        for c in s.customers().get("customers") or []:
            r = returned.get(str(c.get("key")).strip())
            month_amount = max(_f(c.get("net")), 0) + max(_f(c.get("req_net")), 0)
            if r and month_amount > 0:
                risky.append({"code": c.get("key"), "name": c.get("label") or r["name"], "branch": c.get("branch"),
                              "seller": c.get("seller"), "returned": r["amount"], "returned_count": r["count"],
                              "net": _f(c.get("net")), "requests": _f(c.get("req_net")), "month_amount": month_amount})
        risky.sort(key=lambda x: -(x["month_amount"] + x["returned"]))

        # 2) branches: receivables vs sales growth
        branches = []
        for b in network.get("branches") or []:
            k = _norm(b.get("branch_name"))
            debt = _f((b.get("debt") or {}).get("open_account_receivable_rial"))
            year_sales = _f(b.get("current_year_sales_rial"))
            dso = debt / (year_sales / doy) if year_sales > 0 and doy else None
            yc, yp = _f((ytd_b.get(k) or {}).get("net")), _f((ytdp_b.get(k) or {}).get("net"))
            branches.append({"id": b.get("branch_id"), "name": b.get("branch_name"), "debt": debt, "dso": dso,
                             "ytd_growth": _growth(yc, yp) if yp >= MIN_BASE_RIAL else None,
                             "month_net": _f((cur_b.get(k) or {}).get("net"))})
        total_debt = sum(b["debt"] for b in branches)
        total_year_sales = _f((network.get("summary") or {}).get("current_year_sales_rial"))

        # 3) visitors with heavy receivables (only the branches with the most receivables: files are heavy)
        heavy = []
        for b in sorted(branches, key=lambda b: -b["debt"])[:BRIDGE_TOP_BRANCHES]:
            try:
                file = KaramadSalesNetworkService().branch_file(int(b["id"]))
            except Exception:  # noqa: BLE001 — one branch failing must not stop the agent
                continue
            for v in file.get("visitors") or []:
                debt = _f((v.get("debt") or {}).get("open_account_receivable_rial"))
                ys = _f(v.get("current_year_sales_rial"))
                ratio = debt / ys * 100 if ys > 0 else None
                if debt >= VISITOR_DEBT_RIAL and (ratio is None or ratio >= VISITOR_DEBT_RATIO):
                    heavy.append({"name": _norm(v.get("visitor_name")), "branch": b["name"], "debt": debt,
                                  "ratio": ratio, "debtors": (v.get("debt") or {}).get("debtor_customer_count")})
        heavy.sort(key=lambda x: -x["debt"])

        metrics = {
            "month": p["month"], "risky_customers": len(risky),
            "risky_month_amount": sum(x["month_amount"] for x in risky),
            "risky_returned_amount": sum(x["returned"] for x in risky),
            "hybrid_debt": total_debt,
            "dso_days": total_debt / (total_year_sales / doy) if total_year_sales > 0 and doy else None,
            "high_dso_branches": sum(1 for b in branches if b["dso"] is not None and b["dso"] > DSO_HIGH),
            "heavy_visitors": len(heavy), "day": p["day"], "month_len": p["month_len"],
        }
        return {"metrics": metrics, "risky": risky, "branches": branches, "heavy": heavy}

    def rules(self, data, memory, deltas):
        m = data["metrics"]
        month = _month_name(m["month"])
        alerts, actions, good = [], [], []
        risky = data["risky"]
        if risky:
            alerts.append(alert(
                "sales_to_returned_cheque_customers", "critical" if m["risky_month_amount"] >= 1e10 else "high",
                f"{fa_number(len(risky))} مشتری با چک برگشتی تسویه‌نشده در {month} خرید یا سفارش داشته‌اند",
                [f"خرید و سفارش این ماهشان {toman(m['risky_month_amount'])}؛ چک برگشتی بازشان {toman(m['risky_returned_amount'])}.",
                 "فروش اعتباری به این مشتریان، بدهی تازه روی بدهی وصول‌نشده می‌سازد."],
                "ارسال بار به این مشتریان تا تسویه چک برگشتی متوقف شود یا فقط با تأیید مدیر مالی و دریافت نقدی انجام شود.",
                evidence=[{"label": f"{x['name']} ({x['branch']})",
                           "value": f"این ماه {toman(x['month_amount'])} · برگشتی {toman(x['returned'])}"} for x in risky[:5]],
                metric=m["risky_month_amount"]))
            actions.append(action("توقف فروش اعتباری به مشتریان دارای چک برگشتی",
                                  f"{fa_number(len(risky))} مشتری با چک برگشتی باز این ماه خرید/سفارش داشته‌اند.",
                                  "مدیر فروش + مدیر مالی", "high", "امروز", "جلوگیری از بدهی جدید وصول‌نشده"))
        else:
            good.append("هیچ مشتری دارای چک برگشتی تسویه‌نشده این ماه خرید یا سفارش نداشته است.")

        weak = sorted((b for b in data["branches"] if b["dso"] is not None and b["dso"] > DSO_HIGH),
                      key=lambda b: -b["dso"])
        for b in weak[:3]:
            growing = b["ytd_growth"] is not None and b["ytd_growth"] > 0
            alerts.append(alert(
                "growth_with_weak_collection" if growing else "high_dso", "high" if growing else "medium",
                (f"{b['name']}: فروش امسال {_signed(b['ytd_growth'])} ولی وصول {fa_number(round(b['dso']))} روز عقب است"
                 if growing else f"{b['name']}: دوره وصول {fa_number(round(b['dso']))} روز"),
                [f"مطالبات باز {toman(b['debt'])}؛ معادل {fa_number(round(b['dso']))} روز فروش امسال (حد: {fa_number(DSO_HIGH)} روز)."],
                "سقف اعتبار و شرایط پرداخت مشتریان این هیبرید بازبینی و وصول در اولویت قرار گیرد.",
                entity_ref=b["name"], metric=b["dso"]))
        if weak:
            actions.append(action(f"برنامه وصول {weak[0]['name']}", "دوره وصول از حد مجاز گذشته است.",
                                  "مدیر وصول", "high", "این هفته", "کاهش مطالبات و ریسک نقدینگی"))

        heavy = data["heavy"]
        if heavy:
            alerts.append(alert(
                "visitor_debt_heavy", "medium",
                f"{fa_number(len(heavy))} ویزیتور با مطالبات سنگین نسبت به فروششان",
                [f"مطالبات هر کدام بیش از {toman(VISITOR_DEBT_RIAL)} و حداقل {fa_number(VISITOR_DEBT_RATIO)}٪ فروش امسالشان."],
                "فروش اعتباری این ویزیتورها تا کاهش مطالبات محدود و وصول به عملکردشان گره زده شود.",
                evidence=[{"label": f"{x['name']} ({x['branch']})", "value": f"{toman(x['debt'])} · {_pct(x['ratio'])} فروش"}
                          for x in heavy[:5]]))

        projected = m["risky_month_amount"] / max(m["day"], 1) * m["month_len"] if risky else 0.0
        return {
            "headline": (f"{fa_number(m['risky_customers'])} مشتری دارای چک برگشتی در {month} خرید یا سفارش داشته‌اند؛ "
                         f"دوره وصول هیبریدها {fa_number(round(m['dso_days'])) if m['dso_days'] else '—'} روز."),
            "summary": f"مطالبات باز هیبریدها {toman(m['hybrid_debt'])}؛ {fa_number(m['high_dso_branches'])} هیبرید دوره وصول بالای "
                       f"{fa_number(DSO_HIGH)} روز دارند و {fa_number(m['heavy_visitors'])} ویزیتور مطالبات سنگین دارند.",
            "good_signals": good,
            "risks": [a["title"] for a in alerts],
            "recommended_actions": actions,
            "next_best_action": actions[0]["action"] if actions else "پایش روزانه فروش به مشتریان پرریسک ادامه یابد.",
            "alerts": alerts,
            "predictions": [
                prediction("risky_month_projected", f"خرید و سفارش مشتریان دارای چک برگشتی تا پایان {month}", "پایان ماه",
                           projected, "low", "اگر روند همین ماه ادامه یابد (روزانه × روزهای ماه)"),
            ],
        }


SALES_AGENT_CLASSES: list[type[PageAgent]] = [SalesPaceAgent, RequestConversionAgent, SalesFinanceBridgeAgent]


# ================================================================== 4) sales manager
class SalesManagerAgent(SalesPageAgent):
    key = "sales_manager"
    page = "نمای مدیر — فروش"
    name = "Sales Manager Agent"
    role_fa = "هماهنگ‌کننده Agentهای فروش: جمع‌بندی، هشدارهای مهم و سه اقدام اولویت‌دار فروش"
    prompt_fa = "گزارش را برای مدیرعامل بنویس: وضعیت فروش، مهم‌ترین ریسک و سه کاری که این هفته باید انجام شود."
    tracked_metrics = {"critical_alerts": "هشدار بحرانی فروش", "month_net": "فروش خالص ماه تا امروز",
                       "conversion_pct": "نرخ تبدیل درخواست ٪", "risky_customers": "مشتری دارای چک برگشتی با خرید"}
    primary_metric = "critical_alerts"
    primary_unit = "count"

    def run(self, trigger: str = "manual") -> dict[str, Any]:
        self._trigger = trigger
        return super().run(trigger)

    def collect(self) -> dict[str, Any]:
        trigger = getattr(self, "_trigger", "manual")

        def run_one(cls):
            return cls.key, cls(self.store, self.ctx).run(trigger)
        with ThreadPoolExecutor(max_workers=len(SALES_AGENT_CLASSES)) as pool:
            team = dict(pool.map(run_one, SALES_AGENT_CLASSES))
        self.team = team
        mt = lambda key: (team.get(key) or {}).get("metrics") or {}  # noqa: E731
        alerts = [a for r in team.values() for a in (r.get("alerts") or [])]
        metrics = {
            "critical_alerts": sum(1 for a in alerts if a["level"] == "critical"),
            "high_alerts": sum(1 for a in alerts if a["level"] == "high"),
            "agents_ok": sum(1 for r in team.values() if r.get("status") == "success"), "agents_total": len(team),
            "month_net": mt("sales_pace").get("month_net"), "forecast": mt("sales_pace").get("forecast"),
            "growth_pct": mt("sales_pace").get("growth_pct"), "conversion_pct": mt("sales_requests").get("conversion_pct"),
            "open_amount": mt("sales_requests").get("open_amount"), "risky_customers": mt("sales_finance_bridge").get("risky_customers"),
            "dso_days": mt("sales_finance_bridge").get("dso_days"), "month": mt("sales_pace").get("month"),
        }
        return {"metrics": metrics, "team": team}

    def rules(self, data, memory, deltas):
        m, team = data["metrics"], data["team"]
        failed = [r.get("name") for r in team.values() if r.get("status") != "success"]
        ranked = sorted(((r.get("page"), a) for r in team.values() for a in (r.get("alerts") or [])
                         if a["level"] in {"critical", "high"} and a.get("status") != "dismissed"),
                        key=lambda item: (LEVEL_ORDER.get(item[1]["level"], 9), -(item[1].get("consecutive_runs") or 1)))
        alerts = [alert(f"team:{a['type']}", a["level"], f"{page}: {a['title']}", a.get("why") or [], a.get("action") or "",
                        entity_ref=a.get("alert_key"), evidence=a.get("evidence")) for page, a in ranked[:6]]
        if failed:
            alerts.append(alert("sales_agent_failed", "medium", f"{fa_number(len(failed))} Agent فروش اجرا نشد",
                                [", ".join(str(x) for x in failed), "احتمالاً داشبورد فروش (sales-dashboard) در دسترس نبوده است."],
                                "سرور داشبورد فروش روشن و دوباره اجرا شود."))
        priority = {"high": 0, "medium": 1, "low": 2}
        actions = sorted((a for r in team.values() for a in ((r.get("analysis") or {}).get("recommended_actions") or [])),
                         key=lambda a: priority.get(a.get("priority"), 3))[:3]
        predictions = [{**p, "label": f"{r.get('page')} — {p['label']}"} for r in team.values()
                       for p in (r.get("predictions") or [])[:1]]
        good = [g for r in team.values() for g in ((r.get("analysis") or {}).get("good_signals") or [])][:4]
        month = _month_name(m["month"]) if m.get("month") else "این ماه"
        parts = []
        if m.get("month_net") is not None:
            parts.append(f"فروش {month} تا امروز {toman(m['month_net'])} ({_signed(m.get('growth_pct'))} نسبت به همین بازه ماه قبل)")
        if m.get("conversion_pct") is not None:
            parts.append(f"نرخ تبدیل درخواست {_pct(m['conversion_pct'])}")
        if m.get("risky_customers"):
            parts.append(f"{fa_number(m['risky_customers'])} مشتری دارای چک برگشتی خرید کرده‌اند")
        return {
            "headline": "؛ ".join(parts) + "." if parts else "Agentهای فروش داده‌ای برنگرداندند.",
            "summary": " ".join(str((r.get("analysis") or {}).get("headline") or "") for r in team.values()).strip(),
            "good_signals": good,
            "risks": [a["title"] for a in alerts],
            "recommended_actions": actions,
            "next_best_action": actions[0]["action"] if actions else "پایش روزانه فروش ادامه یابد.",
            "alerts": alerts,
            "predictions": predictions[:4],
        }
