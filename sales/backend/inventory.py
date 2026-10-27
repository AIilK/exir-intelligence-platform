"""کنترل موجودی و پیشنهاد سفارش هر شعبه هیبرید.

روش (قابل توضیح برای هر عدد، بدون ML):
  پایه ماهانه هر کالا  = میانگین فروش خالص (فروش − برگشتی) ماه‌های سالم اخیر، پس از حذف اثر فصل
  پیش‌بینی هر ماه       = پایه × ضریب فصلی آن ماه؛ اگر همان ماه سال قبل شعبه عادی بوده، ترکیب وزنی با فروش آن ماه
  تقاضای یک بازه        = جمع پیش‌بینی ماه‌های آن بازه × (روزهای بازه ÷ روزهای ماه)
  تاریخ سفارش ثابت نیست؛ فقط حداکثر دو سفارش در ماه، یعنی هر سفارش باید حدود R = ۱۵ روز دوام بیاورد.
  زمان رسیدن بار L ثابت (بدترین حالت معقول، پیش‌فرض ۷ روز) چون داده واقعی آن ثبت نمی‌شود.
  لازم تا رسیدن بار      = تقاضای امروز تا امروز + L (اگر همین امروز سفارش داده شود)   ← موجودی کمتر: قرمز
  سطح هدف               = تقاضای امروز تا امروز + R + L + safety   ← موجودی کمتر: نارنجی (در سفارش بعدی بیاید)
  مهلت سفارش هر کالا     = تاریخ اتمام − L؛ مهلت سفارش بعدی = زودترین مهلت بین کالاهای A و B
  مقدار سفارش           = سطح هدف − (موجودی − درخواست باز)، یعنی کسری درخواست‌های ثبت‌شده هم سفارش می‌شود؛ گرد به کارتن
  safety: کالای A از نوسان واقعی فروش (z × انحراف معیار)، یا بر اساس تعداد مشتری؛ B درصد ثابت؛ C بدون هشدار خودکار
  کالای B که فقط در ۱ یا ۲ ماه از ماه‌های پایه فروش داشته، نامنظم (C) حساب می‌شود (کالاهای A معاف‌اند)
موجودی از دیتابیس کارآمد فقط خوانده می‌شود؛ تنظیمات در config.json (کلید inventory) ذخیره می‌شوند.
از راهکاران (کارخانه، rahkaran.py): سفارش باز شعبه به کارخانه + فاکتور کارخانه که هنوز در کارآمد خرید نشده = «در راه»؛
  موجودی در محاسبه = موجودی کارآمد + در راه + سفارش باز − درخواست باز (use_incoming)، تا کالای سفارش‌داده‌شده دوباره سفارش نشود.
"""
from __future__ import annotations

import bisect
import math
import threading
import time
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

import loader
import planning as PL
import rahkaran as RK
import sql_source

DEFAULTS = {
    "branch": "هیبرید قزوین",
    "lead_days": 7,           # زمان رسیدن بار: عدد ثابت محافظه‌کارانه (واقعی ۱ تا ۱۰+ روز و ثبت‌نشده)
    "orders_per_month": 2,    # حداکثر تعداد سفارش در ماه؛ هر سفارش باید ۳۰ ÷ این عدد روز دوام بیاورد
    "base_months": 6,         # تعداد ماه‌های سالم اخیر برای پایه
    "a_safety": "data",       # data: نوسان واقعی فروش | breadth: بر اساس تعداد مشتری
    "z_a": 1.3,               # آزمون همه شعب (اردیبهشت تا شهریور ۱۴۰۵): همان تأمین فروش z=۱٫۶۵ با ۲۱٪ سفارش کمتر
    "b_pct": 0.10,            # safety ثابت کالاهای B
    "breadth": [0.15, 0.30, 0.50],  # safety بر اساس سهم بزرگ‌ترین مشتری: کمتر از ۳۰٪ / ۳۰ تا ۵۰٪ / بیش از ۵۰٪
    "dead_days": 90,          # بدون فروش بیش از این تعداد روز: راکد
    "excess_months": 6,       # پوشش بیش از این تعداد ماه: مازاد
    "min_months_sold": 3,     # کالای B با فروش در کمتر از این تعداد از ماه‌های پایه: نامنظم (C)
    "few_months_groups": ["B"],  # کالاهای A از این قاعده معاف‌اند تا هشدار کالای پرفروش قطع نشود (تصمیم کاربر)
    "ly_weight": 0.2,         # وزن فروش همان ماه سال قبل خود شعبه در پیش‌بینی (اگر آن ماه عادی بوده)
    "break_detect": True,     # تغییر ساختاری فروش شعبه (مثلاً افت تهران پس از باز شدن البرز): ماه‌های قبل از آن کنار گذاشته شوند
    "break_ratio": 0.5,       # میانگین ۳ ماه بعد ÷ ۳ ماه قبل کمتر از این (یا بیشتر از معکوس آن): تغییر ساختاری
    "inactive_days": 14,      # شعبه بدون هیچ فروشی در این تعداد روز اخیر: غیرفعال، بدون پیشنهاد سفارش
    "force_active": [],       # شعبه‌هایی که با وجود فروش نداشتن هرگز غیرفعال حساب نمی‌شوند (تصمیم کاربر)
    # آستانه هشدار نارنجی: فقط وقتی کمبود به حد قابل توجهی رسیده. آزمون همه شعب: ۲۳٪ هشدار کمتر با همان تأمین فروش
    "min_order_cartons": 0.5, # سفارش کمتر از نیم کارتن: هشدار نارنجی نمی‌دهد
    "min_gap_pct": 0.2,       # فاصله موجودی تا سطح هدف کمتر از ۲۰٪ سطح هدف: هشدار نارنجی نمی‌دهد
    "use_incoming": True,     # سفارش باز و بار در راه از راهکاران جزو موجودی حساب شود
    # کالای C کم‌فروش ولی منظم (فروش در حداقل این تعداد از ۶ ماه پایه، وابسته به یک مشتری نیست): وقتی موجودی آزاد
    # به فروش تا رسیدن بار برسد، به اندازه c_order_months ماه فروش سفارش داده می‌شود (به عدد، بدون گرد کردن به کارتن)
    "c_regular_months": 3,
    "c_order_months": 1.0,
    # برگشتی مازاد و راکد: نگه‌داشت = پیش‌بینی فروش (با فصل) این تعداد ماه آینده + درخواست باز؛ بقیه برگشت.
    # مازاد به کارتن کامل رو به پایین گرد می‌شود؛ راکد کامل (به عدد) برگشت می‌خورد
    "return_keep_months": 1.5,     # کالاهای A و B
    "return_keep_months_c": 1.0,   # کالاهای C و نامنظم
    "return_keep_dead": 2,         # کالای راکد: این تعداد عدد (به‌علاوه درخواست باز) می‌ماند، بقیه برگشت
}
_MEMO: dict = {}
CACHE_MINUTES = 30
ABC_CUTS = (0.80, 0.95)
STATUS_LABEL = {"red": "تمام می‌شود قبل از رسیدن بار", "orange": "سفارش در نوبت بعد", "ok": "کافی",
                "excess": "مازاد", "dead": "راکد", "c": "نامنظم (سفارش با درخواست)", "nodata": "سابقه ناکافی"}

