"""سهم راهکاران (B2B و صادرات) در شاخص‌های نمای مدیر، تا هر شاخص جمع همه ماژول‌ها باشد.

- فروش خالص ماه نمایندگان B2B راهکاران: همان عدد داشبورد فروش (/api/rk_sales?period=YYYY/MM، خالص = NetPrice پس از کسور و اضافات)؛
- فروش صادراتی ماه: دلار و معادل ریالی با نرخ اسناد (/api/rk_export/month).
- مطالبات مشتریان راهکاران: مانده معین‌های دریافتنی تجاری (۱۲۳۰۰۳/۴/۹/۱۱) هر تفصیلی سطح ۴ در سال مالی جاری
  (همان روش finance_prediction_service)، فقط مانده‌های بدهکار و بدون حساب هیبریدها (تسویه داخلی با کارآمد).
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import text
from app.utils.swr_cache import swr_get

CACHE_SECONDS = 300
_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()

RECEIVABLE_SQL = text(
    """
    WITH active_fy AS (
        SELECT TOP (1) lfy.[StartDate], CASE WHEN :as_of < lfy.[EndDate] THEN :as_of ELSE lfy.[EndDate] END AS [EndDate]
        FROM GNR3.[LedgerFiscalYear] lfy
        WHERE lfy.[LedgerRef] = 1 AND :as_of >= CAST(lfy.[StartDate] AS date) AND :as_of <= CAST(lfy.[EndDate] AS date)
        ORDER BY lfy.[StartDate] DESC
    )
    SELECT b.[DLCode], dl.[Title], b.[Balance]
    FROM (
        SELECT vi.[DLLevel4] AS [DLCode], SUM(COALESCE(vi.[Debit], 0) - COALESCE(vi.[Credit], 0)) AS [Balance]
        FROM FIN3.[VoucherItem] vi
        INNER JOIN FIN3.[Voucher] v ON v.[VoucherID] = vi.[VoucherRef]
        INNER JOIN FIN3.[SL] sl ON sl.[SLID] = vi.[SLRef]
        CROSS JOIN active_fy fy
        WHERE sl.[Code] IN (N'123003', N'123004', N'123009', N'123011') AND vi.[DLLevel4] IS NOT NULL
          AND v.[Date] >= fy.[StartDate] AND v.[Date] < DATEADD(day, 1, fy.[EndDate])
        GROUP BY vi.[DLLevel4]
    ) b
    LEFT JOIN FIN3.[DL] dl ON dl.[Code] = b.[DLCode]
    """
)


def _cached(key: str, loader):
    return swr_get(_cache, _lock, key, CACHE_SECONDS, loader)


def _sales_api(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    from app.auth.internal_key import internal_headers
    from app.services.karamad_distribution_service import SALES_API

    try:
        with urlopen(Request(f"{SALES_API}{path}?{urlencode(params)}", headers={"Accept": "application/json", **internal_headers()}),
                     timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def rahkaran_sales(year: int, month: int) -> dict[str, Any]:
    """فروش خالص نمایندگان B2B راهکاران در ماه (تا امروز برای ماه جاری)؛ None = داشبورد فروش در دسترس نیست."""
    def load():
        data = _sales_api("/api/rk_sales", {"period": f"{year}/{month:02d}"})
        if not data or not data.get("kpis"):
            return {"net_rial": None, "customers": None}
        k = data["kpis"]
        top = lambda rows: [{"key": r.get("key"), "net_rial": float(r.get("net") or 0)}  # noqa: E731
                            for r in sorted(rows or [], key=lambda r: -float(r.get("net") or 0))[:12] if r.get("key")]
        return {"net_rial": float(k.get("net") or 0), "gross_rial": float(k.get("gross") or 0), "returns_rial": float(k.get("returns") or 0),
                "customers": k.get("customers_period"), "today": data.get("today"),
                "provinces": top(data.get("provinces")), "brands": top(data.get("brands"))}
    return _cached(f"sales:{year}/{month}", load)


def karamad_sales(year: int, month: int) -> dict[str, Any]:
    """فروش ناخالص و درخواست‌های باز (فاکتورنشده) شعب کارآمد در ماه، از داشبورد فروش (/api/hybrid، با ارزش افزوده).

    ناخالص = مبلغ پیش از تخفیف‌ها (بدون ارزش افزوده)؛ درخواست باز = درخواست خالص ماه منهای بخشی که فاکتور شده.
    """
    def load():
        m = f"{year}/{month:02d}"
        data = _sales_api("/api/hybrid", {"vat": 1, "date_from": f"{m}/01", "date_to": f"{m}/31"})
        if not data or not data.get("kpis"):
            return {"gross_rial": None, "open_req_rial": None}
        k = data["kpis"]
        fl = lambda v: float(v or 0)  # noqa: E731
        branches = []
        for b in data.get("branches") or []:
            req, conv = fl(b.get("req_net")), b.get("req_conv")
            branches.append({"key": b.get("label") or b.get("key"), "gross_rial": fl(b.get("gross")), "net_rial": fl(b.get("net")),
                             "req_rial": req, "open_req_rial": req * (1 - float(conv)) if conv is not None else 0.0,
                             "req_docs": int(fl(b.get("req_docs")))})
        return {"gross_rial": fl(k.get("gross")), "net_rial": fl(k.get("net")), "returns_rial": fl(k.get("returns_net")),
                "req_rial": fl(k.get("req_net")), "req_done_rial": fl(k.get("req_net_done")),
                "open_req_rial": max(0.0, fl(k.get("req_net")) - fl(k.get("req_net_done"))),
                "req_docs": int(fl(k.get("req_docs"))), "open_req_docs": int(fl(k.get("req_docs")) - fl(k.get("req_docs_done"))),
                "req_conv": k.get("req_conv"), "branches": branches}
    return _cached(f"karamad:{year}/{month}", load)


def rahkaran_export(year: int, month: int) -> dict[str, Any]:
    """فروش صادراتی ماه (دلار و معادل ریالی با نرخ اسناد) با تفکیک کشور و مشتری."""
    def load():
        data = _sales_api("/api/rk_export/month", {"month": f"{year}/{month:02d}"})
        return data or {"net_rial": None, "net_usd": None, "countries": [], "customers": []}
    return _cached(f"export:{year}/{month}", load)


def rahkaran_receivables() -> dict[str, Any]:
    def load():
        from app.database.sqlserver import get_sqlserver_engine

        with get_sqlserver_engine().connect() as c:
            rows = c.execute(RECEIVABLE_SQL, {"as_of": date.today()}).mappings().all()
        own = [r for r in rows if "هیبرید" not in str(r["Title"] or "")]
        debtors = [r for r in own if float(r["Balance"] or 0) > 0]
        debtors.sort(key=lambda r: -float(r["Balance"]))
        return {"open_receivable_rial": round(sum(float(r["Balance"]) for r in debtors), 2),
                "debtor_count": len(debtors),
                "top": [{"key": str(r["Title"] or r["DLCode"]), "code": str(r["DLCode"]), "amount_rial": round(float(r["Balance"]), 2)}
                        for r in debtors[:12]],
                "excluded_hybrid_rial": round(sum(max(0.0, float(r["Balance"] or 0)) for r in rows if r not in own), 2)}
    return _cached("receivables", load)


def overview(year: int, month: int) -> dict[str, Any]:
    prev = (year - 1, 12) if month == 1 else (year, month - 1)
    out: dict[str, Any] = {"year": year, "month": month, "errors": []}
    try:
        out["sales"] = {"cur": rahkaran_sales(year, month), "prev": rahkaran_sales(*prev)}
        out["export"] = {"cur": rahkaran_export(year, month), "prev": rahkaran_export(*prev)}
        out["karamad"] = {"cur": karamad_sales(year, month)}
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"فروش راهکاران: {exc}")
    try:
        out["receivables"] = rahkaran_receivables()
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"مطالبات راهکاران: {exc}")
    try:
        out["collections"] = rahkaran_collections(year, month)
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"وصول راهکاران: {exc}")
    try:
        out["today_inflows"] = today_inflows()
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"وصول امروز: {exc}")
    try:
        out["receivables_report"] = receivables_report()
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"مطالبات باز (پرونده مشتری): {exc}")
    return out


# ---------------------------------------------------------------- وصول ماه: محصول در برابر مواد اولیه
RAW_MATERIAL_ACCOUNT = "124046"  # «دریافتنی غیر رسمی (مواد اولیه)»
EXPORT_ACCOUNT = "123010"  # «حسابهای دریافتنی تجاری ارزی»: مشتریان صادراتی
SEGMENTS = (("rep", "نمایندگان B2B"), ("export", "صادرات"), ("other", "سایر"))


def _is_rep_code(code: str) -> bool:
    """کد تفصیلی نمایندگان و مشتریان محصول: ۶ رقمی ۷xxxxx تا ۹xxxxx (همان قاعده گزارش مانده واحد مالی)."""
    return len(code) == 6 and code[0] in "789"


def is_raw_material_collection(account_code: str | None, counterpart_code: str | None, counterpart_name: str | None) -> bool:
    """وصول از خریدار مواد اولیه: هر ورودی معین ۱۲۴۰۴۶ «دریافتنی غیر رسمی (مواد اولیه)»، یا ورودی حساب‌های دریافتنی
    از طرف حسابی که نماینده/مشتری محصول نیست (کد خارج از ۷xxxxx تا ۹xxxxx) و در نامش «مواد» آمده
    (مثل «خریدار مواد اولیه» روی معین ۱۲۳۰۰۳)."""
    if str(account_code or "") == RAW_MATERIAL_ACCOUNT:
        return True
    name = str(counterpart_name or "").replace("ي", "ی").replace("ك", "ک")
    return "مواد" in name and not _is_rep_code(str(counterpart_code or "").strip())


def rahkaran_collections(year: int, month: int) -> dict[str, Any]:
    """وصول ماه راهکاران (نقد و حواله، بدون چک) در دو بخش: محصول (نمایندگان، صادرات، سایر مشتریان) و مواد اولیه.
    همان حرکت‌های تحلیل نقدینگی (liquidity/cash_movements.py) است؛ محصول = «وصول از مشتری» منهای خریداران مواد."""
    def load():
        import jdatetime
        from collections import defaultdict

        from app.services.liquidity.cash_movements import CashMovementService

        start = jdatetime.date(year, month, 1).togregorian()
        end = jdatetime.date(year + (month == 12), month % 12 + 1, 1).togregorian()
        rows, _, _ = CashMovementService()._classified("b2b", False)
        parts = {"product": defaultdict(float), "raw_material": defaultdict(float)}
        accounts = {"product": defaultdict(float), "raw_material": defaultdict(float)}
        customers: dict[str, dict[tuple[str, str], dict[str, Any]]] = {"product": {}, "raw_material": {}}
        for r in rows:
            m = r.movement
            if m.direction != "inflow" or not (start <= m.day < end):
                continue
            raw = is_raw_material_collection(m.account_code, m.counterpart_code, m.counterpart_name)
            if not raw and r.classification.category != "customer_collection":
                continue
            kind = "raw_material" if raw else "product"
            amount = float(r.signed_amount)
            parts[kind][m.method] += amount
            accounts[kind][f"{m.account_code or '—'} · {m.account_name or 'نامشخص'}"] += amount
            key = (str(m.counterpart_code or ""), str(m.counterpart_name or "نامشخص").strip())
            c = customers[kind].setdefault(key, {"code": key[0], "name": key[1], "amount_rial": 0.0, "count": 0, "by_method": defaultdict(float)})
            c["amount_rial"] += amount
            c["count"] += m.count
            c["by_method"][m.method] += amount
            c.setdefault("accounts", set()).add(str(m.account_code or ""))

        def segment(c: dict[str, Any]) -> str:
            """صادرات = دریافت روی معین ارزی ۱۲۳۰۱۰؛ نماینده B2B = کد تفصیلی ۷xxxxx تا ۹xxxxx؛ بقیه = سایر."""
            if EXPORT_ACCOUNT in c["accounts"]:
                return "export"
            return "rep" if _is_rep_code(c["code"]) else "other"

        def clean(x: dict[str, Any]) -> dict[str, Any]:
            return {"code": x["code"], "name": x["name"], "count": x["count"], "amount_rial": round(x["amount_rial"], 2),
                    "by_method": {k: round(v, 2) for k, v in x["by_method"].items()}}

        def pack(kind: str) -> dict[str, Any]:
            top = sorted(customers[kind].values(), key=lambda x: -x["amount_rial"])[:15]
            return {
                "amount_rial": round(sum(parts[kind].values()), 2),
                "by_method": {k: round(v, 2) for k, v in parts[kind].items()},
                "by_account": [{"key": k, "amount_rial": round(v, 2)} for k, v in sorted(accounts[kind].items(), key=lambda kv: -kv[1])],
                "customer_count": len(customers[kind]),
                "top_customers": [clean(x) for x in top],
            }

        def segments() -> list[dict[str, Any]]:
            out = []
            for key, label in SEGMENTS:
                rows = sorted((c for c in customers["product"].values() if segment(c) == key), key=lambda x: -x["amount_rial"])
                out.append({"key": key, "label": label, "amount_rial": round(sum(c["amount_rial"] for c in rows), 2),
                            "customer_count": len(rows), "customers": [clean(c) for c in rows]})
            return out
        product = pack("product")
        product["segments"] = segments()
        return {"product": product, "raw_material": pack("raw_material"),
                "rule": "نقد و حواله ماه از راهکاران؛ مواد اولیه = معین ۱۲۴۰۴۶ و خریداران مواد روی حساب‌های دریافتنی؛ بقیه وصول از مشتری = محصول."}
    return _cached(f"collections:{year}/{month}", load)


# ---------------------------------------------------------------- مطالبات باز: همان عدد «پرونده مشتری»
def receivables_report() -> dict[str, Any]:
    """مانده بدهی مشتریان راهکاران و حساب چک برگشتی، با همان قاعده گزارش واحد مالی که صفحه «پرونده مشتری» نشان می‌دهد
    (report_open_account_receivable_rial و report_returned_account_rial)، به‌اضافه بزرگ‌ترین بدهکاران."""
    def load():
        from app.services.customer_intelligence_service import CustomerIntelligenceService

        portfolio = CustomerIntelligenceService().collection_portfolio(1000)
        s = portfolio.get("summary") or {}
        rows = [c for c in portfolio.get("customers") or [] if (c.get("collection_position") or {}).get("in_receivable_report")]

        def row(c: dict[str, Any]) -> dict[str, Any]:
            cp = c.get("collection_position") or {}
            return {"code": str(c.get("counterpart_code") or ""), "name": c.get("counterpart_name") or "—",
                    "balance_rial": float(cp.get("open_account_receivable_rial") or 0),
                    "returned_rial": float(cp.get("returned_account_rial") or 0),
                    "open_cheques_rial": float(cp.get("open_cheque_amount_rial") or 0),
                    "overdue_rial": float(c.get("overdue_open_amount") or 0),
                    "last_invoice": c.get("last_invoice_date_jalali")}
        debtors = sorted((row(c) for c in rows), key=lambda x: -(x["balance_rial"] + x["returned_rial"]))
        return {"balance_rial": float(s.get("report_open_account_receivable_rial") or 0),
                "returned_rial": float(s.get("report_returned_account_rial") or 0),
                "customer_count": int(s.get("report_customer_count") or 0),
                "debtor_count": sum(1 for d in debtors if d["balance_rial"] + d["returned_rial"] > 0),
                "top": [d for d in debtors if d["balance_rial"] + d["returned_rial"] > 0][:15]}
    return _cached("receivables_report", load)



# ---------------------------------------------------------------- وصول و واریز امروز
TODAY_GROUPS = (("customer", "وصول مشتریان (نقد و حواله)"), ("returned", "بابت چک برگشتی"), ("raw_material", "خریداران مواد اولیه"),
                ("cheque", "چک نقدشده (وصول‌کننده)"), ("other", "سایر ورودی‌های عملیاتی"))
SYSTEM_LABELS = {"rahkaran": "راهکاران", "karamad": "کارآمد"}
RETURNED_ACCOUNT = "1"  # راهکاران: «حسابهای دریافتنی بابت برگشتی»

# کارآمد: هر واریز (حواله tblDraftD و نقد tblCashD) با شعبه، مشتری و اینکه بابت چک برگشتی بوده یا نه (ReturnChequeRef)
KARAMAD_TODAY_SQL = text("""
    SELECT x.[Method], b.[Name] AS [Branch], CAST(dl.[Code] AS nvarchar(50)) AS [Code], dl.[Name] AS [Name],
           CAST(sl.[Code] AS nvarchar(50)) AS [SL], CASE WHEN x.[ReturnChequeRef] IS NULL THEN 0 ELSE 1 END AS [Returned],
           MAX(CONCAT(x.[Behalf], N' ', x.[Description])) AS [Behalf], SUM(x.[Amount]) AS [Amount], COUNT_BIG(*) AS [N]
    FROM (SELECT N'bank' AS [Method], [BranchRef], [DLRef], [SLRef], [ReturnChequeRef], [Price] AS [Amount], [Behalf], [Description]
          FROM dbo.[tblDraftD] WHERE COALESCE([DraftDate], [BookDate]) = :d
          UNION ALL
          SELECT N'cash', [BranchRef], [DLRef], [SLRef], [ReturnChequeRef], [PriceN], [Behalf], [Description]
          FROM dbo.[tblCashD] WHERE [BookDate] = :d) AS x
    LEFT JOIN dbo.[tblBranch] b ON b.[ID] = x.[BranchRef]
    LEFT JOIN dbo.[tblDL] dl ON dl.[ID] = x.[DLRef]
    LEFT JOIN dbo.[tblSL] sl ON sl.[ID] = x.[SLRef]
    GROUP BY x.[Method], b.[Name], dl.[Code], dl.[Name], sl.[Code], CASE WHEN x.[ReturnChequeRef] IS NULL THEN 0 ELSE 1 END
