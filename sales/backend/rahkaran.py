"""داده کارخانه از دیتابیس راهکاران (Exir_sg3) برای کنترل موجودی شعب هیبرید؛ فقط SELECT.

هر شعبه هیبرید در راهکاران چند مشتری دارد، یکی برای هر خط برند (مثلاً «هیبرید اصفهان - پادینا»، «... - جوو»).
  سفارش باز       = سفارش فروش کارخانه به شعبه (ثبت‌شده، تأییدشده یا نیمه‌انجام) منهای مقدار خارج‌شده از انبار کارخانه
  در راه          = فاکتور کارخانه به شعبه در transit_days روز اخیر منهای خرید ثبت‌شده همان کالا در کارآمد شعبه در همان بازه
                    (شماره فاکتور راهکاران فقط در چند شعبه در کارآمد ثبت می‌شود؛ برای همین مقدار مقایسه می‌شود، نه شماره)
  موجودی کارخانه = مانده انبارهای محصول (کد انبار در factory_stores) در سال مالی جاری
  آزاد کارخانه    = موجودی کارخانه منهای سفارش‌های باز همه مشتریان
کد کالا در راهکاران (LGS3.Part.Code) همان کد کالای کارآمد است و واحد اصلی هر دو «عدد» است.
"""
from __future__ import annotations

import re
import threading
import time
import warnings

import pandas as pd

import loader
import sql_source

ENV_PREFIX = "RAHKARAN_SQLSERVER_"
DEFAULTS = {
    "use_in_branches": False,              # خاموش: محاسبه هر هیبرید فقط با کارآمد (تصمیم کاربر)؛ انبار کارخانه جدا نمایش داده می‌شود
    "live_seconds": 10,                    # هر چند ثانیه امضای تغییر راهکاران بررسی شود (۰ = خاموش، فقط هر ۳۰ دقیقه)
    "open_days": 60,                       # سفارش باز قدیمی‌تر از این تعداد روز کهنه است و حساب نمی‌شود
    "transit_days": 30,                    # بازه مقایسه فاکتور کارخانه با خرید ثبت‌شده در کارآمد
    "factory_stores": ["1", "2", "3", "4"],  # انبار یک/دو/سه محصول و انبار چهار
    "customer_map": {},                    # نگاشت دستی نام مشتری راهکاران ← نام شعبه کارآمد (در صورت خطای نگاشت خودکار)
}
ORDER_STATES = "1, 2, 3"  # ثبت‌شده، تأییدشده، در حال استفاده (۴ بسته، ۵ معلق، ۶ باطل)

# سفارش‌های باز: مقدار هر سطر جزئیات سفارش منهای خروج انبار (سفارش ← مجوز خروج ← حواله انبار)
OPEN_SQL = f"""
SELECT p.FullName AS cust, pt.Code AS code, CAST(o.Date AS date) AS d, o.OrderID AS oid,
       d.MajorUnitQuantity AS ordered, ISNULL(x.issued, 0) AS issued
FROM SLS3.[Order] o
JOIN SLS3.OrderItemProductDetail d ON d.OrderRef = o.OrderID
JOIN LGS3.Part pt ON pt.PartID = d.PartRef
JOIN SLS3.Customer c ON c.CustomerID = o.CustomerRef JOIN GNR3.Party p ON p.PartyID = c.PartyRef
OUTER APPLY (SELECT SUM(v.MajorUnitQuantity) AS issued
             FROM LGS3.IssuePermitItem ipi
             JOIN LGS3.InventoryVoucherItem v ON v.ReferenceRef = ipi.IssuePermitItemID AND v.PartRef = ipi.PartRef
             WHERE ipi.ReferenceRef = d.OrderItemProductDetailID) x
WHERE o.State IN ({ORDER_STATES}) AND o.Date >= DATEADD(day, -?, CAST(GETDATE() AS date))"""
INVOICE_SQL = """
SELECT p.FullName AS cust, pr.Number AS code, CAST(i.Date AS date) AS d, ii.MajorUnitQuantity AS qty
FROM SLS3.InvoiceItem ii JOIN SLS3.Invoice i ON i.InvoiceID = ii.InvoiceRef
JOIN SLS3.Customer c ON c.CustomerID = i.CustomerRef JOIN GNR3.Party p ON p.PartyID = c.PartyRef
JOIN SLS3.Product pr ON pr.ProductID = ii.ProductRef
WHERE i.Date >= DATEADD(day, -?, CAST(GETDATE() AS date)) AND p.FullName LIKE N'%هیبرید%'"""
# مانده انبار: جمع علامت‌دار حواله/رسیدهای دائمی (Direction ۱ ورود، ۲ خروج) در سال مالی جاری
STOCK_SQL = """
SELECT pt.Code AS code, st.Code AS store, SUM(CASE sp.Direction WHEN 1 THEN 1 ELSE -1 END * v.MajorUnitQuantity) AS qty
FROM LGS3.InventoryVoucherItem v
JOIN LGS3.InventoryVoucher iv ON iv.InventoryVoucherID = v.InventoryVoucherRef
JOIN LGS3.InventoryVoucherSpecification sp ON sp.InventoryVoucherSpecificationID = iv.InventoryVoucherSpecificationRef
JOIN LGS3.Part pt ON pt.PartID = v.PartRef JOIN LGS3.Store st ON st.StoreID = iv.StoreRef
WHERE sp.TypeOfEffectOnStock = 1 AND iv.State IN (1, 2)
  AND iv.FiscalYearRef = (SELECT MAX(FiscalYearRef) FROM LGS3.InventoryVoucher)
GROUP BY pt.Code, st.Code"""

