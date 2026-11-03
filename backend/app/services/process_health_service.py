"""فرصت‌های بهبود روندها (نمای مدیر) — جاهایی که داده نشان می‌دهد کار کندتر از انتظار جلو می‌رود.

فقط سه ماه اخیر (۹۰ روز) بررسی می‌شود و فقط مواردی آمده که از خود SQL قطعی است (نه حدس):
- فاکتور برگشت از فروش در راهکاران که کالایش به انبار برگشته (سند انبار دارد) ولی هنوز «پیش‌نویس» است (Status = 1)؛
- دریافت نقد/حواله مشتری در کارآمد که سند حسابداری ندارد (VoucherRef خالی؛ همان گزارش V174)؛
- فاکتورهای ۹۰ روز اخیر که حواله خروج ندارند و فاصله فاکتور تا خروج هر شعبه (خط زمان توزیع بار)؛
- فاصله تاریخ سند تا تاریخ ثبتش در راهکاران (CreationDate − Date)، ماه به ماه؛
- آخرین دوره محاسبه بهای تمام‌شده در راهکاران (CAC3.CalcPeriod).
لحن متن‌ها عمداً ملایم است: «فرصت بهبود» و «پیشنهاد»، نه سرزنش.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.utils.jalali import format_jalali_date

CACHE_SECONDS = 600
WINDOW_DAYS = 90
_lock = threading.Lock()
_state: dict[str, Any] = {"at": 0.0, "data": None, "running": False, "error": ""}

MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def _rahkaran():
    from app.database.sqlserver import get_sqlserver_engine
    return get_sqlserver_engine()


def _day(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else None


def _jmonth(d: date) -> str:
    j = format_jalali_date(d)  # 1405/06/02
    return MONTHS[int(j[5:7]) - 1]


def _since() -> date:
    return date.today() - timedelta(days=WINDOW_DAYS)


def _severity(score: float) -> str:
    return "critical" if score >= 2 else "high" if score >= 1 else "watch"


# ------------------------------------------------------------------ ۱. برگشت از فروش در انتظار قطعی شدن
def return_drafts(c, since: date) -> dict[str, Any]:
    rows = c.execute(text("""
        SELECT r.Number, r.Date, r.NetPrice, r.Description, p.FullName AS Customer
        FROM SLS3.ReturnInvoice r
        LEFT JOIN SLS3.Customer cu ON cu.CustomerID = r.CustomerRef
        LEFT JOIN GNR3.Party p ON p.PartyID = cu.PartyRef
        WHERE r.Status = 1 AND r.Date >= :since
    """), {"since": since}).mappings().all()
    final = c.execute(text("SELECT COUNT(*) FROM SLS3.ReturnInvoice WHERE Status IN (2, 11) AND Date >= :since"),
                      {"since": since}).first()
    today = date.today()
    items = [{"date": _day(r["Date"]), "rial": float(r["NetPrice"] or 0),
              "customer": (r["Customer"] or "—").strip(), "stocked": "سند انبار" in (r["Description"] or "")} for r in rows]
    stocked = sum(1 for x in items if x["stocked"])
    amount = sum(x["rial"] for x in items)
    oldest = max(((today - x["date"]).days for x in items if x["date"]), default=0)
    by_month: dict[str, float] = {}
    for k in range(0, WINDOW_DAYS + 1, 10):  # همه ماه‌های بازه، حتی ماهی که پیش‌نویسی ندارد
        by_month.setdefault(_jmonth(since + timedelta(days=k)), 0.0)
    by_month.setdefault(_jmonth(today), 0.0)
    by_cust: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    for x in sorted(items, key=lambda x: x["date"] or today):
        by_month[_jmonth(x["date"])] += x["rial"]
        by_cust[x["customer"]][0] += 1
        by_cust[x["customer"]][1] += x["rial"]
    done = int(final[0] or 0)
    share = 100 * len(items) / max(1, len(items) + done)
    return {
        "key": "return_drafts", "domain": "فروش و مالی", "system": "راهکاران",
        "title": "برگشتی‌هایی که منتظر قطعی شدن‌اند",
        "headline": f"{len(items):,} فاکتور برگشت هنوز در مرحله پیش‌نویس",
        "count": len(items), "amount_rial": amount, "oldest_days": oldest,
        "severity": _severity((amount >= 1e11) + (share > 50)),
        "stat": {"value": round(share), "unit": "٪", "label": "از برگشتی‌های سه ماه اخیر هنوز قطعی نشده"},
        "evidence": f"برای {stocked:,} مورد سند انبار ثبت شده، یعنی کالا به انبار رسیده و فقط قدم آخر، قطعی کردن فاکتور برگشت، مانده است. "
                    f"در همین سه ماه {done:,} برگشتی قطعی شده.",
        "impact": "تا این فاکتورها قطعی نشوند، مانده این مشتریان و فروش خالص کمی بیشتر از واقعیت دیده می‌شود و پیگیری وصول ممکن است روی عدد بالاتری انجام شود.",
        "fix": "شاید کمک کند فاکتورهای برگشتی که سند انبار دارند در همان هفته قطعی شوند و فهرست پیش‌نویس‌های بالای ۷ روز هفته‌ای یک بار مرور شود.",
        "series": [{"label": k, "value": v} for k, v in by_month.items()],
        "series_label": "مبلغ پیش‌نویس به تفکیک ماه برگشت",
        "top": [{"name": k, "value": v[1], "sub": f"{v[0]:,} فاکتور"} for k, v in sorted(by_cust.items(), key=lambda kv: -kv[1][1])[:6]],
        "go": "/finance/customers",
    }


# ------------------------------------------------------------------ ۲. دریافت‌هایی که هنوز سند نخورده‌اند
def unposted_payments() -> dict[str, Any]:
    from app.services.karamad_unposted_payment_service import KaramadUnpostedPaymentService
    u = KaramadUnpostedPaymentService().build()
    pays = [p for p in u["payments"] if (p["days_waiting"] or 0) <= WINDOW_DAYS]
    debtor = {c["dl_ref"] for c in u["customers"] if c["debtor_in_accounting"]}
    customers = {p["dl_ref"] for p in pays}
    late = [p for p in pays if (p["days_waiting"] or 0) > 30]
    oldest = max((p["days_waiting"] or 0 for p in pays), default=0)
    branches: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "rial": 0.0, "oldest": 0})
    for p in pays:
        b = branches[p["branch"] or "—"]
        b["n"] += 1
        b["rial"] += p["amount_rial"]
        b["oldest"] = max(b["oldest"], p["days_waiting"] or 0)
    amount = sum(p["amount_rial"] for p in pays)
    return {
        "key": "unposted_payments", "domain": "مالی", "system": "کارآمد",
        "title": "دریافت‌هایی که هنوز سند حسابداری نخورده‌اند",
        "headline": f"{len(pays):,} دریافت نقد و حواله در صف صدور سند",
        "count": len(pays), "amount_rial": amount, "oldest_days": oldest,
        "severity": _severity((len(late) > 100) + (len(late) > 0.25 * max(1, len(pays)))),
        "stat": {"value": len(late), "unit": "", "label": "مورد بیش از ۳۰ روز در صف مانده"},
        "evidence": f"پول این دریافت‌ها رسیده و در کارآمد ثبت شده؛ فقط سند حسابداری‌شان هنوز صادر نشده. "
                    f"{len(customers & debtor):,} مشتری از {len(customers):,} مشتریِ این دریافت‌ها فعلاً در حسابداری بدهکار دیده می‌شوند.",
        "impact": "تا سند صادر شود، مانده حسابداری با داشبورد یکی نیست و ممکن است مشتری‌ای که پرداخت کرده بدهکار به نظر برسد.",
        "fix": "پیشنهاد: صدور سند دریافت‌ها روزانه یا دو روز یک بار، و فرستادن فهرست صف بالای ۷ روز هر شعبه برای همکار مالی همان شعبه.",
        "series": [{"label": lbl, "value": sum(p["amount_rial"] for p in pays if lo <= (p["days_waiting"] or 0) <= hi)}
                   for lbl, lo, hi in [("تا ۷ روز", 0, 7), ("۸ تا ۳۰ روز", 8, 30), ("۳۱ تا ۶۰ روز", 31, 60), ("۶۱ تا ۹۰ روز", 61, 90)]],
        "series_label": "مبلغ بر اساس مدت انتظار",
        "top": [{"name": k, "value": v["rial"], "sub": f"{v['n']:,} دریافت · قدیمی‌ترین {v['oldest']:,} روز"}
                for k, v in sorted(branches.items(), key=lambda kv: -kv[1]["rial"])[:6]],
        "go": "/finance/cashBank",
    }


# ------------------------------------------------------------------ ۳ و ۴. توزیع بار (فاکتورهای ۹۰ روز اخیر)
def distribution() -> list[dict[str, Any]]:
    from app.services.karamad_distribution_service import KaramadDistributionService
    inv = KaramadDistributionService().timeline(WINDOW_DAYS)["invoices"]
    waiting = [x for x in inv if x["stage"] == "waiting"]
    late = [x for x in waiting if (x["days_waiting"] or 0) > 7]
    by_branch: dict[str, list[float]] = defaultdict(lambda: [0, 0.0, 0])
    for x in late:
        b = by_branch[x["branch_name"] or "—"]
        b[0] += 1
        b[1] += x["amount_rial"]
        b[2] = max(b[2], x["days_waiting"] or 0)
    groups: dict[str, list[int]] = defaultdict(list)
    for x in inv:
        if x["days_invoice_to_exit"] is not None:
            groups[x["branch_name"] or "—"].append(x["days_invoice_to_exit"])
    lead = sorted(({"branch_name": k, "n": len(v), "avg": sum(v) / len(v), "within3": 100 * sum(d <= 3 for d in v) / len(v),
                    "over7": sum(d > 7 for d in v)} for k, v in groups.items() if len(v) >= 30), key=lambda b: -b["avg"])
    all_leads = [d for v in groups.values() for d in v]
    avg = sum(all_leads) / len(all_leads) if all_leads else 0
    within3 = 100 * sum(d <= 3 for d in all_leads) / len(all_leads) if all_leads else 0
    over7 = sum(d > 7 for d in all_leads)
    oldest = max((x["days_waiting"] or 0 for x in waiting), default=0)
    short = lambda n: n.replace("هیبریدی ", "").replace("هیبرید ", "")  # noqa: E731
    return [{
        "key": "undistributed", "domain": "فروش", "system": "کارآمد",
        "title": "فاکتورهایی که هنوز ارسال نشده‌اند",
        "headline": f"{len(late):,} فاکتور بیش از ۷ روز منتظر حواله خروج",
        "count": len(late), "amount_rial": sum(x["amount_rial"] for x in late), "oldest_days": oldest,
        "severity": _severity((len(late) > 100) + (sum(x["amount_rial"] for x in late) > 5e10)),
        "stat": {"value": len(waiting), "unit": "", "label": "فاکتور سه ماه اخیر هنوز حواله خروج ندارد"},
        "evidence": "این فاکتورها صادر و در فروش و مانده مشتری حساب شده‌اند، ولی هنوز حواله خروجی برایشان ثبت نشده. "
                    "ممکن است بخشی ارسال شده و فقط حواله‌اش جا مانده باشد.",
        "impact": "تا کالا ارسال یا تکلیف فاکتور روشن شود، فروش و مطالبات کمی بیشتر از واقعیت دیده می‌شود و وصول دیرتر شروع می‌شود.",
        "fix": "پیشنهاد: مرور هفتگی فاکتورهای بدون خروج بالای ۷ روز با هر شعبه؛ یا ارسال، یا ثبت حواله جامانده، یا برگشت.",
        "series": [{"label": lbl, "value": sum(x["amount_rial"] for x in waiting if lo <= (x["days_waiting"] or 0) <= hi)}
                   for lbl, lo, hi in [("تا ۳ روز", 0, 3), ("۴ تا ۷", 4, 7), ("۸ تا ۳۰", 8, 30), ("۳۱ تا ۹۰", 31, 90)]],
        "series_label": "مبلغ بر اساس روزهای انتظار",
        "top": [{"name": k, "value": v[1], "sub": f"{v[0]:,} فاکتور · قدیمی‌ترین {v[2]:,} روز"} for k, v in sorted(by_branch.items(), key=lambda kv: -kv[1][1])[:6]],
        "go": "/finance/distribution",
    }, {
        "key": "lead_time", "domain": "فروش", "system": "کارآمد",
        "title": "فاصله فاکتور تا ارسال کالا",
        "headline": f"به طور میانگین {avg:.1f} روز از فاکتور تا خروج",
        "count": over7, "amount_rial": None, "oldest_days": None,
        "severity": _severity((avg > 5) + (within3 < 40)),
        "stat": {"value": round(within3), "unit": "٪", "label": "فاکتورها در ۳ روز ارسال شده‌اند"},
        "evidence": (f"در سه ماه اخیر {over7:,} فاکتور بیش از یک هفته بعد از صدور ارسال شده‌اند. "
                     f"بیشترین فاصله در «{lead[0]['branch_name']}» با میانگین {lead[0]['avg']:.0f} روز است.") if lead else "",
        "impact": "سررسید وصول از تاریخ فاکتور حساب می‌شود ولی کالا دیرتر به مشتری می‌رسد؛ پس دوره وصول واقعی کمی طولانی‌تر از عدد گزارش است.",
        "fix": "هدف پیشنهادی ۷۲ ساعت است؛ برای شعبه‌های با فاصله بیش از ۱۰ روز شاید یک برنامه ارسال هفتگی ثابت کمک کند.",
        "series": [{"label": short(b["branch_name"]), "value": round(b["avg"], 1)} for b in lead[:8]],
        "series_label": "میانگین روز فاکتور تا خروج — شعبه‌هایی که بیشترین فاصله را دارند",
        "series_unit": "روز",
        "top": [{"name": b["branch_name"], "value": None, "sub": f"{b['avg']:.1f} روز · {b['within3']:.0f}٪ در ۳ روز · {b['over7']:,} فاکتور بالای ۷ روز"} for b in lead[:6]],
        "go": "/finance/distribution",
    }]


# ------------------------------------------------------------------ ۵. فاصله تاریخ سند تا ثبت
def voucher_lag(c, since: date) -> dict[str, Any]:
    days = c.execute(text("""
        SELECT CAST(Date AS date) d, COUNT(*) n,
               SUM(CAST(CASE WHEN DATEDIFF(day, Date, CreationDate) < 0 THEN 0 ELSE DATEDIFF(day, Date, CreationDate) END AS float)) lag,
               SUM(CASE WHEN DATEDIFF(day, Date, CreationDate) > 30 THEN 1 ELSE 0 END) late
        FROM FIN3.Voucher WHERE Date >= :since AND VoucherTypeRef NOT IN (5, 6, 7, 11)
        GROUP BY CAST(Date AS date)
    """), {"since": since}).mappings().all()
    months: dict[str, dict[str, Any]] = {}
    for r in sorted(days, key=lambda r: r["d"]):  # ماه شمسی
        d = _day(r["d"])
        m = months.setdefault(format_jalali_date(d)[:7], {"d": d, "n": 0, "lag_sum": 0.0, "late": 0})
        m["n"] += int(r["n"] or 0)
        m["lag_sum"] += float(r["lag"] or 0)
        m["late"] += int(r["late"] or 0)
    rows = [{**m, "lag": m["lag_sum"] / m["n"]} for m in months.values() if m["n"] >= 20]
    types = c.execute(text("""
        SELECT TOP 5 t.Title, COUNT(*) n, SUM(CASE WHEN DATEDIFF(day, v.Date, v.CreationDate) > 7 THEN 1 ELSE 0 END) late,
               AVG(CAST(CASE WHEN DATEDIFF(day, v.Date, v.CreationDate) < 0 THEN 0 ELSE DATEDIFF(day, v.Date, v.CreationDate) END AS float)) lag
        FROM FIN3.Voucher v JOIN FIN3.VoucherType t ON t.VoucherTypeID = v.VoucherTypeRef
        WHERE v.Date >= :since AND v.VoucherTypeRef NOT IN (5, 6, 7, 11)
        GROUP BY t.Title ORDER BY 3 DESC
    """), {"since": since}).mappings().all()
    week = c.execute(text("""
        SELECT COUNT(*), SUM(CASE WHEN DATEDIFF(day, Date, CreationDate) > 7 THEN 1 ELSE 0 END)
        FROM FIN3.Voucher WHERE Date >= :since AND VoucherTypeRef NOT IN (5, 6, 7, 11)
    """), {"since": since}).first()
    total, late7 = int(week[0] or 0), int(week[1] or 0)
    # ماه جاری هنوز فرصت ثبت دارد؛ آخرین ماه کامل مبنای وضعیت است
    last = rows[-2] if len(rows) >= 2 else (rows[-1] if rows else None)
    first = rows[0] if rows else None
    better = bool(first and last and last["lag"] < first["lag"])
    return {
        "key": "voucher_lag", "domain": "مالی", "system": "راهکاران",
        "title": "زمان ثبت اسناد حسابداری",
        "headline": f"{late7:,} سند از {total:,} سند سه ماه اخیر بیش از یک هفته بعد از تاریخش ثبت شده",
        "count": late7, "amount_rial": None, "oldest_days": None,
        "severity": _severity((late7 / max(1, total) > 0.1) + (float(last["lag"]) > 7 if last else 0)),
        "stat": {"value": round(float(last["lag"]), 1) if last else 0, "unit": " روز", "label": f"میانگین فاصله تاریخ سند تا ثبت در {_jmonth(_day(last['d']))}" if last else ""},
        "evidence": (f"میانگین فاصله تاریخ سند تا ثبتش در {_jmonth(_day(first['d']))} {float(first['lag']):.1f} روز و در {_jmonth(_day(last['d']))} "
                     f"{float(last['lag']):.1f} روز بوده" + ("؛ روند رو به بهبود است." if better else ".")) if first and last else "",
        "impact": "وقتی سندی دیرتر ثبت شود، گزارش‌های ماه (P&L، مانده مشتری، نقدینگی) تا چند روز بعد هنوز کمی تغییر می‌کنند.",
        "fix": "پیشنهاد: بستن اسناد هر ماه تا ۵ روز بعد از پایان ماه، و ثبت سند با تاریخ گذشته با هماهنگی مدیر مالی.",
        "series": [{"label": _jmonth(_day(r["d"])), "value": round(float(r["lag"]), 1)} for r in rows],
        "series_label": "میانگین روز فاصله تاریخ سند تا ثبت، ماه به ماه",
        "series_unit": "روز",
        "top": [{"name": t["Title"], "value": None, "sub": f"{int(t['late'] or 0):,} سند بالای یک هفته از {int(t['n']):,} · میانگین {float(t['lag'] or 0):.1f} روز"} for t in types],
        "go": "/finance/history",
    }


# ------------------------------------------------------------------ ۶. محاسبه بهای تمام‌شده
def cost_calc(c) -> dict[str, Any]:
    row = c.execute(text("SELECT TOP (1) Title, EndDate, CreationDate FROM CAC3.CalcPeriod ORDER BY EndDate DESC")).mappings().first()
    end = _day(row["EndDate"]) if row else None
    months = ((date.today() - end).days // 30) if end else None
    return {
        "key": "cost_calc", "domain": "مالی و تولید", "system": "راهکاران",
        "title": "محاسبه بهای تمام‌شده در سیستم",
        "headline": f"آخرین دوره محاسبه‌شده: {(row['Title'] or '').strip()}" if row else "هنوز دوره‌ای محاسبه نشده",
        "count": None, "amount_rial": None, "oldest_days": None,
        "severity": "critical" if months and months > 3 else "watch",
        "stat": {"value": months or 0, "unit": " ماه", "label": "از آخرین محاسبه بهای تمام‌شده در راهکاران گذشته"},
        "evidence": (f"در سه ماه اخیر دوره محاسبه‌ای ثبت نشده؛ آخرین دوره تا {format_jalali_date(end)} است. "
                     "فعلاً بهای کالای فروش‌رفته با اکسل حساب می‌شود.") if row else "",
        "impact": "سود ناخالص و قیمت‌گذاری فعلاً روی ضریب‌های اکسل است و ارزش موجودی انبار در سیستم تا محاسبه دوره به‌روز نمی‌شود.",
        "fix": "پیشنهاد: اجرای ماهانه محاسبه بهای تمام‌شده در راهکاران؛ تا آن موقع بلوک «IAS 2» صفحه P&L می‌تواند مبنای مقایسه باشد.",
        "series": [], "top": [],
        "go": "/finance/pnl",
    }


def _build() -> dict[str, Any]:
    t0 = time.time()
    items, errors = [], []
    since = _since()
    try:
        with _rahkaran().connect() as c:
            for fn in (lambda: return_drafts(c, since), lambda: voucher_lag(c, since), lambda: cost_calc(c)):
                try:
                    items.append(fn())
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"راهکاران: {type(exc).__name__}: {str(exc)[:160]}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"راهکاران: {type(exc).__name__}: {str(exc)[:160]}")
    for fn in (unposted_payments, distribution):
        try:
            got = fn()
            items.extend(got if isinstance(got, list) else [got])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"کارآمد: {type(exc).__name__}: {str(exc)[:160]}")
    rank = {"critical": 0, "high": 1, "watch": 2}
    items.sort(key=lambda x: (rank[x["severity"]], -(x["amount_rial"] or 0)))
    return {"status": "ready", "items": items, "errors": errors, "window_days": WINDOW_DAYS,
            "from_jalali": format_jalali_date(since), "to_jalali": format_jalali_date(date.today()),
            "built_at": datetime.now().isoformat(timespec="seconds"), "built_seconds": round(time.time() - t0, 1)}


def _run():
    try:
        data = _build()
        with _lock:
            _state.update(at=time.time(), data=data, error="")
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _state["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    finally:
        with _lock:
            _state["running"] = False


def load(refresh: bool = False) -> dict[str, Any]:
    """گزارش در پس‌زمینه ساخته می‌شود (حدود ۲۰ ثانیه) و ۱۰ دقیقه نگه داشته می‌شود."""
    with _lock:
        fresh = _state["data"] is not None and time.time() - _state["at"] < CACHE_SECONDS
        if (refresh or not fresh) and not _state["running"]:
            _state["running"] = True
            threading.Thread(target=_run, daemon=True).start()
        if _state["data"] is not None:
            return {**_state["data"], "refreshing": _state["running"]}
        if _state["error"] and not _state["running"]:
            return {"status": "error", "message": _state["error"], "items": []}
        return {"status": "building", "items": []}
