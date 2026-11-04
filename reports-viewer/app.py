"""وب‌اپ نمایش گزارش‌های تجمیعی انبار و دانلود اکسل.

داده به‌صورت زنده از دیتابیس راهکاران خوانده می‌شود (db_reports.py)؛
اگر دیتابیس در دسترس نباشد، از فایل‌های اکسل پوشهٔ شبکه استفاده می‌شود.

اجرا:  python app.py            (پیش‌فرض پورت 8765)
تنظیمات با متغیرهای محیطی: REPORTS_SOURCE (db|excel), REPORTS_REFRESH (ثانیه)،
REPORTS_ENV, REPORTS_DIR, REPORTS_PORT, REPORTS_HOST
"""
import datetime as dt
import glob
import io
import json
import os
import re
import sys
import threading
import time
from urllib.parse import quote

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from openpyxl.cell import WriteOnlyCell

import db_reports
from jalali import jalali_str

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("REPORTS_PORT", "8765"))
HOST = os.environ.get("REPORTS_HOST", "0.0.0.0")


def _default_dir():
    hits = glob.glob(r"\\192.168.0.4\general\2. MEN*\AI\Farahani\14050725")
    return hits[0] if hits else HERE


DATA_DIR = os.environ.get("REPORTS_DIR") or _default_dir()
SOURCE = os.environ.get("REPORTS_SOURCE", "db")
REFRESH_SECONDS = int(os.environ.get("REPORTS_REFRESH", "60"))

# (نام فایل منبع بدون پسوند، نام شیت در خروجی — حداکثر ۳۱ کاراکتر)
SOURCES = [
    ("گزارش موجودی کالا به تفکیک انبار", "موجودی کالا به تفکیک انبار"),
    ("مانده باز درخواست خرید بر اساس رسید انبار", "مانده درخواست خرید-رسید انبار"),
    ("مصرف کالا در محصول و نیمه ساخته", "مصرف کالا در محصول و نیمه ساخته"),
    ("آنالیز تعدادی", "آنالیز تعدادی"),
    ("رسید موقت تولید", "رسید موقت تولید"),
    ("مروراسنادی-مجوز خروج-حواله", "مروراسنادی-مجوز خروج-حواله"),
]


class Snapshot:
    """دادهٔ آمادهٔ یک شیت. هر بار به‌روزرسانی، یک Snapshot تازه ساخته و یکجا جایگزین می‌شود
    تا درخواست‌ها هیچ‌وقت دادهٔ نیمه‌کاره نبینند و منتظر دیتابیس نمانند."""

    def __init__(self, header, rows, version):
        width = max([len(header)] + [len(r) for r in rows])
        header = list(header) + [None] * (width - len(header))
        # ستون‌هایی که نه عنوان دارند نه داده، حذف می‌شوند
        keep = [i for i in range(width)
                if header[i] not in (None, "") or any(i < len(r) and r[i] not in (None, "") for r in rows)]
        self.columns = [str(header[i]) if header[i] not in (None, "") else f"ستون {i + 1}" for i in keep]
        self.rows = [[(r[i] if i < len(r) else None) for i in keep] for r in rows]
        self.cells = [[normalize_cell(v) for v in r] for r in self.rows]
        self.blob = ["".join(r) for r in self.cells]
        # برای ستون‌هایی که مقدار تکراری کم دارند، فهرست کشویی ساخته می‌شود
        self.options = []
        for ci in range(len(self.columns)):
            vals = set()
            for r in self.rows:
                v = r[ci]
                if v not in (None, ""):
                    vals.add(str(v).strip())
                    if len(vals) > MAX_OPTIONS:
                        break
            self.options.append(sorted(vals) if 1 < len(vals) <= MAX_OPTIONS else None)
        self.numeric = [
            any(isinstance(r[ci], (int, float)) for r in self.rows[:2000]) for ci in range(len(self.columns))
        ]
        self.version = version
        self._cache = {}  # نتیجهٔ جست‌وجو/مرتب‌سازی‌های اخیر، برای ورق‌زدن سریع
        self._cache_lock = threading.Lock()

    def query(self, q="", sort=None, desc=False, filters=None):
        filters = {ci: str(raw) for ci, raw in (filters or {}).items() if str(raw).strip()}
        ckey = (normalize(q).lower(), sort, desc, tuple(sorted(filters.items())))
        with self._cache_lock:
            hit = self._cache.pop(ckey, None)
            if hit is not None:
                self._cache[ckey] = hit  # جدیدترین به انتهای صف
                return hit
        idx = range(len(self.rows))
        terms = [t for t in ckey[0].split() if t]
        if terms:
            idx = [i for i in idx if all(t in self.blob[i] for t in terms)]
        for ci, raw in filters.items():
            if 0 <= ci < len(self.columns):
                test = make_test(raw, self.numeric[ci])
                idx = [i for i in idx if test(self.rows[i][ci], self.cells[i][ci])]
        if sort is not None and 0 <= sort < len(self.columns):
            def k(i):
                v = self.rows[i][sort]
                if v is None or v == "":
                    return (2, 0, "")
                if isinstance(v, (int, float)):
                    return (0, v, "")
                return (1, 0, str(v))
            idx = sorted(idx, key=k, reverse=desc)
        idx = list(idx)
        with self._cache_lock:
            self._cache[ckey] = idx
            while len(self._cache) > QUERY_CACHE:
                self._cache.pop(next(iter(self._cache)))
        return idx