""")


def today_inflows() -> dict[str, Any]:
    """پولی که امروز واقعاً وارد صندوق و بانک شده، هر دو سیستم (نقد و حواله؛ چک دریافتی جداست).
    راهکاران: رسیدهای تأییدشده (همان تحلیل نقدینگی)؛ رسید امروزِ تأییدنشده بعد از تأیید اضافه می‌شود.
    کارآمد: واریزهای امروز با شعبه و مشتری. دسته‌بندی حساب‌ها همان account_map است؛ جابه‌جایی بانک‌ها،
    شرکا، تسویه کالای هیبریدها با شرکت و واریز نامشخص کنار گذاشته می‌شوند."""
    def load():
        from collections import defaultdict

        from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
        from app.services.liquidity.account_map import NOTE_CHEQUE_COLLECTION, classify
        from app.services.liquidity.cash_movements import _CHEQUE_PHRASES, CashMovementService

        today = date.today()
        items: dict[tuple, dict[str, Any]] = {}

        def add(system: str, group: str, branch: str | None, code: Any, name: str, method: str, amount: float, count: int) -> None:
            code = str(code or "").removesuffix(".0")
            key = (system, group, branch, code, name)
            it = items.setdefault(key, {"system": system, "group": group, "branch": branch, "code": code, "name": name,
                                        "amount_rial": 0.0, "count": 0, "by_method": defaultdict(float)})
            it["amount_rial"] += amount
            it["count"] += count
            it["by_method"][method] += amount

        def group_of(cat: str, note: str | None) -> str | None:
            if note == NOTE_CHEQUE_COLLECTION:
                return "cheque"
            return {"customer_collection": "customer", "other_operating_inflow": "other"}.get(cat)

        # راهکاران
        rows, _, _ = CashMovementService()._classified("b2b", False)
        rk_days = [r.movement.day for r in rows if r.movement.direction == "inflow"]
        for r in rows:
            m = r.movement
            if m.direction != "inflow" or m.day != today:
                continue
            if is_raw_material_collection(m.account_code, m.counterpart_code, m.counterpart_name):
                group = "raw_material"
            elif str(m.account_code or "") == RETURNED_ACCOUNT and r.classification.category == "customer_collection":
                group = "returned"
            else:
                group = group_of(r.classification.category, m.note)
            if group:
                add("rahkaran", group, None, m.counterpart_code or m.account_code,
                    (m.counterpart_name or "").strip() or (m.account_name or "نامشخص"), m.method, float(m.amount_rial), m.count)

        # کارآمد
        with get_karamad_sqlserver_engine().connect() as c:
            km = c.execute(KARAMAD_TODAY_SQL, {"d": today}).mappings().all()
        for r in km:
            behalf = str(r["Behalf"] or "")
            note = NOTE_CHEQUE_COLLECTION if any(p in behalf for p in _CHEQUE_PHRASES) else None
            cls = classify("karamad", "inflow", r["SL"], note=note)
            group = "returned" if r["Returned"] and cls.category == "customer_collection" else group_of(cls.category, note)
            if group:
                add("karamad", group, (r["Branch"] or "").strip() or "بدون شعبه", r["Code"], (r["Name"] or "").strip() or "نامشخص",
                    r["Method"], float(r["Amount"] or 0), int(r["N"] or 0))

        rows_out = sorted(({**x, "amount_rial": round(x["amount_rial"], 2), "by_method": {k: round(v, 2) for k, v in x["by_method"].items()}}
                           for x in items.values()), key=lambda x: -x["amount_rial"])
        systems = []
        for system, label in SYSTEM_LABELS.items():
            mine = [x for x in rows_out if x["system"] == system]
            groups = []
            for g, glabel in TODAY_GROUPS:
                gr = [x for x in mine if x["group"] == g]
                if gr:
                    groups.append({"key": g, "label": glabel, "amount_rial": round(sum(x["amount_rial"] for x in gr), 2),
                                   "count": sum(x["count"] for x in gr), "items": gr})
            systems.append({"key": system, "label": label, "amount_rial": round(sum(x["amount_rial"] for x in mine), 2),
                            "count": sum(x["count"] for x in mine), "groups": groups,
                            "last_day_jalali": _jalali(max(rk_days)) if system == "rahkaran" and rk_days else None})
        return {"date_jalali": _jalali(today), "amount_rial": round(sum(x["amount_rial"] for x in rows_out), 2),
                "count": sum(x["count"] for x in rows_out), "systems": systems}
    return _cached(f"today:{date.today().isoformat()}", load)


def _jalali(d: date) -> str:
    import jdatetime

    return jdatetime.date.fromgregorian(date=d).strftime("%Y/%m/%d")
