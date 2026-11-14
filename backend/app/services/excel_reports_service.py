"""ماژول «گزارش‌ساز اکسل»: کارپوشه‌های چندبرگه برای ویزیتورها، سرپرست‌ها و هیبریدها.

منابع:
- فروش (داشبورد فروش، /api/report/people): فروش خالص و ناخالص، برگشتی، مشتری خریدار، تعداد گروه کالا و کالا، فاکتور،
  ویزیت ثبت‌شده (= اسناد درخواست کارآمد)، میانگین فروش روزانه، تخفیف حجمی/نقدی/مدیریتی و درصد تحقق شعبه؛
  با ارزش افزوده (قابل پرداخت)، مثل گزارش توزیع. کالاها همه‌جا به تفکیک «گروه کالا» می‌آیند، نه SKU.
- صفحه پورسانت (همان پاسخ): «لیست ویزیتور و سرپرست» ماه پایان بازه و تارگت هر ویزیتور. هر ویزیتور/سرپرستی که در
  لیست آن ماه نیست و ۹۰ روز در کارآمد فاکتور یا درخواستی ندارد «غیرفعال» علامت می‌خورد (ردیف رنگی)؛ نفر تازه لیست بدون فروش هم با فروش صفر می‌آید.
  درصد تحقق ویزیتور = فروش ناخالص ماه ÷ تارگت تا امروز (همان صفحه پورسانت)؛ سرپرست = جمع ویزیتورهای تارگت‌دار تیمش.
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
INACTIVE = "غیرفعال"
INACTIVE_FILL = "F4CCCC"   # رنگ ردیف افراد غیرفعال
# غیرفعال = بیرون از لیست ویزیتور و سرپرست ماه و بدون هیچ فاکتور یا درخواستی در کارآمد در این تعداد روز تا پایان بازه
INACTIVE_DAYS = 90
INACTIVE_TEXT = f"در لیست ماه نیست و {INACTIVE_DAYS} روز در کارآمد فعالیتی ندارد"


def _days_before(jdate: str, days: int) -> str:
    y, m, d = (int(x) for x in jdate.split("/"))
    return (jdatetime.date(y, m, d) - jdatetime.timedelta(days=days)).strftime("%Y/%m/%d")


def _norm(s: Any) -> str:
    return " ".join(str(s or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ").replace("\xa0", " ").split())


def _bkey(s: Any) -> str:
    """«هیبریدی مازندران» در کارآمد = «هیبرید مازندران» در لیست."""
    return re.sub(r"^هیبریدی(?= )", "هیبرید", _norm(s))


def _pname(s: Any) -> str:
    """نام شخص برای مقایسه: بدون شماره تلفن، خط تیره و اسلش."""
    t = _norm(s).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    t = re.sub(r"[-/]?\s*0?9\d{9}", " ", t)
    return " ".join(re.sub(r"[-/]", " ", t).split())


def _same_person(a: Any, b: Any) -> bool:
    x, y = _pname(a), _pname(b)
    return bool(x and y) and (x == y or (len(x) >= 4 and x in y) or (len(y) >= 4 and y in x))


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
def _status(r: dict) -> str:
    note = f" — {r['roster_note']}" if r.get("roster_note") else ""
    if r.get("inactive"):
        return f"{INACTIVE} ({INACTIVE_TEXT})"
    if r.get("new_hire"):
        return f"فعال، تازه (اولین فروش {r['new_hire']}، بعد از لیست)"
    if r.get("idle"):
        return f"فعال، بدون فروش در بازه{note}"
    return f"فعال{note}"


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
    zero = dict(net=0, gross=0, returns_net=0, customers=0, sku=0, groups_n=0, qty=0, invoices=0, req_docs=0, daily_avg=0, city="—", idle=True)
    # ویزیتورهایی که در ۳ ماه اخیر زیر یک سرپرست فروخته‌اند ولی در این بازه فروشی ندارند (با فروش صفر)
    have = {str(s.get("key")) for s in people["sellers"]}
    people["idle"] = [dict(r, **zero) for r in people.get("roster") or [] if str(r.get("key")) not in have]
    have |= {str(r.get("key")) for r in people["idle"]}

    # «لیست ویزیتور و سرپرست» ماه پایان بازه (صفحه پورسانت): فعال/غیرفعال و نفرات تازه لیست بدون فروش
    listed = people.get("listed") or []
    has_roster = bool(people.get("roster_month") and listed)
    active_keys = {str(v["key"]) for v in listed if v.get("key") is not None}
    # فقط شعبه‌هایی که در لیست هستند سنجیده می‌شوند (زنجیره‌ای، اینترنتی و … در لیست ویزیتور و سرپرست نیستند)
    roster_branches = {_bkey(v.get("branch")) for v in listed}
    # کد لیست گاهی با کد کارآمد فرق دارد (مثلاً کد قدیمی): هم‌نام در همان شعبه هم فعال حساب می‌شود
    by_branch_name: dict[str, list[str]] = {}
    for v in listed:
        by_branch_name.setdefault(_bkey(v.get("branch")), []).append(v.get("label"))
    for s in people["sellers"] + people["idle"]:
        if any(_same_person(s.get("label"), n) for n in by_branch_name.get(_bkey(s.get("branch")), ())):
            active_keys.add(str(s.get("key")))
    seller_names = {}
    for s in people["sellers"] + people["idle"]:
        seller_names.setdefault(_bkey(s.get("branch")), []).append(s.get("label"))
    branch_label = {_bkey(s.get("branch")): s.get("branch") for s in people["sellers"] + people["idle"] if s.get("branch")}
    sup_labels = {}
    for s in people["sellers"] + people["idle"]:
        if s.get("supervisor"):
            sup_labels.setdefault(_bkey(s.get("branch")), set()).add(s["supervisor"])
    note_of = {str(v["key"]): v.get("note") for v in listed if v.get("key") is not None and v.get("note")}
    people["listed_idle"] = []
    for v in listed:
        k = str(v["key"]) if v.get("key") is not None else None
        if k and k in have:
            continue
        if any(_same_person(n, v.get("label")) for n in seller_names.get(_bkey(v.get("branch")), ())):
            continue   # همین شخص با کد دیگری در کارآمد فروش دارد
        b = branch_label.get(_bkey(v.get("branch")), v.get("branch"))
        sup = v.get("supervisor")
        hit = [s for s in sup_labels.get(_bkey(v.get("branch")), ()) if _same_person(s, sup)]
        row = dict(zero, key=k or f"لیست:{b}:{v.get('label')}", label=v.get("label"), branch=b, seller_code=v.get("seller_code"),
                   supervisor=hit[0] if len(hit) == 1 else sup, roster_note=v.get("note") or "", listed_only=True)
        people["listed_idle"].append(row)
        have.add(row["key"])

    targets = people.get("targets") or {}
    listed_sups = people.get("listed_supervisors") or []
    # مبنای لیست (مثلاً مهر): هر کس بیرون از لیست که اولین فروشش از شروع این ماه به بعد است، نفر تازه و فعال است
    base_start = f"{people['roster_base']}/01" if people.get("roster_base") else None
    first_sale = people.get("first_sale") or {}
    for s in people["sellers"] + people["idle"]:   # حساب فروش خود سرپرستِ لیست هم فعال است
        if any(_same_person(s.get("label"), n) for n in listed_sups):
            active_keys.add(str(s.get("key")))
    # غیرفعال فقط کسی است که در کارآمد هم مدتی فعالیت نداشته: نبودن در لیست ماه به‌تنهایی غیرفعال نمی‌کند
    cutoff = _days_before(date_to, INACTIVE_DAYS)
    last_act = people.get("last_activity") or {}
    sup_last = people.get("supervisor_last_activity") or {}
    stale = lambda d: not d or d < cutoff  # noqa: E731
    for s in people["sellers"] + people["idle"] + people["listed_idle"]:
        k = str(s.get("key"))
        f = vfin.get(k) or {}
        s["ar_rial"] = f.get("open_account_receivable_rial")
        s["debtors"] = f.get("debtor_customer_count")
        s["ret_cheque_count"] = f.get("returned_cheque_count")
        s["ret_cheque_rial"] = f.get("returned_cheque_rial")
        s["debtor_list"] = f.get("debtors") or []
        s["cheque_list"] = f.get("returned_cheques") or []
        s.update(targets.get(k) or {})
        s.setdefault("roster_note", note_of.get(k, ""))
        unlisted = has_roster and not s.get("listed_only") and k not in active_keys and _bkey(s.get("branch")) in roster_branches
        fs = first_sale.get(k)
        new = bool(unlisted and base_start and fs and fs >= base_start)
        s["new_hire"] = fs if new else None
        s["inactive"] = unlisted and not new and stale(last_act.get(k))
        s["status"] = _status(s)
    for s in people["supervisors"]:
        s["inactive"] = (has_roster and _bkey(s.get("branch")) in roster_branches
                         and not any(_same_person(s.get("label") or s.get("key"), n) for n in listed_sups)
                         and stale(sup_last.get(str(s.get("key")))))
        s["status"] = f"{INACTIVE} ({INACTIVE_TEXT})" if s["inactive"] else "فعال"
    return {"people": people, "branch_debt": branch_debt, "has_roster": has_roster}


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


TARGET_COLS: list[Col] = [_col("تارگت ماه", "target_rial"), _col("تارگت تا امروز", "target_day"),
                          _col("فروش ناخالص ماه (مبنای تحقق)", "target_gross"), _col("درصد تحقق", "target_ach", PCT)]

VISITOR_COLS: list[Col] = [
    ("ویزیتور", lambda r: r.get("label") or r.get("key"), "text"),
    ("وضعیت", lambda r: r.get("status"), "text"),
    ("کد", lambda r: r.get("seller_code"), "text"),
    ("شعبه", lambda r: r.get("branch"), "text"),
    ("سرپرست", lambda r: r.get("supervisor"), "text"),
    ("شهر", lambda r: r.get("city"), "text"),
    _col("فروش خالص", "net"), _col("فروش ناخالص", "gross"), _col("برگشت از فروش", "returns_net"),
    *TARGET_COLS,
    _col("مشتری خریدار", "customers", "int"), _col("تعداد گروه کالای فروخته‌شده", "groups_n", "int"), _col("تعداد کالا", "qty", "int"),
    _col("فاکتور", "invoices", "int"), _col("ویزیت ثبت‌شده (درخواست)", "req_docs", "int"),
    _col("میانگین فروش روزانه", "daily_avg"), _col("پیش‌بینی پایان ماه", "forecast"),
    _col("مانده حساب مشتریان", "ar_rial"), _col("مشتری بدهکار", "debtors", "int"),
    _col("چک برگشتی (تعداد)", "ret_cheque_count", "int"), _col("چک برگشتی (مبلغ)", "ret_cheque_rial"),
    _col("تخفیف حجمی", "vol_disc_rate", PCT), _col("تخفیف نقدی", "cash_disc_rate", PCT), _col("تخفیف مدیریتی", "mgmt_disc_rate", PCT),
    _col("درصد تحقق شعبه", "branch_ach", PCT), ("آخرین فروش", lambda r: r.get("last_date"), "text"),
]
VISITOR_TEXT = 6   # ستون‌های متنی اول (در کارت، شاخص‌ها از بعد از این‌ها)


def _sum_visitors(rows: list[dict]) -> dict[str, float]:
    keys = ("ar_rial", "debtors", "ret_cheque_count", "ret_cheque_rial")
    out = {k: sum(float(r.get(k) or 0) for r in rows) for k in keys} | {"visitor_count": len(rows)}
    # تحقق تیم = جمع فروش ناخالص ماه ویزیتورهای تارگت‌دار ÷ جمع تارگت تا امروزشان
    tg = [r for r in rows if r.get("target_day")]
    if tg:
        day = sum(float(r["target_day"]) for r in tg)
        gross = sum(float(r.get("target_gross") or 0) for r in tg)
        out |= {"target_rial": sum(float(r.get("target_rial") or 0) for r in tg), "target_day": day, "target_gross": gross,
                "target_ach": gross / day if day else None, "target_visitors": len(tg)}
    else:
        out |= {"target_rial": None, "target_day": None, "target_gross": None, "target_ach": None, "target_visitors": 0}
    return out


SUPERVISOR_COLS: list[Col] = [
    ("سرپرست", lambda r: r.get("label") or r.get("key"), "text"),
    ("وضعیت", lambda r: r.get("status"), "text"),
    ("شعبه", lambda r: r.get("branch"), "text"),
    ("شهر", lambda r: r.get("city"), "text"),
    _col("تعداد ویزیتور", "visitor_count", "int"),
    _col("فروش خالص", "net"), _col("فروش ناخالص", "gross"), _col("برگشت از فروش", "returns_net"),
    _col("ویزیتور تارگت‌دار", "target_visitors", "int"), *TARGET_COLS,
    _col("مشتری خریدار", "customers", "int"), _col("تعداد گروه کالا", "groups_n", "int"), _col("تعداد کالا", "qty", "int"),
    _col("ویزیت ثبت‌شده (درخواست)", "req_docs", "int"), _col("میانگین فروش روزانه", "daily_avg"),
    _col("درصد تحقق شعبه", "branch_ach", PCT), _col("تارگت ماه شعبه", "branch_target_rial"),
    _col("تخفیف حجمی", "vol_disc_rate", PCT), _col("تخفیف نقدی", "cash_disc_rate", PCT), _col("تخفیف مدیریتی", "mgmt_disc_rate", PCT),
    _col("مانده حساب مشتریان ویزیتورها", "ar_rial"), _col("چک برگشتی (تعداد)", "ret_cheque_count", "int"),
    _col("چک برگشتی (مبلغ)", "ret_cheque_rial"),
]
SUPERVISOR_TEXT = 4

HYBRID_COLS: list[Col] = [
    _col("رتبه تحقق", "ach_rank", "int"),
    ("هیبرید", lambda r: r.get("label") or r.get("key"), "text"),
    ("شهر", lambda r: r.get("city"), "text"),
    _col("درصد تحقق", "branch_ach", PCT), _col("تارگت ماه", "branch_target_rial"),
    _col("فروش خالص", "net"), _col("فروش ناخالص", "gross"), _col("برگشت از فروش", "returns_net"),
    _col("مشتری خریدار", "customers", "int"), _col("تعداد ویزیتور", "visitor_count", "int"), _col("تعداد گروه کالا", "groups_n", "int"),
    _col("ویزیت ثبت‌شده (درخواست)", "req_docs", "int"), _col("میانگین فروش روزانه", "daily_avg"),
    _col("فاکتور توزیع‌شده (مبلغ)", "distributed"), _col("فاکتور توزیع‌نشده (مبلغ)", "undistributed"),
    _col("فاکتور توزیع‌نشده (تعداد)", "undistributed_count", "int"),
    _col("مانده حساب مشتریان شعبه", "branch_ar"), _col("بستانکاری مشتریان", "branch_credit"),
    _col("چک برگشتی (تعداد)", "ret_cheque_count", "int"), _col("چک برگشتی (مبلغ)", "ret_cheque_rial"),
    _col("تخفیف حجمی", "vol_disc_rate", PCT), _col("تخفیف نقدی", "cash_disc_rate", PCT), _col("تخفیف مدیریتی", "mgmt_disc_rate", PCT),
]

FMT = {"money": "#,##0", "int": "#,##0", PCT: "0.0%"}


def _fill_row(ws, row: int, ncols: int, start_col: int = 1, color: str = INACTIVE_FILL) -> None:
    from openpyxl.styles import PatternFill

    for c in range(start_col, start_col + ncols):
        ws.cell(row=row, column=c).fill = PatternFill("solid", fgColor=color)


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

    def _ws(self, title: str, reserved: bool = False):
        ws = self.wb.active if self.first else self.wb.create_sheet()
        self.first = False
        ws.title = title if reserved else self._title(title)
        ws.sheet_view.rightToLeft = True
        return ws

    def sheet(self, title: str, cols: list[Col], rows: list[dict], note: str | None = None, total: bool = True):
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        ws = self._ws(title)
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
            if r.get("inactive"):
                _fill_row(ws, ws.max_row, len(cols) + 1)
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
            fmt = FMT.get(c[2])
            if fmt:
                for row in ws.iter_rows(min_row=start + 1, max_row=last + 1, min_col=j, max_col=j):
                    row[0].number_format = fmt
            ws.column_dimensions[letter].width = 22 if c[2] == "text" else 16
        ws.column_dimensions["A"].width = 6
        ws.freeze_panes = ws.cell(row=start + 1, column=3)
        ws.auto_filter.ref = f"A{start}:{get_column_letter(len(cols) + 1)}{max(last, start + 1)}"

    def side_by_side(self, title: str, blocks: list[tuple[str, list[Col], list[dict], str]]):
        """چند جدول در یک برگه، کنار هم (با یک ستون خالی بین‌شان)؛ هر جدول عنوان، سرستون و ردیف جمع خودش را دارد.
        blocks: (عنوان، ستون‌ها، ردیف‌ها، رنگ سرستون)."""
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        ws = self._ws(title)
        col0 = 1
        for bi, (btitle, cols, rows, color) in enumerate(blocks):
            ws.cell(row=1, column=col0, value=btitle).font = Font(bold=True, size=12)
            heads = ["ردیف"] + [c[0] for c in cols]
            for j, h in enumerate(heads):
                cell = ws.cell(row=2, column=col0 + j, value=h)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor=color)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for i, r in enumerate(rows, 1):
                ws.cell(row=2 + i, column=col0, value=i)
                for j, c in enumerate(cols, 1):
                    cell = ws.cell(row=2 + i, column=col0 + j, value=c[1](r))
                    if FMT.get(c[2]):
                        cell.number_format = FMT[c[2]]
                if r.get("inactive"):
                    _fill_row(ws, 2 + i, len(heads), col0)
            last = 2 + len(rows)
            if rows:
                ws.cell(row=last + 1, column=col0, value="جمع").font = Font(bold=True)
                for j, c in enumerate(cols, 1):
                    cell = ws.cell(row=last + 1, column=col0 + j)
                    if c[2] in ("money", "int"):
                        letter = get_column_letter(col0 + j)
                        cell.value = f"=SUBTOTAL(9,{letter}3:{letter}{last})"
                        cell.number_format = FMT[c[2]]
                    cell.font = Font(bold=True)
                for j in range(len(heads)):
                    ws.cell(row=last + 1, column=col0 + j).fill = PatternFill("solid", fgColor="DDEBF7")
            else:
                ws.cell(row=3, column=col0, value="—")
            if bi == 0:   # فیلتر اکسل فقط روی یک جدول هر برگه ممکن است
                ws.auto_filter.ref = f"{get_column_letter(col0)}2:{get_column_letter(col0 + len(cols))}{max(last, 3)}"
            ws.column_dimensions[get_column_letter(col0)].width = 6
            for j, c in enumerate(cols, 1):
                ws.column_dimensions[get_column_letter(col0 + j)].width = 22 if c[2] == "text" else 16
            ws.column_dimensions[get_column_letter(col0 + len(heads))].width = 4
            col0 += len(heads) + 1
        ws.row_dimensions[2].height = 34
        ws.freeze_panes = "A3"

    def reserve(self, title: str) -> str:
        """نام برگه‌ای که بعداً ساخته می‌شود (برای لینک از کارت سرپرست به کارت ویزیتور)."""
        return self._title(title)

    def card(self, title: str, header: str, metrics: list[tuple[str, Any, str]], sections: list[dict], reserved: bool = False,
             inactive: bool = False):
        """برگه کارت: سطر عنوان، شاخص‌ها زیر هم (عنوان | مقدار)، بعد جدول‌ها (گروه کالا، تحقق، ویزیتورها، مطالبات، چک برگشتی)."""
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        ws = self._ws(title, reserved)
        ws.append([header])
        ws["A1"].font = Font(bold=True, size=13)
        if inactive:
            _fill_row(ws, 1, 6)
        for label, value, kind in metrics:
            ws.append([label, value])
            ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
            if kind in FMT:
                ws.cell(row=ws.max_row, column=2).number_format = FMT[kind]
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
            for i, row in enumerate(sec["rows"]):
                link = row[0][1] if row and isinstance(row[0], tuple) else None
                ws.append([row[0][0], *row[1:]] if row and isinstance(row[0], tuple) else row)
                r = ws.max_row
                for col in sec.get("money", ()):
                    ws.cell(row=r, column=col).number_format = "#,##0"
                for col in sec.get("pct", ()):
                    ws.cell(row=r, column=col).number_format = "0.0%"
                if link:   # (متن، نام برگه مقصد) ← لینک داخلی
                    ws.cell(row=r, column=1).hyperlink = f"#'{link}'!A1"
                    ws.cell(row=r, column=1).font = Font(color="0563C1", underline="single")
                if i in sec.get("inactive_rows", ()):
                    _fill_row(ws, r, len(sec["headers"]))
            if not sec["rows"]:
                ws.append([sec.get("empty", "—")])
            elif not filtered:   # فیلتر اکسل روی اولین جدول (هر برگه فقط یک فیلتر دارد)
                ws.auto_filter.ref = f"A{head}:{get_column_letter(len(sec['headers']))}{ws.max_row}"
                filtered = True
        widths = sections and max(len(x["headers"]) for x in sections) or 2
        for k in range(1, max(widths, 2) + 1):
            ws.column_dimensions[get_column_letter(k)].width = 30 if k == 1 else 44 if k == 2 else 17

    def visitor_card(self, v: dict, groups: list[dict], title: str | None = None, brands: list[dict] | None = None):
        """یک برگه برای هر ویزیتور: همه شاخص‌ها، تحقق تارگت، فروش به تفکیک گروه کالا، مطالبات و چک‌های برگشتی."""
        head = f"{v.get('label')} — {v.get('branch') or ''} — سرپرست {v.get('supervisor') or '—'} — {v.get('city') or ''} — {v.get('status')}"
        if v.get("idle") and v.get("last_date"):
            head += f" (آخرین فروش {v.get('last_date')})"
        sections = [_target_groups_section(v)] if v.get("target_groups") else []
        sections += [
            {"title": "فروش به تفکیک گروه کالا", "headers": ["گروه کالا", "تعداد کالای متمایز", "تعداد", "فروش خالص (ریال)"],
             "money": (2, 3, 4), "rows": [[r.get("group"), r.get("items"), r.get("qty"), _rial(r.get("net"))] for r in groups]},
            _brand_section("فروش به تفکیک برند", brands or [], items=True),
            {"title": "مانده مطالبات به تفکیک مشتری", "headers": ["کد مشتری", "مشتری", "مانده (ریال)"], "money": (3,), "color": "7F6000",
             "rows": [[d.get("customer_code"), d.get("customer_name"), _rial(d.get("amount_rial"))] for d in v.get("debtor_list") or []]},
            {"title": "چک‌های برگشتی", "headers": ["کد مشتری", "مشتری", "شماره چک", "سریال", "سررسید", "وضعیت", "مبلغ (ریال)"], "money": (7,),
             "color": "7F6000",
             "rows": [[c.get("customer_code"), c.get("customer_name"), c.get("number"), c.get("serial"), c.get("due_date_jalali"), c.get("status"),
                       _rial(c.get("amount_rial"))] for c in v.get("cheque_list") or []]}]
        self.card(title or str(v.get("label") or v.get("key")), head,
                  [(t, get(v), kind) for t, get, kind in VISITOR_COLS[VISITOR_TEXT:]], sections,
                  reserved=title is not None, inactive=bool(v.get("inactive")))

    def bytes(self) -> bytes:
        buf = BytesIO()
        self.wb.save(buf)
        return buf.getvalue()


def _target_groups_section(v: dict) -> dict:
    return {"title": "تحقق تارگت تعدادی به تفکیک گروه کالا (ماه پایان بازه)", "color": "375623",
            "headers": ["گروه کالا", "فروش ماه (تعداد)", "تارگت ماه (تعداد)", "تارگت تا امروز (تعداد)", "درصد تحقق"],
            "money": (2, 3, 4), "pct": (5,),
            "rows": [[g.get("group"), g.get("qty"), g.get("target"), g.get("target_day"), g.get("ach")] for g in v.get("target_groups") or []]}


GROUP_COLS: list[Col] = [("ویزیتور", lambda r: r.get("visitor"), "text"), ("شعبه", lambda r: r.get("branch"), "text"),
                         ("سرپرست", lambda r: r.get("supervisor"), "text"), ("گروه کالا", lambda r: r.get("group"), "text"),
                         _col("تعداد کالای متمایز", "items", "int"), _col("تعداد", "qty", "int"), _col("فروش خالص", "net")]


def _groups(products: list[dict], visitors: list[dict]) -> list[dict]:
    """فروش همین ویزیتورها به تفکیک گروه کالا (هر ردیف با نام ویزیتور، شعبه و سرپرست)."""
    by = {str(v["key"]): v for v in visitors}
    return [dict(r, visitor=by[str(r["key"])].get("label"), branch=by[str(r["key"])].get("branch"),
                 supervisor=by[str(r["key"])].get("supervisor"), inactive=by[str(r["key"])].get("inactive"))
            for r in products if str(r.get("key")) in by]


DEBT_COLS: list[Col] = [("ویزیتور", lambda r: r.get("visitor"), "text"), ("شعبه", lambda r: r.get("branch"), "text"),
                        ("سرپرست", lambda r: r.get("supervisor"), "text"), ("کد مشتری", lambda r: r.get("customer_code"), "text"),
                        ("مشتری", lambda r: r.get("customer_name"), "text"), _col("مانده مطالبات", "amount_rial")]
CHEQUE_COLS: list[Col] = [("ویزیتور", lambda r: r.get("visitor"), "text"), ("شعبه", lambda r: r.get("branch"), "text"),
                          ("سرپرست", lambda r: r.get("supervisor"), "text"), ("کد مشتری", lambda r: r.get("customer_code"), "text"),
                          ("مشتری", lambda r: r.get("customer_name"), "text"), ("شماره چک", lambda r: r.get("number"), "text"),
                          ("سریال چک", lambda r: r.get("serial"), "text"),
                          ("سررسید", lambda r: r.get("due_date_jalali"), "text"), ("وضعیت", lambda r: r.get("status"), "text"),
                          _col("مبلغ چک", "amount_rial")]


def _per_customer(visitors: list[dict], field: str) -> list[dict]:
    """ردیف‌های مشتری هر ویزیتور (مانده مطالبات یا چک برگشتی) با نام ویزیتور، شعبه و سرپرست."""
    return [dict(r, visitor=v.get("label"), branch=v.get("branch"), supervisor=v.get("supervisor"), inactive=v.get("inactive"))
            for v in visitors for r in v.get(field) or []]


def _customer_sheet(book: "Book", visitors: list[dict]) -> None:
    """مانده مطالبات و چک‌های برگشتی به تفکیک مشتری، کنار هم در یک برگه."""
    book.side_by_side("مطالبات و چک‌های برگشتی", [
        ("مانده مطالبات به تفکیک مشتری (وضعیت امروز کارآمد)", DEBT_COLS, _per_customer(visitors, "debtor_list"), "7F6000"),
        ("چک‌های برگشتی تسویه‌نشده (سررسید از ابتدای سال جاری)", CHEQUE_COLS, _per_customer(visitors, "cheque_list"), "833C0B")])


MAX_CARD_SHEETS = 150


def _team_groups(products: list[dict], visitors: list[dict]) -> list[list[Any]]:
    """فروش یک تیم به تفکیک گروه کالا."""
    keys = {str(v["key"]) for v in visitors}
    agg: dict[str, list[Any]] = {}
    for r in products:
        if str(r.get("key")) in keys:
            a = agg.setdefault(str(r.get("group")), [r.get("group"), 0.0, 0.0])
            a[1] += float(r.get("qty") or 0)
            a[2] += float(r.get("net") or 0)
    return [[g, q, _rial(v)] for g, q, v in sorted(agg.values(), key=lambda a: -a[2])]


def _team_brands(brands: list[dict], visitors: list[dict]) -> list[dict]:
    """فروش یک تیم به تفکیک برند (جمع ویزیتورها)."""
    keys = {str(v["key"]) for v in visitors}
    agg: dict[str, dict] = {}
    for r in brands:
        if str(r.get("key")) in keys:
            a = agg.setdefault(str(r.get("brand")), {"brand": r.get("brand"), "qty": 0.0, "net": 0.0})
            a["qty"] += float(r.get("qty") or 0)
            a["net"] += float(r.get("net") or 0)
    return sorted(agg.values(), key=lambda a: -a["net"])


def _brand_section(title: str, rows: list[dict], items: bool = False) -> dict:
    """جدول فروش به تفکیک برند با سهم هر برند از کل فروش خالص."""
    total = sum(float(r.get("net") or 0) for r in rows) or None
    share = lambda r: (float(r.get("net") or 0) / total) if total else None  # noqa: E731
    if items:
        return {"title": title, "color": "833C0B", "headers": ["برند", "تعداد کالای متمایز", "تعداد", "فروش خالص (ریال)", "سهم از فروش"],
                "money": (2, 3, 4), "pct": (5,),
                "rows": [[r.get("brand"), r.get("items"), r.get("qty"), _rial(r.get("net")), share(r)] for r in rows]}
    return {"title": title, "color": "833C0B", "headers": ["برند", "تعداد", "فروش خالص (ریال)", "سهم از فروش"],
            "money": (2, 3), "pct": (4,), "rows": [[r.get("brand"), r.get("qty"), _rial(r.get("net")), share(r)] for r in rows]}


BRAND_COLS: list[Col] = [("ویزیتور", lambda r: r.get("visitor"), "text"), ("شعبه", lambda r: r.get("branch"), "text"),
                         ("سرپرست", lambda r: r.get("supervisor"), "text"), ("برند", lambda r: r.get("brand"), "text"),
                         _col("تعداد کالای متمایز", "items", "int"), _col("تعداد", "qty", "int"), _col("فروش خالص", "net")]


def _supervisor_cards(book: "Book", sups: list[dict], team: dict[str, list[dict]], products: list[dict],
                      brands: list[dict] | None = None) -> bool:
    """برای هر سرپرست: کارت سرپرست (مثل کارت ویزیتور) و بلافاصله کارت همه ویزیتورهایش. False = سقف برگه‌ها پر شد."""
    made = 0
    for s in sups:
        crew = team.get(_norm(s.get("label") or s.get("key")), [])
        if made + 1 + len(crew) > MAX_CARD_SHEETS:
            return False
        name = str(s.get("label") or s.get("key"))
        sheet_names = [book.reserve(str(v.get("label") or v.get("key"))) for v in crew]
        tg_crew = [v for v in crew if v.get("target_day")]
        sections = [{"title": "ویزیتورهای این سرپرست (روی نام بزنید تا کارتش باز شود؛ ردیف رنگی = غیرفعال)",
                     "headers": ["ویزیتور", "وضعیت", "فروش خالص", "فروش ناخالص", "تارگت تا امروز", "درصد تحقق", "مشتری خریدار",
                                 "تعداد گروه کالا", "ویزیت ثبت‌شده", "میانگین فروش روزانه", "مانده حساب مشتریان", "چک برگشتی (مبلغ)"],
                     "money": (3, 4, 5, 7, 8, 9, 10, 11, 12), "pct": (6,),
                     "inactive_rows": {k for k, v in enumerate(crew) if v.get("inactive")},
                     "rows": [[(v.get("label"), sheet_names[k]), v.get("status"), _rial(v.get("net")), _rial(v.get("gross")),
                               _rial(v.get("target_day")), v.get("target_ach"), v.get("customers"), v.get("groups_n"),
                               v.get("req_docs"), _rial(v.get("daily_avg")), _rial(v.get("ar_rial")), _rial(v.get("ret_cheque_rial"))]
                              for k, v in enumerate(crew)]}]
        if tg_crew:
            sections.append({"title": "تحقق تارگت ویزیتورهای تارگت‌دار (ماه پایان بازه)", "color": "375623",
                             "headers": ["ویزیتور", "تارگت ماه", "تارگت تا امروز", "فروش ناخالص ماه", "درصد تحقق"],
                             "money": (2, 3, 4), "pct": (5,),
                             "rows": [[v.get("label"), _rial(v.get("target_rial")), _rial(v.get("target_day")), _rial(v.get("target_gross")),
                                       v.get("target_ach")] for v in sorted(tg_crew, key=lambda x: -(x.get("target_ach") or 0))]})
        sections += [
            {"title": "فروش تیم به تفکیک گروه کالا", "headers": ["گروه کالا", "تعداد", "فروش خالص (ریال)"], "money": (2, 3),
             "rows": _team_groups(products, crew)},
            _brand_section("فروش تیم به تفکیک برند", _team_brands(brands or [], crew)),
            {"title": "مانده مطالبات به تفکیک مشتری", "headers": ["ویزیتور", "کد مشتری", "مشتری", "مانده (ریال)"], "money": (4,),
             "color": "7F6000",
             "rows": sorted(([v.get("label"), d.get("customer_code"), d.get("customer_name"), _rial(d.get("amount_rial"))]
                             for v in crew for d in v.get("debtor_list") or []), key=lambda r: -(r[3] or 0))},
            {"title": "چک‌های برگشتی", "headers": ["ویزیتور", "کد مشتری", "مشتری", "شماره چک", "سریال", "سررسید", "وضعیت", "مبلغ (ریال)"],
             "money": (8,), "color": "7F6000",
             "rows": [[v.get("label"), c.get("customer_code"), c.get("customer_name"), c.get("number"), c.get("serial"),
                       c.get("due_date_jalali"), c.get("status"), _rial(c.get("amount_rial"))] for v in crew for c in v.get("cheque_list") or []]}]
        book.card(f"سرپرست {name}", f"سرپرست {name} — {s.get('branch') or ''} — {s.get('city') or ''} — {s.get('status')}",
                  [(t, get(s), kind) for t, get, kind in SUPERVISOR_COLS[SUPERVISOR_TEXT:]], sections, inactive=bool(s.get("inactive")))
        for k, v in enumerate(crew):
            book.visitor_card(v, [r for r in products if str(r.get("key")) == str(v["key"])], title=sheet_names[k],
                              brands=[r for r in brands or [] if str(r.get("key")) == str(v["key"])])
        made += 1 + len(crew)
    return True


def _visitor_sheets(book: "Book", products: list[dict], visitors: list[dict], brands: list[dict] | None = None) -> bool:
    """برای هر ویزیتور یک برگه کارت (اگر تعدادشان از سقف برگه‌ها بیشتر نباشد)."""
    if len(visitors) > MAX_PERSON_SHEETS:
        return False
    for v in visitors:
        book.visitor_card(v, [r for r in products if str(r.get("key")) == str(v["key"])],
                          brands=[r for r in brands or [] if str(r.get("key")) == str(v["key"])])
    return True


def _same(a: Any, b: str | None) -> bool:
    return not b or _norm(a) == _norm(b)


# دو اکسل جمعی هیبریدها (کارت آخر صفحه گزارش‌ساز): ۷ هیبرید منتخب، و همه هیبریدهای دیگر
HYBRID_GROUP_A = ("اصفهان", "یزد", "کرمانشاه", "مازندران", "گیلان", "مرکزی", "آذربایجان غربی")
HYBRID_GROUPS = {"a": "هیبریدهای " + "، ".join(HYBRID_GROUP_A), "b": "سایر هیبریدها"}


def _hybrid_region(name: Any) -> str:
    """«هیبریدی مازندران» ← «مازندران» (برای تطبیق نام استان)."""
    return re.sub(r"^هیبریدی?\s*", "", _norm(name)).strip()


def in_hybrid_group(group: str, name: Any) -> bool:
    if "هیبرید" not in _norm(name):
        return False
    a = {_norm(x) for x in HYBRID_GROUP_A}
    return (_hybrid_region(name) in a) == (group == "a")


def _group_card(book: "Book", title: str, hybs: list[dict], team: list[dict], products: list[dict], brands: list[dict]) -> None:
    """کارت جمع چند هیبرید: جمع شاخص‌ها، جدول هیبریدها، فروش به تفکیک برند و گروه کالا."""
    num = lambda k: sum(float(b.get(k) or 0) for b in hybs)  # noqa: E731
    gross = num("gross")
    tgt = sum(float(b.get("branch_target_rial") or 0) for b in hybs if b.get("branch_ach") is not None)
    tot = {k: num(k) for k in ("net", "gross", "returns_net", "customers", "visitor_count", "req_docs", "daily_avg", "distributed",
                               "undistributed", "undistributed_count", "branch_ar", "branch_credit", "ret_cheque_count",
                               "ret_cheque_rial", "branch_target_rial")}
    # درصد تحقق جمع = میانگین وزنی تحقق شعبه‌ها بر اساس تارگت ماه (روزهای گذشته برای همه یکی است)
    tot["branch_ach"] = (sum(float(b["branch_ach"]) * float(b.get("branch_target_rial") or 0) for b in hybs
                             if b.get("branch_ach") is not None) / tgt) if tgt else None
    tot["branch_target_rial"] = tot["branch_target_rial"] or None
    for r in ("vol_disc_rate", "cash_disc_rate", "mgmt_disc_rate"):
        tot[r] = (sum(float(b.get(r) or 0) * float(b.get("gross") or 0) for b in hybs) / gross) if gross else None
    groups = _team_groups(products, team)
    tot["groups_n"] = len([g for g in groups if g[1]])
    rows = [[b.get("ach_rank"), b.get("label") or b.get("key"), b.get("branch_ach"), _rial(b.get("branch_target_rial")), _rial(b.get("net")),
             _rial(b.get("gross")), (float(b.get("net") or 0) / tot["net"]) if tot["net"] else None, b.get("visitor_count"),
             b.get("customers"), _rial(b.get("undistributed")), _rial(b.get("branch_ar")), _rial(b.get("ret_cheque_rial"))]
            for b in hybs]
    book.card(title[:31] if len(title) <= 31 else "جمع هیبریدها",
              f"{title} — {len(hybs)} هیبرید، {len(team)} ویزیتور",
              [(t, get(tot), kind) for i, (t, get, kind) in enumerate(HYBRID_COLS) if i not in (0, 1, 2)],
              [{"title": "هیبریدهای این گروه (به ترتیب رتبه تحقق)",
                "headers": ["رتبه تحقق", "هیبرید", "درصد تحقق", "تارگت ماه", "فروش خالص", "فروش ناخالص", "سهم از فروش گروه",
                            "تعداد ویزیتور", "مشتری خریدار", "فاکتور توزیع‌نشده", "مانده حساب مشتریان", "چک برگشتی (مبلغ)"],
                "money": (4, 5, 6, 8, 9, 10, 11, 12), "pct": (3, 7), "rows": rows},
               _brand_section("فروش گروه به تفکیک برند", _team_brands(brands, team)),
               {"title": "فروش گروه به تفکیک گروه کالا", "headers": ["گروه کالا", "تعداد", "فروش خالص (ریال)"], "money": (2, 3),
                "rows": groups}])


def build(kind: str, date_from: str | None = None, date_to: str | None = None, city: str | None = None,
          supervisor: str | None = None, visitor: str | None = None, branch: str | None = None,
          group: str | None = None) -> tuple[bytes, str]:
    """انتخاب زنجیره‌ای: ویزیتورهای «شهر › سرپرست › ویزیتور» دامنه گزارش‌اند؛ گزارش سرپرست/هیبرید همان سرپرستان و
    هیبریدهایی است که این ویزیتورها زیرشان کار می‌کنند (و فقط همین ویزیتورها در ریزشان)."""
    if kind not in KINDS:
        raise KeyError(kind)
    df, dt = default_range()
    date_from, date_to = date_from or df, date_to or dt
    data = load(date_from, date_to)
    p = data["people"]
    sellers = sorted(p["sellers"], key=lambda r: -float(r.get("net") or 0))
    # نفرات تازه لیست ماه که هنوز فروشی ندارند هم با فروش صفر می‌آیند
    sellers += p.get("listed_idle", [])
    filters = {"city": city, "supervisor": supervisor, "visitor": visitor, "branch": branch}
    # هیبرید (و شهر) فقط برای پیدا کردن سرپرست است: با انتخاب سرپرست، همه ویزیتورهایش در هر هیبریدی (مثل صفحه)
    scope = [v for v in sellers if (supervisor or (_same(v.get("city"), city) and _same(v.get("branch"), branch)))
             and _same(v.get("supervisor"), supervisor) and _same(v.get("label") or v.get("key"), visitor)]
    narrowed = any(filters.values())
    if group:   # اکسل جمعی گروه هیبریدها: همه ویزیتورهای هیبریدهای گروه، بی‌توجه به فیلترهای دیگر
        if group not in HYBRID_GROUPS:
            raise ValueError("گروه هیبرید نامعتبر است.")
        kind = "hybrids"
        scope = [v for v in sellers if in_hybrid_group(group, v.get("branch"))]
        narrowed = True
    products = p.get("seller_products") or []
    brands = p.get("seller_brands") or []
    book = Book()

    if kind == "visitors":
        rows = scope
        # برگه اول = کارت خود ویزیتور(ها)؛ اگر تعداد زیاد باشد و کارت ساخته نشود، جدول عملکرد جای آن را می‌گیرد
        if not _visitor_sheets(book, products, rows, brands):
            book.sheet("عملکرد ویزیتورها", VISITOR_COLS, rows,
                       f"عملکرد ویزیتورها {date_from} تا {date_to} — بیش از {MAX_PERSON_SHEETS} ویزیتور؛ برای کارت جدای هر نفر "
                       "هیبرید یا سرپرست را محدود کنید. ردیف رنگی = غیرفعال (در لیست ماه نیست و ۹۰ روز در کارآمد فعالیتی ندارد)")
        book.sheet("ریز گروه کالا", GROUP_COLS, _groups(products, rows), "فروش هر ویزیتور به تفکیک گروه کالا در بازه")
        book.sheet("ریز برند", BRAND_COLS, _groups(brands, rows), "فروش هر ویزیتور به تفکیک برند در بازه")
        _customer_sheet(book, rows)

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
        _supervisor_cards(book, sups, team, products, brands)
        book.sheet("سرپرست‌ها", SUPERVISOR_COLS, sups,
                   f"عملکرد سرپرست‌ها {date_from} تا {date_to} (همه اعداد = جمع ویزیتورهای زیرمجموعه هر سرپرست؛ "
                   "ردیف رنگی = غیرفعال)")
        members = [v for s in sups for v in team.get(_norm(s.get("label") or s.get("key")), [])]
        book.sheet("ویزیتورهای سرپرستان", VISITOR_COLS, members)
        book.sheet("ریز گروه کالا", GROUP_COLS, _groups(products, members), "فروش هر ویزیتور به تفکیک گروه کالا در بازه")
        book.sheet("ریز برند", BRAND_COLS, _groups(brands, members), "فروش هر ویزیتور به تفکیک برند در بازه")
        _customer_sheet(book, members)

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
        keys = [_norm(b.get("label") or b.get("key")) for b in hybs]
        if group:   # برگه اول: کارت جمع همه هیبریدهای گروه
            _group_card(book, HYBRID_GROUPS[group], hybs, [v for k in keys for v in crew.get(k, [])], products, brands)
        # برگه اول = کارت شعبه/شهر هر هیبرید (برگه جمع «هیبریدها» حذف شد)
        for b in hybs[:MAX_PERSON_SHEETS]:
            k = _norm(b.get("label") or b.get("key"))
            team = crew.get(k, [])
            bsups = sorted(sup_by_branch.get(k, []), key=lambda r: -float(r.get("net") or 0))
            book.card(str(b.get("label") or b.get("key")).replace("هیبریدی", "").replace("هیبرید", "").strip() or "هیبرید",
                      f"{b.get('label')} — {len(bsups)} سرپرست، {len(team)} ویزیتور — رتبه تحقق {int(b['ach_rank']) if b.get('ach_rank') else '—'}",
                      [(t, get(b), kind) for i, (t, get, kind) in enumerate(HYBRID_COLS) if i not in (1, 2)],
                      [{"title": "سرپرستان این هیبرید (اعداد هر سرپرست = جمع ویزیتورهای زیرمجموعه‌اش؛ ردیف رنگی = غیرفعال)",
                        "headers": ["سرپرست", "وضعیت", "تعداد ویزیتور", "فروش خالص", "فروش ناخالص", "برگشت از فروش", "تارگت تا امروز",
                                    "درصد تحقق", "مشتری خریدار", "ویزیت ثبت‌شده", "مانده حساب مشتریان", "چک برگشتی (مبلغ)"],
                        "money": (4, 5, 6, 7, 11, 12), "pct": (8,),
                        "inactive_rows": {i for i, s in enumerate(bsups) if s.get("inactive")},
                        "rows": [[s.get("label") or s.get("key"), s.get("status"),
                                  len([v for v in team if _norm(v.get("supervisor")) == _norm(s.get("label") or s.get("key"))]),
                                  _rial(s.get("net")), _rial(s.get("gross")), _rial(s.get("returns_net")), _rial(s.get("target_day")),
                                  s.get("target_ach"), s.get("customers"), s.get("req_docs"), _rial(s.get("ar_rial")),
                                  _rial(s.get("ret_cheque_rial"))] for s in bsups]},
                       {"title": "ویزیتورهای این هیبرید (ردیف رنگی = غیرفعال)", "color": "375623",
                        "headers": ["ویزیتور", "وضعیت", "سرپرست", "فروش خالص", "فروش ناخالص", "تارگت تا امروز", "درصد تحقق",
                                    "مشتری خریدار", "تعداد گروه کالا", "ویزیت ثبت‌شده", "مانده حساب مشتریان", "چک برگشتی (مبلغ)"],
                        "money": (4, 5, 6, 11, 12), "pct": (7,),
                        "inactive_rows": {i for i, v in enumerate(team) if v.get("inactive")},
                        "rows": [[v.get("label"), v.get("status"), v.get("supervisor"), _rial(v.get("net")), _rial(v.get("gross")),
                                  _rial(v.get("target_day")), v.get("target_ach"), v.get("customers"), v.get("groups_n"),
                                  v.get("req_docs"), _rial(v.get("ar_rial")), _rial(v.get("ret_cheque_rial"))] for v in team]},
                       {"title": "فروش شعبه به تفکیک گروه کالا", "headers": ["گروه کالا", "تعداد", "فروش خالص (ریال)"], "money": (2, 3),
                        "rows": _team_groups(products, team)},
                       _brand_section("فروش شعبه به تفکیک برند", _team_brands(brands, team))])
        book.sheet("سرپرستان هیبریدها", SUPERVISOR_COLS, [s for k in keys for s in sup_by_branch.get(k, [])])
        crew_all = [v for k in keys for v in crew.get(k, [])]
        book.sheet("ویزیتورهای هیبریدها", VISITOR_COLS, crew_all)
        book.sheet("ریز گروه کالا", GROUP_COLS, _groups(products, crew_all), "فروش هر ویزیتور به تفکیک گروه کالا در بازه")
        book.sheet("ریز برند", BRAND_COLS, _groups(brands, crew_all), "فروش هر ویزیتور به تفکیک برند در بازه")
        _customer_sheet(book, crew_all)

    tag = re.sub(r'[\/:*?"<>|]+', " ", "-".join(x for x in (HYBRID_GROUPS.get(group or ""), branch, city, supervisor, visitor) if x)).strip()
    fname = f"گزارش-{KINDS[kind]}-{date_from.replace('/', '-')}-تا-{date_to.replace('/', '-')}{('-' + tag) if tag else ''}.xlsx"
    return book.bytes(), fname


VISITOR_FIELDS = ("net", "gross", "returns_net", "customers", "groups_n", "qty", "invoices", "req_docs", "daily_avg", "forecast",
                  "ar_rial", "debtors", "ret_cheque_count", "ret_cheque_rial", "vol_disc_rate", "cash_disc_rate", "mgmt_disc_rate",
                  "branch_ach", "last_date", "seller_code", "target_rial", "target_day", "target_ach", "status", "inactive")


def options(date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    """همه ویزیتورها با شهر، سرپرست، شعبه و همه شاخص‌های اکسل ویزیتور (مبالغ ریال)، برای انتخاب زنجیره‌ای و جدول صفحه."""
    df, dt = default_range()
    date_from, date_to = date_from or df, date_to or dt
    try:
        p = load(date_from, date_to)["people"]
    except Exception as exc:  # noqa: BLE001
        return {"date_from": date_from, "date_to": date_to, "people": [], "error": str(exc)}
    people = [{"visitor": s.get("label") or s.get("key"), "city": s.get("city") or "—", "supervisor": s.get("supervisor") or "—",
               "branch": s.get("branch") or "—", "net_rial": float(s.get("net") or 0), **{k: s.get(k) for k in VISITOR_FIELDS}}
              for s in p["sellers"] + p.get("listed_idle", [])]
    people.sort(key=lambda r: -r["net_rial"])
    return {"date_from": date_from, "date_to": date_to, "people": people, "error": None}
