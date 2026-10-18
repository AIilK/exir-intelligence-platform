"""فروش فروشگاه‌های زنجیره‌ای به مصرف‌کننده (sell-out) از فایل‌های اکسل ماهانه هر زنجیره.

روند کار:
  هر ماه فایل‌های اکسل زنجیره‌ها در پوشه data/chain_store گذاشته می‌شوند (هر فرمتی که زنجیره می‌دهد).
  با هر باز شدن صفحه، فایل‌های جدید یا تغییرکرده خوانده و برای هر (ماه، زنجیره) در data/chain_store/_archive
  به‌صورت JSON ذخیره می‌شوند؛ یک نسخه از فایل اصلی هم در _archive/raw/<ماه> نگه داشته می‌شود.
  داشبورد فقط از آرشیو می‌خواند، پس پاک کردن یا جایگزین کردن فایل‌های پوشه، ماه‌های قبل را از بین نمی‌برد.
  فایل جدید برای همان (ماه، زنجیره)، داده قبلی آن ماه را جایگزین می‌کند (مثلاً نسخه اصلاح‌شده).

ماه هر فایل: اول از تاریخ «از …» داخل فایل؛ وگرنه از «برج N» در نام فایل (سال: سال جاری، یا سال قبل اگر N بعد از ماه جاری باشد؛
  یا سال ۴ رقمی داخل نام فایل مثل «شهروند برج 6 1405»).
زنجیره هر فایل: از نام فایل با فهرست CHAINS (قابل تغییر در config.json → chain_store.chains).
کالا: بارکد فایل با بارکد کالا در کارآمد (tblGoods.Barcode و tblGoodsBarcode، فقط SELECT) به کد کالا وصل می‌شود.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

import loader
import sql_source

# زنجیره‌ها: match = عبارت‌هایی که در نام فایل می‌آیند؛ customers = کد مشتری زنجیره در کارآمد (برای sell-in)
CHAINS = [
    {"name": "هایپر می", "match": ["هایپر می", "هایپرمی", "hyperme"], "customers": ["14900123"]},
    {"name": "شهروند", "match": ["شهروند"], "customers": ["14900158"]},
    {"name": "نجم خاورمیانه", "match": ["نجم"], "customers": ["14200017"]},
    {"name": "مادر دزفول", "match": ["مادر دزفول", "مادر"], "customers": ["14200598"]},
    {"name": "هایپر استار (ماف)", "match": ["هایپر استار", "هایپراستار", "ماف"], "customers": ["14900005"]},
    {"name": "تعاونی سپه", "match": ["سپه"], "customers": ["14900002"]},
]
EXCEL = {".xls", ".xlsx", ".xlsm", ".xlsb"}
BARCODE_SQL = """
SELECT g.Code AS code, g.Barcode AS barcode FROM dbo.tblGoods g WHERE g.Barcode IS NOT NULL AND g.Barcode <> ''
UNION
SELECT g.Code, b.Barcode FROM dbo.tblGoodsBarcode b JOIN dbo.tblGoods g ON g.ID = b.GoodsRef WHERE b.Barcode <> ''"""
BARCODE_HOURS = 24
FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def norm(s) -> str:
    """یکسان‌سازی متن فارسی برای مقایسه: ی/ک عربی، ارقام فارسی، نیم‌فاصله و فاصله‌های اضافه."""
    s = str(s or "").translate(FA_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("‌", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def squash(s) -> str:
    return re.sub(r"[\s()\[\]:_\-.]", "", norm(s))


def jalali_today() -> str:
    """تاریخ شمسی امروز (yyyy/mm/dd)؛ فقط وقتی تقویم کارآمد هنوز خوانده نشده."""
    t = time.localtime()
    gy, gm, gd = t.tm_year, t.tm_mon, t.tm_mday
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return f"{jy}/{jm:02d}/{jd:02d}"


def chains(cfg: dict) -> list[dict]:
    return (cfg.get("chain_store") or {}).get("chains") or CHAINS


# ---------------------------------------------------------------- خواندن فایل‌ها
_NS = "{urn:schemas-microsoft-com:office:spreadsheet}"


def _xml2003(path: Path) -> list[list]:
    """«XML Spreadsheet 2003» که بعضی نرم‌افزارها با پسوند .xls می‌سازند."""
    root = ET.parse(path).getroot()
    sheets = []
    for ws in root.iter(_NS + "Worksheet"):
        rows = []
        for r in ws.iter(_NS + "Row"):
            row = []
            for c in r.iter(_NS + "Cell"):
                idx = c.get(_NS + "Index")
                if idx:
                    row += [None] * (int(idx) - 1 - len(row))
                d = c.find(_NS + "Data")
                v = d.text if d is not None else None
                if d is not None and d.get(_NS + "Type") == "Number" and v is not None:
                    v = float(v)
                row.append(v)
            rows.append(row)
        sheets.append(rows)
    return sheets


def read_grid(path: Path) -> list[list[list]]:
    """همه شیت‌ها به‌صورت جدول خام (بدون سرستون)."""
    with open(path, "rb") as fh:
        head = fh.read(4096).lstrip(b"\xef\xbb\xbf \r\n\t")
    if head.startswith(b"<?xml") and b"urn:schemas-microsoft-com:office:spreadsheet" in head:
        return _xml2003(path)
    if head[:1] == b"<":  # جدول HTML با پسوند xls
        return [df.astype(object).where(df.notna(), None).values.tolist() for df in pd.read_html(path, header=None)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        books = pd.read_excel(path, sheet_name=None, header=None)
    return [df.astype(object).where(df.notna(), None).values.tolist() for df in books.values()]


def _num(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return 0.0 if pd.isna(v) else float(v)
    s = norm(v).replace(",", "").replace("٬", "").replace("/", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _barcode(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\D", "", norm(v))


# نقش هر ستون از روی متن سرستون (به ترتیب اولویت)
def _pick(heads: list[str], tests) -> int | None:
    for t in tests:
        for i, h in enumerate(heads):
            if h and t(h):
                return i
    return None


def _columns(heads: list[str]) -> dict:
    q = lambda h: "تعداد" in h or "مقدار" in h  # noqa: E731
    money = lambda h: "مبلغ" in h or "ریال" in h or "ارزش" in h  # noqa: E731
    return {
        "barcode": _pick(heads, [lambda h: "بارکد" in h, lambda h: h == "کدکالا"]),
        "name": _pick(heads, [lambda h: h == "نامکالا", lambda h: h == "کالا", lambda h: "نامکالا" in h]),
        "qty": _pick(heads, [lambda h: "خالص" in h and q(h) and "برگشت" not in h, lambda h: "مقدارفروش" in h,
                             lambda h: q(h) and "برگشت" not in h and "مرجوع" not in h]),
        "value": _pick(heads, [lambda h: "خالص" in h and money(h) and "برگشت" not in h, lambda h: "مبلغفروش" in h,
                               lambda h: "ارزشفروش" in h, lambda h: money(h) and "فروش" in h and "برگشت" not in h
                               and "مرجوع" not in h and "تخفیف" not in h and "مالیات" not in h]),
        "disc": _pick(heads, [lambda h: "تخفیف" in h]),
        "store": _pick(heads, [lambda h: h in ("شعبه", "فروشگاه", "نامشعبه", "نامفروشگاه")]),
        "subgroup": _pick(heads, [lambda h: "زیرگروه" in h, lambda h: h == "گروه" or h == "گروهکالا"]),
        "stock": _pick(heads, [lambda h: "موجودی" in h]),
    }


_DATE = re.compile(r"(1[34]\d\d)[/\-.](\d{1,2})[/\-.](\d{1,2})")


def parse_file(path: Path) -> dict:
    """سطرهای کالا (بارکد، نام، شعبه، تعداد، مبلغ خالص، تخفیف) و تاریخ شروع دوره گزارش، از هر فرمتی که زنجیره می‌دهد."""
    for grid in read_grid(path):
        for hi, row in enumerate(grid[:40]):
            heads = [squash(c) for c in row]
            cols = _columns(heads)
            if cols["name"] is None or cols["qty"] is None or (cols["barcode"] is None and cols["value"] is None):
                continue
            # تاریخ دوره: سطرهای بالای سرستون؛ اول سلولی که «از» دارد
            dates = []
            for r in grid[:hi]:
                for c in r:
                    if c is None:
                        continue
                    t = norm(c)
                    for j, m in enumerate(_DATE.finditer(t)):
                        first = j == 0 and "از" in t[:m.start()]
                        dates.append((0 if first else 1, f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"))
            rows = []
            for r in grid[hi + 1:]:
                get = lambda k: r[cols[k]] if cols[k] is not None and cols[k] < len(r) else None  # noqa: E731
                name = norm(get("name"))
                bc = _barcode(get("barcode")) if cols["barcode"] is not None else ""
                first = norm(r[0]) if r and r[0] is not None else ""
                if (not name and not bc) or "جمع" in name or first.startswith("جمع"):
                    continue
                rows.append({"barcode": bc, "name": name or bc, "store": norm(get("store")) if cols["store"] is not None else "",
                             "subgroup": norm(get("subgroup")) if cols["subgroup"] is not None else "",
                             "qty": _num(get("qty")), "value": _num(get("value")), "disc": _num(get("disc")),
                             "stock": _num(get("stock")) if cols["stock"] is not None and get("stock") is not None else None})
            if not rows:
                continue
            dates.sort()
            return {"rows": rows, "date_from": dates[0][1] if dates else None,
                    "columns": {k: (norm(row[v]) if v is not None else None) for k, v in cols.items()}}
    raise ValueError("سرستون «نام کالا» و «تعداد» در هیچ شیتی پیدا نشد")


def _aggregate(rows: list[dict]) -> list[dict]:
    """سطرهای تکراری (مثل برگشتی منفی همان کالا) جمع می‌شوند."""
    df = pd.DataFrame(rows)
    df["stock"] = pd.to_numeric(df["stock"], errors="coerce")
    df["key"] = df["barcode"].where(df["barcode"] != "", df["name"])
    g = df.groupby(["key", "store"], sort=False).agg(
        barcode=("barcode", "first"), name=("name", "first"), subgroup=("subgroup", "first"),
        qty=("qty", "sum"), value=("value", "sum"), disc=("disc", "sum"), stock=("stock", "max")).reset_index()
    g = g.drop(columns="key")
    g["stock"] = g["stock"].astype(object).where(g["stock"].notna(), None)
    return g.to_dict("records")


def file_month(name: str, date_from: str | None, today: str) -> tuple[str, str]:
    """(ماه yyyy/mm، منبع تشخیص)."""
    if date_from:
        return date_from[:7], "تاریخ داخل فایل"
    n = norm(name)
    m = re.search(r"برج\s*(\d{1,2})", n) or re.search(r"(?:^|\D)(\d{1,2})(?:\D|$)", re.sub(r"1[34]\d\d", " ", n))
    if not m or not 1 <= int(m.group(1)) <= 12:
        raise ValueError("ماه فایل مشخص نیست؛ «برج N» را در نام فایل بنویسید (مثلاً «شهروند برج 7.xlsx»)")
    mon = int(m.group(1))
    y = re.search(r"(1[34]\d\d)", n)
    if y:
        year = int(y.group(1))
    else:
        ty, tm = int(today[:4]), int(today[5:7])
        year = ty if mon <= tm else ty - 1
    return f"{year}/{mon:02d}", "نام فایل"


def file_chain(name: str, cfg: dict) -> str:
    n = norm(Path(name).stem).lower()
    nz = n.replace(" ", "")
    for c in chains(cfg):
        if any(norm(a).lower().replace(" ", "") in nz for a in c["match"]):
            return c["name"]
    # زنجیره تعریف‌نشده: نام فایل بدون «برج N»، سال و کلمه‌های اضافه
    s = re.sub(r"برج\s*\d+|1[34]\d\d|\d+|فروش|گزارش|sell ?out", " ", n)
    return re.sub(r"\s+", " ", s).strip(" -_") or Path(name).stem


# ---------------------------------------------------------------- آرشیو ماه‌ها
class SelloutStore:
    def __init__(self, folder: Path, cache_dir: Path, env_file: Path):
        self.folder = folder
        self.archive = folder / "_archive"
        self.index_file = self.archive / "index.json"
        self.cache = cache_dir / "barcodes.pkl"
        self.env_file = env_file
        self.lock = threading.Lock()
        self.bc: dict | None = None
        self.bc_time = 0.0
        self.bc_error: str | None = None
        self.bc_busy = False
        self.frame: pd.DataFrame | None = None

    def _index(self) -> dict:
        if self.index_file.exists():
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        return {"files": {}}

    @staticmethod
    def _sig(p: Path) -> str:
        return hashlib.sha1(p.read_bytes()).hexdigest()

    @staticmethod
    def _slug(month: str, chain: str) -> str:
        safe = re.sub(r'[\\/:*?"<>|]', "_", chain)
        return f"{month.replace('/', '-')}__{safe}.json"

    def sync(self, cfg: dict, today: str) -> list[dict]:
        """فایل‌های جدید/تغییرکرده پوشه را در آرشیو ثبت می‌کند. خروجی: وضعیت همه فایل‌های پوشه."""
        with self.lock:
            self.archive.mkdir(parents=True, exist_ok=True)
            idx = self._index()
            files = sorted(p for p in self.folder.iterdir()
                           if p.is_file() and p.suffix.lower() in EXCEL and not p.name.startswith("~$"))
            seen = {}
            changed = set()
            for p in files:
                sig = self._sig(p)
                old = idx["files"].get(p.name)
                if old and old.get("sig") == sig and old.get("ok"):
                    seen[p.name] = old
                    continue
                info = {"sig": sig, "ok": False, "parsed_at": time.strftime("%Y-%m-%d %H:%M")}
                try:
                    res = parse_file(p)
                    month, how = file_month(p.name, res["date_from"], today)
                    rows = _aggregate(res["rows"])
                    info.update(ok=True, month=month, month_from=how, chain=file_chain(p.name, cfg), rows=len(rows),
                                qty=sum(r["qty"] for r in rows), value=sum(r["value"] for r in rows),
                                columns=res["columns"])
                    raw = self.archive / "raw" / month.replace("/", "-")
                    raw.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, raw / p.name)
                    info["_rows"] = rows
                    changed.add((month, info["chain"]))
                except Exception as e:  # فایل خراب یا فرمت ناشناخته: بقیه فایل‌ها خوانده می‌شوند
                    info["error"] = str(e)
                seen[p.name] = info
            # هر (ماه، زنجیره) تغییرکرده از همه فایل‌های فعلی آن کلید دوباره ساخته می‌شود
            for month, chain in changed:
                parts = [(n, i) for n, i in seen.items() if i.get("ok") and i["month"] == month and i["chain"] == chain]
                rows = []
                for n, i in parts:
                    if "_rows" not in i:  # فایل تغییرنکرده همان کلید: از نسخه پشتیبان دوباره خوانده می‌شود
                        i["_rows"] = _aggregate(parse_file(self.archive / "raw" / month.replace("/", "-") / n)["rows"])
                    rows += i["_rows"]
                doc = {"month": month, "chain": chain, "sources": [n for n, _ in parts],
                       "saved_at": time.strftime("%Y-%m-%d %H:%M"), "rows": rows}
                (self.archive / self._slug(month, chain)).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            for i in seen.values():
                i.pop("_rows", None)
            # فایل‌هایی که از پوشه برداشته شده‌اند از فهرست می‌روند ولی داده ماهشان در آرشیو می‌ماند
            idx["files"] = seen
            self.index_file.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
            if changed or self.frame is None:
                self.frame = self._load()
            return [{"file": n, **{k: v for k, v in i.items() if k != "sig"}} for n, i in seen.items()]

    def _load(self) -> pd.DataFrame:
        parts = []
        for f in sorted(self.archive.glob("*.json")):
            if f.name == "index.json":
                continue
            doc = json.loads(f.read_text(encoding="utf-8"))
            if doc.get("rows"):
                parts.append(pd.DataFrame(doc["rows"]).assign(month=doc["month"], chain=doc["chain"]))
        if not parts:
            return pd.DataFrame(columns=["barcode", "name", "store", "subgroup", "qty", "value", "disc", "stock", "month", "chain"])
        return pd.concat(parts, ignore_index=True)

    # ------------------------------------------------------------ بارکد → کد کالای کارآمد
    def barcodes(self) -> dict:
        if self.bc is None and self.cache.exists():
            df = pd.read_pickle(self.cache)
            self.bc, self.bc_time = dict(zip(df["barcode"], df["code"])), self.cache.stat().st_mtime
        stale = time.time() - self.bc_time > BARCODE_HOURS * 3600
        if self.bc is None:
            self._fetch_barcodes()
        elif stale and not self.bc_busy:
            threading.Thread(target=self._fetch_barcodes, daemon=True).start()
        return self.bc or {}

    def _fetch_barcodes(self):
        self.bc_busy = True
        try:
            cn = sql_source.connect(sql_source.settings(sql_source.read_env(self.env_file)))
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    df = pd.read_sql(BARCODE_SQL, cn)
            finally:
                cn.close()
            df["code"] = df["code"].map(loader._clean_code)
            df["barcode"] = df["barcode"].map(_barcode)
            df = df[df["barcode"] != ""].drop_duplicates("barcode")
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_pickle(self.cache)
            self.bc, self.bc_time, self.bc_error = dict(zip(df["barcode"], df["code"])), time.time(), None
        except Exception as e:  # بدون اتصال: نگاشت قبلی (اگر باشد) می‌ماند
            self.bc_error = str(e)
            if self.bc is None:
                self.bc = {}
        finally:
            self.bc_busy = False
