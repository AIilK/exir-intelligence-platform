"""خواندن لایو داده فروش از دیتابیس نرم‌افزار پخش کارآمد (KDB) روی SQL Server.

همان ستون‌های گزارش فروش کارآمد از ویوها ساخته می‌شود و از مسیر نرمال‌سازی loader عبور می‌کند:
  فاکتور فروش و برگشتی  ← vwFactorFBLinesFull  (هر سطر یک کالا)
  درخواست               ← vwFactorDLinesFull   (FactorStatus: 0 درخواست، 1 فاکتور شده، 2 باطل — باطل‌ها حذف)
  لیست مشتریان          ← tblCustomer
ستون‌های cate و Brand در دیتابیس نیستند؛ از category_map.json خوانده می‌شوند
(ساخت دوباره از روی یک فایل اکسل نمونه: python backend/sql_source.py --build-map "<مسیر فایل>").

ویوهای کارآمد کند هستند (حدود ۳۵ ثانیه برای هر ماه کامل)، پس داده ماه‌به‌ماه در data/cache/sql
ذخیره می‌شود: ماه جاری هر چند دقیقه، ماه‌های بسته روزی یک بار و هر بار فقط یک ماه تازه می‌شود.

لایو: هر چند ثانیه امضای هر روز (تعداد فاکتور + بزرگ‌ترین RowVer) از جدول‌های پایه خوانده می‌شود
(کسری از ثانیه برای کل تاریخچه)؛ فقط روزهایی که امضایشان عوض شده از ویوها دوباره خوانده و جایگزین می‌شوند.
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
import threading
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

import loader

ROOT = Path(__file__).resolve().parent.parent
MAP_FILE = ROOT / "category_map.json"
CACHE_DIR = ROOT / "data" / "cache" / "sql"
CACHE_VERSION = 1
ENV_PREFIX = "KARAMAD_SQLSERVER_"
CUSTOMERS_REFRESH_MIN = 60
# مشتریان «نمونه کالا» (فاکتور صفر ریالی نمونه محصول، در هر شعبه کد جدا): از نمودار نرخ تخفیف کنار گذاشته می‌شوند
SAMPLE_CUSTOMER = "نمونه کالا"

# ستون‌های مشترک فاکتور و درخواست با نام ستون‌های گزارش کارآمد
_COLS = """
    v.BranchName AS [نام شعبه], v.BranchCode AS [کد شعبه],
    v.SupervisorCode AS [کد سرپرست], v.SupervisorName AS [نام سرپرست],
    v.VisitorCode AS [کد فروشنده], v.VisitorName AS [نام فروشنده],
    v.GoodsCode AS [کد کالا], v.GoodsName AS [نام کالا],
    v.BrandName AS [نام برند], v.CategoryName AS [نام گروه کالا],
    v.CityName AS [نام شهر], v.RouteName AS [نام مسیر], v.LineName AS [نام لاین],
    v.PaymentTypeName AS [نحوه پرداخت],
    v.Code AS [شماره], v.ID AS [شناسه فاکتور],
    v.CustomerCode AS [کد مشتری], v.CustomerName AS [نام مشتری],
    v.TotalT AS [مجموع تعداد], v.Price AS [فی فروش], v.SumPrice AS [جمع قبل تخفیف],
    v.Discount AS [تخفیف حجمی], v.CashDiscount AS [تخفیف نقدی],
    v.Vat AS [ارزش افزوده], v.PriceP AS [قابل پرداخت]"""

SALES_SQL = f"""
SELECT v.PersianDate AS [تاریخ], v.FactorType AS [نوع فاکتور], v.FactorDCode AS [شماره مرجع], {_COLS}
FROM dbo.vwFactorFBLinesFull v
WHERE v.DateE BETWEEN ? AND ? AND v.BranchName LIKE ?"""

REQUESTS_SQL = f"""
SELECT c.PersianDate AS [تاریخ], v.FactorStatus AS [وضعیت درخواست], {_COLS}
FROM dbo.vwFactorDLinesFull v
JOIN dbo.tblCalendar c ON c.GregorianDate = v.DateE
WHERE v.DateE BETWEEN ? AND ? AND v.BranchName LIKE ? AND v.FactorStatus <> 2"""

CUSTOMERS_SQL = """
SELECT b.Name AS branch, c.Code AS customer_code, c.Name AS customer, ci.Name AS city,
       g.Name AS trade, gr.Name AS grade, c.RFMScore AS rfm, cr.Credit AS credit,
       c.Status AS active, pt.Name AS payment