EMPTY = Snapshot([], [], 0)


class Sheet:
    def __init__(self, key, base, title):
        self.key, self.base, self.title = key, base, title
        self.path = os.path.join(DATA_DIR, base + ".xlsx")
        self.mtime = None  # زمان داده: زمان دریافت از دیتابیس یا تاریخ فایل اکسل
        self.source, self.error, self.last_try = None, None, 0.0
        self.snap = EMPTY
        self._raw = None  # دادهٔ خام قبلی؛ اگر تغییری نکرده باشد Snapshot دوباره ساخته نمی‌شود
        self.lock = threading.Lock()

    def ensure(self, force=False):
        """فقط وقتی هنوز داده‌ای نداریم (یا force) منتظر می‌ماند؛ به‌روزرسانی دوره‌ای در پس‌زمینه انجام می‌شود."""
        if not force and self.snap is not EMPTY:
            return self.snap
        with self.lock:
            if force or self.snap is EMPTY:
                self.reload()
        return self.snap

    def reload(self):
        if SOURCE == "db":
            self.last_try = time.time()
            try:
                header, rows = db_reports.fetch(self.base)
                self._set(header, rows, time.time(), "db")
                self.error = None
                return
            except Exception as e:
                self.error = f"دیتابیس در دسترس نیست: {e}"
                if self.source == "db":
                    return  # آخرین دادهٔ دیتابیس نگه داشته می‌شود
        self._ensure_excel()

    def _ensure_excel(self):
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            raise HTTPException(404, f"فایل منبع پیدا نشد: {self.base}.xlsx")
        if mtime == self.mtime and self.source == "excel":
            return
        wb = openpyxl.load_workbook(self.path, read_only=True, data_only=True)
        it = wb.worksheets[0].iter_rows(values_only=True)
        header = list(next(it, ()))
        rows = [list(r) for r in it if any(v not in (None, "") for v in r)]
        wb.close()
        self._set(header, rows, mtime, "excel")

    def _set(self, header, rows, stamp, source):
        raw = (list(header), rows)
        if raw != self._raw or self.snap is EMPTY:
            self.snap = Snapshot(header, rows, self.snap.version + 1)
            self._raw = raw
        self.mtime, self.source = stamp, source

    def info(self):
        snap = self.ensure()
        return {"key": self.key, "title": self.title, "file": self.base + ".xlsx",
                "rows": len(snap.rows), "cols": len(snap.columns), "updated": jalali_str(self.mtime),
                "source": self.source, "warning": self.error}


MAX_OPTIONS = 60
QUERY_CACHE = 24  # تعداد نتیجهٔ جست‌وجوی اخیر که برای هر شیت نگه داشته می‌شود
_NUM_OP = re.compile(r"^(>=|<=|>|<|=)\s*(-?[\d.,]+)$")
_NUM_RANGE = re.compile(r"^(-?[\d.,]+)\s*(?:\.\.|تا)\s*(-?[\d.,]+)$")
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize(s: str):
    return (s or "").replace("ي", "ی").replace("ك", "ک").translate(_FA_DIGITS).strip()