# مانده هر کالا در هر انبار کارخانه، با نام کالا و انبار؛ is_product = کالای قابل فروش (تعریف‌شده در SLS3.Product)
FACTORY_SQL = """
SELECT pt.Code AS code, pt.Name AS name, st.Code AS store, st.Name AS store_name, u.Name AS unit,
       CASE WHEN EXISTS (SELECT 1 FROM SLS3.Product p WHERE p.PartRef = pt.PartID) THEN 1 ELSE 0 END AS is_product, x.qty
FROM (SELECT v.PartRef, iv.StoreRef, SUM(CASE sp.Direction WHEN 1 THEN 1 ELSE -1 END * v.MajorUnitQuantity) AS qty
      FROM LGS3.InventoryVoucherItem v
      JOIN LGS3.InventoryVoucher iv ON iv.InventoryVoucherID = v.InventoryVoucherRef
      JOIN LGS3.InventoryVoucherSpecification sp ON sp.InventoryVoucherSpecificationID = iv.InventoryVoucherSpecificationRef
      WHERE sp.TypeOfEffectOnStock = 1 AND iv.State IN (1, 2)
        AND iv.FiscalYearRef = (SELECT MAX(FiscalYearRef) FROM LGS3.InventoryVoucher)
      GROUP BY v.PartRef, iv.StoreRef) x
JOIN LGS3.Part pt ON pt.PartID = x.PartRef JOIN LGS3.Store st ON st.StoreID = x.StoreRef
LEFT JOIN GNR3.Unit u ON u.UnitID = pt.MajorUnitRef
WHERE x.qty <> 0"""
# امضای تغییر: تعداد سطر و بیشترین rowversion جدول‌هایی که موجودی و سفارش باز از آن‌ها ساخته می‌شود.
# هر ثبت، ویرایش (از جمله تغییر وضعیت) یا حذف دست‌کم یکی را عوض می‌کند؛ کل کوئری کمتر از نیم ثانیه است.
SIG_SQL = """
SELECT 'v' t, COUNT_BIG(*) n, CAST(MAX(Version) AS bigint) rv FROM LGS3.InventoryVoucher
UNION ALL SELECT 'vi', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM LGS3.InventoryVoucherItem
UNION ALL SELECT 'o', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM SLS3.[Order]
UNION ALL SELECT 'oi', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM SLS3.OrderItemProductDetail
UNION ALL SELECT 'pi', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM LGS3.IssuePermitItem
UNION ALL SELECT 's', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM LGS3.Store"""
# فهرست همه انبارهای راهکاران (حتی انبارهای بدون مانده) تا ستون هر انبار در جدول کالاها بیاید
STORES_SQL = "SELECT Code AS store, Name AS store_name FROM LGS3.Store"


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("rahkaran") or {})}


def configured(env_file) -> bool:
    env = sql_source.read_env(env_file)
    return all(env.get(ENV_PREFIX + k) for k in ("SERVER", "DATABASE", "USERNAME", "PASSWORD"))


def _norm(s) -> str:
    return re.sub(r"[‌\s]+", " ", str(s).replace("ي", "ی").replace("ك", "ک")).strip()