FROM dbo.tblCustomer c
JOIN dbo.tblBranch b ON b.ID = c.BranchRef
LEFT JOIN dbo.tblCity ci ON ci.ID = c.CityRef
LEFT JOIN dbo.tblGuild g ON g.ID = c.GuildRef
LEFT JOIN dbo.tblGrade gr ON gr.ID = c.GradeRef
LEFT JOIN dbo.tblPaymentType pt ON pt.ID = c.PaymentTypeRef
LEFT JOIN (SELECT CustomerRef, MAX(Credit) AS Credit FROM dbo.tblCustomerCredit GROUP BY CustomerRef) cr
       ON cr.CustomerRef = c.ID
WHERE c.Status = 1 AND b.Name LIKE ?"""

# ماه‌های شمسی از history_from (یا n ماه آخر) تا ماه جاری: بازه میلادی، آخرین روز شمسی و روزهای کاری
# (همه به‌جز جمعه)؛ سپری‌شده = روزهای کاری قبل از امروز
MONTHS_SQL = """
SET NOCOUNT ON;
DECLARE @cur nvarchar(7) = (SELECT LEFT(PersianDate, 7) FROM dbo.tblCalendar
                            WHERE GregorianDate = CAST(GETDATE() AS date));
DECLARE @today nvarchar(10) = (SELECT PersianDate FROM dbo.tblCalendar WHERE GregorianDate = CAST(GETDATE() AS date));
SELECT TOP (?) LEFT(PersianDate, 7) AS month, MIN(GregorianDate) AS d_from, MAX(GregorianDate) AS d_to,
       MAX(PersianDate) AS last_day, @today AS today,
       SUM(CASE WHEN PersianWeekName <> N'جمعه' THEN 1 ELSE 0 END) AS wd_total,
       SUM(CASE WHEN PersianWeekName <> N'جمعه' AND GregorianDate < CAST(GETDATE() AS date) THEN 1 ELSE 0 END) AS wd_elapsed