# موجودی همه شعب در سال مالی جاری، یک‌جا
STOCK_SQL = """
SELECT s.BranchRef AS bid, g.Code AS code, s.StoreRef AS store, SUM(s.TotalT) AS qty
FROM dbo.vwStockFull s JOIN dbo.tblGoods g ON g.ID = s.GoodsRef
WHERE s.FiscalYear = (SELECT MAX(FiscalYear) FROM dbo.vwStockFull)
GROUP BY s.BranchRef, g.Code, s.StoreRef"""
GOODS_SQL = """
SELECT g.Code AS code, g.Name AS name, g.Unity AS unity, sp.Name AS supplier, b.Name AS brand, c.Name AS grp
FROM dbo.tblGoods g LEFT JOIN dbo.tblSupplier sp ON sp.ID = g.SupplierRef
LEFT JOIN dbo.tblGoodsBrand b ON b.ID = g.BrandRef LEFT JOIN dbo.tblGoodsCategory c ON c.ID = g.CategoryRef"""
# قیمت خرید: آخرین قیمت هر کالا در فاکتورهای خرید یک سال اخیر (اول همین شعبه، وگرنه هر شعبه)
PRICE_SQL = """
SELECT g.Code AS code, k.BranchRef AS branch_id, k.DateE AS d, l.Price AS price
FROM dbo.tblFactorKLines l JOIN dbo.tblFactorK k ON k.ID = l.FactorRef JOIN dbo.tblGoods g ON g.ID = l.GoodsRef
WHERE k.DateE >= DATEADD(day, -365, CAST(GETDATE() AS date)) AND l.Price > 1000"""
# ارزش انبار همان گزارش کارآمد: میانگین قیمت خرید هر کالا در همین شعبه و سال مالی جاری، از تابع خود کارآمد
# (کالایی که در این شعبه قیمت ندارد ارزش صفر می‌گیرد، مثل گزارش کارآمد)
AVG_PRICE_SQL = """
SELECT g.Code AS code, p.LastPrice AS price
FROM dbo.funGoodsAvgPrice(CAST(GETDATE() AS date), ?, (SELECT MAX(FiscalYear) FROM dbo.vwStockFull)) p
JOIN dbo.tblGoods g ON g.ID = p.ID"""
PURCH_SQL = """
SELECT k.BranchRef AS bid, g.Code AS code, c.PersianDate AS date, CONVERT(char(10), k.DateE, 23) AS gdate, l.TotalT AS qty
FROM dbo.tblFactorKLines l JOIN dbo.tblFactorK k ON k.ID = l.FactorRef JOIN dbo.tblGoods g ON g.ID = l.GoodsRef
JOIN dbo.tblCalendar c ON c.GregorianDate = k.DateE
WHERE k.DateE >= DATEADD(day, -180, CAST(GETDATE() AS date))"""


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("inventory") or {})}


def is_waste_store(names: pd.Series) -> pd.Series:
    """انبار غیرقابل فروش فقط از روی نام (ضایعات، مغایرت). پرچم IsWastage کارآمد قابل اعتماد نیست:
    انبار اصلی یزد، گیلان و آذربایجان شرقی با آن علامت خورده‌اند."""
    return names.str.contains("ضایعات|مغایرت", regex=True)


def _read(cn, sql, params):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return pd.read_sql(sql, cn, params=params)


# ---------------------------------------------------------------- خواندن موجودی از کارآمد (فقط SELECT)
class InventorySource:
    """موجودی، کالا، قیمت خرید و خریدهای اخیر همه شعب در یک بار خواندن؛ هر ۳۰ دقیقه (یا با درخواست کاربر) تازه می‌شود."""

    def __init__(self, env_file, read_cfg=None):
        self.env_file = env_file
        self.read_cfg = read_cfg or (lambda: {})
        self.snap: dict | None = None
        self.per_branch: dict[str, dict] = {}
        self.lock = threading.Lock()

    def _load(self):
        cn = sql_source.connect(sql_source.settings(sql_source.read_env(self.env_file)))
        try:
            br = _read(cn, "SELECT ID, Name FROM dbo.tblBranch", [])
            stores = _read(cn, "SELECT ID, BranchRef, Name, IsWastage FROM dbo.tblStore", [])
            stock = _read(cn, STOCK_SQL, [])
            goods = _read(cn, GOODS_SQL, [])
            price = _read(cn, PRICE_SQL, [])
            purch = _read(cn, PURCH_SQL, [])
        finally:
            cn.close()
        for df in (goods, price, purch):
            df["code"] = df["code"].map(loader._clean_code)
        br["name"] = br["Name"].map(loader._clean_text)
        stores["name"] = stores["Name"].map(loader._clean_text)
        stores["waste"] = is_waste_store(stores["name"])
        stock = self._prep_stock(stock, stores)
        purch["qty"] = pd.to_numeric(purch["qty"], errors="coerce").fillna(0.0)
        for k in ("name", "supplier", "brand", "grp"):
            goods[k] = goods[k].map(loader._clean_text)
        now = time.time()
        self.snap = {"fetched": now, "stock_at": now, "branches": dict(zip(br["name"], br["ID"].astype(int))), "stores": stores,
                     "stock": stock, "goods": goods.drop_duplicates("code").set_index("code"),
                     "price": price.sort_values("d"), "purch": purch, "rk": None, "rk_error": None}
        self.per_branch = {}
        # راهکاران اختیاری است: اگر تنظیم نشده یا در دسترس نیست، کنترل موجودی فقط با کارآمد ادامه می‌دهد
        if RK.settings(self.read_cfg())["use_in_branches"] and RK.configured(self.env_file):
            try:
                hyb = [b for b in self.snap["branches"] if "هیبرید" in b]
                self.snap["rk"] = RK.load(self.env_file, self.read_cfg(), hyb)
            except Exception as e:  # noqa: BLE001 — خطای اتصال راهکاران نباید تب موجودی را از کار بیندازد
                self.snap["rk_error"] = str(e)

    def get(self, branch: str, force: bool = False) -> dict:
        with self.lock:
            if self.snap is None or force or time.time() - self.snap["fetched"] >= CACHE_MINUTES * 60:
                self._load()
            if branch in self.per_branch:
                return self.per_branch[branch]
            sn = self.snap
            if branch not in sn["branches"]:
                raise loader.DataError(f"شعبه «{branch}» در دیتابیس کارآمد پیدا نشد.")
            bid = sn["branches"][branch]
            st = sn["stock"][sn["stock"]["bid"] == bid]
            pr = sn["price"]
            own = pr[pr["branch_id"] == bid].groupby("code")["price"].last()
            stores = sn["stores"][sn["stores"]["BranchRef"] == bid]
            c = {"fetched": sn["stock_at"], "branch_id": bid,
                 "stores": [{"id": int(r.ID), "name": r.name, "wastage": bool(r.waste)} for r in stores.itertuples()],
                 "stock": st[~st["waste"]].groupby("code")["qty"].sum(),
                 "waste": st[st["waste"]].groupby("code")["qty"].sum(),
                 "goods": sn["goods"],
                 "price": own.combine_first(self._any_price()).astype(float),
                 "purch": sn["purch"][sn["purch"]["bid"] == bid]}
            c["avg_price"] = self._avg_price(bid)
            c["rk"] = self._rk_branch(branch, c["purch"])
            c["rk_error"] = sn["rk_error"]
            self.per_branch[branch] = c
            return c

    @staticmethod
    def _prep_stock(stock: pd.DataFrame, stores: pd.DataFrame) -> pd.DataFrame:
        stock["code"] = stock["code"].map(loader._clean_code)
        stock["qty"] = pd.to_numeric(stock["qty"], errors="coerce").fillna(0.0)
        stock["waste"] = stock["store"].isin(set(stores.loc[stores["waste"], "ID"]))
        return stock

    def stock_at(self) -> float:
        return self.snap["stock_at"] if self.snap else 0.0

    def refresh_stock(self) -> bool:
        """لایو: فقط موجودی انبارها دوباره خوانده می‌شود (چند ثانیه)؛ قیمت، خرید و راهکاران همان چرخه ۳۰ دقیقه‌ای می‌مانند."""
        if self.snap is None:
            return False
        cn = sql_source.connect(sql_source.settings(sql_source.read_env(self.env_file)))
        try:
            stock = _read(cn, STOCK_SQL, [])
        finally:
            cn.close()
        with self.lock:
            sn = self.snap
            stock = self._prep_stock(stock, sn["stores"])
            now = time.time()
            sn["stock"], sn["stock_at"] = stock, now
            for c in self.per_branch.values():
                st = stock[stock["bid"] == c["branch_id"]]
                c["stock"] = st[~st["waste"]].groupby("code")["qty"].sum()
                c["waste"] = st[st["waste"]].groupby("code")["qty"].sum()
                c["fetched"] = now
        return True

    def _avg_price(self, bid: int) -> pd.Series:
        """میانگین قیمت خرید کالاهای شعبه از funGoodsAvgPrice کارآمد (ارزش انبار گزارش کارآمد)."""
        cn = sql_source.connect(sql_source.settings(sql_source.read_env(self.env_file)))
        try:
            p = _read(cn, AVG_PRICE_SQL, [bid])
        finally:
            cn.close()
        p["code"] = p["code"].map(loader._clean_code)
        return pd.to_numeric(p["price"], errors="coerce").fillna(0.0).groupby(p["code"]).last()

    def _rk_branch(self, branch: str, purch: pd.DataFrame) -> dict | None:
        """سفارش باز و بار در راه همین شعبه از راهکاران، به تفکیک کد کالا."""
        rk = self.snap["rk"]
        if rk is None:
            return None
        s = rk["settings"]
        o = rk["open"][rk["open"]["branch"] == branch]
        inv = rk["invoices"][rk["invoices"]["branch"] == branch]
        start = (pd.Timestamp.today().normalize() - pd.Timedelta(days=int(s["transit_days"]))).strftime("%Y-%m-%d")
        # در راه = فاکتور کارخانه در بازه − خرید ثبت‌شده کارآمد در همان بازه (هر کالا جدا، منفی = صفر)
        got = purch[purch["gdate"] >= start].groupby("code")["qty"].sum()
        sent = inv[inv["d"] >= start].groupby("code")["qty"].sum()
        transit = (sent - got.reindex(sent.index).fillna(0)).clip(lower=0)
        return {"open": o.groupby("code")["open"].sum(), "open_since": o.groupby("code")["d"].min(),
                "open_orders": int(o["oid"].nunique()), "transit": transit[transit > 0],
                "sent": float(sent.sum()), "got": float(got.sum()), "transit_from": start,
                "customers": sorted(o["cust"].unique()) if len(o) else [],
                "factory_stock": rk["factory_stock"], "factory_free": rk["factory_free"], "settings": s}

    def _any_price(self) -> pd.Series:
        if "_any" not in self.snap:
            self.snap["_any"] = self.snap["price"].groupby("code")["price"].last()
        return self.snap["_any"]


