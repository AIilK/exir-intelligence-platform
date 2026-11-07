"""ماژول «گزارش‌ساز اکسل»: کارپوشه‌های چندبرگه برای ویزیتورها، سرپرست‌ها و هیبریدها.

منابع:
- فروش (داشبورد فروش، /api/report/people): فروش خالص و ناخالص، برگشتی، مشتری خریدار، تعداد SKU و کالا، فاکتور،
  ویزیت ثبت‌شده (= اسناد درخواست کارآمد؛ جدول «عدم سفارش» کارآمد خالی است)، میانگین فروش روزانه، تخفیف حجمی/نقدی/مدیریتی
  و درصد تحقق شعبه (همان «تحقق و پورسانت»)؛ با ارزش افزوده (قابل پرداخت)، مثل گزارش توزیع.
- مالی (کارآمد): مانده حساب مشتریان و چک برگشتی هر ویزیتور (visitor_finance)، مانده هر شعبه (sales-network)
  و فاکتورهای توزیع‌شده/نشده هر هیبرید در ماه‌های بازه (توزیع بار).
مبالغ به ریال. انتخاب زنجیره‌ای هیبرید › سرپرست › ویزیتور (شهر هم پشتیبانی می‌شود)؛ هر برگه هم فیلتر خود اکسل دارد.
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


def _rial(rial: Any) -> float | None:
    try:
        return round(float(rial))
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
    # ویزیتورهایی که در ۳ ماه اخیر زیر یک سرپرست فروخته‌اند ولی در این بازه فروشی ندارند (با فروش صفر)
    have = {str(s.get("key")) for s in people["sellers"]}
    people["idle"] = [dict(r, net=0, gross=0, returns_net=0, customers=0, sku=0, qty=0, invoices=0, req_docs=0, daily_avg=0,
                           city="—", idle=True) for r in people.get("roster") or [] if str(r.get("key")) not in have]
    for s in people["sellers"] + people["idle"]:
        f = vfin.get(str(s.get("key"))) or {}
        s["ar_rial"] = f.get("open_account_receivable_rial")
        s["debtors"] = f.get("debtor_customer_count")
        s["ret_cheque_count"] = f.get("returned_cheque_count")
        s["ret_cheque_rial"] = f.get("returned_cheque_rial")
        s["debtor_list"] = f.get("debtors") or []
        s["cheque_list"] = f.get("returned_cheques") or []
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
        return title, lambda r: _rial(r.get(key)), fmt
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

    def reserve(self, title: str) -> str:
        """نام برگه‌ای که بعداً ساخته می‌شود (برای لینک از کارت سرپرست به کارت ویزیتور)."""
        return self._title(title)

    def card(self, title: str, header: str, metrics: list[tuple[str, Any, str]], sections: list[dict], reserved: bool = False):
        """برگه کارت: سطر عنوان، شاخص‌ها زیر هم (عنوان | مقدار)، بعد جدول‌ها (کالا، ویزیتورها، مطالبات، چک برگشتی)."""
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        ws = self.wb.active if self.first else self.wb.create_sheet()
        self.first = False
        ws.title = title if reserved else self._title(title)
        ws.sheet_view.rightToLeft = True
        ws.append([header])
        ws["A1"].font = Font(bold=True, size=13)
        fmt = {"money": "#,##0", "int": "#,##0", PCT: "0.0%"}
        for label, value, kind in metrics:
            ws.append([label, value])
            ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
            if kind in fmt:
                ws.cell(row=ws.max_row, column=2).number_format = fmt[kind]
        filtered = False
        for sec in sections:
            ws.append([])
            if sec.get("title"):
                ws.append([sec["title"]])
                ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=12)
            ws.append(sec["headers"])
            head = ws.max_row
            for cell in ws[head]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor=sec.get("color", "1F4E78"))
                cell.alignment = Alignment(horizontal="center", wrap_text=True)
            for row in sec["rows"]:
                link = row[0][1] if row and isinstance(row[0], tuple) else None
                ws.append([row[0][0], *row[1:]] if row and isinstance(row[0], tuple) else row)
                r = ws.max_row
                for col in sec.get("money", ()):
                    ws.cell(row=r, column=col).number_format = "#,##0"
                if link:   # (متن، نام برگه مقصد) ← لینک داخلی
                    ws.cell(row=r, column=1).hyperlink = f"#'{link}'!A1"
                    ws.cell(row=r, column=1).font = Font(color="0563C1", underline="single")
            if not sec["rows"]:
                ws.append(["—"])
            elif not filtered:   # فیلتر اکسل روی اولین جدول (هر برگه فقط یک فیلتر دارد)
                ws.auto_filter.ref = f"A{head}:{get_column_letter(len(sec['headers']))}{ws.max_row}"
                filtered = True
        widths = sections and max(len(x["headers"]) for x in sections) or 2
        for k in range(1, max(widths, 2) + 1):
            ws.column_dimensions[get_column_letter(k)].width = 30 if k == 1 else 44 if k == 2 else 17

    def visitor_card(self, v: dict, skus: list[dict], title: str | None = None):
        """یک برگه برای هر ویزیتور: همه شاخص‌ها، کالاهای پرفروش، مانده مطالبات و چک‌های برگشتی به تفکیک مشتری."""
        self.card(title or str(v.get("label") or v.get("key")),
                  f"{v.get('label')} — {v.get('branch') or ''} — سرپرست {v.get('supervisor') or '—'} — {v.get('city') or ''}"
                  + (f" — بدون فروش در این بازه (آخرین فروش {v.get('last_date')})" if v.get("idle") else ""),
                  [(t, get(v), kind) for t, get, kind in VISITOR_COLS[5:]],
                  [{"headers": ["کد کالا", "کالا", "تعداد", "فروش خالص (ریال)"], "money": (3, 4),
                    "rows": [[r.get("product_code"), r.get("product"), r.get("qty"), _rial(r.get("net"))] for r in skus]},
                   {"title": "مانده مطالبات به تفکیک مشتری", "headers": ["کد مشتری", "مشتری", "مانده (ریال)"], "money": (3,), "color": "7F6000",
                    "rows": [[d.get("customer_code"), d.get("customer_name"), _rial(d.get("amount_rial"))] for d in v.get("debtor_list") or []]},
                   {"title": "چک‌های برگشتی", "headers": ["کد مشتری", "مشتری", "سریال", "سررسید", "وضعیت", "مبلغ (ریال)"], "money": (6,),
                    "color": "7F6000",
                    "rows": [[c.get("customer_code"), c.get("customer_name"), c.get("serial"), c.get("due_date_jalali"), c.get("status"),
                              _rial(c.get("amount_rial"))] for c in v.get("cheque_list") or []]}],
                  reserved=title is not None)

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
    applied = " › ".join(f"{k}: {v}" for k, v in (("هیبرید", filters.get("branch")), ("شهر", filters.get("city")), ("سرپرست", filters.get("supervisor")),
                                                  ("ویزیتور", filters.get("visitor"))) if v) or "همه"
    return [f"گزارش {KINDS[kind]} — {date_from} تا {date_to}", f"انتخاب: {applied}", "",
            "مبالغ به ریال و با ارزش افزوده (قابل پرداخت)، همان عدد داشبورد فروش.",
            "ویزیت ثبت‌شده = تعداد اسناد درخواست ثبت‌شده در بازه (کارآمد جدول جداگانه‌ای برای ویزیت بدون سفارش ندارد).",
            "مشتری خریدار = مشتری با فروش خالص مثبت در بازه. تعداد SKU = کالاهای متمایز فروخته‌شده.",
            "میانگین فروش روزانه = فروش خالص ÷ روزهای کاری سپری‌شده؛ پیش‌بینی پایان ماه فقط برای ماه جاری.",
            "مانده حساب و چک برگشتی = وضعیت امروز مشتریان هر ویزیتور در کارآمد (چک برگشتی از ابتدای سال جاری).",
            "تخفیف حجمی/نقدی/مدیریتی = نسبت هر تخفیف به فروش ناخالص.",
            "درصد تحقق شعبه = همان «تحقق و پورسانت»: فروش ناخالص ماه ÷ تارگت سپری‌شده ماه.",
            "شهر هر ویزیتور = شهر غالب مشتریانش (کارآمد برای ویزیتور شهر جدا ندارد).",
            "ردیف «جمع» با فیلتر اکسل خودکار به‌روز می‌شود (SUBTOTAL)."] + extra


SKU_COLS: list[Col] = [("ویزیتور", lambda r: r.get("visitor"), "text"), ("شعبه", lambda r: r.get("branch"), "text"),
                       ("سرپرست", lambda r: r.get("supervisor"), "text"), ("کد کالا", lambda r: r.get("product_code"), "text"),
                       ("کالا", lambda r: r.get("product"), "text"), _col("تعداد", "qty", "int"), _col("فروش خالص", "net")]


def _skus(products: list[dict], visitors: list[dict]) -> list[dict]:
    """پرفروش‌ترین کالاهای همین ویزیتورها (هر ردیف با نام ویزیتور، شعبه و سرپرست)."""
    by = {str(v["key"]): v for v in visitors}
    return [dict(r, visitor=by[str(r["key"])].get("label"), branch=by[str(r["key"])].get("branch"),
                 supervisor=by[str(r["key"])].get("supervisor")) for r in products if str(r.get("key")) in by]


DEBT_COLS: list[Col] = [("ویزیتور", lambda r: r.get("visitor"), "text"), ("شعبه", lambda r: r.get("branch"), "text"),
                        ("سرپرست", lambda r: r.get("supervisor"), "text"), ("کد مشتری", lambda r: r.get("customer_code"), "text"),
                        ("مشتری", lambda r: r.get("customer_name"), "text"), _col("مانده مطالبات", "amount_rial")]
CHEQUE_COLS: list[Col] = [("ویزیتور", lambda r: r.get("visitor"), "text"), ("شعبه", lambda r: r.get("branch"), "text"),
                          ("سرپرست", lambda r: r.get("supervisor"), "text"), ("کد مشتری", lambda r: r.get("customer_code"), "text"),
                          ("مشتری", lambda r: r.get("customer_name"), "text"), ("سریال چک", lambda r: r.get("serial"), "text"),
                          ("سررسید", lambda r: r.get("due_date_jalali"), "text"), ("وضعیت", lambda r: r.get("status"), "text"),
                          _col("مبلغ چک", "amount_rial")]


def _per_customer(visitors: list[dict], field: str) -> list[dict]:
    """ردیف‌های مشتری هر ویزیتور (مانده مطالبات یا چک برگشتی) با نام ویزیتور، شعبه و سرپرست."""
    return [dict(r, visitor=v.get("label"), branch=v.get("branch"), supervisor=v.get("supervisor"))
            for v in visitors for r in v.get(field) or []]


def _customer_sheets(book: "Book", visitors: list[dict]) -> None:
    book.sheet("مطالبات به تفکیک مشتری", DEBT_COLS, _per_customer(visitors, "debtor_list"),
               "مانده مطالبات هر ویزیتور به تفکیک مشتری (وضعیت امروز کارآمد؛ چک برگشتی اول، بعد فاکتورها به ترتیب قدیمی‌ترین)")
    book.sheet("چک‌های برگشتی", CHEQUE_COLS, _per_customer(visitors, "cheque_list"),
               "چک‌های برگشتی تسویه‌نشده مشتریان هر ویزیتور (سررسید از ابتدای سال جاری)")


MAX_CARD_SHEETS = 150


def _team_skus(products: list[dict], visitors: list[dict], limit: int = 40) -> list[list[Any]]:
    """کالاهای پرفروش یک تیم (جمع ۴۰ کالای اول هر ویزیتور)."""
    keys = {str(v["key"]) for v in visitors}
    agg: dict[str, list[Any]] = {}
    for r in products:
        if str(r.get("key")) in keys:
            a = agg.setdefault(str(r.get("product_code")), [r.get("product_code"), r.get("product"), 0.0, 0.0])
            a[2] += float(r.get("qty") or 0)
            a[3] += float(r.get("net") or 0)
    return [[c, n, q, _rial(v)] for c, n, q, v in sorted(agg.values(), key=lambda a: -a[3])[:limit]]


def _supervisor_cards(book: "Book", sups: list[dict], team: dict[str, list[dict]], products: list[dict]) -> bool:
    """برای هر سرپرست: کارت سرپرست (مثل کارت ویزیتور) و بلافاصله کارت همه ویزیتورهایش. False = سقف برگه‌ها پر شد."""
    made = 0
    for s in sups:
        crew = team.get(_norm(s.get("label") or s.get("key")), [])
        if made + 1 + len(crew) > MAX_CARD_SHEETS:
            return False
        name = str(s.get("label") or s.get("key"))
        sheet_names = [book.reserve(str(v.get("label") or v.get("key"))) for v in crew]
        # کارت سرپرست را قبل از رزرو نام ویزیتورها نمی‌سازیم تا لینک‌ها نام درست را داشته باشند
        book.card(f"سرپرست {name}", f"سرپرست {name} — {s.get('branch') or ''} — {s.get('city') or ''}",
                  [(t, get(s), kind) for t, get, kind in SUPERVISOR_COLS[3:]],
                  [{"title": "ویزیتورهای این سرپرست (روی نام بزنید تا کارتش باز شود)",
                    "headers": ["ویزیتور", "فروش خالص", "فروش ناخالص", "مشتری خریدار", "تعداد SKU", "ویزیت ثبت‌شده",
                                "میانگین فروش روزانه", "مانده حساب مشتریان", "چک برگشتی (مبلغ)"], "money": (2, 3, 4, 5, 6, 7, 8, 9),
                    "rows": [[(f"{v.get('label')} (بدون فروش در این بازه)" if v.get("idle") else v.get("label"), sheet_names[k]), _rial(v.get("net")), _rial(v.get("gross")), v.get("customers"), v.get("sku"),
                              v.get("req_docs"), _rial(v.get("daily_avg")), _rial(v.get("ar_rial")), _rial(v.get("ret_cheque_rial"))]
                             for k, v in enumerate(crew)]},
                   {"title": "کالاهای پرفروش تیم", "headers": ["کد کالا", "کالا", "تعداد", "فروش خالص (ریال)"], "money": (3, 4),
                    "rows": _team_skus(products, crew)},
                   {"title": "مانده مطالبات به تفکیک مشتری", "headers": ["ویزیتور", "کد مشتری", "مشتری", "مانده (ریال)"], "money": (4,),
                    "color": "7F6000",
                    "rows": sorted(([v.get("label"), d.get("customer_code"), d.get("customer_name"), _rial(d.get("amount_rial"))]
                                    for v in crew for d in v.get("debtor_list") or []), key=lambda r: -(r[3] or 0))},
                   {"title": "چک‌های برگشتی", "headers": ["ویزیتور", "کد مشتری", "مشتری", "سریال", "سررسید", "وضعیت", "مبلغ (ریال)"],
                    "money": (7,), "color": "7F6000",
                    "rows": [[v.get("label"), c.get("customer_code"), c.get("customer_name"), c.get("serial"), c.get("due_date_jalali"),
                              c.get("status"), _rial(c.get("amount_rial"))] for v in crew for c in v.get("cheque_list") or []]}])
        for k, v in enumerate(crew):
            book.visitor_card(v, [r for r in products if str(r.get("key")) == str(v["key"])], title=sheet_names[k])
        made += 1 + len(crew)
    return True


def _visitor_sheets(book: "Book", products: list[dict], visitors: list[dict]) -> bool:
    """برای هر ویزیتور یک برگه کارت (اگر تعدادشان از سقف برگه‌ها بیشتر نباشد)."""
    if len(visitors) > MAX_PERSON_SHEETS:
        return False
    for v in visitors:
        book.visitor_card(v, [r for r in products if str(r.get("key")) == str(v["key"])])
    return True


def _same(a: Any, b: str | None) -> bool:
    return not b or _norm(a) == _norm(b)


def build(kind: str, date_from: str | None = None, date_to: str | None = None, city: str | None = None,
          supervisor: str | None = None, visitor: str | None = None, branch: str | None = None) -> tuple[bytes, str]:
    """انتخاب زنجیره‌ای: ویزیتورهای «شهر › سرپرست › ویزیتور» دامنه گزارش‌اند؛ گزارش سرپرست/هیبرید همان سرپرستان و
    هیبریدهایی است که این ویزیتورها زیرشان کار می‌کنند (و فقط همین ویزیتورها در ریزشان)."""
    if kind not in KINDS:
        raise KeyError(kind)
    df, dt = default_range()
    date_from, date_to = date_from or df, date_to or dt
    data = load(date_from, date_to)
    p = data["people"]
    sellers = sorted(p["sellers"], key=lambda r: -float(r.get("net") or 0))
    filters = {"city": city, "supervisor": supervisor, "visitor": visitor, "branch": branch}
    # هیبرید (و شهر) فقط برای پیدا کردن سرپرست است: با انتخاب سرپرست، همه ویزیتورهایش در هر هیبریدی (مثل صفحه)
    scope = [v for v in sellers if (supervisor or (_same(v.get("city"), city) and _same(v.get("branch"), branch)))
             and _same(v.get("supervisor"), supervisor) and _same(v.get("label") or v.get("key"), visitor)]
    narrowed = any(filters.values())
    book = Book()

    if kind == "visitors":
        rows = scope
        book.sheet("عملکرد ویزیتورها", VISITOR_COLS, rows, f"عملکرد ویزیتورها {date_from} تا {date_to}")
        products = p.get("seller_products") or []
        book.sheet("ریز SKU هر ویزیتور", SKU_COLS, _skus(products, rows), "۴۰ کالای پرفروش هر ویزیتور در بازه")
        _customer_sheets(book, rows)
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
        cards = _visitor_sheets(book, products, rows)
        book.guide(_guide(kind, date_from, date_to, filters,
                          ["برای هر ویزیتور یک برگه کارت با همه شاخص‌ها و کالاهای پرفروشش ساخته شده است." if cards else
                           f"تعداد ویزیتورها بیش از {MAX_PERSON_SHEETS} است؛ برگه جداگانه هر ویزیتور ساخته نشد (هیبرید یا سرپرست را محدود کنید)."]))

    elif kind == "supervisors":
        # سرپرستانِ انتخاب (شهر › سرپرست › ویزیتور)، ولی تیم هر سرپرست = همه ویزیتورهایش در هر شهری که باشند،
        # به‌علاوه ویزیتورهایی که در ۳ ماه اخیر زیرش فروخته‌اند و در این بازه فروشی ندارند
        chosen = {_norm(v.get("supervisor")) for v in scope}
        team: dict[str, list[dict]] = {}
        for v in sellers + p.get("idle", []):
            if not narrowed or _norm(v.get("supervisor")) in chosen:
                team.setdefault(_norm(v.get("supervisor")), []).append(v)
        sups = [dict(s) for s in p["supervisors"] if not narrowed or _norm(s.get("label") or s.get("key")) in chosen]
        for s in sups:
            s.update(_sum_visitors(team.get(_norm(s.get("label") or s.get("key")), [])))
        sups.sort(key=lambda r: -float(r.get("net") or 0))
        products = p.get("seller_products") or []
        cards = _supervisor_cards(book, sups, team, products)
        book.sheet("سرپرست‌ها", SUPERVISOR_COLS, sups,
                   f"عملکرد سرپرست‌ها {date_from} تا {date_to} (همه اعداد = جمع ویزیتورهای زیرمجموعه هر سرپرست)")
        members = [v for s in sups for v in team.get(_norm(s.get("label") or s.get("key")), [])]
        book.sheet("ویزیتورهای سرپرستان", VISITOR_COLS, members)
        book.sheet("ریز SKU ویزیتورها", SKU_COLS, _skus(products, members), "۴۰ کالای پرفروش هر ویزیتور در بازه")
        _customer_sheets(book, members)
        book.guide(_guide(kind, date_from, date_to, filters,
                          ["تیم هر سرپرست = همه ویزیتورهایی که فاکتورشان به نام همین سرپرست است، در هر شهری، "
                           "به‌علاوه ویزیتورهایی که در ۳ ماه اخیر زیر او فروخته‌اند و در این بازه فروشی ندارند (با فروش صفر).",
                           "برگه اول: کارت سرپرست (همه شاخص‌ها، ویزیتورهایش با لینک به کارت هرکدام، کالاهای پرفروش تیم، "
                           "مانده مطالبات و چک‌های برگشتی به تفکیک مشتری)؛ بعد کارت همه ویزیتورهای همان سرپرست، و در آخر جدول‌های کل."]
                          + ([] if cards else [f"به‌خاطر تعداد زیاد، کارت‌ها فقط برای {MAX_CARD_SHEETS} برگه اول ساخته شد؛ هیبرید یا سرپرست را محدود کنید."])))

    else:
        dist = _distribution(date_from, date_to)
        # اکسل هیبرید همیشه کل شعبه است: هیبریدهای انتخاب (حتی با انتخاب یک سرپرست یا ویزیتور) با همه ویزیتورهایشان
        picked = {_norm(v.get("branch")) for v in scope}
        pool = [v for v in sellers if not narrowed or _norm(v.get("branch")) in picked]
        crew: dict[str, list[dict]] = {}
        for v in pool:
            crew.setdefault(_norm(v.get("branch")), []).append(v)
        hybs = [dict(b) for b in p["branches"] if "هیبرید" in _norm(b.get("label") or b.get("key"))
                and (not narrowed or _norm(b.get("label") or b.get("key")) in crew)]
        sup_by_branch: dict[str, list[dict]] = {}
        for s in p["supervisors"]:
            mine = [v for v in pool if _norm(v.get("supervisor")) == _norm(s.get("label") or s.get("key"))]
            if mine or not narrowed:
                sup_by_branch.setdefault(_norm(s.get("branch")), []).append(dict(s, **_sum_visitors(mine)))
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
        crew_all = [v for k in keys for v in crew.get(k, [])]
        book.sheet("ویزیتورهای هیبریدها", VISITOR_COLS, crew_all)
        book.sheet("ریز SKU ویزیتورها", SKU_COLS, _skus(p.get("seller_products") or [], crew_all), "۴۰ کالای پرفروش هر ویزیتور در بازه")
        _customer_sheets(book, crew_all)
        for b in hybs[:MAX_PERSON_SHEETS]:
            # کارت هر هیبرید: شاخص‌های کل شعبه، همه سرپرستانش (جمع زیرمجموعه هرکدام) و همه ویزیتورهایش
            k = _norm(b.get("label") or b.get("key"))
            team = crew.get(k, [])
            bsups = sorted(sup_by_branch.get(k, []), key=lambda r: -float(r.get("net") or 0))
            book.card(str(b.get("label") or b.get("key")).replace("هیبرید", "").strip() or "هیبرید",
                      f"{b.get('label')} — {len(bsups)} سرپرست، {len(team)} ویزیتور — رتبه تحقق {int(b['ach_rank']) if b.get('ach_rank') else '—'}",
                      [(t, get(b), kind) for i, (t, get, kind) in enumerate(HYBRID_COLS) if i not in (1, 2)],
                      [{"title": "سرپرستان این هیبرید (اعداد هر سرپرست = جمع ویزیتورهای زیرمجموعه‌اش)",
                        "headers": ["سرپرست", "تعداد ویزیتور", "فروش خالص", "فروش ناخالص", "برگشت از فروش", "مشتری خریدار",
                                    "ویزیت ثبت‌شده", "مانده حساب مشتریان", "چک برگشتی (مبلغ)"], "money": (3, 4, 5, 8, 9),
                        "rows": [[s.get("label") or s.get("key"), len([v for v in team if _norm(v.get("supervisor")) == _norm(s.get("label") or s.get("key"))]),
                                  _rial(s.get("net")), _rial(s.get("gross")), _rial(s.get("returns_net")), s.get("customers"), s.get("req_docs"),
                                  _rial(s.get("ar_rial")), _rial(s.get("ret_cheque_rial"))] for s in bsups]},
                       {"title": "ویزیتورهای این هیبرید", "color": "375623",
                        "headers": ["ویزیتور", "سرپرست", "فروش خالص", "فروش ناخالص", "مشتری خریدار", "تعداد SKU", "ویزیت ثبت‌شده",
                                    "مانده حساب مشتریان", "چک برگشتی (مبلغ)"], "money": (3, 4, 8, 9),
                        "rows": [[v.get("label"), v.get("supervisor"), _rial(v.get("net")), _rial(v.get("gross")), v.get("customers"), v.get("sku"),
                                  v.get("req_docs"), _rial(v.get("ar_rial")), _rial(v.get("ret_cheque_rial"))] for v in team]}])
        book.guide(_guide(kind, date_from, date_to, filters,
                          ["فاکتور توزیع‌شده/نشده = جمع ماه‌های بازه از «توزیع بار» (توزیع‌نشده = بدون حواله خروج، برگشتی‌ها کم شده).",
                           "مانده حساب و بستانکاری شعبه = وضعیت امروز همه مشتریان شعبه در کارآمد.",
                           f"برای هر هیبرید (حداکثر {MAX_PERSON_SHEETS}) یک برگه با ریز ویزیتورهایش ساخته شده است.",
                           "اکسل هیبرید اطلاعات کل شعبه است: با انتخاب یک سرپرست یا ویزیتور هم همه سرپرستان و ویزیتورهای همان هیبرید می‌آیند."]))

    tag = re.sub(r'[\/:*?"<>|]+', " ", "-".join(x for x in (branch, city, supervisor, visitor) if x)).strip()
    fname = f"گزارش-{KINDS[kind]}-{date_from.replace('/', '-')}-تا-{date_to.replace('/', '-')}{('-' + tag) if tag else ''}.xlsx"
    return book.bytes(), fname


VISITOR_FIELDS = ("net", "gross", "returns_net", "customers", "sku", "qty", "invoices", "req_docs", "daily_avg", "forecast",
                  "ar_rial", "debtors", "ret_cheque_count", "ret_cheque_rial", "vol_disc_rate", "cash_disc_rate", "mgmt_disc_rate",
                  "branch_ach", "last_date", "seller_code")


def options(date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    """همه ویزیتورها با شهر، سرپرست، شعبه و همه شاخص‌های اکسل ویزیتور (مبالغ ریال)، برای انتخاب زنجیره‌ای و جدول صفحه."""
    df, dt = default_range()
    date_from, date_to = date_from or df, date_to or dt
    try:
        sellers = load(date_from, date_to)["people"]["sellers"]
    except Exception as exc:  # noqa: BLE001
        return {"date_from": date_from, "date_to": date_to, "people": [], "error": str(exc)}
    people = [{"visitor": s.get("label") or s.get("key"), "city": s.get("city") or "—", "supervisor": s.get("supervisor") or "—",
               "branch": s.get("branch") or "—", "net_rial": float(s.get("net") or 0), **{k: s.get(k) for k in VISITOR_FIELDS}}
              for s in sellers]
    people.sort(key=lambda r: -r["net_rial"])
    return {"date_from": date_from, "date_to": date_to, "people": people, "error": None}