def branch_of(cust: str, branches: list[str], manual: dict) -> str | None:
    """نام مشتری راهکاران ← شعبه کارآمد؛ طولانی‌ترین نام استان که در نام مشتری آمده («خراسان جنوبی» قبل از «خراسان»).
    «هیبرید غرب (برند) - تهران» همان «هیبرید تهران» است."""
    if cust in manual:
        return manual[cust]
    c = _norm(cust)
    if "هیبرید" not in c:
        return None
    if "غرب" in c and "تهران" in c and "هیبرید تهران" in branches:
        return "هیبرید تهران"
    best = None
    for b in branches:
        reg = _norm(b).replace("هیبریدی", "").replace("هیبرید", "").strip()
        if reg and reg in c and (best is None or len(reg) > len(best[1])):
            best = (b, reg)
    return best[0] if best else None


def _read(cn, sql, params):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return pd.read_sql(sql, cn, params=params)


def load(env_file, cfg: dict, branches: list[str]) -> dict:
    """همه داده لازم راهکاران در یک اتصال. خروجی: سفارش باز و فاکتور هر شعبه (با نام شعبه کارآمد) و موجودی کارخانه."""
    s = settings(cfg)
    cn = sql_source.connect(sql_source.settings(sql_source.read_env(env_file), prefix=ENV_PREFIX))
    try:
        cur = cn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")  # بدون قفل روی جداول راهکاران
        cur.close()
        opn = _read(cn, OPEN_SQL, [int(s["open_days"])])
        inv = _read(cn, INVOICE_SQL, [int(s["transit_days"])])
        stock = _read(cn, STOCK_SQL, [])
    finally:
        cn.close()
    for df in (opn, inv, stock):
        df["code"] = df["code"].map(loader._clean_code)
    stock["store"] = stock["store"].map(loader._clean_code)
    manual = s.get("customer_map") or {}
    names = pd.concat([opn["cust"], inv["cust"]]).dropna().unique()
    cmap = {c: branch_of(c, branches, manual) for c in names}
    for df in (opn, inv):
        df["cust"] = df["cust"].map(loader._clean_text)
        df["branch"] = df["cust"].map({loader._clean_text(k): v for k, v in cmap.items()})
        df["d"] = pd.to_datetime(df["d"]).dt.strftime("%Y-%m-%d")
    opn["open"] = (pd.to_numeric(opn["ordered"], errors="coerce").fillna(0)
                   - pd.to_numeric(opn["issued"], errors="coerce").fillna(0)).clip(lower=0)
    opn = opn[opn["open"] > 0]
    inv["qty"] = pd.to_numeric(inv["qty"], errors="coerce").fillna(0.0)
    stock["qty"] = pd.to_numeric(stock["qty"], errors="coerce").fillna(0.0)
    fstock = stock[stock["store"].isin([str(x) for x in s["factory_stores"]])].groupby("code")["qty"].sum().clip(lower=0)
    open_all = opn.groupby("code")["open"].sum()
    hyb = {c for c, b in cmap.items() if b}
    return {
        "open": opn[opn["branch"].notna()][["branch", "cust", "code", "d", "oid", "open"]],
        "invoices": inv[inv["branch"].notna()][["branch", "code", "d", "qty"]],
        "factory_stock": fstock,
        "factory_free": (fstock - open_all.reindex(fstock.index).fillna(0)).clip(lower=0),
        "customers": sorted(hyb), "unmapped": sorted(c for c in names if not cmap[c] and "هیبرید" in _norm(c)),
        "settings": s,
    }


# ---------------------------------------------------------------- انبار کارخانه (جدا از محاسبه شعب)
def store_kind(code: str, name: str, sellable: list[str]) -> str:
    """دسته انبار برای نمایش: محصول (قابل ارسال به شعب)، زنجیره‌ای، نمونه، راکد، ضایعات، مواد اولیه و بسته‌بندی، سایر."""
    if code in sellable:
        return "product"
    for key, kind in (("زنجیره", "chain"), ("نمونه", "sample"), ("راکد", "stale"), ("ضایعات", "waste"),
                      ("مواد اولیه", "raw"), ("توزین", "raw")):
        if key in name:
            return kind
    return "other"