# ---------------------------------------------------------------- تقویم
class Days:
    """همه روزهای تقویم کارآمد (شمسی، مرتب) برای جمع و تفریق روز و طول ماه‌ها."""

    def __init__(self, cal: pd.DataFrame):
        c = cal.sort_values("date")
        self.dates = c["date"].tolist()
        self.work = dict(zip(c["date"], c["workday"].astype(bool)))
        self.mlen = c.groupby(c["date"].str[:7]).size().to_dict()

    def idx(self, d: str) -> int:
        return bisect.bisect_left(self.dates, d)

    def add(self, d: str, k: int) -> str:
        i = min(max(self.idx(d) + k, 0), len(self.dates) - 1)
        return self.dates[i]

    def diff(self, a: str, b: str) -> int:
        return self.idx(b) - self.idx(a)

    def months_in(self, start: str, end: str) -> dict[str, float]:
        """سهم هر ماه از بازه [start, end): تعداد روز ÷ طول ماه."""
        out: dict[str, float] = {}
        for d in self.dates[self.idx(start):self.idx(end)]:
            out[d[:7]] = out.get(d[:7], 0) + 1
        return {m: n / self.mlen[m] for m, n in out.items()}


# ---------------------------------------------------------------- محاسبه
def _ceil_carton(q: np.ndarray, unity: np.ndarray) -> np.ndarray:
    """گرد به کارتن کامل؛ سفارش کمتر از نیم کارتن به عدد گرد می‌شود تا کالای کم‌فروش چند برابر نیاز سفارش نشود."""
    u = np.where(unity > 1, unity, 1.0)
    full = np.ceil(q / u - 1e-9) * u
    return np.where(q <= 0, 0.0, np.where(q >= 0.5 * u, full, np.ceil(q - 1e-9)))


def hybrid_branches(data: dict) -> list[str]:
    return sorted(b for b in data["sales"]["branch"].unique() if "هیبرید" in str(b))


def stock_totals(src: dict) -> dict:
    """جمع موجودی انبار اصلی و ضایعات شعبه فقط از کارآمد؛ مستقل از محاسبه سفارش تا شعب با سابقه ناکافی هم داشته باشند.
    موجودی منفی هر کالا صفر حساب می‌شود؛ ارزش = موجودی × میانگین قیمت خرید کارآمد (همان «ارزش انبار» گزارش کارآمد)."""
    price = src["avg_price"]
    out = {}
    for k, s in (("main", src["stock"]), ("waste", src["waste"])):
        q = s.clip(lower=0)
        out[f"{k}_units"] = float(q.sum())
        out[f"{k}_value"] = float((q * price.reindex(q.index).fillna(0.0)).sum())
    out["total_units"] = out["main_units"] + out["waste_units"]
    out["total_value"] = out["main_value"] + out["waste_value"]
    out["main_skus"] = int((src["stock"] > 0).sum())
    return out


def _calendar_season(data: dict, ps: dict):
    """تقویم و ضریب فصلی فقط وقتی داده یا تنظیمات عوض شود دوباره ساخته می‌شوند."""
    pi = data["plan_inputs"]
    key = (id(pi["calendar"]), id(pi.get("old")), repr(sorted(ps.items())))
    if _MEMO.get("key") != key:
        cal = PL.Calendar(pi["calendar"], data["sales"]["date"].unique())
        _MEMO.update(key=key, days=Days(pi["calendar"]), season=PL.season_index(pi.get("old"), cal, ps))
    return _MEMO["days"], _MEMO["season"]


def _base_months(mnet: pd.Series, first: str, cur: str, ps: dict, s: dict, season: dict) -> tuple[list[str], str | None]:
    """ماه‌های سالمِ بسته بعد از ماه اول شعبه؛ اگر فروش شعبه تغییر ساختاری پایدار داشته (پس از حذف اثر فصل، سه ماه
    پشت سر هم نصف یا دو برابر سه ماه قبل)، فقط ماه‌های بعد از آخرین تغییر. جهش یک‌ماهه (مثل کمپین شهریور) تغییر نیست."""
    normal = [m for m in mnet.index if first < m < cur and not PL.is_abnormal(m, ps)]
    brk = None
    if s.get("break_detect") and len(normal) >= 5:
        r = float(s["break_ratio"])
        v = mnet.reindex(normal).clip(lower=0).values / np.array([PL.season_factor(season, ps, "", m[5:7]) for m in normal])
        for i in range(len(normal) - 3, 1, -1):  # آخرین نقطه تغییر؛ ۳ ماه بعد و حداقل ۲ ماه قبل
            after, before = v[i:i + 3], v[max(0, i - 3):i]
            if len(after) < 3 or len(before) < 2 or before.mean() <= 0:
                continue
            ratio = after.mean() / before.mean()
            if ratio < r or ratio > 1 / r:
                brk = normal[i]
                break
    if brk:
        normal = [m for m in normal if m >= brk]
    return normal[-int(s["base_months"]):], brk


