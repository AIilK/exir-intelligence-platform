"""گزارش سود و زیان (P&L) — همان سه کارپوشه مالی: B2B، صادرات (EXPORT) و هیبرید.

منبع: فایل‌های «P&L … .xlsx/.xlsb» در پوشه مشترک (تنظیم PNL_FOLDER، پیش‌فرض \\\\192.168.0.4\\Ai\\New folder).
- شیت گزارش (Report / P&L): همان چیدمان اکسل — برندها در ستون‌ها، ردیف‌های سود و زیان، جمع، «On sales» و دوره‌های قبل.
  اعداد همان مقادیر محاسبه‌شده خود اکسل‌اند (میلیون ریال)، پس گزارش دقیقاً با فایل یکی است.
- شیت‌های جزئیات (فروش، برگشت، تخفیفات، بهای تمام شده، هزینه، وصول فاکتور، …): خلاصه (Pivot) و ریز محدود.

هر فایل یک بار خوانده و در backend/data/pnl_cache ذخیره می‌شود؛ با تغییر فایل (زمان/اندازه) خودکار دوباره خوانده می‌شود.
فایل هیبرید (~۶۶ مگابایت، ~۹۰۰ هزار ردیف) حدود یک تا دو دقیقه طول می‌کشد؛ در پس‌زمینه ساخته می‌شود.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

DEFAULT_FOLDER = r"\\192.168.0.4\Ai\New folder"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "pnl_cache"
CACHE_VERSION = 4
TOP = 40
SOURCES: dict[str, dict[str, Any]] = {
    "hybrid": {"title": "هیبرید", "pattern": re.compile(r"p&l.*hybrid.*\.xls[xb]$", re.I), "report": "P&L"},
    "b2b": {"title": "B2B", "pattern": re.compile(r"p&l.*b2b.*\.xlsx$", re.I), "report": "Report"},
    "export": {"title": "صادرات", "pattern": re.compile(r"p&l.*export.*\.xlsx$", re.I), "report": "Report"},
}
# ردیف‌های اصلی (برای جمع تجمیعی سه کانال و نمودار آبشاری)
CANON: list[tuple[str, Callable[[str], bool]]] = [
    ("qty", lambda s: s.startswith("net sales(q")),
    ("gross", lambda s: s.startswith("gross sales")),
    ("return", lambda s: s == "return"),
    ("discount", lambda s: s in ("discounts", "discount")),
    ("net", lambda s: s == "total net sales"),
    ("vat", lambda s: s == "value added"),
    ("cogs", lambda s: s.startswith("cost of goods")),
    ("gp", lambda s: s == "gross profit"),
    ("opex", lambda s: s == "total expenses"),
    ("op", lambda s: s == "operation profit"),
    ("tax", lambda s: s == "tax"),
    ("np", lambda s: s == "net profit"),
    ("margin", lambda s: s == "net margin"),
]
TOTAL_KEYS = {"net", "gp", "opex", "op", "np"}
RATIO_LABELS = {"%", "discount %", "net margin"}

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def folder() -> Path:
    return Path(os.environ.get("PNL_FOLDER") or DEFAULT_FOLDER)


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _round(v: float | None, d: int = 2) -> float | None:
    return None if v is None else round(v, d)


def find_files() -> dict[str, Path | None]:
    out: dict[str, Path | None] = {k: None for k in SOURCES}
    try:
        files = [p for p in folder().iterdir() if p.is_file() and not p.name.startswith("~$")]
    except OSError:
        return out
    for key, spec in SOURCES.items():
        hits = sorted((p for p in files if spec["pattern"].search(p.name)), key=lambda p: p.stat().st_mtime, reverse=True)
        out[key] = hits[0] if hits else None
    return out


# ---------------------------------------------------------------- خواندن شیت‌ها (xlsx و xlsb با یک رابط)
def _rows(path: Path, sheet: str) -> Iterable[list[Any]]:
    if path.suffix.lower() == ".xlsb":
        import pyxlsb
        with pyxlsb.open_workbook(str(path)) as wb:
            with wb.get_sheet(sheet) as sh:
                for row in sh.rows():
                    yield [c.v for c in row]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        try:
            for row in wb[sheet].iter_rows(values_only=True):
                yield list(row)
        finally:
            wb.close()


def _sheet_names(path: Path) -> list[str]:
    if path.suffix.lower() == ".xlsb":
        import pyxlsb
        with pyxlsb.open_workbook(str(path)) as wb:
            return list(wb.sheets)
    import openpyxl
    wb = openpyxl.load_workbook(str(path), read_only=True)
    try:
        return wb.sheetnames
    finally:
        wb.close()


# ---------------------------------------------------------------- شیت گزارش سود و زیان
def parse_report(rows: list[list[Any]]) -> dict[str, Any]:
    head_i = next(i for i, r in enumerate(rows) if any(str(v).strip() == "Padina" for v in r if v is not None))
    head = rows[head_i]
    brand_cols: list[tuple[int, str]] = []
    periods: list[dict[str, Any]] = []
    first = next(j for j, v in enumerate(head) if str(v or "").strip() == "Padina")
    j = first
    while j < len(head) and head[j] not in (None, "") and str(head[j]).strip() not in ("Total",) and not re.match(r"^\d{4}", str(head[j]).strip()):
        brand_cols.append((j, str(head[j]).strip()))
        j += 1
    for k in range(j, len(head)):
        v = str(head[k] or "").strip()
        if v and v.lower() != "on sales":
            ratio = k + 1 if k + 1 < len(head) and str(head[k + 1] or "").strip().lower() == "on sales" else None
            label = "جمع دوره" if v == "Total" else (v[:-2] if v.endswith(".0") else v)
            periods.append({"key": f"p{len(periods)}", "label": label, "col": k, "ratio_col": ratio})
    label_col = 1
    # تنظیمات اکسل (Method، WithReturn، کانال، ضریب بهای تمام شده)
    settings: dict[str, Any] = {}
    for r in rows[:head_i + 8]:
        for v in r:
            s = str(v or "").strip()
            if s.lower().startswith("method"):
                settings["method"] = s
            elif s.lower() in ("withreturn", "withoutreturn"):
                settings["return_mode"] = s
            elif s.lower() in ("b2b", "b2b&export", "export"):
                settings["channel"] = s
    mult = next((_num(r[c]) for r in rows[:head_i] for c in range(len(r)) if _num(r[c]) and 1 < (_num(r[c]) or 0) < 3), None)
    if mult:
        settings["cost_multiplier"] = mult

    out_rows: list[dict[str, Any]] = []
    group = None
    in_discount = False  # ریز انواع تخفیف (B2B بعد از Total Net Sales، هیبرید بعد از Value added)
    for i in range(head_i + 1, len(rows)):
        r = rows[i] + [None] * (len(head) - len(rows[i]))
        label = str(r[label_col] or "").strip()
        code = r[0] if r[0] not in (None, "") else None
        if not label:
            continue
        low = label.lower()
        canon = next((k for k, f in CANON if f(low)), None)
        vals = {b: _round(_num(r[c])) for c, b in brand_cols}
        per = {p["key"]: {"value": _round(_num(r[p["col"]])), "ratio": _round(_num(r[p["ratio_col"]]), 4) if p["ratio_col"] else None} for p in periods}
        numeric = [v for v in vals.values() if v is not None] + [x["value"] for x in per.values() if x["value"] is not None]
        if not numeric and canon is None:
            # عنوان گروه (مثلاً «پورسانت»)
            group = label
            continue
        fractional = [v for v in numeric if v and abs(v) < 1.5 and not float(v).is_integer()]
        is_ratio = low in RATIO_LABELS or bool(fractional and all(abs(v) <= 1.5 for v in numeric) and low != "opex")
        kind = "ratio" if is_ratio else ("total" if canon in TOTAL_KEYS or low in ("total", "سود قبل مالیات") else "line")
        if low == "opex":
            kind, label = "share", "سهم تخصیص هزینه (بر اساس تعداد)"
            group, in_discount = "opex", False
        elif canon is not None or low == "%":
            group = None
            in_discount = canon in ("net", "vat") and low != "%"
        elif in_discount:
            group = "discount_detail"
            if low == "total":
                label, kind, in_discount = "جمع تخفیفات", "total", False
        out_rows.append({"label": label, "code": str(int(code)) if isinstance(code, float) else (str(code) if code else None),
                         "kind": kind, "canon": canon, "group": group if kind not in ("total",) and canon is None else None,
                         "values": vals, "periods": per})
    return {"brands": [b for _, b in brand_cols], "periods": [{k: p[k] for k in ("key", "label")} | {"has_ratio": bool(p["ratio_col"])} for p in periods],
            "rows": out_rows, "settings": settings, "unit": "میلیون ریال"}


# ---------------------------------------------------------------- خلاصه شیت‌های جزئیات
MONTHS_FA = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def month_label(v: str) -> str:
    """«05/04» (سال/ماه در اکسل هیبرید) ← «تیر ۰۵»"""
    m = re.match(r"^(\d{2})/(\d{2})$", v)
    return f"{MONTHS_FA[int(m.group(2)) - 1]} ۱۴{m.group(1)}" if m and 1 <= int(m.group(2)) <= 12 else v


class Pivot:
    """جمع چند ستون عددی به تفکیک یک یا چند کلید (کلید سوم اختیاری: تابع تبدیل نمایش)."""

    def __init__(self, keys: list[tuple], measures: list[tuple[str, int]]):
        self.keys, self.measures = keys, measures
        self.data: dict[tuple, list[float]] = defaultdict(lambda: [0.0] * (len(measures) + 1))

    def add(self, row: list[Any]):
        key = tuple((k[2](_clean(row[k[1]])) if len(k) > 2 else _clean(row[k[1]])) if k[1] < len(row) else "" for k in self.keys)
        acc = self.data[key]
        for n, (_, i) in enumerate(self.measures):
            v = _num(row[i]) if i < len(row) else None
            if v:
                acc[n] += v
        acc[-1] += 1

    def result(self, title: str, limit: int | None = None, sort: int = 0) -> dict[str, Any]:
        items = sorted(self.data.items(), key=lambda kv: -abs(kv[1][sort]))
        total = [sum(v[n] for v in self.data.values()) for n in range(len(self.measures) + 1)]
        rows = [{"keys": list(k), "values": [round(x, 0) for x in v[:-1]], "count": int(v[-1])} for k, v in (items[:limit] if limit else items)]
        return {"title": title, "key_labels": [k[0] for k in self.keys], "measure_labels": [m for m, _ in self.measures],
                "rows": rows, "total": [round(x, 0) for x in total[:-1]], "total_count": int(total[-1]), "row_count": len(items),
                "truncated": bool(limit and len(items) > limit)}


def _clean(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip().replace("ي", "ی").replace("ك", "ک")
    return s or "—"


def _scan(path: Path, sheet: str, header_row: int, pivots: list[Pivot], keep: Callable[[list[Any]], bool] | None = None,
          progress: Callable[[str], None] | None = None) -> int:
    n = 0
    for i, row in enumerate(_rows(path, sheet)):
        if i <= header_row or not row:
            continue
        if keep and not keep(row):
            continue
        for p in pivots:
            p.add(row)
        n += 1
        if progress and n % 50000 == 0:
            progress(f"{sheet}: {n:,} ردیف")
    return n


def _table(path: Path, sheet: str, header_row: int, cols: list[tuple[str, int]], limit: int = 3000,
           keep: Callable[[list[Any]], bool] | None = None) -> dict[str, Any]:
    rows = []
    for i, row in enumerate(_rows(path, sheet)):
        if i <= header_row or not row:
            continue
        if keep and not keep(row):
            continue
        rows.append([(_num(row[c]) if _num(row[c]) is not None else _clean(row[c])) if c < len(row) else None for _, c in cols])
        if len(rows) >= limit:
            break
    return {"columns": [c for c, _ in cols], "rows": rows}


def _ledger_details(path: Path, progress, currency: str = "ریال") -> list[dict[str, Any]]:
    """B2B / صادرات: شیت‌های خروجی راهکاران. صادرات در «فروش تعدادی» و «بهای تمام شده» ارزی (دلار) است."""
    out: list[dict[str, Any]] = []
    cur = f"({currency})"
    names = _sheet_names(path)
    if "فروش ریالی 1405" in names:
        a, b = Pivot([("برند", 0), ("کانال", 1)], [("فروش (مانده بستانکار، ریال)", 9)]), Pivot([("مشتری", 4), ("برند", 0)], [("فروش (ریال)", 9)])
        _scan(path, "فروش ریالی 1405", 0, [a, b], keep=lambda r: _clean(r[0]) not in ("#N/A", "—"), progress=progress)
        out.append({"key": "sales_value", "title": "فروش ریالی", "source": "فروش ریالی 1405", "pivots": [a.result("فروش به تفکیک برند و کانال"), b.result("بیشترین فروش مشتریان", TOP)]})
    if "فروش تعدادی 1405" in names:
        a = Pivot([("برند", 0), ("کانال", 1)], [(f"فروش خالص {cur}", 11), (f"مبلغ ناخالص فروش {cur}", 6), ("کاهنده (تخفیف)", 8), ("مقدار فروش خالص", 19)])
        b = Pivot([("مشتری", 3), ("برند", 0)], [(f"فروش خالص {cur}", 11), ("مقدار", 19)])
        _scan(path, "فروش تعدادی 1405", 0, [a, b], keep=lambda r: _clean(r[0]) not in ("#N/A", "—"), progress=progress)
        out.append({"key": "sales_qty", "title": "فروش تعدادی", "source": "فروش تعدادی 1405", "pivots": [a.result("فروش تعدادی به تفکیک برند و کانال"), b.result("بیشترین مشتریان", TOP)]})
    if "برگشت از فروش 1405" in names:
        a, b = Pivot([("برند", 0), ("کانال", 1)], [("برگشت (مانده بدهکار، ریال)", 8)]), Pivot([("مشتری", 4), ("برند", 0)], [("برگشت (ریال)", 8)])
        _scan(path, "برگشت از فروش 1405", 0, [a, b], progress=progress)
        out.append({"key": "returns", "title": "برگشت از فروش", "source": "برگشت از فروش 1405", "pivots": [a.result("برگشت به تفکیک برند و کانال"), b.result("بیشترین برگشت مشتریان", TOP)]})
    if "تخفیفات 1405" in names:
        a = Pivot([("نوع تخفیف", 1), ("برند", 2)], [("تخفیف (ریال)", 12)])
        b = Pivot([("نوع تخفیف", 1), ("کانال", 3)], [("تخفیف (ریال)", 12)])
        c = Pivot([("مشتری", 6), ("نوع تخفیف", 1)], [("تخفیف (ریال)", 12)])
        _scan(path, "تخفیفات 1405", 0, [a, b, c], keep=lambda r: _clean(r[1]) != "—", progress=progress)
        out.append({"key": "discounts", "title": "تخفیفات", "source": "تخفیفات 1405", "pivots": [a.result("تخفیف به تفکیک نوع و برند"), b.result("تخفیف به تفکیک نوع و کانال"), c.result("بیشترین تخفیف مشتریان", TOP)]})
    if "بهای تمام شده کالا" in names:
        a = Pivot([("برند", 0)], [("بهای تمام شده (ریال، قبل از ضریب)", 1), (f"فروش خالص {cur}", 13), ("مقدار فروش خالص", 21)])
        b = Pivot([("کالا", 5), ("برند", 0)], [("بهای تمام شده (ریال)", 1), (f"فروش خالص {cur}", 13), ("مقدار", 21)])
        _scan(path, "بهای تمام شده کالا", 0, [a, b], keep=lambda r: _num(r[1]) is not None, progress=progress)
        out.append({"key": "cogs", "title": "بهای تمام شده", "source": "بهای تمام شده کالا", "pivots": [a.result("بهای تمام شده به تفکیک برند"), b.result("بیشترین بهای تمام شده کالاها", 60)]})
    if "هزینه 1405" in names:
        out.append({"key": "expenses", "title": "هزینه‌ها", "source": "هزینه 1405",
                    "table": _table(path, "هزینه 1405", 0, [("کد", 1), ("عنوان", 2), ("بدهکار", 4), ("بستانکار", 5), ("مانده بدهکار", 6)], 200,
                                    keep=lambda r: _clean(r[2]) != "—")})
    if "Cost" in names:
        out.append({"key": "unit_cost", "title": "بهای واحد کالا", "source": "Cost",
                    "table": _table(path, "Cost", 0, [("کد کالا", 12), ("عنوان", 13), ("بهای واحد", 14), ("کد نیمه‌ساخته", 2), ("نیمه‌ساخته", 1), ("دستمزد", 3), ("سربار", 4), ("مواد", 5)], 3000,
                                    keep=lambda r: len(r) > 13 and _clean(r[13]) != "—")})
    return out


def _hybrid_details(path: Path, progress) -> list[dict[str, Any]]:
    """هیبرید: ریز فاکتورهای کارآمد."""
    out: list[dict[str, Any]] = []
    names = _sheet_names(path)
    if "sales 1405" in names:
        m = [("جمع قبل تخفیف", 49), ("تخفیف حجمی", 50), ("تخفیف نقدی", 51), ("ارزش افزوده", 52), ("قابل پرداخت", 53), ("تعداد", 47)]
        piv = {
            "brand": Pivot([("برند", 0), ("نوع فاکتور", 30)], m),
            "branch": Pivot([("شعبه", 9), ("نوع فاکتور", 30)], m),
            "month": Pivot([("ماه", 68, month_label), ("نوع فاکتور", 30)], m),
            "group": Pivot([("گروه کالا", 27), ("برند", 0)], m),
            "customer": Pivot([("مشتری", 44), ("شعبه", 9)], m),
            "seller": Pivot([("فروشنده", 5), ("شعبه", 9)], m),
            "item": Pivot([("کالا", 7), ("برند", 0)], m),
            "pay": Pivot([("نحوه پرداخت", 35)], m),
        }
        _scan(path, "sales 1405", 0, list(piv.values()), keep=lambda r: len(r) > 30 and _clean(r[30]) != "—", progress=progress)
        out.append({"key": "sales", "title": "فروش (ریز فاکتور)", "source": "sales 1405", "pivots": [
            piv["brand"].result("فروش به تفکیک برند و نوع فاکتور", sort=4), piv["branch"].result("فروش به تفکیک شعبه", sort=4),
            piv["month"].result("فروش ماهانه", sort=4), piv["pay"].result("نحوه پرداخت", sort=4),
            piv["group"].result("گروه کالا", 60, sort=4), piv["item"].result("بیشترین فروش کالاها", 60, sort=4),
            piv["customer"].result("بیشترین فروش مشتریان", 60, sort=4), piv["seller"].result("بیشترین فروش فروشندگان", 60, sort=4)]})
    if "تخفیفات" in names:
        a = Pivot([("نوع", 0), ("برند", 2)], [("مبلغ تخفیف", 14)])
        b = Pivot([("نوع", 0), ("کانال", 1)], [("مبلغ تخفیف", 14)])
        c = Pivot([("نام تخفیف", 13), ("نوع", 0)], [("مبلغ تخفیف", 14)])
        d = Pivot([("فرمول", 20), ("نوع", 0)], [("مبلغ تخفیف", 14)])
        _scan(path, "تخفیفات", 0, [a, b, c, d], progress=progress)
        out.append({"key": "discounts", "title": "تخفیفات", "source": "تخفیفات", "pivots": [a.result("تخفیف به تفکیک نوع و برند"), b.result("تخفیف به تفکیک نوع و کانال"),
                                                                                       c.result("نام تخفیف", TOP), d.result("فرمول تخفیف", TOP)]})
    if "وصول فاکتور" in names:
        m = [("مبلغ ناخالص", 17), ("قابل پرداخت", 21), ("مانده", 24), ("نقد", 26), ("حواله", 29), ("چک", 32), ("تخفیف تسویه", 35)]
        a, b, c = Pivot([("شعبه", 3)], m), Pivot([("برند", 1)], m), Pivot([("نحوه پرداخت", 11)], m)
        _scan(path, "وصول فاکتور", 0, [a, b, c], progress=progress)
        out.append({"key": "collection", "title": "وصول فاکتور", "source": "وصول فاکتور", "pivots": [a.result("وصول به تفکیک شعبه", sort=1), b.result("وصول به تفکیک برند", sort=1), c.result("نحوه پرداخت", sort=1)]})
    if "هزینه ها" in names:
        out.append({"key": "expenses", "title": "هزینه‌ها", "source": "هزینه ها",
                    "table": _table(path, "هزینه ها", 0, [("گروه", 23), ("کد معین", 13), ("معین", 14), ("بدهکار", 15), ("بستانکار", 16), ("مانده بدهکار", 17)], 400,
                                    keep=lambda r: len(r) > 14 and _clean(r[14]) != "—")})
    if "cost" in names:
        out.append({"key": "unit_cost", "title": "بهای واحد کالا", "source": "cost",
                    "table": _table(path, "cost", 0, [("کد کالا", 11), ("عنوان", 12), ("بهای واحد", 13), ("نیمه‌ساخته", 1), ("دستمزد", 3), ("سربار", 4), ("مواد", 5)], 3000,
                                    keep=lambda r: len(r) > 12 and _clean(r[12]) != "—")})
    return out


# ---------------------------------------------------------------- ساخت و کش
def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _fingerprint(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"file": path.name, "mtime": st.st_mtime, "size": st.st_size, "version": CACHE_VERSION}


def _build(key: str, path: Path):
    job = _jobs[key]
    def progress(msg: str):
        job["message"] = msg
    try:
        t0 = time.time()
        progress("خواندن شیت گزارش")
        report = parse_report(list(_rows(path, SOURCES[key]["report"])))
        details = _hybrid_details(path, progress) if key == "hybrid" else _ledger_details(path, progress, "دلار" if key == "export" else "ریال")
        data = {"key": key, "title": SOURCES[key]["title"], "source": _fingerprint(path),
                "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="minutes"),
                "built_seconds": round(time.time() - t0, 1), "report": report, "details": details}
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _cache_path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_cache_path(key))
        job.update(state="done", message="")
    except Exception as exc:  # noqa: BLE001
        job.update(state="error", message=f"{type(exc).__name__}: {str(exc)[:300]}")


def load(key: str, rebuild: bool = False) -> dict[str, Any]:
    """داده یک کانال؛ اگر کش تازه نیست ساخت در پس‌زمینه شروع می‌شود و status = building برمی‌گردد."""
    if key not in SOURCES:
        raise KeyError(key)
    path = find_files()[key]
    if path is None:
        return {"key": key, "status": "missing", "message": f"فایل P&L {SOURCES[key]['title']} در {folder()} پیدا نشد."}
    fp = _fingerprint(path)
    cached = None
    if _cache_path(key).exists() and not rebuild:
        try:
            cached = json.loads(_cache_path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
    if cached and cached.get("source") == fp:
        return {"status": "ready", **cached}
    with _lock:
        job = _jobs.get(key)
        if not job or job.get("state") != "running":
            job = _jobs[key] = {"state": "running", "message": "شروع", "started": time.time()}
            threading.Thread(target=_build, args=(key, path), daemon=True).start()
    if job.get("state") == "error":
        return {"key": key, "status": "error", "message": job["message"]}
    stale = {"status": "building", "stale": True, **cached} if cached else {"key": key, "status": "building"}
    stale.update(message=job.get("message"), elapsed=round(time.time() - job.get("started", time.time())))
    return stale


def overview() -> dict[str, Any]:
    files = find_files()
    return {"folder": str(folder()),
            "sources": [{"key": k, "title": s["title"], "file": files[k].name if files[k] else None,
                         "modified": datetime.fromtimestamp(files[k].stat().st_mtime).isoformat(timespec="minutes") if files[k] else None}
                        for k, s in SOURCES.items()]}