def load_factory(env_file, cfg: dict) -> dict:
    """موجودی همه انبارهای کارخانه و سفارش‌های باز همه مشتریان در یک اتصال."""
    s = settings(cfg)
    cn = sql_source.connect(sql_source.settings(sql_source.read_env(env_file), prefix=ENV_PREFIX))
    try:
        cur = cn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur.close()
        st = _read(cn, FACTORY_SQL, [])
        stores = _read(cn, STORES_SQL, [])
        opn = _read(cn, OPEN_SQL, [int(s["open_days"])])
    finally:
        cn.close()
    st["code"] = st["code"].map(loader._clean_code)
    for df in (st, stores):
        df["store"] = df["store"].map(loader._clean_code)
        df["store_name"] = df["store_name"].map(lambda x: _norm(loader._clean_text(x)))
    for k in ("name", "unit"):
        st[k] = st[k].map(loader._clean_text)
    st["qty"] = pd.to_numeric(st["qty"], errors="coerce").fillna(0.0)
    st["is_product"] = st["is_product"].astype(bool)
    sellable = [str(x) for x in s["factory_stores"]]
    st["kind"] = [store_kind(c, n, sellable) for c, n in zip(st["store"], st["store_name"])]
    stores["kind"] = [store_kind(c, n, sellable) for c, n in zip(stores["store"], stores["store_name"])]
    opn["code"] = opn["code"].map(loader._clean_code)
    opn["open"] = (pd.to_numeric(opn["ordered"], errors="coerce").fillna(0)
                   - pd.to_numeric(opn["issued"], errors="coerce").fillna(0)).clip(lower=0)
    opn["hybrid"] = opn["cust"].map(lambda c: "هیبرید" in _norm(c))
    return {"stock": st, "stores": stores.drop_duplicates("store"), "open": opn[opn["open"] > 0][["code", "open", "hybrid"]], "settings": s}


def signature(env_file, sql: str = SIG_SQL) -> tuple:
    cn = sql_source.connect(sql_source.settings(sql_source.read_env(env_file), prefix=ENV_PREFIX))
    try:
        cur = cn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        rows = cur.execute(sql).fetchall()
    finally:
        cn.close()
    return tuple((r.t, int(r.n), int(r.rv or 0)) for r in rows)


class FactorySource:
    """موجودی انبار کارخانه از راهکاران. لایو: هر live_seconds ثانیه امضای تغییر خوانده می‌شود و فقط وقتی
    عوض شده باشد همه داده دوباره خوانده می‌شود (حدود ۴ ثانیه). بدون لایو هر ۳۰ دقیقه (یا با درخواست کاربر).
    load و sig_sql: همین روش برای داده دیگری از راهکاران (فروش B2B در rahkaran_sales)."""

    def __init__(self, env_file, read_cfg, load=None, sig_sql: str = SIG_SQL):
        self.env_file, self.read_cfg = env_file, read_cfg
        self.load, self.sig_sql = load or load_factory, sig_sql
        self.snap: dict | None = None
        self.lock = threading.Lock()
        self.sig: tuple | None = None
        self.stamp = 0  # با هر خواندن تازه زیاد می‌شود تا فرانت‌اند جدول را دوباره بگیرد
        self.live_checked = 0.0
        self.live_error: str | None = None

    def _reload(self):
        if not configured(self.env_file):
            raise loader.DataError("مشخصات اتصال راهکاران (RAHKARAN_SQLSERVER_*) در فایل .env نیست.")
        sig = signature(self.env_file, self.sig_sql)  # قبل از خواندن، تا تغییر حین خواندن در بررسی بعدی دیده شود
        self.snap = {**self.load(self.env_file, self.read_cfg()), "fetched": time.time()}
        self.sig = sig
        self.stamp += 1

    def get(self, force: bool = False) -> dict:
        with self.lock:
            if self.snap is None or force or time.time() - self.snap["fetched"] >= 30 * 60:
                self._reload()
            return self.snap

    def live_step(self) -> bool:
        """یک بررسی لایو؛ True اگر داده تازه خوانده شد. تا کسی صفحه را باز نکرده (snap خالی) چیزی خوانده نمی‌شود."""
        if self.snap is None:
            return False
        sig = signature(self.env_file, self.sig_sql)
        self.live_checked = time.time()
        if sig == self.sig:
            return False
        with self.lock:
            self._reload()
        return True

    def is_live(self) -> bool:
        wait = float(settings(self.read_cfg())["live_seconds"] or 0)
        return wait > 0 and not self.live_error and time.time() - self.live_checked <= max(30.0, 3 * wait)