def normalize_cell(v):
    return "" if v is None else normalize(str(v)).lower()


def _num(s):
    return float(s.replace(",", ""))


def make_test(raw: str, numeric: bool):
    """فیلتر ستون:  ==مقدار (دقیقاً برابر، از فهرست کشویی)،
    در ستون عددی: >100 , <=5 , =0 , 10..50 یا «10 تا 50»؛ در بقیه: شامل متن."""
    s = normalize(raw)
    if s.startswith("=="):
        want = s[2:].strip().lower()
        return lambda v, cell: cell.strip() == want
    if numeric:
        m = _NUM_RANGE.match(s)
        if m:
            lo, hi = sorted((_num(m.group(1)), _num(m.group(2))))
            return lambda v, cell: isinstance(v, (int, float)) and lo <= v <= hi
        m = _NUM_OP.match(s)
        if m:
            op, n = m.group(1), _num(m.group(2))
            ops = {">": n.__lt__, "<": n.__gt__, ">=": n.__le__, "<=": n.__ge__, "=": n.__eq__}
            return lambda v, cell: isinstance(v, (int, float)) and ops[op](v)
    s = s.lower()
    return lambda v, cell: s in cell


def parse_filters(f: str):
    if not f:
        return {}
    try:
        return {int(k): v for k, v in json.loads(f).items()}
    except (ValueError, AttributeError):
        raise HTTPException(400, "فیلتر نامعتبر")


SHEETS = [Sheet(str(i), b, t) for i, (b, t) in enumerate(SOURCES)]


def get_sheet(key):
    for s in SHEETS:
        if s.key == key:
            return s
    raise HTTPException(404, "شیت پیدا نشد")


def jsonable(v):
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    return v


def write_sheet(wb, title, snap: Snapshot, idx):
    """خروجی در حالت write-only ساخته می‌شود (چند برابر سریع‌تر و کم‌حافظه‌تر از حالت عادی openpyxl)."""
    ws = wb.create_sheet(title)
    ws.sheet_view.rightToLeft = True
    ws.freeze_panes = "A2"
    sample = [snap.rows[i] for i in idx[:500]]
    for ci, name in enumerate(snap.columns):  # در حالت write-only عرض ستون باید قبل از نوشتن ردیف‌ها تعیین شود
        longest = max([len(str(name))] + [len(str(r[ci])) for r in sample if r[ci] is not None])
        ws.column_dimensions[get_column_letter(ci + 1)].width = min(max(10, longest + 2), 60)
    hdr_font = Font(bold=True, color="FFFFFF")
    hdr_fill = PatternFill("solid", fgColor="1F4E78")
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    hdr = []
    for name in snap.columns:
        c = WriteOnlyCell(ws, value=name)
        c.font, c.fill, c.alignment = hdr_font, hdr_fill, hdr_align
        hdr.append(c)
    ws.append(hdr)
    rows = snap.rows
    for i in idx:
        ws.append(rows[i])
    if snap.columns:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(snap.columns))}{max(len(idx), 1) + 1}"


def build_xlsx(parts):
    wb = openpyxl.Workbook(write_only=True)
    for title, snap, idx in parts:
        write_sheet(wb, title, snap, idx)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def xlsx_response(data: bytes, filename):
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=report.xlsx; filename*=UTF-8''{quote(filename)}"},
    )


app = FastAPI(title="گزارش‌های تجمیعی")
# پاسخ‌های JSON (ردیف‌های جدول) فشرده ارسال می‌شوند؛ روی شبکه حجم را حدود ۸۵٪ کم می‌کند
app.add_middleware(GZipMiddleware, minimum_size=1024)


def _refresh_loop():
    """داده‌ها در پس‌زمینه تازه می‌شوند تا هیچ کاربری منتظر اجرای کوئری‌ها نماند."""
    while True:
        time.sleep(REFRESH_SECONDS)
        for s in SHEETS:
            try:
                with s.lock:
                    s.reload()
            except Exception as e:
                print("refresh failed:", s.base, e)