def compute(data: dict, src: dict, cfg: dict, branch: str | None = None) -> dict:
    s = settings(cfg)
    ps = PL.settings(cfg)
    branch = branch or s["branch"]
    s = {**s, "branch": branch}
    meta = data["meta"]
    pi = data.get("plan_inputs") or {}
    if pi.get("calendar") is None:
        raise loader.DataError("تقویم کارآمد هنوز خوانده نشده؛ چند دقیقه بعد دوباره امتحان کنید.")
    days, season = _calendar_season(data, ps)
    today = meta.get("today") or data["sales"]["date"].max()
    cur = today[:7]
    lead = int(s["lead_days"])
    warn: list[dict] = []

    sales = data["sales"]
    sales = sales[(sales["branch"] == branch) & ~sales["is_sample"]]
    if not len(sales):
        raise loader.DataError(f"برای «{branch}» فروشی در داشبورد نیست؛ فیلتر شعبه منبع داده را بررسی کنید.")
    req = data.get("requests")
    req = req[(req["branch"] == branch)] if req is not None else None

    # -- ماه‌های پایه: ماه‌های سالمِ بسته، بعد از ماه اول شعبه (ناقص)
    months = sorted(sales["month"].unique())
    # ماه اول شعبه = اولین ماه با فروش خالص مثبت (فاکتورهای آزمایشی که کامل برگشت خورده‌اند حساب نمی‌شوند)
    mnet = sales.groupby("month", observed=True)["qty"].sum()
    first = mnet[mnet > 0].index.min()
    base_months, brk = _base_months(mnet, first, cur, ps, s, season)
    if len(base_months) < 2:
        raise loader.DataError("برای این شعبه کمتر از دو ماه سالم سابقه هست؛ پیشنهاد ممکن نیست.")
    last_branch_sale = sales.loc[(~sales["is_return"]) & (sales["qty"] > 0), "date"].max()
    inactive = days.diff(last_branch_sale, today) > int(s["inactive_days"]) and branch not in set(s.get("force_active") or [])

    # -- فروش خالص ماهانه هر کالا (فروش + برگشتی که تعدادش منفی است)
    mq = sales.groupby(["product_code", "month"], observed=True)["qty"].sum().unstack(fill_value=0.0)
    mq = mq.reindex(columns=months, fill_value=0.0)
    sold = sales[~sales["is_return"]]
    gross_b = sold[sold["month"].isin(base_months)].groupby("product_code", observed=True)["qty"].sum()
    ret_b = -sales[sales["is_return"] & sales["month"].isin(base_months)].groupby("product_code", observed=True)["qty"].sum()
    mode = lambda x: x.value_counts().index[0]
    info = sales.groupby("product_code", observed=True).agg(product=("product", mode), brand=("brand", mode),
                                                              category=("category", mode))
    # مشتریان: تعداد و سهم بزرگ‌ترین مشتری در ماه‌های پایه
    cb = sold[sold["month"].isin(base_months)].groupby(["product_code", "customer_code"], observed=True)["qty"].sum()
    cb = cb[cb > 0]
    n_cust = cb.groupby(level=0).size()
    top_share = cb.groupby(level=0).max() / cb.groupby(level=0).sum()
    top_cust = cb.groupby(level=0).idxmax().map(lambda t: t[1])
    cust_name = sold.groupby("customer_code", observed=True)["customer"].agg(mode)
    last_sale = sold[sold["qty"] > 0].groupby("product_code", observed=True)["date"].max()
    open_req = req[req["status"] == 0].groupby("product_code", observed=True)["qty"].sum() if req is not None and len(req) else pd.Series(dtype=float)

    # -- راهکاران (اختیاری): سفارش باز شعبه به کارخانه و فاکتور کارخانه که هنوز در کارآمد خرید نشده
    rk = src.get("rk")
    use_in = bool(s.get("use_incoming")) and rk is not None
    empty = pd.Series(dtype=float)
    rk_open, rk_transit = (rk["open"], rk["transit"]) if rk else (empty, empty)

    # -- همه کالاهای مرتبط: موجودی دار، یا فروش در ماه‌های پایه، یا درخواست باز، یا در راه از کارخانه
    stock = src["stock"]
    codes = sorted(set(stock[stock != 0].index) | set(mq.index[(mq[base_months] != 0).any(axis=1)]) | set(open_req.index)
                   | set(rk_open.index) | set(rk_transit.index))
    g = src["goods"].reindex(codes)
    df = pd.DataFrame(index=pd.Index(codes, name="code"))
    df["product"] = info["product"].reindex(codes).fillna(g["name"])
    df["brand"] = info["brand"].reindex(codes).fillna(g["brand"])
    df["category"] = info["category"].reindex(codes).fillna("سایر")
    df["supplier"] = g["supplier"].fillna(loader.UNKNOWN)
    df["unity"] = pd.to_numeric(g["unity"], errors="coerce").fillna(1.0).clip(lower=1.0)
    df["stock"] = stock.reindex(codes).fillna(0.0)
    df["waste"] = src["waste"].reindex(codes).fillna(0.0)
    df["open_req"] = open_req.reindex(codes).fillna(0.0)
    df["rk_open"] = rk_open.reindex(codes).fillna(0.0)
    df["rk_transit"] = rk_transit.reindex(codes).fillna(0.0)
    df["incoming"] = df["rk_open"] + df["rk_transit"]
    df["open_since"] = rk["open_since"].reindex(codes) if rk else None
    df["factory_stock"] = rk["factory_stock"].reindex(codes).fillna(0.0) if rk else np.nan
    df["factory_free"] = rk["factory_free"].reindex(codes).fillna(0.0) if rk else np.nan
    inc = df["incoming"] if use_in else 0.0
    # موجودی + در راه + سفارش باز کارخانه − درخواست‌های باز؛ منفی یعنی حتی درخواست‌های ثبت‌شده هم تأمین نمی‌شوند
    df["net_avail"] = df["stock"].clip(lower=0) + inc - df["open_req"]
    df["avail"] = df["net_avail"].clip(lower=0)
    df["req_short"] = (-df["net_avail"]).clip(lower=0)
    df["price"] = src["price"].reindex(codes)
    price_fill = float(src["price"].median()) if len(src["price"]) else 0.0
    # ارزش موجودی همان «ارزش انبار» گزارش کارآمد (میانگین قیمت خرید شعبه؛ بدون قیمت = صفر)؛
    # ارزش سفارش پایین‌تر با آخرین قیمت خرید می‌ماند چون خرید بعدی به قیمت روز است
    df["avg_price"] = src["avg_price"].reindex(codes).fillna(0.0)
    df["value"] = df["stock"].clip(lower=0) * df["avg_price"]

    # -- آمار ماهانه (ماه‌های پایه، بدون حذف فصل) و پایه بدون اثر فصل
    B = mq.reindex(index=codes, fill_value=0.0)[base_months].clip(lower=0)
    sf = lambda cat, mm: PL.season_factor(season, ps, cat, mm)
    fac = np.array([[sf(c, m[5:7]) for m in base_months] for c in df["category"]])
    Bd = B.values / fac
    df["base"] = Bd.mean(axis=1)
    df["sd"] = Bd.std(axis=1)
    df["mean"] = B.mean(axis=1)
    df["median"] = B.median(axis=1)
    df["min"] = B.min(axis=1)
    df["max"] = B.max(axis=1)
    df["months_sold"] = (B > 0).sum(axis=1)
    df["cv"] = np.where(df["base"] > 0, df["sd"] / df["base"].replace(0, np.nan), np.nan)
    if len(base_months) >= 6:
        a, b = B[base_months[-3:]].mean(axis=1), B[base_months[-6:-3]].mean(axis=1)
        df["trend"] = np.where(b > 0, a / b.replace(0, np.nan) - 1, np.nan)
    else:
        df["trend"] = np.nan
    df["gross_b"] = gross_b.reindex(codes).fillna(0.0)
    df["ret_rate"] = np.where(df["gross_b"] > 0, ret_b.reindex(codes).fillna(0.0) / df["gross_b"].replace(0, np.nan), np.nan)
    df["n_cust"] = n_cust.reindex(codes).fillna(0).astype(int)
    df["top_share"] = top_share.reindex(codes)
    df["top_cust"] = top_cust.reindex(codes).map(cust_name)
    ly1, ly2 = PL.month_add(cur, -12), PL.month_add(cur, -11)
    df["ly_cur"] = mq[ly1].reindex(codes).fillna(0.0) if ly1 in mq else np.nan
    df["ly_next"] = mq[ly2].reindex(codes).fillna(0.0) if ly2 in mq else np.nan
    df["cur_month"] = mq[cur].reindex(codes).fillna(0.0) if cur in mq else 0.0
    # فروش خالص تعدادی از ابتدای سال جاری تا امروز (همه ماه‌ها، حتی غیرعادی و ماه جاری ناقص)
    ytd_months = [m for m in months if m[:4] == cur[:4]]
    df["ytd"] = mq.reindex(index=codes, fill_value=0.0)[ytd_months].sum(axis=1)
    df["last_sale"] = last_sale.reindex(codes)
    df["idle_days"] = [days.diff(d, today) if isinstance(d, str) else None for d in df["last_sale"]]

    # -- ABC بر اساس پایه
    tot = df["base"].clip(lower=0).sort_values(ascending=False)
    cum = tot.cumsum() / tot.sum() if tot.sum() > 0 else tot
    df["abc"] = pd.Series(np.where(cum <= ABC_CUTS[0], "A", np.where(cum <= ABC_CUTS[1], "B", "C")), index=tot.index)
    df.loc[df["base"] <= 0, "abc"] = "-"
    # فروش فقط در ۱ یا ۲ ماه از ماه‌های پایه (مثلاً یک خرید بزرگ تک‌مشتری): نامنظم، حتی اگر حجمش زیاد باشد
    # آستانه برای ۶ ماه پایه تعریف شده؛ با ماه‌های پایه کمتر به همان نسبت کم می‌شود (مثلاً ۲ ماه پایه: حداقل ۱ ماه)
    min_sold = max(1, round(int(s["min_months_sold"]) * len(base_months) / 6))
    df["abc_raw"] = df["abc"]  # دسته قبل از قاعده «ماه‌های کم فروش»
    df["few_months"] = df["abc"].isin(s["few_months_groups"]) & (df["months_sold"] < min_sold)
    df.loc[df["few_months"], "abc"] = "C"

    # -- پیش‌بینی هر ماه: پایه × ضریب فصل، ترکیب با فروش همان ماه سال قبل خود شعبه (اگر آن ماه عادی بوده
    #    و کالا آن زمان فروخته می‌شده)
    w_ly = float(s["ly_weight"])
    nz = mq.reindex(index=codes, fill_value=0.0).ne(0)
    first_sale = nz.idxmax(axis=1).where(nz.any(axis=1))
    fc_cache: dict[str, tuple] = {}

    def fc(m: str):
        if m not in fc_cache:
            model = df["base"] * np.array([sf(c, m[5:7]) for c in df["category"]])
            ly = PL.month_add(m, -12)
            use = pd.Series(False, index=df.index)
            growth = None
            if w_ly > 0 and ly in mq.columns and first < ly and not PL.is_abnormal(ly, ps) and (brk is None or ly >= brk):
                use = first_sale.notna() & (first_sale <= ly)
                lyv = mq[ly].reindex(codes).fillna(0.0).clip(lower=0)
                # رشد شعبه از آن زمان: جمع پیش‌بینی فصلی ÷ جمع فروش سال قبل همان کالاها (تا سطح امروز شعبه حفظ شود)
                tot_ly = float(lyv[use].sum())
                growth = float(np.clip(model[use].sum() / tot_ly, 0.5, 3.0)) if tot_ly > 0 else None
                if growth is None:
                    use[:] = False
                    out = model
                else:
                    out = model.where(~use, (1 - w_ly) * model + w_ly * lyv * growth)
            else:
                out = model
            fc_cache[m] = (out, model, use, ly, growth)
        return fc_cache[m]

    # -- نوبت‌های سفارش و بازه‌ها
    review = int(round(30 / max(int(s["orders_per_month"]), 1)))
    arr0 = days.add(today, lead)              # اگر همین امروز سفارش داده شود
    arr1 = days.add(today, review + lead)     # تا رسیدن بار سفارشِ بعد از آن
    w_need = days.months_in(today, arr0)
    w_cover = days.months_in(today, arr1)
    cats = df["category"].unique()
    F = lambda w: {c: sum(sf(c, m[5:7]) * v for m, v in w.items()) for c in cats}
    f_cover = F(w_cover)
    cover_m = sum(w_cover.values())
    df["need"] = sum(fc(m)[0] * v for m, v in w_need.items())
    df["demand_cover"] = sum(fc(m)[0] * v for m, v in w_cover.items())
    nxt = PL.month_add(cur, 1)
    df["sf_now"] = [sf(c, cur[5:7]) for c in df["category"]]
    df["sf_next"] = [sf(c, nxt[5:7]) for c in df["category"]]
    df["fc_now"], df["fc_next"] = fc(cur)[0], fc(nxt)[0]
    df["fc_next_model"], df["ly_next_used"] = fc(nxt)[1], fc(nxt)[2]
    df["ly_now_used"] = fc(cur)[2]
    df["ly_growth"] = fc(nxt)[4]
    ly_used = sorted({fc(m)[3] for m in list(w_cover) + [cur, nxt] if fc(m)[2].any()})
    ly_growth = {fc(m)[3]: fc(m)[4] for m in list(w_cover) + [cur, nxt] if fc(m)[2].any()}
    daily = df["fc_now"] / days.mlen.get(cur, 30)
    df["daily"] = daily
    df["cover_days"] = np.where(daily > 0, df["avail"] / daily.replace(0, np.nan), np.inf)
    df["cover_months"] = np.where(df["fc_now"] > 0, (df["stock"].clip(lower=0) + inc) / df["fc_now"].replace(0, np.nan), np.inf)

    # -- safety
    bp = s["breadth"]
    breadth_pct = np.where(df["top_share"].fillna(1) > 0.5, bp[2], np.where(df["top_share"].fillna(1) > 0.3, bp[1], bp[0]))
    ss_data = float(s["z_a"]) * df["sd"] * df["category"].map(f_cover) / math.sqrt(max(cover_m, 1e-9))
    df["safety"] = np.select(
        [df["abc"] == "A", df["abc"] == "B"],
        [ss_data if s["a_safety"] == "data" else breadth_pct * df["demand_cover"], float(s["b_pct"]) * df["demand_cover"]], 0.0)
    df["safety_pct"] = np.where(df["demand_cover"] > 0, df["safety"] / df["demand_cover"].replace(0, np.nan), np.nan)
    df["target"] = df["demand_cover"] + df["safety"]

    # -- وضعیت و سفارش
    ab = df["abc"].isin(["A", "B"])
    # راکد: نه فروش و نه خرید در dead_days روز اخیر. کالایی که تازه رسیده (هنوز فرصت فروش نداشته) راکد نیست.
    # (خریدها از ۱۸۰ روز اخیر خوانده می‌شوند؛ خرید قدیمی‌تر یعنی «خرید اخیر ندارد»)
    pb = src["purch"]
    last_buy = pb[pb["qty"] > 0].groupby("code")["date"].max()
    df["last_buy"] = last_buy.reindex(codes)
    df["buy_days"] = [days.diff(d, today) if isinstance(d, str) else None for d in df["last_buy"]]
    dead = ((df["stock"] > 0) & (df["idle_days"].isna() | (df["idle_days"].fillna(0) > s["dead_days"]))
            & (df["buy_days"].isna() | (df["buy_days"].fillna(0) > s["dead_days"])))
    st = np.select(
        [ab & (df["net_avail"] < df["need"]), ab & (df["net_avail"] < df["target"]), dead,
         ab & (df["cover_months"] > s["excess_months"]), ab,
         (df["abc"] == "C") & (df["req_short"] > 0), df["abc"] == "C"],
        ["red", "orange", "dead", "excess", "ok", "red", "c"], "nodata")
    df["status"] = st
    # سفارش = سطح هدف − (موجودی − درخواست باز)؛ کسری درخواست‌های ثبت‌شده هم سفارش داده می‌شود
    raw = np.where(df["status"].isin(["red", "orange"]) & ab, df["target"] - df["net_avail"],
                   np.where((df["abc"] == "C") & (df["status"] == "red"), df["req_short"], 0.0))
    df["order"] = _ceil_carton(np.clip(raw, 0, None), df["unity"].values)
    # نارنجیِ کم‌اهمیت (سفارش کمتر از نیم کارتن یا فاصله کم تا سطح هدف) هشدار نمی‌گیرد؛ در بررسی بعدی دوباره سنجیده می‌شود
    gap_pct = np.where(df["target"] > 0, (df["target"] - df["net_avail"]) / df["target"].replace(0, np.nan), 0)
    small = (df["status"] == "orange") & ((df["order"] < float(s["min_order_cartons"]) * df["unity"])
                                          | (gap_pct < float(s["min_gap_pct"])))
    df.loc[small, "status"] = "ok"
    df.loc[small, "order"] = 0.0
    # کالای C کم‌فروش ولی منظم: موجودی آزاد ≤ فروش تا رسیدن بار ← سفارش به اندازه چند ماه فروش (به عدد)
    c_min = max(1, round(int(s["c_regular_months"]) * len(base_months) / 6))
    df["c_low"] = ((df["abc"] == "C") & df["status"].isin(["c", "red"]) & (df["months_sold"] >= c_min)
                   & (df["top_share"].fillna(1) <= 0.5) & (df["net_avail"] <= df["need"]))
    c_qty = np.ceil(np.clip(df["need"] + float(s["c_order_months"]) * df["fc_now"].clip(lower=0) - df["net_avail"], 1, None))
    df.loc[df["c_low"], "order"] = np.maximum(df.loc[df["c_low"], "order"], c_qty[df["c_low"]])
    df.loc[df["c_low"] & (df["status"] == "c"), "status"] = "orange"
    if inactive:  # شعبه غیرفعال: پیشنهاد سفارش نمی‌دهیم
        df["order"] = 0.0
    # کارخانه به اندازه سفارش موجودی آزاد ندارد (موجودی انبار محصول منهای سفارش‌های باز همه مشتریان)
    df["factory_short"] = (df["order"] > 0) & (df["factory_free"] < df["order"]) if rk else False
    df["cartons"] = np.where(df["unity"] > 1, df["order"] / df["unity"], np.nan)
    df["order_value"] = df["order"] * df["price"].fillna(price_fill)
    df["runout"] = [days.add(today, int(c)) if np.isfinite(c) and c < 400 else None for c in df["cover_days"]]
    # مهلت سفارش: آخرین روزی که اگر سفارش داده شود، بار قبل از اتمام موجودی می‌رسد
    df["order_by_days"] = np.where(np.isfinite(df["cover_days"]), np.clip(np.floor(df["cover_days"]) - lead, 0, None), np.nan)
    df["order_by"] = [days.add(today, int(c)) if np.isfinite(c) and c < 400 else None for c in df["order_by_days"]]
    cand = df[df["abc"].isin(["A", "B"]) & df["order_by_days"].notna() & (df["status"] != "dead")]
    cand = cand[cand["order_by_days"] == cand["order_by_days"].min()] if len(cand) else cand
    deadline = cand["order_by"].iat[0] if len(cand) else None
    deadline_items = cand.sort_values("base", ascending=False)["product"].head(3).tolist() if len(cand) else []

    # -- پیشنهاد برگشت (فقط مازاد و راکد)
    def demand(months: float) -> pd.Series:
        w = days.months_in(today, days.add(today, int(round(months * 30))))
        return sum(fc(m)[0].clip(lower=0) * v for m, v in w.items())
    keep_m = np.where(df["abc"].isin(["A", "B"]), float(s["return_keep_months"]), float(s["return_keep_months_c"]))
    df["ret_keep"] = np.ceil(np.where(df["status"] == "dead", float(s["return_keep_dead"]),
        np.where(df["abc"].isin(["A", "B"]), demand(float(s["return_keep_months"])), demand(float(s["return_keep_months_c"]))))
        + df["open_req"].clip(lower=0))
    df["ret_keep_months"] = np.where(df["status"] == "dead", 0.0, keep_m)
    over = (df["stock"].clip(lower=0) - df["ret_keep"]).clip(lower=0)
    full = np.where(df["unity"] > 1, np.floor(over / df["unity"]) * df["unity"], np.floor(over))
    df["ret_qty"] = np.select([df["status"] == "dead", df["status"] == "excess"], [np.floor(over), full], 0.0)
    df["ret_cartons"] = np.where(df["unity"] > 1, df["ret_qty"] / df["unity"], np.nan)
    df["ret_value"] = df["ret_qty"] * df["avg_price"]

    # -- توضیح هر سطر
    df["why"] = [_why(r, s, review, arr0, arr1, nxt, use_in) for r in df.itertuples()]

    # -- جمع‌ها
    purch = src["purch"]
    p90 = purch[purch["date"] >= days.add(today, -90)].groupby("code")["qty"].sum()
    s90 = sales[sales["date"] >= days.add(today, -90)].groupby("product_code", observed=True)["qty"].sum()
    df["bought_90"] = p90.reindex(codes).fillna(0.0)
    df["sold_90"] = s90.reindex(codes).fillna(0.0)
    df["monthly_now"] = df["fc_now"]
    sup = df.groupby("supplier").agg(stock=("stock", "sum"), value=("value", "sum"), monthly=("monthly_now", "sum"),
                                     red=("status", lambda x: int((x == "red").sum())),
                                     orange=("status", lambda x: int((x == "orange").sum())),
                                     order=("order", "sum"), order_value=("order_value", "sum"),
                                     bought_90=("bought_90", "sum"), sold_90=("sold_90", "sum"),
                                     skus=("stock", "size")).reset_index()
    # کیفیت داده: شعبه‌ای که فروش دارد ولی خریدی ثبت نمی‌کند، موجودی کارآمدش واقعی نیست
    data_issue = None
    sold90, bought90 = float(df["sold_90"].sum()), float(df["bought_90"].sum())
    if sold90 > 0 and bought90 < 0.1 * sold90:
        data_issue = (f"در ۹۰ روز اخیر {sold90:,.0f} عدد فروش ولی فقط {bought90:,.0f} عدد خرید ثبت شده؛ "
                      "احتمالاً کالا بدون فاکتور خرید به این شعبه می‌رسد و موجودی کارآمد آن قابل اعتماد نیست.")
    sup["cover_months"] = sup["stock"] / sup["monthly"].replace(0, np.nan)
    sup["buy_sell"] = sup["bought_90"] / sup["sold_90"].where(sup["sold_90"] > 0)
    dv = df.loc[df["status"] == "dead", "value"].sum()
    ex = df.loc[df["status"] == "excess", "value"].sum()
    red = df["status"] == "red"
    kpis = {
        "stock_units": float(df["stock"].clip(lower=0).sum()), "stock_value": float(df["value"].sum()),
        "stock_skus": int((df["stock"] > 0).sum()),
        "red": int(red.sum()), "red_a": int((red & (df["abc"] == "A")).sum()),
        "red_zero": int((red & (df["stock"] <= 0)).sum()),
        "orange": int((df["status"] == "orange").sum()),
        "order_units": float(df["order"].sum()), "order_value": float(df["order_value"].sum()),
        "order_lines": int((df["order"] > 0).sum()),
        "order_cartons": float(np.where(df["unity"] > 1, df["order"] / df["unity"], 0).sum()),
        "dead_value": float(dv), "dead_skus": int((df["status"] == "dead").sum()),
        "dead_units": float(df.loc[df["status"] == "dead", "stock"].clip(lower=0).sum()),
        "excess_units": float(df.loc[df["status"] == "excess", "stock"].clip(lower=0).sum()),
        "excess_value": float(ex), "excess_skus": int((df["status"] == "excess").sum()),
        "ret_units": float(df["ret_qty"].sum()), "ret_value": float(df["ret_value"].sum()),
        "ret_skus": int((df["ret_qty"] > 0).sum()),
        "open_req": float(df["open_req"].sum()), "waste_units": float(df["waste"].sum()),
        "rk_open": float(df["rk_open"].sum()), "rk_transit": float(df["rk_transit"].sum()),
        "incoming": float(df["incoming"].sum()), "rk_orders": int(rk["open_orders"]) if rk else 0,
        "factory_short": int(df["factory_short"].sum()) if rk else 0,
    }

    if rk:
        warn.append({"level": "info", "text": (
            f"از راهکاران: {_n(df['rk_open'].sum())} عدد سفارش باز این شعبه به کارخانه ({rk['open_orders']} سفارش ثبت‌شده/تأییدشده"
            f" از {rk['settings']['open_days']} روز اخیر که هنوز از انبار کارخانه خارج نشده) و {_n(df['rk_transit'].sum())} عدد بار در راه"
            f" (فاکتور کارخانه از {rk['transit_from']} منهای خرید ثبت‌شده در کارآمد؛ {_n(rk['sent'])} فاکتور در برابر {_n(rk['got'])} خرید). "
            + ("هر دو جزو موجودی حساب شده‌اند تا دوباره سفارش داده نشوند." if use_in else "در محاسبه سفارش حساب نشده‌اند (use_incoming خاموش است)."))})
        if kpis["factory_short"]:
            warn.append({"level": "warn", "text": f"برای {kpis['factory_short']} کالای پیشنهادی، موجودی آزاد انبار محصول کارخانه کمتر از مقدار سفارش است."})
    elif src.get("rk_error"):
        warn.insert(0, {"level": "warn", "text": f"داده راهکاران خوانده نشد؛ سفارش باز و بار در راه کارخانه در محاسبه نیست. ({src['rk_error'][:200]})"})
    if data_issue and len(purch):
        warn.insert(0, {"level": "danger", "text": data_issue})
    if inactive:
        warn.insert(0, {"level": "danger", "text": f"این شعبه از {last_branch_sale} هیچ فروشی نداشته و غیرفعال حساب شده؛ پیشنهاد سفارش داده نمی‌شود."})
    if brk:
        warn.insert(0, {"level": "warn", "text": (
            f"فروش این شعبه از {brk} تغییر ساختاری داشته (پس از حذف اثر فصل، سه ماه پشت سر هم کمتر از نصف یا بیشتر از دو برابر سه ماه قبل)؛ "
            f"فقط ماه‌های بعد از {brk} در پایه آمده‌اند.")})
    warn.append({"level": "info", "text": (
        f"زمان رسیدن بار ثابت {lead} روز در نظر گرفته شده (در عمل بین ۱ تا ۱۰ روز یا بیشتر است و تاریخ واقعی ثبت نمی‌شود). "
        f"تاریخ سفارش ثابت نیست؛ با حداکثر {s['orders_per_month']} سفارش در ماه، هر سفارش باید حدود {review} روز به‌علاوه زمان رسیدن بار دوام بیاورد.")})
    if not season.get("available"):
        warn.append({"level": "warn", "text": "ضریب فصلی در دسترس نیست؛ تقاضا بدون اثر فصل محاسبه شده است."})
    neg = int((df["stock"] < 0).sum())
    if neg:
        warn.append({"level": "warn", "text": f"{neg} کالا موجودی منفی دارند؛ معمولاً یعنی فاکتور خرید دیرتر از فروش ثبت شده. موجودی این کالاها صفر حساب شده."})
    if df["open_req"].sum() > 0:
        warn.append({"level": "info", "text": f"{int(df['open_req'].sum())} عدد درخواست باز (فاکتور نشده) از موجودی قابل فروش کم شده است."})
    warn.append({"level": "info", "text": (
        f"پایه هر کالا = میانگین فروش خالص (فروش منهای برگشتی) ماه‌های {'، '.join(base_months)} پس از حذف اثر فصل. "
        f"ماه‌های غیرعادی ({'، '.join(sorted(ps['abnormal_months']))} و فروردین‌ها) و ماه اول شعبه کنار گذاشته شده‌اند.")})
    warn.append({"level": "info", "text": (
        "safety کالاهای A " + ("از نوسان واقعی فروش هر کالا (z × انحراف معیار) محاسبه می‌شود" if s["a_safety"] == "data"
                               else f"بر اساس سهم بزرگ‌ترین مشتری است: {int(bp[0]*100)}٪ / {int(bp[1]*100)}٪ / {int(bp[2]*100)}٪")
        + f"؛ کالاهای B {int(s['b_pct']*100)}٪ ثابت؛ کالاهای C هشدار خودکار ندارند و فقط کمبود درخواست باز را نشان می‌دهند. "
        "در آزمون تاریخی خرداد تا مهر ۱۴۰۵ این روش حدود ۸۵٪ کمبودهای کالاهای A را از قبل شناسایی کرد.")})
    warn.append({"level": "info", "text": "موجودی انبار ضایعات در محاسبه نیست. سفارش از نیم کارتن به بالا به کارتن کامل گرد می‌شود (تعداد در کارتن از کارآمد) و کمتر از آن به عدد."})
    warn.append({"level": "info", "text": (
        (f"فروش همان ماه سال قبل خود شعبه ({'، '.join(f'{m} × رشد {g:.2f}' for m, g in ly_growth.items())}) با وزن {w_ly:.0%} در پیش‌بینی آمده است"
         " (فقط برای کالاهایی که آن زمان فروخته می‌شدند؛ «رشد» نسبت سطح فروش امروز شعبه به همان ماه سال قبل است)."
         if ly_used else "برای ماه‌های پیش رو، ماه عادیِ سال قبل در سابقه این شعبه نیست؛ پیش‌بینی فقط با ضریب فصلی است.")
        + f" کالاهای B که در کمتر از {min_sold} ماه از {len(base_months)} ماه پایه فروش داشته‌اند، نامنظم (C) حساب شده‌اند"
        + f" ({int(df['few_months'].sum())} کالا).")})

    cols = ["code", "product", "brand", "category", "supplier", "abc", "abc_raw", "few_months", "status", "stock", "waste", "open_req",
            "avail", "req_short", "fc_now", "fc_next", "fc_next_model", "ly_next_used", "ly_growth", "sf_next",
            "need", "target", "safety", "safety_pct", "order", "cartons", "unity", "order_value", "price", "value",
            "base", "mean", "median", "min", "max", "months_sold", "cv", "trend", "ret_rate", "n_cust", "top_share",
            "top_cust", "ly_cur", "ly_next", "cur_month", "ytd", "daily", "cover_days", "cover_months", "runout", "order_by",
            "last_sale", "idle_days", "last_buy", "buy_days", "sf_now", "bought_90", "sold_90", "rk_open", "rk_transit", "incoming", "open_since",
            "factory_stock", "factory_free", "factory_short", "c_low",
            "ret_keep", "ret_keep_months", "ret_qty", "ret_cartons", "ret_value", "why"]
    out = df.reset_index()[cols].replace([np.inf, -np.inf], np.nan)
    hist_months = [m for m in months if m >= PL.month_add(cur, -12)]
    H = mq.reindex(index=codes, fill_value=0.0)[hist_months]
    return {
        "branch": branch, "today": today, "settings": s, "fetched": datetime.fromtimestamp(src["fetched"]).strftime("%Y-%m-%d %H:%M"),
        "orders": {"arr0": arr0, "arr1": arr1, "lead": lead, "review": review, "per_month": int(s["orders_per_month"]),
                   "deadline": deadline, "deadline_items": deadline_items,
                   "days_to_deadline": days.diff(today, deadline) if deadline else None,
                   "cover_days": days.diff(today, arr1)},
        "base_months": base_months, "ytd_from": ytd_months[0] if ytd_months else None, "kpis": kpis, "ly_used": ly_used, "next_month": nxt,
        "break_month": brk, "inactive": bool(inactive), "last_branch_sale": last_branch_sale,
        "data_issue": data_issue if len(purch) else None,
        "suppliers": sup.replace([np.inf, -np.inf], np.nan).sort_values("value", ascending=False),
        "rows": out, "hist_months": hist_months, "hist": {c: [float(v) for v in H.loc[c]] for c in codes},
        "abnormal": [m for m in hist_months if PL.is_abnormal(m, ps)],
        "warnings": warn, "status_label": STATUS_LABEL,
        "rahkaran": ({"ok": True, "use_incoming": use_in, "customers": rk["customers"], "orders": rk["open_orders"],
                      "transit_from": rk["transit_from"]} if rk else {"ok": False, "error": src.get("rk_error"),
                                                                     "disabled": not src.get("rk_error")}),
    }