FROM dbo.tblCalendar
WHERE LEFT(PersianDate, 7) <= @cur AND LEFT(PersianDate, 7) >= ?
GROUP BY LEFT(PersianDate, 7)
ORDER BY month DESC"""


# ورودی‌های بخش برنامه‌ریزی (planning.py)؛ هر دو سبک‌اند و چند ثانیه طول می‌کشند.
# تقویم: همه روزها از اولین تاریخچه تا چند ماه آینده (روز کاری = به‌جز جمعه)
CALENDAR_SQL = """
SELECT PersianDate AS date, CASE WHEN PersianWeekName <> N'جمعه' THEN 1 ELSE 0 END AS workday
FROM dbo.tblCalendar WHERE PersianDate >= ? AND PersianDate < ?"""

# تاریخچه قدیمی (قبل از history_from) فقط برای ضریب فصلی: تعداد خالص ماهانه هر کالا از جدول‌های پایه
# (ویوها برای این حجم کندند). فروش مثبت و برگشتی منفی.
OLD_HISTORY_SQL = """
SET NOCOUNT ON;
SELECT x.month, x.goods_code, x.goods_group, SUM(x.qty) AS qty FROM (
  SELECT LEFT(c.PersianDate, 7) AS month, g.Code AS goods_code, gc.Name AS goods_group, l.TotalT AS qty
  FROM dbo.tblFactorFLines l JOIN dbo.tblFactorF f ON f.ID = l.FactorRef
  JOIN dbo.tblBranch b ON b.ID = f.BranchRef JOIN dbo.tblCalendar c ON c.GregorianDate = f.DateE
  JOIN dbo.tblGoods g ON g.ID = l.GoodsRef LEFT JOIN dbo.tblGoodsCategory gc ON gc.ID = g.CategoryRef
  WHERE b.Name LIKE ? AND c.PersianDate < ?
  UNION ALL
  SELECT LEFT(c.PersianDate, 7), g.Code, gc.Name, -l.TotalT
  FROM dbo.tblFactorBLines l JOIN dbo.tblFactorB f ON f.ID = l.FactorRef
  JOIN dbo.tblBranch b ON b.ID = f.BranchRef JOIN dbo.tblCalendar c ON c.GregorianDate = f.DateE
  JOIN dbo.tblGoods g ON g.ID = l.GoodsRef LEFT JOIN dbo.tblGoodsCategory gc ON gc.ID = g.CategoryRef
  WHERE b.Name LIKE ? AND c.PersianDate < ?
) x GROUP BY x.month, x.goods_code, x.goods_group"""
PLAN_INPUTS_REFRESH_HOURS = 24 * 7

# امضای هر روز در جدول‌های پایه فاکتور (F)، برگشتی (B) و درخواست (D). SQL Server با هر ثبت یا ویرایش
# ستون RowVer را بالا می‌برد و حذف، تعداد را کم می‌کند؛ پس هر تغییر سرفاکتور، امضای همان روز را عوض می‌کند.
# (ویرایشی که فقط سطرها را عوض کند و به سرفاکتور دست نزند، با بروزرسانی دوره‌ای ماه گرفته می‌شود.)
# NOLOCK: این کوئری فقط «چه روزی عوض شد» را می‌پرسد و نباید پشت قفل ثبت فاکتور در کارآمد بماند
# (بدون آن یک بار ۶۲ ثانیه منتظر ماند)؛ اگر تغییر نیمه‌کاره دیده شود، بررسی بعدی خودش اصلاح می‌کند.
_SIG_ONE = """SELECT '{t}' AS t, f.DateE AS d, COUNT(*) AS n, MAX(f.RowVer) AS rv FROM dbo.tblFactor{t} f WITH (NOLOCK)
JOIN dbo.tblBranch b WITH (NOLOCK) ON b.ID = f.BranchRef WHERE f.DateE BETWEEN ? AND ? AND b.Name LIKE ? GROUP BY f.DateE"""
SIG_TIMEOUT = 30  # ثانیه
SIG_SQL = "\nUNION ALL\n".join(_SIG_ONE.format(t=t) for t in "FBD")
# اگر در یک ماه بیش از این تعداد روز عوض شده باشد، کل ماه یک‌جا خوانده می‌شود
LIVE_MAX_DAYS = 8


def branch_patterns(cfg: dict) -> list[str]:
    """branch_like می‌تواند چند عبارت جداشده با | یا , باشد (مثل «هیبرید|زنجیره|اینترنت»)؛ خالی = همه شعب."""
    parts = [p.strip() for p in re.split(r"[|,،]", str(cfg.get("branch_like") or "")) if p.strip()]
    return [f"%{p}%" for p in parts] or ["%%"]


def _branch_sql(sql: str, n: int) -> str:
    """«ستون LIKE ?» شعبه را به «(ستون LIKE ? OR ...)» برای n عبارت تبدیل می‌کند."""
    for col in ("v.BranchName", "b.Name"):
        sql = sql.replace(f"{col} LIKE ?", "(" + " OR ".join([f"{col} LIKE ?"] * n) + ")")
    return sql


def history_window(cfg: dict) -> tuple[int, str]:
    """(حداکثر تعداد ماه، اولین ماه) برای MONTHS_SQL. اگر history_from (مثل 1404/01) تنظیم شده باشد،
    همه ماه‌ها از آن ماه تا ماه جاری نگه داشته می‌شوند و history_months نادیده گرفته می‌شود."""
    start = str(cfg.get("history_from") or "").strip().replace("-", "/")
    if start:
        return 1000, start[:7]
    return int(cfg["history_months"]), "0000/00"


def _history_start(cfg: dict, months: list[dict]) -> str:
    """اولین ماه تاریخچه بارگذاری‌شده؛ تاریخچه قدیمی (برای ضریب فصلی) قبل از این ماه خوانده می‌شود."""
    start = history_window(cfg)[1]
    return start if start != "0000/00" else min(m["month"] for m in months)


# ---------------------------------------------------------------- اتصال
def read_env(path: Path) -> dict:
    """فایل .env ساده (KEY=VALUE)؛ متغیرهای محیطی سیستم اولویت دارند."""
    env = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k.startswith(ENV_PREFIX)})
    return env


def settings(env: dict, prefix: str = ENV_PREFIX) -> dict:
    g = lambda k, d=None: env.get(prefix + k, d)
    missing = [k for k in ("SERVER", "DATABASE", "USERNAME", "PASSWORD") if not g(k)]
    if missing:
        raise loader.DataError(f"تنظیمات اتصال SQL در فایل .env کامل نیست: {', '.join(prefix + k for k in missing)}")
    return {"server": g("SERVER"), "database": g("DATABASE"), "username": g("USERNAME"), "password": g("PASSWORD"),
            "driver": g("DRIVER", "ODBC Driver 18 for SQL Server"),
            "trust": g("TRUST_CERTIFICATE", "true").lower() in ("1", "true", "yes")}


def connect(s: dict):
    try:
        import pyodbc
    except ImportError:
        raise loader.DataError("کتابخانه pyodbc نصب نیست: python -m pip install pyodbc")
    cs = (f"DRIVER={{{s['driver']}}};SERVER={s['server']};DATABASE={s['database']};"
          f"UID={s['username']};PWD={{{s['password']}}};Encrypt=yes;"
          f"TrustServerCertificate={'yes' if s['trust'] else 'no'}")
    try:
        return pyodbc.connect(cs, timeout=15)
    except pyodbc.Error as e:
        raise loader.DataError(f"اتصال به SQL Server ({s['server']}/{s['database']}) ممکن نشد: {e}")


def _read(cn, sql: str, params: list) -> pd.DataFrame:
    with warnings.catch_warnings():  # pandas برای اتصال pyodbc هشدار SQLAlchemy می‌دهد
        warnings.simplefilter("ignore", UserWarning)
        return pd.read_sql(sql, cn, params=params)


# ---------------------------------------------------------------- تبدیل
def _apply_map(df: pd.DataFrame, cmap: dict) -> pd.DataFrame:
    """ستون‌های cate و Brand: اول بر اساس کد کالا، بعد گروه کالا / برند، وگرنه خود گروه و برند."""
    code = df["کد کالا"].map(loader._clean_code)
    prod = cmap.get("products", {})
    group = df["نام گروه کالا"].map(loader._clean_text)
    brand = df["نام برند"].map(loader._clean_text)
    df["cate"] = code.map(lambda c: prod.get(c, [None, None])[0])
    df["cate"] = df["cate"].fillna(group.map(cmap.get("groups", {}))).fillna(cmap.get("fallback", "سایر"))
    df["Brand"] = code.map(lambda c: prod.get(c, [None, None])[1])
    df["Brand"] = df["Brand"].fillna(brand.map(cmap.get("brands", {}))).fillna(brand)
    return df


def _categorize(df: pd.DataFrame | None, cmap: dict):
    """گروه کلی کالا (cate) از نگاشت فعلی: کد کالا ← گروه کارآمد ← «سایر».
    موقع ساخت داده اعمال می‌شود تا تغییر category_map.json بدون خواندن دوباره ماه‌ها اثر کند."""
    if df is None:
        return
    prod = {k: v[0] for k, v in cmap.get("products", {}).items()}
    cat = df["product_code"].map(prod).fillna(df["product_group"].map(cmap.get("groups", {})))
    df["category"] = cat.fillna(cmap.get("fallback", "سایر")).astype(object)


def _compact(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """متن‌های تکراری (نام شعبه، کالا، ...) یک شیء مشترک شوند؛ حافظه و حجم کش چند برابر کمتر.
    (pandas 3 بدون pyarrow هر مقدار متنی را جدا نگه می‌دارد.)"""
    if df is not None:
        for c in df.columns:
            if pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object:
                df[c] = df[c].astype("category").astype(object)
    return df


def _load_map() -> dict:
    return json.loads(MAP_FILE.read_text(encoding="utf-8")) if MAP_FILE.is_file() else {}


def _read_sig(cn, d_from, d_to, like: list[str]) -> dict:
    """{(جدول F/B/D، تاریخ میلادی): (تعداد، RowVer)} برای همه روزهای بازه."""
    cur = cn.cursor()
    old, cn.timeout = cn.timeout, SIG_TIMEOUT
    try:
        cur.execute(_branch_sql(SIG_SQL, len(like)), *([d_from, d_to, *like] * 3))
        return {(r.t, r.d): (int(r.n), bytes(r.rv)) for r in cur.fetchall()}
    finally:
        cn.timeout = old


def _month_sig(sig: dict, m: dict) -> dict:
    return {k: v for k, v in sig.items() if m["d_from"] <= k[1] <= m["d_to"]}


def _runs(days: list) -> list[list]:
    """روزهای مرتب ← بازه‌های پیوسته [از، تا] تا هر بازه با یک کوئری خوانده شود."""
    out: list[list] = []
    for d in days:
        if out and (d - out[-1][1]).days == 1:
            out[-1][1] = d
        else:
            out.append([d, d])
    return out


def _patch(old: pd.DataFrame | None, new: pd.DataFrame | None, dates: set[str]) -> pd.DataFrame | None:
    """سطرهای روزهای داده‌شده (تاریخ شمسی) با خوانش تازه جایگزین می‌شوند."""
    keep = old[~old["date"].isin(dates)] if old is not None else None
    parts = [x for x in (keep, new) if x is not None and len(x)]
    return _compact(pd.concat(parts, ignore_index=True)) if parts else None


def _month_frames(raw_s: pd.DataFrame, raw_r: pd.DataFrame, cmap: dict):
    sales = loader._normalize(_apply_map(raw_s, cmap)) if len(raw_s) else None
    requests = loader._normalize(_apply_map(raw_r, cmap)) if len(raw_r) else None
    if sales is not None:
        loader.finish(sales, requests)
    elif requests is not None:  # ماهی که فقط درخواست دارد (مثلاً روز اول ماه)
        requests["net"] = requests["gross"] - requests["vol_disc"]
        requests["status"] = pd.to_numeric(requests["status"], errors="coerce").fillna(0).astype(int)
    return _compact(sales), _compact(requests)


# ---------------------------------------------------------------- مخزن ماه‌به‌ماه
class SqlStore:
    """داده هر ماه جدا نگه داشته و روی دیسک کش می‌شود؛ refresh_step هر بار یک کار انجام می‌دهد."""

    def __init__(self, env_file: Path):
        self.env_file = env_file
        self.months: list[dict] = []          # از جدید به قدیم
        self.data: dict[str, dict] = {}       # month -> {sales, requests, fetched, branch_like}
        self.customers: pd.DataFrame | None = None
        self.customers_fetched = 0.0
        self.customers_branch: str | None = None  # فیلتر شعبه‌ای که لیست مشتریان با آن خوانده شده
        self.plan_inputs: dict | None = None  # {calendar, old, fetched, branch_like, before}
        self.force_current = False
        self.force_months: set[str] = set()   # ماه‌هایی که کاربر دستی خواسته؛ قبل از کارهای دیگر خوانده می‌شوند
        self.fetching: str | None = None      # ماهی که همین الان در حال خواندن است
        self.lock = threading.Lock()
        self.data_lock = threading.Lock()     # جایگزینی داده یک ماه (گام کامل و گام لایو در دو رشته جدا)
        self.live_checked = 0.0               # آخرین بررسی لایو
        self.live_changed = 0.0               # آخرین باری که بررسی لایو داده تازه آورد
        self._prep: dict[str, tuple] = {}     # month -> (sales, requests, map_key, آماده sales, آماده requests)
        self.conn_info: dict = {}

    # -- کش دیسک
    @staticmethod
    def _path(month: str) -> Path:
        return CACHE_DIR / f"{month.replace('/', '-')}.pkl"

    def load_cache(self, cfg: dict):
        if not CACHE_DIR.is_dir():
            return
        for p in CACHE_DIR.glob("*.pkl"):
            try:
                with p.open("rb") as f:
                    d = pickle.load(f)
            except Exception:
                p.unlink(missing_ok=True)
                continue
            # کش با فیلتر شعبه دیگر هم بارگذاری می‌شود تا داشبورد خالی نماند؛ stale() آن را دوباره می‌خواند
            if d.get("version") != CACHE_VERSION:
                continue
            if p.stem == "customers":
                self.customers, self.customers_fetched = d["frame"], d["fetched"]
                self.customers_branch = d.get("branch_like")
            elif p.stem == "plan_inputs":
                self.plan_inputs = d
            else:
                if not d.get("compact2"):  # کش قدیمی: یک بار فشرده و دوباره ذخیره شود
                    d["sales"], d["requests"], d["compact2"] = _compact(d["sales"]), _compact(d["requests"]), True
                    self._save(p, d)
                self.data[d["month"]] = d
                if d.get("info") and not any(m["month"] == d["month"] for m in self.months):
                    self.months.append(d["info"])
        self.months.sort(key=lambda m: m["month"], reverse=True)

    def _save(self, path: Path, d: dict):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")  # دو رشته ممکن است هم‌زمان یک ماه را ذخیره کنند
        with tmp.open("wb") as f:
            pickle.dump(d, f)
        tmp.replace(path)

    # -- یک گام تازه‌سازی
    def refresh_step(self, cfg: dict) -> str | None:
        """یک ماه یا لیست مشتریان را تازه می‌کند؛ نام کار انجام‌شده یا None اگر کاری نبود."""
        with self.lock:
            s = settings(read_env(self.env_file))
            self.conn_info = {"server": s["server"], "database": s["database"], "username": s["username"]}
            like = branch_patterns(cfg)
            now = time.time()
            cn = connect(s)
            try:
                cur = cn.cursor()
                cur.execute(MONTHS_SQL, *history_window(cfg))
                while cur.description is None and cur.nextset():
                    pass
                months = [{"month": r.month, "d_from": r.d_from, "d_to": r.d_to, "last_day": r.last_day, "today": r.today,
                           "wd_total": int(r.wd_total), "wd_elapsed": int(r.wd_elapsed)} for r in cur.fetchall()]
                if not months:
                    raise loader.DataError("تاریخ امروز در تقویم کارآمد (tblCalendar) پیدا نشد.")
                self.months = months
                keep = {m["month"] for m in months}
                with self.data_lock:
                    for k in [k for k in self.data if k not in keep]:
                        del self.data[k]
                cur_m = months[0]["month"]

                def stale(m: dict) -> bool:
                    d = self.data.get(m["month"])
                    if d is None or d.get("branch_like") != cfg["branch_like"]:
                        return True
                    if m["month"] == cur_m:
                        mins = float(cfg.get("refresh_minutes") or 0)
                        return self.force_current or (mins > 0 and now - d["fetched"] >= mins * 60)
                    # ماه بسته: یک بار پس از بسته شدن و بعد هر history_refresh_hours ساعت
                    return now - d["fetched"] >= float(cfg["history_refresh_hours"]) * 3600 \
                        or d.get("closed") is False

                self.force_months &= keep
                task = next((m for m in months[:1] if stale(m)), None)
                # ماه‌هایی که دستی درخواست شده‌اند، از جدید به قدیم
                task = task or next((m for m in months[1:] if m["month"] in self.force_months), None)
                if task is None and (self.customers is None or now - self.customers_fetched >= CUSTOMERS_REFRESH_MIN * 60
                                     or self.customers_branch != cfg["branch_like"]):
                    self._fetch_customers(cn, like, cfg)
                    return "customers"
                task = task or next((m for m in months[1:] if stale(m)), None)
                if task is None:
                    before = _history_start(cfg, months)
                    p = self.plan_inputs
                    if p is None or p.get("branch_like") != cfg["branch_like"] or p.get("before") != before \
                            or now - p["fetched"] >= PLAN_INPUTS_REFRESH_HOURS * 3600:
                        self._fetch_plan_inputs(cn, like, cfg, before)
                        return "plan"
                    return None
                self.fetching = task["month"]
                try:
                    self._fetch_month(cn, task, like, cfg, closed=task["month"] != cur_m)
                finally:
                    self.fetching = None
                self.force_months.discard(task["month"])
                if task["month"] == cur_m:
                    self.force_current = False
                return task["month"]
            finally:
                cn.close()

    def _fetch_month(self, cn, m: dict, like: list[str], cfg: dict, closed: bool):
        cmap = _load_map()
        # امضای روزها پیش از خواندن: تغییری که حین خواندن (تا چند دقیقه) ثبت شود، در گام لایو بعدی گرفته می‌شود
        sig = _month_sig(_read_sig(cn, m["d_from"], m["d_to"], like), m)
        rng = [m["d_from"], m["d_to"], *like]
        sales, requests = _month_frames(_read(cn, _branch_sql(SALES_SQL, len(like)), rng),
                                        _read(cn, _branch_sql(REQUESTS_SQL, len(like)), rng), cmap)
        d = {"version": CACHE_VERSION, "month": m["month"], "info": m, "branch_like": cfg["branch_like"],
             "fetched": time.time(), "closed": closed, "compact2": True, "sales": sales, "requests": requests,
             "sig": sig}
        with self.data_lock:
            self.data[m["month"]] = d
        self._save(self._path(m["month"]), d)

    # -- لایو
    def live_step(self, cfg: dict) -> bool:
        """روزهای تغییرکرده همه ماه‌های بارگذاری‌شده را پیدا می‌کند و فقط همان روزها را دوباره می‌خواند.
        True اگر داده عوض شد. مستقل از refresh_step (رشته جدا) تا خواندن طولانی یک ماه، لایو را معطل نکند."""
        months = [m for m in self.months if (d := self.data.get(m["month"])) is not None
                  and d.get("branch_like") == cfg["branch_like"]]
        if not months:
            return False
        like = branch_patterns(cfg)
        cn = connect(settings(read_env(self.env_file)))
        try:
            sig = _read_sig(cn, min(m["d_from"] for m in months), max(m["d_to"] for m in months), like)
            self.live_checked = time.time()
            cmap, changed = None, False
            for m in months:
                new = _month_sig(sig, m)
                with self.data_lock:
                    cur = self.data.get(m["month"])
                    if cur is not None and cur.get("sig") is None:
                        # کش قدیمی بدون امضا: از همین لحظه مبنا می‌شود (بروزرسانی دوره‌ای ماه سر جایش است)
                        self.data[m["month"]] = {**cur, "sig": new}
                        continue
                if cur is None:
                    continue
                old = cur["sig"]
                days = sorted({k[1] for k in old.keys() | new.keys() if old.get(k) != new.get(k)})
                if not days:
                    continue
                if len(days) > LIVE_MAX_DAYS:  # مثلاً کش قدیمی پس از اجرای دوباره: کل ماه یک‌جا
                    self.request_months([m["month"]])
                    continue
                cmap = cmap if cmap is not None else _load_map()
                raw_s, raw_r = [], []
                for a, b in _runs(days):
                    rng = [a, b, *like]
                    raw_s.append(_read(cn, _branch_sql(SALES_SQL, len(like)), rng))
                    raw_r.append(_read(cn, _branch_sql(REQUESTS_SQL, len(like)), rng))
                sales, requests = _month_frames(pd.concat(raw_s, ignore_index=True),
                                                pd.concat(raw_r, ignore_index=True), cmap)
                day_set = set(days)
                dates = {f"{m['month']}/{(x - m['d_from']).days + 1:02d}" for x in days}
                with self.data_lock:
                    cur = self.data.get(m["month"])
                    if cur is None or cur.get("sig") is None:
                        continue
                    d = {**cur, "sales": _patch(cur["sales"], sales, dates),
                         "requests": _patch(cur["requests"], requests, dates),
                         "sig": {**{k: v for k, v in cur["sig"].items() if k[1] not in day_set},
                                 **{k: v for k, v in new.items() if k[1] in day_set}},
                         "live": time.time()}
                    self.data[m["month"]] = d
                self._save(self._path(m["month"]), d)
                changed = True
            if changed:
                self.live_changed = time.time()
            return changed
        finally:
            cn.close()

    def _fetch_customers(self, cn, like: list[str], cfg: dict):
        c = _read(cn, _branch_sql(CUSTOMERS_SQL, len(like)), like)
        c["customer_code"] = c["customer_code"].map(loader._clean_code)
        for k in ("branch", "customer", "city", "trade", "payment"):
            c[k] = c[k].map(loader._clean_text)
        c["active"] = c["active"].astype(bool)
        self.customers, self.customers_fetched = c, time.time()
        self.customers_branch = cfg["branch_like"]
        self._save(CACHE_DIR / "customers.pkl", {"version": CACHE_VERSION, "branch_like": cfg["branch_like"],
                                                  "frame": c, "fetched": self.customers_fetched})

    def _fetch_plan_inputs(self, cn, like: list[str], cfg: dict, before: str):
        cal = _read(cn, CALENDAR_SQL, ["1395/01/01", f"{int(before[:4]) + 4}/01/01"])
        cal["date"] = cal["date"].astype(str).str.strip()
        cal["workday"] = cal["workday"].astype(bool)
        old = _read(cn, _branch_sql(OLD_HISTORY_SQL, len(like)), [*like, f"{before}/01", *like, f"{before}/01"])
        old["goods_code"] = old["goods_code"].map(loader._clean_code)
        old["goods_group"] = old["goods_group"].map(loader._clean_text)
        old["qty"] = pd.to_numeric(old["qty"], errors="coerce").fillna(0.0)
        self.plan_inputs = {"version": CACHE_VERSION, "branch_like": cfg["branch_like"], "before": before,
                            "fetched": time.time(), "calendar": cal, "old": old}
        self._save(CACHE_DIR / "plan_inputs.pkl", self.plan_inputs)

    def request_refresh(self):
        self.force_current = True

    def request_months(self, months: list[str]):
        """ماه‌های داده‌شده در اولین فرصت دوباره خوانده می‌شوند (ماه جاری از مسیر خودش)."""
        cur = self.months[0]["month"] if self.months else None
        for m in months:
            if m == cur:
                self.force_current = True
            else:
                self.force_months.add(m)

    # -- ساخت داده نهایی برای داشبورد
    def _prepared(self, d: dict, cmap: dict, map_key):
        """ستون‌های ساختنی (ماه، گروه کلی، نمونه کالا) برای یک ماه؛ تا داده یا نگاشت آن ماه عوض نشده، دوباره ساخته نمی‌شود
        (در لایو فقط ماهی که تغییر کرده دوباره آماده می‌شود، نه کل تاریخچه)."""
        p = self._prep.get(d["month"])
        if p is not None and p[0] is d["sales"] and p[1] is d["requests"] and p[2] == map_key:
            return p[3], p[4]
        out = []
        for df in (d["sales"], d["requests"]):
            if df is not None:
                df = df.copy(deep=False)  # ستون‌های تازه به داده ذخیره‌شده اضافه نشوند
                df["month"] = df["date"].str[:7]
                _categorize(df, cmap)
                df["is_sample"] = df["customer"].astype(str).str.contains(SAMPLE_CUSTOMER, regex=False)
                df = _compact(df)
            out.append(df)
        self._prep[d["month"]] = (d["sales"], d["requests"], map_key, *out)
        return out[0], out[1]

    def build(self) -> dict | None:
        with self.data_lock:
            data = dict(self.data)
        months = [m for m in self.months if m["month"] in data]
        cmap = _load_map()
        map_key = MAP_FILE.stat().st_mtime_ns if MAP_FILE.is_file() else None
        prepared = [self._prepared(data[m["month"]], cmap, map_key) for m in months[::-1]]
        for k in [k for k in self._prep if k not in data]:
            del self._prep[k]
        sales = [p[0] for p in prepared if p[0] is not None]
        if not sales:
            return None
        reqs = [p[1] for p in prepared if p[1] is not None]
        s = pd.concat(sales, ignore_index=True)
        r = pd.concat(reqs, ignore_index=True) if reqs else None
        cur = self.months[0]
        cur_sales = s[s["month"] == cur["month"]]
        core = [c for c in cmap.get("core_categories", []) if c in set(s["category"])]
        if len(core) < 2:
            core = cur_sales.groupby("category")["net"].sum().sort_values(ascending=False).head(6).index.tolist()
        # زمان آخرین داده: خوانش کامل یا وصله لایو، هر کدام تازه‌تر
        stamp = {k: max(d["fetched"], d.get("live") or 0) for k, d in data.items()}
        fetched = max(stamp[m["month"]] for m in months)
        info = self.conn_info or {"server": "", "database": "KDB"}
        plan = None
        if self.plan_inputs is not None:
            old = self.plan_inputs["old"].copy()
            prod = {k: v[0] for k, v in cmap.get("products", {}).items()}
            old["category"] = old["goods_code"].map(prod).fillna(old["goods_group"].map(cmap.get("groups", {}))) \
                .fillna(cmap.get("fallback", "سایر"))
            plan = {"calendar": self.plan_inputs["calendar"], "old": old, "before": self.plan_inputs["before"],
                    "fetched": datetime.fromtimestamp(self.plan_inputs["fetched"]).strftime("%Y-%m-%d %H:%M")}
        return {
            "sales": s,
            "requests": r,
            "customers": self.customers,
            "plan_inputs": plan,
            "meta": {
                "source": "sql",
                "file": f"{info['server']} / {info['database']}",
                "file_name": f"SQL لایو · {info['database']}",
                "sales_sheet": "vwFactorFBLinesFull",
                "requests_sheet": "vwFactorDLinesFull",
                "month": cur["month"],
                "month_from": f"{cur['month']}/01",
                "month_to": cur["last_day"],
                "today": cur.get("today"),
                "months": [{"month": m["month"], "from": f"{m['month']}/01", "to": m["last_day"],
                            "loaded": m["month"] in data,
                            "fetched": datetime.fromtimestamp(stamp[m["month"]]).strftime("%Y-%m-%d %H:%M")
                            if m["month"] in data else None,
                            "rows_sales": int(len(data[m["month"]]["sales"]))
                            if m["month"] in data and data[m["month"]]["sales"] is not None else 0,
                            "rows_requests": int(len(data[m["month"]]["requests"]))
                            if m["month"] in data and data[m["month"]]["requests"] is not None else 0}
                           for m in self.months],
                "loaded_at": datetime.fromtimestamp(stamp[cur["month"]] if cur["month"] in data else fetched)
                .strftime("%Y-%m-%d %H:%M:%S"),
                "wd_elapsed_file": float(max(cur["wd_elapsed"], 1)),
                "wd_total_file": float(cur["wd_total"]),
                "core_categories": core,
                "rows_sales": int(len(s)),
                "rows_requests": int(len(r)) if r is not None else 0,
                "rows_customers": int(len(self.customers)) if self.customers is not None else 0,
            },
        }


# ---------------------------------------------------------------- نگاشت cate / Brand
def build_map(excel: Path) -> dict:
    """نگاشت cate / Brand / گروه‌های اصلی را از یک فایل اکسل نمونه استخراج می‌کند (ابزار یک‌باره)."""
    d = loader.parse_workbook(excel)
    both = pd.concat([d["sales"], d["requests"]]) if d["requests"] is not None else d["sales"]
    mode = lambda x: x.value_counts().index[0]
    prod = both.groupby("product_code").agg(cate=("category", mode), brand=("brand_raw", mode))
    return {
        "source_file": excel.name,
        "core_categories": d["meta"]["core_categories"],
        "products": {k: [r.cate, r.brand] for k, r in prod.iterrows()},
        "groups": both.groupby("product_group")["category"].agg(mode).to_dict(),
        "brands": both.groupby("brand")["brand_raw"].agg(mode).to_dict(),
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 3 and sys.argv[1] == "--build-map":
        out = build_map(Path(sys.argv[2]))
        MAP_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{MAP_FILE}: {len(out['products'])} کالا، {len(out['groups'])} گروه، {len(out['brands'])} برند")