@app.on_event("startup")
def preload():
    def run():
        try:
            export_all()  # همهٔ شیت‌ها را می‌خواند و اکسل تجمیعی را از قبل آماده می‌کند
        except Exception as e:
            print("preload failed:", e)
        _refresh_loop()
    threading.Thread(target=run, daemon=True).start()


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


_DB_NAME = None


@app.get("/api/sheets")
def sheets():
    global _DB_NAME
    out = []
    for s in SHEETS:
        try:
            out.append(s.info())
        except HTTPException as e:
            out.append({"key": s.key, "title": s.title, "file": s.base + ".xlsx", "error": e.detail})
    if SOURCE == "db":
        if _DB_NAME is None:
            _DB_NAME = db_reports._load_env(db_reports.ENV_PATH).get("SQLSERVER_DATABASE")
        src = f"دیتابیس راهکاران ({_DB_NAME}) — به‌روزرسانی خودکار هر {REFRESH_SECONDS} ثانیه"
    else:
        src = DATA_DIR
    return {"dir": src, "source": SOURCE, "today": jalali_str(dt.datetime.now().timestamp(), False), "sheets": out}


@app.post("/api/refresh")
def refresh():
    for s in SHEETS:
        s.ensure(force=True)
    return sheets()


@app.get("/api/sheets/{key}")
def sheet_rows(key: str, page: int = Query(1, ge=1), size: int = Query(100, ge=1, le=1000),
               q: str = "", sort: int | None = None, desc: bool = False, f: str = ""):
    snap = get_sheet(key).ensure()
    idx = snap.query(q, sort, desc, parse_filters(f))
    start = (page - 1) * size
    return {
        "columns": snap.columns,
        "options": snap.options,
        "numeric": snap.numeric,
        "total": len(idx),
        "all": len(snap.rows),
        "page": page,
        "size": size,
        "rows": [[jsonable(v) for v in snap.rows[i]] for i in idx[start:start + size]],
    }


_export_cache = {"key": None, "data": b""}
_export_lock = threading.Lock()


@app.get("/api/export")
def export_all():
    with _export_lock:
        snaps = [s.ensure() for s in SHEETS]
        key = tuple(id(sn) for sn in snaps)
        if _export_cache["key"] != key:  # تا وقتی داده واقعاً عوض نشده، همان خروجی قبلی داده می‌شود
            data = build_xlsx([(s.title, sn, range(len(sn.rows))) for s, sn in zip(SHEETS, snaps)])
            _export_cache.update(key=key, data=data, snaps=snaps)
        data = _export_cache["data"]
    today = jalali_str(dt.datetime.now().timestamp(), False).replace("/", "-")
    return xlsx_response(data, f"گزارش‌های تجمیعی {today}.xlsx")


@app.get("/api/export/{key}")
def export_one(key: str, q: str = "", sort: int | None = None, desc: bool = False, f: str = ""):
    s = get_sheet(key)
    filters = parse_filters(f)
    snap = s.ensure()
    idx = snap.query(q, sort, desc, filters)
    data = build_xlsx([(s.title, snap, idx)])
    today = jalali_str(dt.datetime.now().timestamp(), False).replace("/", "-")
    suffix = " (فیلتر شده)" if q.strip() or any(str(v).strip() for v in filters.values()) else ""
    return xlsx_response(data, f"{s.title}{suffix} {today}.xlsx")


def _log_to_file():
    """در اجرای بدون پنجره (pythonw) خروجی‌ها در logs\\app.log نوشته می‌شوند."""
    log_dir = os.path.join(HERE, "logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "app.log")
    if os.path.exists(path) and os.path.getsize(path) > 5 * 1024 * 1024:
        os.replace(path, path + ".1")
    log = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print(f"\n===== start {dt.datetime.now():%Y-%m-%d %H:%M:%S} =====")


if __name__ == "__main__":
    if sys.stdout is None or os.environ.get("REPORTS_LOG"):
        _log_to_file()
    else:
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")
    print(f"Source: {SOURCE}  Data dir: {DATA_DIR}")
    print(f"Open: http://localhost:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
