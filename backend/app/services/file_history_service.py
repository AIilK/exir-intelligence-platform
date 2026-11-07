"""پروفایل تاریخچه هر هیبرید و هر نماینده راهکاران برای تحلیل هوش مصنوعی (app/services/ai_file_analysis_service.py).

همه اعداد این‌جا با کد و از همان منابعی ساخته می‌شوند که صفحه‌ها نشان می‌دهند؛ هوش مصنوعی فقط همین پروفایل را می‌بیند
و خودش هیچ عددی حساب یا از دیتابیس نمی‌خواند. مبالغ به «میلیون تومان» (mt) گرد می‌شوند تا پروفایل کوچک و خوانا بماند.
نام مشتریان تکی در پروفایل نیست؛ فقط جمع‌های ماهانه هیبرید یا نماینده.

هیبرید:  فروش ماه‌به‌ماه (داشبورد فروش)، توزیع و وصول ماه‌های اخیر (گزارش توزیع)، چک‌های دریافتی هر ماه و
         سرنوشتشان (وصول، برگشت، باز) از کارآمد، و روند امتیاز ریسک هفتگی.
نماینده: فروش ماه‌به‌ماه امسال کنار همان ماه پارسال (داشبورد فروش راهکاران)، شاخص‌های فروش، وضعیت مالی فعلی
         (پرتفوی وصول) و چک‌های دریافتی هر ماه و سرنوشتشان از راهکاران.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, text

logger = logging.getLogger(__name__)

HISTORY_MONTHS = 24
DISTRIBUTION_MONTHS = 6


def mt(rial: Any) -> float:
    """ریال ← میلیون تومان، یک رقم اعشار."""
    try:
        return round(float(rial or 0) / 1e7, 1)
    except (TypeError, ValueError):
        return 0.0


def _jmonth(d: Any) -> str | None:
    import jdatetime

    if isinstance(d, datetime):
        d = d.date()
    if not isinstance(d, date):
        return None
    j = jdatetime.date.fromgregorian(date=d)
    return f"{j.year}/{j.month:02d}"


def _recent_jmonths(n: int) -> list[tuple[int, int]]:
    import jdatetime

    t = jdatetime.date.today()
    out = []
    for back in range(n):
        idx = t.year * 12 + t.month - 1 - back
        out.append((idx // 12, idx % 12 + 1))
    return out


def _since() -> date:
    return date.today() - timedelta(days=HISTORY_MONTHS * 31)


def _roll_up(rows, key_field: str) -> dict[Any, list[dict[str, Any]]]:
    """ردیف‌های روزانه چک (کلید، روز ثبت، تعداد/مبلغ هر وضعیت) ← ماه شمسی."""
    acc: dict[Any, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for r in rows:
        month = _jmonth(r["Day"])
        if month is None or r[key_field] is None:
            continue
        m = acc[r[key_field]][month]
        for f in ("n", "amount", "collected", "returned", "open", "term_sum", "term_n"):
            m[f] += float(r[f] or 0)
    result = {}
    for k, months in acc.items():
        result[k] = [{
            "month": month,
            "cheques": int(v["n"]),
            "amount_mt": mt(v["amount"]),
            "collected_mt": mt(v["collected"]),
            "returned_mt": mt(v["returned"]),
            "still_open_mt": mt(v["open"]),
            "avg_term_days": round(v["term_sum"] / v["term_n"]) if v["term_n"] else None,
        } for month, v in sorted(months.items())]
    return result


# ---------------------------------------------------------------- چک‌ها
def karamad_cheque_months() -> dict[int, list[dict[str, Any]]]:
    """چک‌های دریافتی هر هیبرید (شعبه کارآمد) به تفکیک ماه ثبت، با سرنوشت فعلی هر چک."""
    from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
    from app.services.karamad_live_received_cheque_service import not_guarantee_cheque
    from app.services.karamad_sales_network_service import COLLECTED_CHEQUE_STATUS, RETURNED_CHEQUE_STATUSES

    returned = ",".join(str(s) for s in RETURNED_CHEQUE_STATUSES)
    sql = text(f"""
        SELECT d.[BranchRef], CAST(d.[BookDate] AS date) AS Day,
               COUNT(*) AS n, SUM(d.[Price]) AS amount,
               SUM(CASE WHEN d.[StatusRef] = {COLLECTED_CHEQUE_STATUS} THEN d.[Price] ELSE 0 END) AS collected,
               SUM(CASE WHEN d.[StatusRef] IN ({returned}) THEN d.[Price] ELSE 0 END) AS returned,
               SUM(CASE WHEN d.[StatusRef] <> {COLLECTED_CHEQUE_STATUS} AND d.[StatusRef] NOT IN ({returned}) THEN d.[Price] ELSE 0 END) AS [open],
               SUM(CASE WHEN d.[DueDate] IS NOT NULL THEN DATEDIFF(day, d.[BookDate], d.[DueDate]) ELSE 0 END) AS term_sum,
               SUM(CASE WHEN d.[DueDate] IS NOT NULL THEN 1 ELSE 0 END) AS term_n
        FROM dbo.[tblChequeD] d
        WHERE d.[BookDate] >= :since AND d.[BranchRef] IS NOT NULL AND {not_guarantee_cheque("d")}
        GROUP BY d.[BranchRef], CAST(d.[BookDate] AS date)
    """)
    with get_karamad_sqlserver_engine().connect() as c:
        rows = c.execute(sql, {"since": _since()}).mappings().all()
    return {int(k): v for k, v in _roll_up(rows, "BranchRef").items()}


def rahkaran_cheque_months(refs: list[int]) -> dict[int, list[dict[str, Any]]]:
    """چک‌های دریافتی هر نماینده راهکاران به تفکیک ماه رسید؛ همان فیلترهای رفتار چک مشتری (finance_prediction_service)."""
    if not refs:
        return {}
    from app.database.sqlserver import get_sqlserver_engine
    from app.services.customer_cheque_return_risk import RAHKARAN_COLLECTED_STATES, RAHKARAN_RETURNED_STATES

    collected = ", ".join(str(s) for s in sorted(RAHKARAN_COLLECTED_STATES))
    returned = ", ".join(str(s) for s in sorted(RAHKARAN_RETURNED_STATES))
    sql = text(f"""
        SELECT note.[CounterPartRef], CAST(receipt.[Date] AS date) AS Day,
               COUNT(*) AS n, SUM(note.[Amount]) AS amount,
               SUM(CASE WHEN master_note.[State] IN ({collected}) THEN note.[Amount] ELSE 0 END) AS collected,
               SUM(CASE WHEN master_note.[State] IN ({returned}) THEN note.[Amount] ELSE 0 END) AS returned,
               SUM(CASE WHEN master_note.[State] NOT IN ({collected}, {returned}) THEN note.[Amount] ELSE 0 END) AS [open],
               SUM(CASE WHEN note.[DueDate] IS NOT NULL THEN DATEDIFF(day, CAST(receipt.[Date] AS date), CAST(note.[DueDate] AS date)) ELSE 0 END) AS term_sum,
               SUM(CASE WHEN note.[DueDate] IS NOT NULL THEN 1 ELSE 0 END) AS term_n
        FROM RPA3.[ReceiptReceivableNote] AS note
        INNER JOIN RPA3.[Receipt] AS receipt ON receipt.[ReceiptID] = note.[ReceiptRef]
        LEFT JOIN RPA3.[ReceivableNote] AS master_note ON master_note.[ReceivableNoteID] = note.[ReceivableNoteRef]
        WHERE receipt.[ApproveState] = 3 AND receipt.[ItemType] = 1
          AND master_note.[NoteType] = 1 AND master_note.[NormalORGuarantee] = 1
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(master_note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%ضمانت%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%تضمین%'
          AND ISNULL(note.[Description], N'') NOT LIKE N'%حسن انجام%'
          AND receipt.[Date] >= :since AND note.[CounterPartRef] IN :refs
        GROUP BY note.[CounterPartRef], CAST(receipt.[Date] AS date)
    """).bindparams(bindparam("refs", expanding=True))
    with get_sqlserver_engine().connect() as c:
        rows = c.execute(sql, {"since": _since(), "refs": [int(r) for r in refs]}).mappings().all()
    return {int(k): v for k, v in _roll_up(rows, "CounterPartRef").items()}


# ---------------------------------------------------------------- هیبریدها
def _sales_api(path: str, **params: Any) -> dict[str, Any] | None:
    """داشبورد فروش (sales/backend) با کلید داخلی؛ خطا یا قطعی = None."""
    from app.services.manager_combined_service import _sales_api as get

    return get(path, params)


def hybrid_profiles() -> dict[int, dict[str, Any]]:
    """پروفایل تاریخچه همه هیبریدها (یک بار برای همه: فروش هر هیبرید یک درخواست، چک‌ها یک کوئری)."""
    from app.services import hybrid_risk_service
    from app.services.karamad_distribution_service import KaramadDistributionService
    from app.services.karamad_sales_network_service import KaramadSalesNetworkService

    overview = KaramadSalesNetworkService().overview()
    branches = overview.get("branches") or []
    cheques = karamad_cheque_months()

    distribution: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dist = KaramadDistributionService()
    for y, m in reversed(_recent_jmonths(DISTRIBUTION_MONTHS)):
        try:
            report = dist.monthly(y, m)
        except Exception as exc:  # noqa: BLE001
            logger.warning("distribution %s/%s unavailable: %s", y, m, exc)
            continue
        for b in report.get("branches") or []:
            distribution[str(b.get("branch_name") or "").strip()].append({
                "month": f"{y}/{m:02d}", "sales_mt": mt(b.get("sales_rial")),
                "distributed_mt": mt(b.get("distributed_rial")), "collected_mt": mt(b.get("collected_rial")),
                "remaining_mt": mt(b.get("remaining_rial")),
            })

    risk = hybrid_risk_service.latest()
    risk_now = {b["branch_id"]: b for b in risk.get("branches") or []}
    risk_trend: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for snap in reversed(hybrid_risk_service._snapshots(12)):
        for b in snap.get("branches") or []:
            risk_trend[b["branch_id"]].append({"date": snap.get("generated_at_jalali"), "score": b["score"]})

    profiles = {}
    for b in branches:
        bid, name = int(b["branch_id"]), str(b.get("branch_name") or "").strip()
        sales = _sales_api("/api/monthly", vat=1, branch=name) or {}
        r = risk_now.get(bid) or {}
        profiles[bid] = {
            "kind": "hybrid", "key": str(bid), "name": name,
            "people": {"hybrid_owners": b.get("hybrids") or [], "active_visitors": b.get("active_visitor_count"),
                       "active_customers": b.get("active_customer_count")},
            "current": {
                "risk_score": r.get("score"), "risk_level": r.get("level_label"),
                "risk_components": {c["title"]: c["points"] for c in r.get("components") or []},
                "open_receivable_mt": mt((b.get("debt") or {}).get("open_account_receivable_rial")),
                "open_cheques_mt": mt(b.get("open_cheque_amount_rial")),
                "current_year_sales_mt": mt(b.get("current_year_sales_rial")),
                "previous_year_sales_mt": mt(b.get("previous_year_sales_rial")),
                "collection_period_days": (r.get("metrics") or {}).get("collection_period_days"),
                "cheque_holding_days": (r.get("metrics") or {}).get("cheque_holding_days"),
            },
            "monthly_sales": [{"month": x["month"], "net_mt": mt(x.get("net")), "invoices": x.get("invoices"),
                               "customers": x.get("customers")} for x in (sales.get("months") or [])],
            "monthly_distribution_and_collection": distribution.get(name, []),
            "monthly_cheques_received": cheques.get(bid, []),
            "weekly_risk_score_trend": risk_trend.get(bid, []),
        }
    return profiles


# ---------------------------------------------------------------- نمایندگان راهکاران
def rep_profiles() -> dict[str, dict[str, Any]]:
    """پروفایل تاریخچه همه نمایندگان راهکاران که در ۲۰ ماه اخیر خرید داشته‌اند (کلید: کد نماینده)."""
    from app.utils.internal_api import internal_get

    listing = _sales_api("/api/rk_sales/customers") or {}
    reps = [c for c in listing.get("customers") or [] if (c.get("net") or 0) > 0 or (c.get("ly_net") or 0) > 0]
    portfolio = internal_get("/finance/customer-collection-portfolio?source=rahkaran&limit=1000")
    fin = {str(c.get("counterpart_code")): c for c in portfolio.get("customers") or []}
    refs = [int(fin[c["code"]]["counterpart_ref"]) for c in reps if c["code"] in fin and fin[c["code"]].get("counterpart_ref")]
    cheques = rahkaran_cheque_months(refs)

    profiles = {}
    for c in reps:
        code = str(c["code"])
        detail = _sales_api("/api/rk_sales/customer", code=code) or {}
        k = detail.get("kpis") or {}
        f = fin.get(code) or {}
        ref = int(f["counterpart_ref"]) if f.get("counterpart_ref") else None
        profiles[code] = {
            "kind": "rep", "key": code, "name": c.get("name") or code,
            "where": {"province": c.get("province"), "city": c.get("city"), "brand": c.get("brand")},
            "sales_kpis_this_year": {
                "net_mt": mt(k.get("net")), "same_period_last_year_mt": mt(k.get("ly_net")),
                "growth_percent": k.get("growth"), "return_rate_percent": k.get("return_rate"),
                "discount_rate_percent": k.get("disc_rate"), "invoices": k.get("invoices"),
                "first_purchase": detail.get("first_date"), "last_purchase": detail.get("last_date"),
            },
            "top_categories": [{"category": x.get("key"), "share_percent": x.get("share")} for x in (detail.get("categories") or [])[:5]],
            "monthly_sales_vs_last_year": [{"month": x["month"], "net_mt": mt(x.get("net")), "last_year_mt": mt(x.get("ly_net"))}
                                           for x in detail.get("monthly") or []],
            "financial_position_now": {
                "open_exposure_mt": mt(f.get("open_exposure")), "overdue_mt": mt(f.get("overdue_open_amount")),
                "returned_cheques": f.get("returned_cheque_count"), "returned_cheques_mt": mt(f.get("returned_cheque_amount")),
                "future_open_cheques_mt": mt(f.get("future_open_cheque_amount")),
                "lifetime_cheques": f.get("historical_cheque_count"), "rule_based_risk_level": f.get("risk_level"),
                "last_invoice": f.get("last_invoice_date_jalali"),
            } if f else None,
            "monthly_cheques_received": cheques.get(ref, []) if ref else [],
        }
    return profiles