def _n(v) -> str:
    return f"{v:,.0f}" if v is not None and np.isfinite(v) else "—"


def _why(r, s, review, arr0, arr1, nxt, use_in=False) -> list:
    """توضیح قطعی و قابل بازبینی هر پیشنهاد، به صورت مرحله‌به‌مرحله: [[عنوان، متن], ...]"""
    if r.status == "dead":
        last = f"آخرین فروش {r.last_sale}" if isinstance(r.last_sale, str) else "در دوره داده هیچ فروشی نداشته"
        buy = f"آخرین خرید {r.last_buy}" if isinstance(r.last_buy, str) else f"در {s['dead_days']} روز اخیر خریدی نداشته"
        return [["وضعیت", f"{last}؛ {buy}؛ {_n(r.stock)} عدد در انبار مانده است."],
                ["برگشت", f"{_n(r.ret_keep)} عدد می‌ماند ({_n(s['return_keep_dead'])} عدد برای قفسه"
                 + (f" + {_n(r.open_req)} درخواست باز" if r.open_req > 0 else "") + f")؛ {_n(r.ret_qty)} عدد برگشت."]]
    if r.status == "nodata":
        return [["وضعیت", "در ماه‌های سالم اخیر فروشی نداشته؛ برای پیش‌بینی سابقه کافی نیست."]]
    if r.abc == "C" and r.c_low:
        return [["وضعیت", f"کالای کم‌فروش ولی منظم (گروه C): در {_n(r.months_sold)} ماه از ماه‌های پایه فروش داشته."],
                ["فروش ماهانه", f"میانگین {_n(r.mean)} عدد (کمترین {_n(r.min)}، بیشترین {_n(r.max)})."],
                ["موجودی", f"{_n(r.stock)} عدد" + (f" منهای {_n(r.open_req)} عدد درخواست باز = {_n(r.net_avail)} عدد آزاد" if r.open_req > 0 else " آزاد")
                 + f"؛ تا رسیدن بار ({arr0}) حدود {_n(r.need)} عدد لازم است."],
                ["مقدار سفارش", f"{_n(r.need)} تا رسیدن بار + {_n(float(s['c_order_months']) * max(r.fc_now, 0))} برای {s['c_order_months']:g} ماه فروش"
                 f" − {_n(r.net_avail)} موجودی آزاد، حداقل ۱ عدد و بدون گرد کردن به کارتن = {_n(r.order)} عدد."]]
    if r.abc == "C":
        why_c = (f"فقط در {_n(r.months_sold)} ماه از ماه‌های پایه فروش داشته و نامنظم حساب می‌شود (گروه C)."
                 if r.few_months else "کالای کم‌فروش و نامنظم (گروه C).")
        if r.status == "red":
            return [["وضعیت", why_c],
                    ["درخواست باز", f"{_n(r.open_req)} عدد، ولی موجودی فقط {_n(r.stock)} عدد است."],
                    ["پیشنهاد", f"فقط کسری درخواست سفارش شود: {_n(r.req_short)} عدد."]]
        return [["وضعیت", why_c],
                ["فروش ماهانه", f"بین {_n(r.min)} و {_n(r.max)} عدد."],
                ["پیشنهاد", "هشدار خودکار ندارد؛ سفارش بر اساس درخواست مشتری."]]
    lines = [["فروش ماهانه", f"میانگین {_n(r.mean)} عدد (کمترین {_n(r.min)}، بیشترین {_n(r.max)})؛ فروش خالص، پس از کسر برگشتی."],
             ["ضریب فصل", f"این ماه {r.sf_now:.2f} و ماه بعد {r.sf_next:.2f}."]]
    if r.ly_next_used:
        w = float(s["ly_weight"])
        lines.append([f"پیش‌بینی {nxt}",
                      f"{1 - w:.0%} پیش‌بینی فصلی ({_n(r.fc_next_model)}) + {w:.0%} فروش همین ماه سال قبل"
                      f" ({_n(max(r.ly_next, 0))} با رشد شعبه {r.ly_growth:.2f}) = {_n(r.fc_next)} عدد."])
    lines.append(["تا رسیدن بار", f"اگر امروز سفارش داده شود، بار حدود {arr0} می‌رسد؛ تا آن موقع حدود {_n(r.need)} عدد لازم است."])
    inc = ""
    if use_in and r.incoming > 0:
        parts = ([f"{_n(r.rk_transit)} در راه"] if r.rk_transit > 0 else []) + ([f"{_n(r.rk_open)} سفارش باز کارخانه"] if r.rk_open > 0 else [])
        inc = f" + {' و '.join(parts)}"
    if r.req_short > 0:
        have = f"{_n(r.stock)} عدد{inc}، ولی درخواست باز {_n(r.open_req)} عدد است؛ یعنی {_n(r.req_short)} عدد کسری درخواست."
    else:
        have = (f"قابل فروش {_n(r.avail)} عدد" + (f" (انبار {_n(r.stock)}{inc})" if inc else "")
                + (f" (پس از کسر {_n(r.open_req)} عدد درخواست باز)" if r.open_req > 0 else "") + ".")
    lines.append(["موجودی", have])
    if r.status in ("red", "orange"):
        lines.append(["سطح هدف", f"باید تا سفارش بعدی ({review} روز دیگر) و رسیدن بار آن ({arr1}) دوام بیاورد: "
                                f"{_n(r.target - r.safety)} تقاضا + {_n(r.safety)} ذخیره اطمینان = {_n(r.target)} عدد."])
    if r.status == "red":
        lines.append(["نتیجه", "قبل از رسیدن بار تمام می‌شود؛ باید فوری سفارش شود."])
    elif r.status == "orange":
        by = f" (حداکثر تا {r.order_by})" if isinstance(r.order_by, str) else ""
        lines.append(["نتیجه", f"تا رسیدن بار کافی است، ولی نه تا سفارش بعد؛ باید در سفارش بعدی{by} باشد."])
    if r.status in ("red", "orange"):
        plus = f" + {_n(r.req_short)} کسری درخواست" if r.req_short > 0 else ""
        raw = r.target + max(r.req_short, 0) - r.avail
        calc = f"{_n(r.target)} سطح هدف{plus} − {_n(r.avail)} موجودی قابل فروش = {_n(raw)} عدد"
        if abs(r.order - raw) >= 1:
            calc += f"؛ گرد به کارتن کامل ({_n(r.unity)} تایی): {_n(r.order)} عدد" if r.unity and r.unity > 1 else f" ← {_n(r.order)} عدد"
        lines.append(["مقدار سفارش", calc + "."])
    elif r.status == "excess":
        lines.append(["نتیجه", f"حدود {r.cover_months:.1f} ماه فروش موجودی دارد؛ مازاد است و سفارش لازم نیست."])
    else:
        lines.append(["نتیجه", "تا نوبت بعد کافی است."])
    if r.factory_short:
        lines.append(["نکته", f"موجودی آزاد انبار محصول کارخانه فقط {_n(r.factory_free)} عدد است."])
    if r.top_share is not None and np.isfinite(r.top_share) and r.top_share > 0.5:
        lines.append(["نکته", f"{r.top_share:.0%} فروش این کالا از یک مشتری ({r.top_cust}) است؛ نوسان آن بیشتر است."])
    if r.ret_rate is not None and np.isfinite(r.ret_rate) and r.ret_rate > 0.2:
        lines.append(["نکته", f"{r.ret_rate:.0%} فروش آن برگشت خورده و پایه از فروش خالص حساب شده."])
    return lines
