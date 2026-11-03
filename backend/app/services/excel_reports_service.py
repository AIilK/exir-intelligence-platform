"""ماژول «گزارش‌ساز اکسل»: کارپوشه‌های چندبرگه برای ویزیتورها، سرپرست‌ها و هیبریدها.

منابع:
- فروش (داشبورد فروش، /api/report/people): فروش خالص و ناخالص، برگشتی، مشتری خریدار، تعداد SKU و کالا، فاکتور،
  ویزیت ثبت‌شده (= اسناد درخواست کارآمد؛ جدول «عدم سفارش» کارآمد خالی است)، میانگین فروش روزانه، تخفیف حجمی/نقدی/مدیریتی
  و درصد تحقق شعبه (همان «تحقق و پورسانت»)؛ با ارزش افزوده (قابل پرداخت)، مثل گزارش توزیع.
- مالی (کارآمد): مانده حساب مشتریان و چک برگشتی هر ویزیتور (visitor_finance)، مانده هر شعبه (sales-network)
  و فاکتورهای توزیع‌شده/نشده هر هیبرید در ماه‌های بازه (توزیع بار).
مبالغ به تومان. فیلترها: نام شخص (یا شعبه در گزارش هیبرید)، شهر و شعبه؛ هر برگه هم فیلتر خود اکسل دارد.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Callable

import jdatetime

from app.services.manager_combined_service import _sales_api

KINDS = {"visitors": "ویزیتورها", "supervisors": "سرپرست‌ها", "hybrids": "هیبریدها"}
MAX_PERSON_SHEETS = 40


def _norm(s: Any) -> str:
    return " ".join(str(s or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ").split())


def _has(text: Any, needle: str | None) -> bool:
    return not needle or _norm(needle) in _norm(text)


def _toman(rial: Any) -> float | None:
    try:
        return round(float(rial) / 10)
    except (TypeError, ValueError):
        return None


def _months(date_from: str, date_to: str) -> list[tuple[int, int]]:
    y, m = int(date_from[:4]), int(date_from[5:7])
    ty, tm = int(date_to[:4]), int(date_to[5:7])
    out = []
    while (y, m) <= (ty, tm) and len(out) < 24:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def default_range() -> tuple[str, str]:
    t = jdatetime.date.today()
    return f"{t.year}/{t.month:02d}/01", t.strftime("%Y/%m/%d")


# ------------------------------------------------------------------ داده
def load(date_from: str, date_to: str) -> dict[str, Any]:
    if not (re.fullmatch(r"\d{4}/\d{2}/\d{2}", date_from) and re.fullmatch(r"\d{4}/\d{2}/\d{2}", date_to)):
        raise ValueError("تاریخ باید به شکل ۱۴۰۵/۰۸/۰۱ باشد.")
    people = _sales_api("/api/report/people", {"date_from": date_from, "date_to": date_to, "vat": "1"})
    if not people:
        raise RuntimeError("داشبورد فروش در دسترس نیست؛ عملکرد فروش خوانده نشد.")
    from app.services.karamad_sales_network_service import KaramadSalesNetworkService

    net = KaramadSalesNetworkService()
    vfin = {str(v.get("seller_key")): v for v in (net.visitor_finance().get("visitors") or [])}
    branch_debt = {_norm(b["branch_name"]): b for b in (net.overview().get("branches") or [])}
    for s in people["sellers"]:
        f = vfin.get(str(s.get("key"))) or {}
        s["ar_rial"] = f.get("open_account_receivable_rial")
        s["debtors"] = f.get("debtor_customer_count")
        s["ret_cheque_count"] = f.get("returned_cheque_count")
        s["ret_cheque_rial"] = f.get("returned_cheque_rial")
    return {"people": people, "branch_debt": branch_debt}


def _distribution(date_from: str, date_to: str) -> dict[str, dict[str, float]]:
    from app.services.karamad_distribution_service import KaramadDistributionService

    out: dict[str, dict[str, float]] = {}
    svc = KaramadDistributionService()
    for y, m in _months(date_from, date_to):
        for b in svc.monthly(y, m).get("branches") or []:
            d = out.setdefault(_norm(b["branch_name"]), {"distributed": 0.0, "undistributed": 0.0, "undistributed_count": 0})
            d["distributed"] += float(b.get("distributed_rial") or 0)
            d["undistributed"] += float(b.get("undistributed_rial") or 0)
            d["undistributed_count"] += int(b.get("undistributed_count") or 0)
    return out


# ------------------------------------------------------------------ ستون‌ها
Col = tuple[str, Callable[[dict], Any], str]   # عنوان، مقدار، قالب (money / pct / int / text)
PCT = "pct"


def _col(title: str, key: str, fmt: str = "money") -> Col:
    if fmt == "money":
        return title, lambda r: _toman(r.get(key)), fmt
    return title, lambda r: r.get(key), fmt


VISITOR_COLS: list[Col] = [
    ("ویزیتور", lambda r: r.get("label") or r.get("key"), "text"),
    ("کد", lambda r: r.get("seller_code"), "text"),
    ("شعبه", lambda r: r.get("branch"), "text"),
    ("سرپرست", lambda r: r.get("supervisor"), "text"),
    ("شهر", lambda r: r.get("city"), "text"),
    _col("فروش خالص", "net"), _col("فروش ناخالص", "gross"), _col("برگشت از فروش", "returns_net"),
    _col("مشتری خریدار", "customers", "int"), _col("تعداد SKU فروخته‌شده", "sku", "int"), _col("تعداد کالا", "qty", "int"),
    _col("فاکتور", "invoices", "int"), _col("ویزیت ثبت‌شده (درخواست)", "req_docs", "int"),
    _col("میانگین فروش روزانه", "daily_avg"), _col("پیش‌بینی پایان ماه", "forecast"),
    _col("مانده حساب مشتریان", "ar_rial"), _col("مشتری بدهکار", "debtors", "int"),
    _col("چک برگشتی (تعداد)", "ret_cheque_count", "int"), _col("چک برگشتی (مبلغ)", "ret_cheque_rial"),
    _col("تخفیف حجمی", "vol_disc_rate", PCT), _col("تخفیف نقدی", "cash_disc_rate", PCT), _col("تخفیف مدیریتی", "mgmt_disc_rate", PCT),
    _col("درصد تحقق شعبه", "branch_ach", PCT), ("آخرین فروش", lambda r: r.get("last_date"), "text"),
]


def _sum_visitors(rows: list[dict]) -> dict[str, float]:
    keys = ("ar_rial", "debtors", "ret_cheque_count", "ret_cheque_rial")
    return {k: sum(float(r.get(k) or 0) for r in rows) for k in keys} | {"visitor_count": len(rows)}


SUPERVISOR_COLS: list[Col] = [
    ("سرپرست", lambda r: r.get("label") or r.get("key"), "text"),
    ("شعبه", lambda r: r.get("branch"), "text"),
    ("شهر", lambda r: r.get("city"), "text"),
    _col("تعداد ویزیتور", "visitor_count", "int"),
    _col("فروش خالص", "net"), _col("فروش ناخالص", "gross"), _col("برگشت از فروش", "returns_net"),
    _col("مشتری خریدار", "customers", "int"), _col("تعداد SKU", "sku", "int"), _col("تعداد کالا", "qty", "int"),
    _col("ویزیت ثبت‌شده (درخواست)", "req_docs", "int"), _col("میانگین فروش روزانه", "daily_avg"),
    _col("درصد تحقق شعبه", "branch_ach", PCT), _col("تارگت ماه شعبه", "branch_target_rial"),
    _col("تخفیف حجمی", "vol_disc_rate", PCT), _col("تخفیف نقدی", "cash_disc_rate", PCT), _col("تخفیف مدیریتی", "mgmt_disc_rate", PCT),
    _col("مانده حساب مشتریان ویزیتورها", "ar_rial"), _col("چک برگشتی (تعداد)", "ret_cheque_count", "int"),
    _col("چک برگشتی (مبلغ)", "ret_cheque_rial"),
]

HYBRID_COLS: list[Col] = [
    _col("رتبه تحقق", "ach_rank", "int"),
    ("هیبرید", lambda r: r.get("label") or r.get("key"), "text"),
    ("شهر", lambda r: r.get("city"), "text"),
    _col("درصد تحقق", "branch_ach", PCT), _col("تارگت ماه", "branch_target_rial"),
    _col("فروش خالص", "net"), _col("فروش ناخالص", "gross"), _col("برگشت از فروش", "returns_net"),
    _col("مشتری خریدار", "customers", "int"), _col("تعداد ویزیتور", "visitor_count", "int"), _col("تعداد SKU", "sku", "int"),
    _col("ویزیت ثبت‌شده (درخواست)", "req_docs", "int"), _col("میانگین فروش روزانه", "daily_avg"),
    _col("فاکتور توزیع‌شده (مبلغ)", "distributed"), _col("فاکتور توزیع‌نشده (مبلغ)", "undistributed"),
    _col("فاکتور توزیع‌نشده (تعداد)", "undistributed_count", "int"),
    _col("مانده حساب مشتریان شعبه", "branch_ar"), _col("بستانکاری مشتریان", "branch_credit"),
    _col("چک برگشتی (تعداد)", "ret_cheque_count", "int"), _col("چک برگشتی (مبلغ)", "ret_cheque_rial"),
    _col("تخفیف حجمی", "vol_disc_rate", PCT), _col("تخفیف نقدی", "cash_disc_rate", PCT), _col("تخفیف مدیریتی", "mgmt_disc_rate", PCT),
]


# ------------------------------------------------------------------ کارپوشه
class Book:
    def __init__(self):
        from openpyxl import Workbook

        self.wb = Workbook()
        self.first = True
        self.names: set[str] = set()

    def _title(self, title: str) -> str:
        base = re.sub(r"[\[\]:*?/\\]", " ", title).strip()[:31] or "برگه"
        name, i = base, 2
        while name in self.names:
            name = f"{base[:27]} ({i})"
            i += 1
        self.names.add(name)
        return name

    def sheet(self, title: str, cols: list[Col], rows: list[dict], note: str | None = None, total: bool = True):
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        ws = self.wb.active if self.first else self.wb.create_sheet()
        self.first = False
        ws.title = self._title(title)
        ws.sheet_view.rightToLeft = True
        start = 1
        if note:
            ws.append([note])
            ws["A1"].font = Font(italic=True, color="555555")
            start = 2
        ws.append(["ردیف"] + [c[0] for c in cols])
        for cell in ws[start]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[start].height = 34
        for i, r in enumerate(rows, 1):
            ws.append([i] + [c[1](r) for c in cols])
        last = start + len(rows)
        if total and rows:
            sums = ["جمع"]
            for j, c in enumerate(cols, 2):
                letter = get_column_letter(j)
                sums.append(f"=SUBTOTAL(9,{letter}{start + 1}:{letter}{last})" if c[2] in ("money", "int") and j > 2 else None)
            ws.append(sums)
            for cell in ws[last + 1]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="DDEBF7")
        for j, c in enumerate(cols, 2):
            letter = get_column_letter(j)
            fmt = {"money": "#,##0", "int": "#,##0", PCT: "0.0%"}.get(c[2])
            if fmt:
                for row in ws.iter_rows(min_row=start + 1, max_row=last + 1, min_col=j, max_col=j):
                    row[0].number_format = fmt
            ws.column_dimensions[letter].width = 22 if c[2] == "text" else 16
        ws.column_dimensions["A"].width = 6
        ws.freeze_panes = ws.cell(row=start + 1, column=3)
        ws.auto_filter.ref = f"A{start}:{get_column_letter(len(cols) + 1)}{max(last, start + 1)}"

    def guide(self, lines: list[str]):
        from openpyxl.styles import Font

        ws = self.wb.create_sheet(self._title("راهنما"))
        ws.sheet_view.rightToLeft = True
        for line in lines:
            ws.append([line])
        ws["A1"].font = Font(bold=True, size=13)
        ws.column_dimensions["A"].width = 120

    def bytes(self) -> bytes:
        buf = BytesIO()
        self.wb.save(buf)
        return buf.getvalue()


def _guide(kind: str, date_from: str, date_to: str, filters: dict[str, str | None], extra: list[str]) -> list[str]:
    applied = "، ".join(f"{k}: {v}" for k, v in (("نام", filters.get("name")), ("شهر", filters.get("city")), ("شعبه", filters.get("branch"))) if v) or "بدون فیلتر"
    return [f"گزارش {KINDS[kind]} — {date_from} تا {date_to}", f"فیلتر: {applied}", "",
            "مبالغ به تومان و با ارزش افزوده (قابل پرداخت)، همان عدد داشبورد فروش.",
            "ویزیت ثبت‌شده = تعداد اسناد درخواست ثبت‌شده تا تاریخ پایان بازه (کارآمد جدول جداگانه‌ای برای ویزیت بدون سفارش ندارد).",
            "مشتری خریدار = مشتری با فروش خالص مثبت در بازه. تعداد SKU = کالاهای متمایز فروخته‌شده.",
            "میانگین فروش روزانه = فروش خالص ÷ روزهای کاری سپری‌شده؛ پیش‌بینی پایان ماه فقط برای ماه جاری.",
            "مانده حساب و چک برگشتی = وضعیت امروز مشتریان هر ویزیتور در کارآمد (چک برگشتی از ابتدای سال جاری).",
            "تخفیف حجمی/نقدی/مدیریتی = نسبت هر تخفیف به فروش ناخالص.",
            "درصد تحقق شعبه = همان «تحقق و پورسانت»: فروش ناخالص ماه ÷ تارگت سپری‌شده ماه.",
            "ردیف «جمع» با فیلتر اکسل خودکار به‌روز می‌شود (SUBTOTAL)."] + extra


def build(kind: str, date_from: str | None = None, date_to: str | None = None,
          name: str | None = None, city: str | None = None, branch: str | None = None) -> tuple[bytes, str]:
    if kind not in KINDS:
        raise KeyError(kind)
    df, dt = default_range()
    date_from, date_to = date_from or df, date_to or dt
    data = load(date_from, date_to)
    p = data["people"]
    sellers = sorted(p["sellers"], key=lambda r: -float(r.get("net") or 0))
    filters = {"name": name, "city": city, "branch": branch}
    book = Book()

    if kind == "visitors":
        rows = [s for s in sellers if _has(s.get("label") or s.get("key"), name) and _has(s.get("city"), city) and _has(s.get("branch"), branch)]
        book.sheet("عملکرد ویزیتورها", VISITOR_COLS, rows, f"عملکرد ویزیتورها {date_from} تا {date_to}")
        keys = {str(s["key"]) for s in rows}
        names = {str(s["key"]): s for s in rows}
        sku = [dict(r, visitor=names[str(r["key"])].get("label"), branch=names[str(r["key"])].get("branch"))
               for r in p.get("seller_products") or [] if str(r.get("key")) in keys]
        book.sheet("ریز SKU هر ویزیتور", [("ویزیتور", lambda r: r.get("visitor"), "text"), ("شعبه", lambda r: r.get("branch"), "text"),
                                         ("کد کالا", lambda r: r.get("product_code"), "text"), ("کالا", lambda r: r.get("product"), "text"),
                                         _col("تعداد", "qty", "int"), _col("فروش خالص", "net")], sku,
                   "۴۰ کالای پرفروش هر ویزیتور در بازه")
        by_branch: dict[str, list[dict]] = {}
        for s in rows:
            by_branch.setdefault(s.get("branch") or "—", []).append(s)
        agg = [dict(label=b, net=sum(float(x.get("net") or 0) for x in v), gross=sum(float(x.get("gross") or 0) for x in v),
                    customers=sum(float(x.get("customers") or 0) for x in v), req_docs=sum(float(x.get("req_docs") or 0) for x in v),
                    **_sum_visitors(v)) for b, v in by_branch.items()]
        book.sheet("جمع به تفکیک شعبه", [("شعبه", lambda r: r.get("label"), "text"), _col("تعداد ویزیتور", "visitor_count", "int"),
                                        _col("فروش خالص", "net"), _col("فروش ناخالص", "gross"), _col("مشتری خریدار (جمع ویزیتورها)", "customers", "int"),
                                        _col("ویزیت ثبت‌شده", "req_docs", "int"), _col("مانده حساب مشتریان", "ar_rial"),
                                        _col("چک برگشتی (مبلغ)", "ret_cheque_rial")], sorted(agg, key=lambda r: -r["net"]))
        book.guide(_guide(kind, date_from, date_to, filters, []))

    elif kind == "supervisors":
        sups = [dict(s) for s in p["supervisors"] if _has(s.get("label") or s.get("key"), name) and _has(s.get("city"), city) and _has(s.get("branch"), branch)]
        team: dict[str, list[dict]] = {}
        for s in sellers:
            team.setdefault(_norm(s.get("supervisor")), []).append(s)
        for s in sups:
            s.update(_sum_visitors(team.get(_norm(s.get("label") or s.get("key")), [])))
        sups.sort(key=lambda r: -float(r.get("net") or 0))
        book.sheet("سرپرست‌ها", SUPERVISOR_COLS, sups, f"عملکرد سرپرست‌ها {date_from} تا {date_to} (جمع ویزیتورهای هر سرپرست)")
        members = [v for s in sups for v in team.get(_norm(s.get("label") or s.get("key")), [])]
        book.sheet("ویزیتورهای سرپرستان", VISITOR_COLS, members)
        for s in sups[:MAX_PERSON_SHEETS]:
            book.sheet(str(s.get("label") or s.get("key")), VISITOR_COLS, team.get(_norm(s.get("label") or s.get("key")), []),
                       f"سرپرست {s.get('label')} — {s.get('branch') or ''} — تحقق شعبه {round(float(s.get('branch_ach') or 0) * 100, 1)}٪")
        book.guide(_guide(kind, date_from, date_to, filters,
                          [f"برای هر سرپرست (حداکثر {MAX_PERSON_SHEETS} سرپرست پرفروش) یک برگه با ریز ویزیتورهایش ساخته شده است."]))

    else:
        dist = _distribution(date_from, date_to)
        hybs = [dict(b) for b in p["branches"] if "هیبرید" in _norm(b.get("label") or b.get("key"))
                and _has(b.get("label") or b.get("key"), name or branch) and _has(b.get("city"), city)]
        crew: dict[str, list[dict]] = {}
        for s in sellers:
            crew.setdefault(_norm(s.get("branch")), []).append(s)
        sup_by_branch: dict[str, list[dict]] = {}
        for s in p["supervisors"]:
            sup_by_branch.setdefault(_norm(s.get("branch")), []).append(dict(s, **_sum_visitors([v for v in sellers if _norm(v.get("supervisor")) == _norm(s.get("label") or s.get("key"))])))
        for b in hybs:
            k = _norm(b.get("label") or b.get("key"))
            b.update(_sum_visitors(crew.get(k, [])))
            b.update(dist.get(k, {}))
            debt = (data["branch_debt"].get(k) or {}).get("debt") or {}
            b["branch_ar"], b["branch_credit"] = debt.get("open_account_receivable_rial"), debt.get("customer_credit_rial")
        hybs.sort(key=lambda r: (r.get("ach_rank") is None, r.get("ach_rank") or 0, -float(r.get("net") or 0)))
        book.sheet("هیبریدها", HYBRID_COLS, hybs, f"عملکرد هیبریدها {date_from} تا {date_to} — مرتب بر اساس رتبه درصد تحقق")
        keys = [_norm(b.get("label") or b.get("key")) for b in hybs]
        book.sheet("سرپرستان هیبریدها", SUPERVISOR_COLS, [s for k in keys for s in sup_by_branch.get(k, [])])
        book.sheet("ویزیتورهای هیبریدها", VISITOR_COLS, [v for k in keys for v in crew.get(k, [])])
        for b in hybs[:MAX_PERSON_SHEETS]:
            k = _norm(b.get("label") or b.get("key"))
            book.sheet(str(b.get("label") or b.get("key")).replace("هیبرید", "").strip() or "هیبرید", VISITOR_COLS, crew.get(k, []),
                       f"{b.get('label')} — رتبه تحقق {int(b['ach_rank']) if b.get('ach_rank') else '—'} — تحقق {round(float(b.get('branch_ach') or 0) * 100, 1)}٪"
                       f" — توزیع‌نشده {int(b.get('undistributed_count') or 0)} فاکتور")
        book.guide(_guide(kind, date_from, date_to, filters,
                          ["فاکتور توزیع‌شده/نشده = جمع ماه‌های بازه از «توزیع بار» (توزیع‌نشده = بدون حواله خروج، برگشتی‌ها کم شده).",
                           "مانده حساب و بستانکاری شعبه = وضعیت امروز مشتریان شعبه در کارآمد.",
                           f"برای هر هیبرید (حداکثر {MAX_PERSON_SHEETS}) یک برگه با ریز ویزیتورهایش ساخته شده است."]))

    tag = "-".join(x for x in (name, city, branch) if x)
    fname = f"گزارش-{KINDS[kind]}-{date_from.replace('/', '-')}-تا-{date_to.replace('/', '-')}{('-' + tag) if tag else ''}.xlsx"
    return book.bytes(), fname


def options(date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    """فهرست نام‌ها، شهرها و شعبه‌ها برای فیلترهای صفحه."""
    df, dt = default_range()
    date_from, date_to = date_from or df, date_to or dt
    p = _sales_api("/api/report/people", {"date_from": date_from, "date_to": date_to, "vat": "1"}) or {}
    uniq = lambda xs: sorted({str(x) for x in xs if x})  # noqa: E731
    sellers, sups, brs = p.get("sellers") or [], p.get("supervisors") or [], p.get("branches") or []
    return {"date_from": date_from, "date_to": date_to,
            "visitors": uniq(s.get("label") for s in sellers), "supervisors": uniq(s.get("label") for s in sups),
            "branches": uniq(b.get("label") for b in brs), "hybrids": uniq(b.get("label") for b in brs if "هیبرید" in _norm(b.get("label"))),
            "cities": uniq([s.get("city") for s in sellers] + [b.get("city") for b in brs])}
