"""گزارش هفتگی ریسک هیبریدها: امتیاز ۰ تا ۱۰۰ و سطح ریسک هر هیبرید، فقط با قواعد ثابت (بدون هوش مصنوعی).

هر هفته (شنبه صبح، app/automation/daily_finance_job.py) یک «عکس» از همه هیبریدها ساخته و ذخیره می‌شود،
تا روند هر هیبرید نسبت به هفته قبل و حدود یک ماه قبل دیده شود. با دکمه به‌روزرسانی هم دستی ساخته می‌شود.

امتیاز از چهار جزء ساخته می‌شود (هر جزء ۰ تا ۱، وزن‌ها جمعاً ۱۰۰):
  ۳۵  چک باز پرخطر   سهم مبلغ چک‌های باز با «احتمال برگشت بالا» از کل چک‌های باز
  ۲۵  چک برگشتی باز  مبلغ چک برگشتیِ تسویه‌نشده نسبت به (مطالبات + چک باز)؛ ۱۰٪ یا بیشتر = حداکثر
  ۲۵  دوره وصول      مطالبات باز تقسیم بر فروش روزانه امسال؛ تا ۴۵ روز صفر، ۱۵۰ روز یا بیشتر حداکثر
  ۱۵  دوره چک در دست مبلغ چک‌های باز تقسیم بر فروش روزانه امسال (چند روز فروش در چک وصول‌نشده است)؛
                    تا ۳۰ روز صفر، ۱۲۰ روز یا بیشتر حداکثر
(«فاکتور پرداخت‌نشده» عمداً جزء امتیاز نیست: کارآمد فاکتورِ پرداخت‌شده با چکِ هنوز وصول‌نشده را هم
 پرداخت‌نشده می‌شمارد، پس همان چک‌های باز دوباره شمرده می‌شد.)
سطح: کمتر از ۲۵ کم، کمتر از ۴۵ متوسط، کمتر از ۶۵ زیاد، بقیه بحرانی.
همه اعداد از همان پرونده هیبرید (KaramadSalesNetworkService.branch_file) می‌آیند که صفحه هیبرید نشان می‌دهد.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "hybrid_risk.sqlite3"
REBUILD_AFTER_DAYS = 7

# (کلید، وزن، عنوان فارسی)
COMPONENTS = (
    ("high_risk_cheques", 35, "چک باز پرخطر"),
    ("returned_cheques", 25, "چک برگشتی باز"),
    ("collection_period", 25, "دوره وصول"),
    ("cheque_holding", 15, "دوره چک در دست"),
)
LEVELS = ((25, "low", "کم"), (45, "medium", "متوسط"), (65, "high", "زیاد"), (101, "critical", "بحرانی"))

_build_lock = threading.Lock()
_state = {"building": False, "error": None}


# ---------------------------------------------------------------- محاسبه
def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _toman(rial: float) -> str:
    value = abs(rial or 0) / 10
    if value >= 1e9:
        text = f"{value / 1e9:,.1f} میلیارد"
    elif value >= 1e6:
        text = f"{value / 1e6:,.0f} میلیون"
    else:
        text = f"{value:,.0f}"
    return text.translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬")) + " تومان"


def _fa(number: float, digits: int = 0) -> str:
    return f"{number:,.{digits}f}".translate(str.maketrans("0123456789,.", "۰۱۲۳۴۵۶۷۸۹٬٫"))


def _level(score: float) -> tuple[str, str]:
    for limit, key, label in LEVELS:
        if score < limit:
            return key, label
    return "critical", "بحرانی"


def _fiscal_days_elapsed(today: datetime | None = None) -> int:
    import jdatetime

    t = jdatetime.date.fromgregorian(date=(today or datetime.now()).date())
    start = jdatetime.date(t.year, 1, 1).togregorian()
    return max(1, (t.togregorian() - start).days + 1)


def score_branch(file: dict[str, Any], days_elapsed: int) -> dict[str, Any]:
    """امتیاز و دلیل‌های ریسک یک هیبرید از پرونده‌اش (همان داده صفحه هیبرید)."""
    summary = (file.get("cheques") or {}).get("summary") or {}
    debt = file.get("debt") or {}
    stats = file.get("sales_stats") or {}
    amount = lambda key: float((summary.get(key) or {}).get("amount_rial") or 0)  # noqa: E731
    count = lambda key: int((summary.get(key) or {}).get("count") or 0)  # noqa: E731

    open_cheques, high_risk, returned = amount("open"), amount("high"), amount("returned")
    receivable = float(debt.get("open_account_receivable_rial") or 0)
    unpaid = float(debt.get("current_year_unpaid_invoice_rial") or 0)
    sales = float(stats.get("current_year_sales_rial") or 0)
    daily_sales = sales / days_elapsed if sales > 0 else 0
    dso = receivable / daily_sales if daily_sales > 0 else None
    cheque_days = open_cheques / daily_sales if daily_sales > 0 else None

    parts = {
        "high_risk_cheques": _clamp(high_risk / open_cheques) if open_cheques > 0 else 0.0,
        "returned_cheques": _clamp((returned / max(receivable + open_cheques, 1)) / 0.10),
        "collection_period": _clamp(((dso or 0) - 45) / (150 - 45)) if dso is not None else 0.0,
        "cheque_holding": _clamp(((cheque_days or 0) - 30) / (120 - 30)) if cheque_days is not None else 0.0,
    }
    components = [{"key": key, "title": title, "weight": weight, "ratio": round(parts[key], 3),
                   "points": round(parts[key] * weight, 1)} for key, weight, title in COMPONENTS]
    score = round(sum(c["points"] for c in components))
    level, level_label = _level(score)

    why = {
        "high_risk_cheques": f"{_toman(high_risk)} از {_toman(open_cheques)} چک باز ({_fa(high_risk / open_cheques * 100)}٪) "
                             f"احتمال برگشت بالا دارد ({_fa(count('high'))} فقره)." if open_cheques > 0 else "",
        "returned_cheques": f"{_fa(count('returned'))} چک برگشتیِ تسویه‌نشده به مبلغ {_toman(returned)}." if returned > 0 else "",
        "collection_period": f"دوره وصول {_fa(dso)} روز (مطالبات باز {_toman(receivable)})." if dso is not None else "",
        "cheque_holding": f"معادل {_fa(cheque_days)} روز فروش در چک‌های وصول‌نشده است ({_toman(open_cheques)})." if cheque_days is not None else "",
    }
    reasons = [why[c["key"]] for c in sorted(components, key=lambda c: -c["points"]) if c["points"] >= 2 and why[c["key"]]]
    return {
        "branch_id": file.get("branch_id"), "branch_name": file.get("branch_name"),
        "score": score, "level": level, "level_label": level_label,
        "components": components, "reasons": reasons or ["همه شاخص‌های ریسک در محدوده عادی است."],
        "metrics": {
            "open_cheque_rial": open_cheques, "open_cheque_count": count("open"),
            "high_risk_cheque_rial": high_risk, "high_risk_cheque_count": count("high"),
            "returned_cheque_rial": returned, "returned_cheque_count": count("returned"),
            "receivable_rial": receivable, "debtor_customer_count": int(debt.get("debtor_customer_count") or 0),
            "customer_count": int(debt.get("customer_count") or 0),
            "current_year_sales_rial": sales, "current_year_unpaid_invoice_rial": unpaid,
            "collection_period_days": round(dso, 1) if dso is not None else None,
            "cheque_holding_days": round(cheque_days, 1) if cheque_days is not None else None,
        },
    }


# ---------------------------------------------------------------- ذخیره
def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,"
               " trigger_type TEXT NOT NULL, payload TEXT NOT NULL)")
    return db


def _snapshots(limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as db:
        rows = db.execute("SELECT * FROM snapshots ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": r["id"], "created_at": r["created_at"], "trigger": r["trigger_type"], **json.loads(r["payload"])} for r in rows]


def build(trigger: str = "manual") -> dict[str, Any]:
    """همه هیبریدها را امتیاز می‌دهد و یک عکس تازه ذخیره می‌کند (چند دقیقه؛ هر هیبرید یک پرونده)."""
    from app.services.karamad_sales_network_service import KaramadSalesNetworkService
    from app.utils.jalali import format_jalali_date

    with _build_lock:
        _state.update(building=True, error=None)
        try:
            started = time.monotonic()
            service = KaramadSalesNetworkService()
            overview = service.overview()
            days = _fiscal_days_elapsed()
            branches, failed = [], []
            for row in overview.get("branches") or []:
                try:
                    file = service.branch_file(int(row["branch_id"]))
                    if file.get("status") not in (None, "success"):
                        raise RuntimeError(file.get("message") or file.get("status"))
                    branches.append(score_branch(file, days))
                except Exception as exc:  # noqa: BLE001 — یک هیبرید خراب، بقیه گزارش را متوقف نکند
                    failed.append({"branch_id": row.get("branch_id"), "branch_name": row.get("branch_name"), "error": str(exc)[:200]})
            branches.sort(key=lambda b: -b["score"])
            now = datetime.now(timezone.utc)
            payload = {"generated_at_jalali": format_jalali_date(now.astimezone().date()),
                       "fiscal_days_elapsed": days, "branches": branches, "failed": failed,
                       "build_seconds": round(time.monotonic() - started, 1)}
            with _connect() as db:
                db.execute("INSERT INTO snapshots(created_at, trigger_type, payload) VALUES(?,?,?)",
                           (now.isoformat(), trigger, json.dumps(payload, ensure_ascii=False)))
            return payload
        except Exception as exc:
            _state["error"] = str(exc)[:300]
            raise
        finally:
            _state["building"] = False


def build_in_background(trigger: str = "manual") -> bool:
    if _state["building"]:
        return False
    _state["building"] = True

    def run() -> None:
        try:
            build(trigger)
        except Exception:  # noqa: BLE001
            logger.exception("hybrid risk snapshot failed")
    threading.Thread(target=run, name="hybrid-risk-build", daemon=True).start()
    return True


def ensure_recent(trigger: str = "startup") -> None:
    """اگر هیچ عکسی نیست یا آخرین عکس قدیمی‌تر از یک هفته است (مثلاً سرور شنبه خاموش بوده)، در پس‌زمینه بساز."""
    latest = _snapshots(1)
    if latest:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(latest[0]["created_at"])
        if age < timedelta(days=REBUILD_AFTER_DAYS):
            return
    build_in_background(trigger)


# ---------------------------------------------------------------- خواندن
def _closest(snapshots: list[dict[str, Any]], latest_at: datetime, min_days: float, max_days: float) -> dict[str, Any] | None:
    for snap in snapshots[1:]:
        age = (latest_at - datetime.fromisoformat(snap["created_at"])).total_seconds() / 86400
        if min_days <= age <= max_days:
            return snap
    return None


def latest() -> dict[str, Any]:
    """آخرین گزارش، همراه با تغییر امتیاز هر هیبرید نسبت به هفته قبل و حدود یک ماه قبل."""
    snaps = _snapshots(20)
    if not snaps:
        return {"status": "building" if _state["building"] else "empty", "branches": [],
                "message": "اولین گزارش ریسک هیبریدها در حال ساخت است." if _state["building"]
                else "هنوز گزارشی ساخته نشده است."}
    cur = snaps[0]
    at = datetime.fromisoformat(cur["created_at"])
    week = _closest(snaps, at, 5, 10)
    month = _closest(snaps, at, 21, 40)
    by_id = lambda snap: {b["branch_id"]: b for b in (snap or {}).get("branches") or []}  # noqa: E731
    week_by, month_by = by_id(week), by_id(month)
    branches = []
    for b in cur["branches"]:
        w, m = week_by.get(b["branch_id"]), month_by.get(b["branch_id"])
        branches.append({**b,
                         "week_delta": b["score"] - w["score"] if w else None,
                         "month_delta": b["score"] - m["score"] if m else None,
                         "week_level": w["level"] if w else None})
    counts = {key: sum(1 for b in branches if b["level"] == key) for _, key, _ in LEVELS}
    return {
        "status": "ready", "refreshing": _state["building"],
        "generated_at": cur["created_at"], "generated_at_jalali": cur.get("generated_at_jalali"),
        "trigger": cur["trigger"],
        "week_compared_to": week["generated_at_jalali"] if week else None,
        "month_compared_to": month["generated_at_jalali"] if month else None,
        "levels": counts, "branches": branches, "failed": cur.get("failed") or [],
        "components": [{"key": k, "weight": w, "title": t} for k, w, t in COMPONENTS],
    }
