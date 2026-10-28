"""فروش B2B (نمایندگان استانی) از دیتابیس راهکاران؛ فقط SELECT. معادل فایل «B2B-Sales Report 1405».

فهرست مشتریان (کد، نام، شهر، استان، برند) از شیت draft همان فایل در data/rahkaran/b2b_customers.csv است
و گروه کالاها از همان شیت در data/rahkaran/products.csv. کد مشتری = SLS3.Customer.Number.
  ناخالص = InvoiceItem.Price ، خالص = InvoiceItem.NetPrice (پس از کسور و اضافات)، تعداد = MajorUnitQuantity
  فاکتور = ترکیب (مشتری، روز)، مثل ستون «فاکتور سال/ماه» شیت Calc
  فاکتورهای با وضعیت ۲ و ۱۱ حساب می‌شوند (۱ = پیش‌نویس)؛ با این قاعده عدد مهر ۱۴۰۵ دقیقاً برابر اکسل است.
برگشتی‌ها (SLS3.ReturnInvoice) در اکسل نیستند؛ جدا نمایش داده می‌شوند و از فروش کم نمی‌شوند.
تخفیف نقدی = مبلغ سیاست فروش «تخفیف مشتریان اصلی ۱۴۰۵» روی هر قلم فاکتور (SLS3.InvoiceItemPolicyResult.Price)،
  مثل ستون «مبلغ سیاست‌های فاکتور» شیت «فاکتور با سیاست فروش»؛ جمع کل = خالص + تخفیف نقدی.
درخواست فروش (ستون «ریال ناخالص درخواست» شیت‌های Customer Brand و Total report) = SLS3.SaleRequestItem.Price
  درخواست‌های «تأییدشده» (۲) و «بسته‌شده» (۴)، مثل شیت درخواست؛ باطل (۶) و بقیه حساب نمی‌شوند.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

import loader
import rahkaran as RK
import sql_source

ROOT = Path(__file__).resolve().parent.parent
CUSTOMERS_FILE = ROOT / "data" / "rahkaran" / "b2b_customers.csv"
PRODUCTS_FILE = ROOT / "data" / "rahkaran" / "products.csv"
STATUSES = "2, 11"
REQUEST_STATES = "2, 4"
CASH_POLICY = "تخفیف مشتریان اصلی"  # نام سیاست تخفیف نقدی (با سال، مثل «... 1405»)
# ستون‌های گروه کالا در شیت Total report (Category 1 شیت draft)
TOTAL_REPORT_CATS = ["رنگ مو", "اکسیدان", "پودر دکلره", "اسپری مو", "اسپری چسب مو فلزی"]
DEFAULT_FROM = "1404/01/01"  # یک سال قبل هم خوانده می‌شود تا مقایسه با سال گذشته ممکن باشد
OTHER = "سایر"
# نام برند در شیت draft چند املا دارد
BRAND_FIX = {"ارکیا": "آرکیا", "اوردانت": "اورادنت"}

LINES_SQL = """
SELECT 'S' AS kind, c.Number AS code, FORMAT(i.Date, 'yyyy/MM/dd', 'fa-IR') AS date, i.Number AS inv,
       pr.Number AS product_code, pr.Name AS product, ii.MajorUnitQuantity AS qty, ii.Price AS gross, ii.NetPrice AS net,
       ISNULL(cd.cash, 0) AS cash
FROM SLS3.InvoiceItem ii JOIN SLS3.Invoice i ON i.InvoiceID = ii.InvoiceRef
JOIN SLS3.Customer c ON c.CustomerID = i.CustomerRef JOIN SLS3.Product pr ON pr.ProductID = ii.ProductRef
OUTER APPLY (SELECT SUM(pr2.Price) AS cash FROM SLS3.InvoiceItemPolicyResult pr2
             JOIN GNR3.BusinessPolicy bp ON bp.BusinessPolicyID = pr2.BusinessPolicyRef
             WHERE pr2.InvoiceItemRef = ii.InvoiceItemID AND bp.Name LIKE N'{cash}%') cd
WHERE i.Date >= ? AND i.Status IN ({st}) AND c.Number IN ({codes})
UNION ALL
SELECT 'R', c.Number, FORMAT(r.Date, 'yyyy/MM/dd', 'fa-IR'), r.Number,
       pr.Number, pr.Name, ri.MajorUnitQuantity, ri.Price, ri.NetPrice, 0
FROM SLS3.ReturnInvoiceItem ri JOIN SLS3.ReturnInvoice r ON r.ReturnInvoiceID = ri.ReturnInvoiceRef
JOIN SLS3.Customer c ON c.CustomerID = r.CustomerRef JOIN SLS3.Product pr ON pr.ProductID = ri.ProductRef
WHERE r.Date >= ? AND r.Status IN ({st}) AND c.Number IN ({codes})
UNION ALL
SELECT 'Q', c.Number, FORMAT(q.Date, 'yyyy/MM/dd', 'fa-IR'), q.Number,
       pr.Number, pr.Name, qi.MajorUnitQuantity, qi.Price, qi.NetPrice, 0
FROM SLS3.SaleRequestItem qi JOIN SLS3.SaleRequest q ON q.SaleRequestID = qi.SaleRequestRef
JOIN SLS3.Customer c ON c.CustomerID = q.CustomerRef JOIN SLS3.Product pr ON pr.ProductID = qi.ProductRef
WHERE q.Date >= ? AND q.State IN ({rq}) AND c.Number IN ({codes})"""
# امضای تغییر فاکتور، برگشتی و درخواست (مثل rahkaran.SIG_SQL)
SIG_SQL = """
SELECT 'i' t, COUNT_BIG(*) n, CAST(MAX(Version) AS bigint) rv FROM SLS3.Invoice
UNION ALL SELECT 'ii', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM SLS3.InvoiceItem
UNION ALL SELECT 'r', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM SLS3.ReturnInvoice
UNION ALL SELECT 'ri', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM SLS3.ReturnInvoiceItem
UNION ALL SELECT 'q', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM SLS3.SaleRequest
UNION ALL SELECT 'qi', COUNT_BIG(*), CAST(MAX(Version) AS bigint) FROM SLS3.SaleRequestItem"""
TODAY_SQL = "SELECT FORMAT(GETDATE(), 'yyyy/MM/dd', 'fa-IR') AS d"


def norm(s) -> str:
    return re.sub(r"[‌\s]+", " ", str(s or "").replace("ي", "ی").replace("ك", "ک")).strip()


def to_gregorian(jdate: str) -> str:
    """۱۴۰۴/۰۱/۰۱ ← 2025-03-21 (الگوریتم استاندارد تقویم جلالی)"""
    jy, jm, jd = (int(x) for x in jdate.split("/"))
    jy += 1595
    days = -355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186)
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    for gm, n in enumerate([31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], start=1):
        if gd <= n:
            break
        gd -= n
    return f"{gy:04d}-{gm:02d}-{gd:02d}"


def customers() -> pd.DataFrame:
    """مشتریان B2B شیت draft؛ شهرِ خالی از انتهای نام («... - کرج») برداشته می‌شود."""
    c = pd.read_csv(CUSTOMERS_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    c["code"] = c["code"].map(loader._clean_code)
    for k in ("name", "short", "city", "brand", "province"):
        c[k] = c[k].map(norm)
    c["brand"] = c["brand"].replace(BRAND_FIX)
    tail = c["name"].str.rsplit("-", n=1).str[-1].map(norm)
    c["city"] = c["city"].where(c["city"] != "", tail)
    c["short"] = c["short"].where(c["short"] != "", c["name"])
    return c.drop_duplicates("code").set_index("code")


# ---------------------------------------------------------------- کدهای جدید نمایندگان (خارج از شیت draft)
# کد مشتری نمایندگان در راهکاران بازه هر برند است؛ نماینده‌ای که بعد از ساخت شیت draft کد گرفته خودکار اضافه می‌شود
CODE_BRANDS = [("874", "اورادنت"), ("875", "آپ اسکای"), ("79", "مولهنس"), ("81", "پادینا"), ("82", "بیس"), ("83", "آرکیا"),
               ("84", "لورینت"), ("85", "کالیون"), ("86", "وینا"), ("88", "آدونیس"), ("89", "جوو"), ("92", "تاکوری")]
# حساب‌هایی که در همین بازه‌ها هستند ولی نماینده نیستند
NOT_REP = ("هیبرید", "زنجیره", "انبار پخش", "اینترنتی", "اهدایی", "نمونه", "کارکنان", "مرجوعی", "صادرات")
EXPORT_FILE = ROOT / "data" / "rahkaran" / "export_customers.csv"
# نام کشور یا شهر خارجی در نام حساب ← کشور؛ این حساب‌ها صادراتی‌اند (در صفحه فروش صادراتی می‌آیند، نه B2B)
COUNTRIES = [("بغداد", "عراق"), ("عراق", "عراق"), ("ازبکستان", "ازبکستان"), ("اربکستان", "ازبکستان"), ("عمان", "عمان"),
             ("افغانستان", "افغانستان"), ("هرات", "افغانستان"), ("تاجیکستان", "تاجیکستان"), ("تاجکستان", "تاجیکستان"),
             ("ارمنستان", "ارمنستان"), ("روسیه", "روسیه"), ("سنگال", "سنگال"), ("ترکیه", "ترکیه"), ("گرجستان", "گرجستان"),
             ("قزاقستان", "قزاقستان"), ("ترکمنستان", "ترکمنستان"), ("باکو", "آذربایجان"), ("جمهوری آذربایجان", "آذربایجان")]


def foreign_country(name: str) -> str:
    return next((c for key, c in COUNTRIES if key in name), "")


def short_name(name: str) -> str:
    """نام کوتاه از نام حساب: «. دایلر (همدان) مولهنس» ← دایلر"""
    name = norm(name).strip(" .")
    return norm(re.split(r"[(\-]", name)[0]) or name
CANDIDATES_SQL = """
SELECT DISTINCT c.Number AS code, p.FullName AS name
FROM SLS3.Invoice i JOIN SLS3.Customer c ON c.CustomerID = i.CustomerRef JOIN GNR3.Party p ON p.PartyID = c.PartyRef
WHERE i.Date >= ? AND i.Status IN ({st}) AND LEN(c.Number) = 6 AND LEFT(c.Number, 1) IN ('7', '8', '9')
UNION
SELECT DISTINCT c.Number, p.FullName
FROM SLS3.SaleRequest q JOIN SLS3.Customer c ON c.CustomerID = q.CustomerRef JOIN GNR3.Party p ON p.PartyID = c.PartyRef
WHERE q.Date >= ? AND q.State IN ({rq}) AND LEN(c.Number) = 6 AND LEFT(c.Number, 1) IN ('7', '8', '9')"""


def code_brand(code: str) -> str:
    return next((b for pre, b in CODE_BRANDS if code.startswith(pre)), "")


def new_reps(found: pd.DataFrame, cust: pd.DataFrame) -> pd.DataFrame:
    """کدهای نماینده‌ای که در راهکاران فاکتور یا درخواست دارند ولی در شیت draft نیستند.
    استان و شهر: از نام کوتاه نماینده‌ای که در draft هست («... - محسن دوسته»)، یا از نام شهر/استان در نام حساب."""
    export = set(pd.read_csv(EXPORT_FILE, dtype=str, encoding="utf-8-sig")["code"].map(loader._clean_code))
    found = found.assign(code=found["code"].map(loader._clean_code), name=found["name"].map(norm))
    found = found[~found["code"].isin(cust.index) & ~found["code"].isin(export) & found["code"].map(code_brand).ne("")]
    found = found[~found["name"].map(lambda n: any(w in n for w in NOT_REP) or bool(foreign_country(n)))].drop_duplicates("code")
    if found.empty:
        return found.assign(short="", city="", province="", brand="", source="")
    person = cust.drop_duplicates("short").set_index("short")
    brands = {b for _, b in CODE_BRANDS} | set(cust["brand"])
    place = {}  # شهر یا استان ← (شهر، استان)؛ نام برند (داده ناقص ستون شهر) کنار گذاشته می‌شود
    for r in cust.itertuples():
        if len(r.city) > 2 and r.city not in brands:
            place.setdefault(r.city, (r.city, r.province))
        place.setdefault(r.province, (r.province, r.province))
    rows = []
    for r in found.itertuples():
        name = r.name.strip(" .")
        short = short_name(name)
        # اول شهر یا استانی که در نام حساب آمده، بعد نماینده هم‌نام در draft («... - محسن دوسته»)
        hit = next((k for k in sorted(place, key=len, reverse=True) if k in name), None)
        who = next((k for k in sorted(person.index, key=len, reverse=True) if len(k) > 3 and k in name), None)
        if hit:
            city, prov = place[hit]
        elif who:
            city, prov = person.at[who, "city"], person.at[who, "province"]
        else:
            city, prov = "", "نامشخص"
        if who:
            short = who
        rows.append({"code": r.code, "name": name, "short": short, "city": city, "province": prov,
                     "brand": code_brand(r.code), "channel": "B2B", "source": "auto"})
    return pd.DataFrame(rows)


def products() -> pd.DataFrame:
    p = pd.read_csv(PRODUCTS_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    p["code"] = p["code"].map(loader._clean_code)
    for k in ("cat1", "cat2"):
        p[k] = p[k].map(norm).replace("", OTHER)
    return p.drop_duplicates("code").set_index("code")[["cat1", "cat2"]]


def load(env_file, cfg: dict) -> dict:
    """همه سطرهای فاکتور، برگشتی و درخواست مشتریان B2B از sales_from (تاریخ جلالی، تنظیم rahkaran.sales_from)."""
    s = RK.settings(cfg)
    cust = customers().assign(source="draft")
    since = to_gregorian(s.get("sales_from") or DEFAULT_FROM)
    cn = sql_source.connect(sql_source.settings(sql_source.read_env(env_file), prefix=RK.ENV_PREFIX))
    try:
        cur = cn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur.close()
        found = RK._read(cn, CANDIDATES_SQL.format(st=STATUSES, rq=REQUEST_STATES), [since] * 2)
        cust = pd.concat([cust, new_reps(found, cust).set_index("code")])
        codes = ",".join(f"'{c}'" for c in cust.index if c.isdigit())
        df = RK._read(cn, LINES_SQL.format(st=STATUSES, rq=REQUEST_STATES, codes=codes, cash=CASH_POLICY), [since] * 3)
        today = RK._read(cn, TODAY_SQL, [])["d"].iloc[0]
    finally:
        cn.close()
    for k in ("code", "product_code"):
        df[k] = df[k].map(loader._clean_code)
    df["product"] = df["product"].map(loader._clean_text)
    df["inv"] = df["inv"].astype(str)
    for k in ("qty", "gross", "net", "cash"):
        df[k] = pd.to_numeric(df[k], errors="coerce").fillna(0.0)
    df["month"] = df["date"].str[:7]
    cat = products().reindex(df["product_code"])
    df["cat1"] = cat["cat1"].fillna(OTHER).values
    df["cat2"] = cat["cat2"].fillna(OTHER).values
    info = cust.reindex(df["code"])
    for k in ("short", "city", "province", "brand"):
        df[k] = info[k].values
    return {"lines": df, "customers": cust.reset_index(), "today": today, "since": s.get("sales_from") or DEFAULT_FROM}


# ---------------------------------------------------------------- محاسبه
def periods(snap: dict) -> list[dict]:
    """YTD سال جاری و ماه‌های دارای فروش، جدیدترین اول."""
    y = snap["today"][:4]
    months = sorted({m for m in snap["lines"].loc[snap["lines"]["kind"] == "S", "month"].unique() if m.startswith(y)}, reverse=True)
    return [{"value": "YTD", "label": f"از ابتدای {y}"}] + [{"value": m, "label": m} for m in months]


def window(snap: dict, period: str) -> tuple[pd.Series, pd.Series, str]:
    """ماسک دوره و همان دوره در سال قبل (برای ماه جاری و YTD تا همان روز)."""
    df, today = snap["lines"], snap["today"]
    y = today[:4]
    ly = str(int(y) - 1)
    if period == "YTD" or not re.fullmatch(r"\d{4}/\d{2}", period or ""):
        cur = df["date"].str[:4].eq(y)
        prev = df["date"].str[:4].eq(ly) & (df["date"].str[5:] <= today[5:])
        return cur, prev, "YTD"
    cur = df["month"].eq(period)
    prev = df["month"].eq(f"{int(period[:4]) - 1}{period[4:]}")
    if period == today[:7]:
        prev &= df["date"].str[8:] <= today[8:]
    return cur, prev, period


def _kpis(s: pd.DataFrame, r: pd.DataFrame, ly: pd.DataFrame, codes, ytd: pd.DataFrame, q: pd.DataFrame | None = None) -> dict:
    """codes: کدهای مشتری محدوده (تعداد مشتری = کد یکتا)؛ ytd: فاکتورهای همان محدوده از ابتدای سال جاری.
    مشتری فعال = کدی که از ابتدای سال خرید (فروش خالص مثبت) داشته؛ بقیه «بدون خرید از ابتدای سال»."""
    codes = set(codes)
    active = set(ytd.loc[ytd["net"] > 0, "code"]) & codes
    gross, net = float(s["gross"].sum()), float(s["net"].sum())
    inv = int(s.drop_duplicates(["code", "date"]).shape[0])
    ly_net = float(ly["net"].sum())
    return {"gross": gross, "net": net, "qty": float(s["qty"].sum()), "invoices": inv,
            "avg_invoice": net / inv if inv else None, "disc_rate": 1 - net / gross if gross else None,
            "customers": len(active), "customers_total": len(codes), "customers_inactive": len(codes - active),
            "customers_period": int(s.loc[s["net"] > 0, "code"].nunique()),
            "returns": float(r["net"].sum()), "return_rate": float(r["net"].sum()) / net if net else None,
            "ly_net": ly_net, "growth": net / ly_net - 1 if ly_net else None, "skus": int(s["product_code"].nunique()),
            "req_gross": float(q["gross"].sum()) if q is not None else None,
            "cash": float(s["cash"].sum()), "net_cash": net + float(s["cash"].sum())}


def _group(s: pd.DataFrame, by: str, ly: pd.DataFrame | None = None) -> pd.DataFrame:
    g = s.groupby(by).agg(net=("net", "sum"), gross=("gross", "sum"), qty=("qty", "sum"),
                          customers=("code", "nunique")).reset_index().rename(columns={by: "key"})
    g["share"] = g["net"] / g["net"].sum() if g["net"].sum() else None
    if ly is not None:
        g["ly_net"] = g["key"].map(ly.groupby(by)["net"].sum()).fillna(0.0)
    return g.sort_values("net", ascending=False)


def _monthly(df: pd.DataFrame, mask_rows: pd.Series, today: str) -> list[dict]:
    """فروش خالص ماه‌به‌ماه سال جاری کنار همان ماه سال قبل."""
    y, ly = today[:4], str(int(today[:4]) - 1)
    s = df[mask_rows & (df["kind"] == "S")]
    by = s.groupby([s["date"].str[:4], s["date"].str[5:7]])["net"].sum()
    last = int(today[5:7])
    return [{"month": f"{y}/{m:02d}", "net": float(by.get((y, f"{m:02d}"), 0.0)),
             "ly_net": float(by.get((ly, f"{m:02d}"), 0.0))} for m in range(1, last + 1)]


def _ytd(snap: dict, keep: pd.Series) -> pd.DataFrame:
    """فاکتورهای فروش محدوده (keep) از ابتدای سال جاری، برای شمارش مشتری فعال"""
    df = snap["lines"]
    return df[keep & df["kind"].eq("S") & df["date"].str.startswith(snap["today"][:4])]


def _scope(snap: dict, period: str, brand: str | None, province: str | None = None, code: str | None = None):
    df = snap["lines"]
    cur, prev, period = window(snap, period)
    keep = pd.Series(True, index=df.index)
    if brand:
        keep &= df["brand"].eq(brand)
    if province:
        keep &= df["province"].map(norm).eq(norm(province))
    if code:
        keep &= df["code"].eq(code)
    sale = df["kind"].eq("S")
    return df[cur & keep & sale], df[cur & keep & df["kind"].eq("R")], df[prev & keep & sale], keep, period


def summary(snap: dict, period: str, brand: str | None) -> dict:
    s, r, ly, keep, period = _scope(snap, period, brand)
    cust = snap["customers"]
    if brand:
        cust = cust[cust["brand"] == brand]
    s = s.assign(province=s["province"].map(norm))
    ly = ly.assign(province=ly["province"].map(norm))
    prov = _group(s, "province", ly)
    by_brand = s.groupby(["province", "brand"])["net"].sum()
    prov["brands"] = [[{"brand": b, "net": float(v)} for b, v in by_brand.get(p, pd.Series(dtype=float)).sort_values(ascending=False).items()]
                      for p in prov["key"]]
    prov["customers_total"] = prov["key"].map(cust["province"].map(norm).value_counts()).fillna(0).astype(int)
    # مشتریان سازنده ۸۰٪ فروش (مثل نمودار TOP 80% شیت Bubble Chart)
    c = s.groupby("code").agg(net=("net", "sum"), gross=("gross", "sum"), qty=("qty", "sum")).sort_values("net", ascending=False)
    c = c[c["net"] > 0]
    cum = c["net"].cumsum() / c["net"].sum() if len(c) else c["net"]
    top = c[(cum.shift(fill_value=0) < 0.8)].reset_index()
    info = snap["customers"].set_index("code")
    for k in ("name", "short", "city", "province", "brand"):
        top[k] = top["code"].map(info[k])
    top["share"] = top["net"] / c["net"].sum() if len(c) else None
    return {"period": period, "brand": brand, "kpis": _kpis(s, r, ly, cust["code"], _ytd(snap, keep)),
            "provinces": prov, "brands": _group(s, "brand", ly), "categories": _group(s, "cat2"),
            "top80": top, "top80_of": int(len(c)), "monthly": _monthly(snap["lines"], keep, snap["today"])}


def _customer_rows(snap: dict, s: pd.DataFrame, ly: pd.DataFrame, cust: pd.DataFrame) -> pd.DataFrame:
    """یک سطر برای هر مشتری فهرست (حتی بدون خرید در دوره) با آخرین خرید در کل داده."""
    all_s = snap["lines"][snap["lines"]["kind"] == "S"]
    g = s.groupby("code").agg(net=("net", "sum"), gross=("gross", "sum"), qty=("qty", "sum"), cash=("cash", "sum"))
    inv = s.drop_duplicates(["code", "date"]).groupby("code").size()
    rows = cust[["code", "name", "short", "city", "province", "brand", "source"]].copy()
    rows["net"] = rows["code"].map(g["net"]).fillna(0.0)
    rows["gross"] = rows["code"].map(g["gross"]).fillna(0.0)
    rows["qty"] = rows["code"].map(g["qty"]).fillna(0.0)
    rows["cash"] = rows["code"].map(g["cash"]).fillna(0.0)
    rows["net_cash"] = rows["net"] + rows["cash"]
    rows["invoices"] = rows["code"].map(inv).fillna(0).astype(int)
    rows["ly_net"] = rows["code"].map(ly.groupby("code")["net"].sum()).fillna(0.0)
    rows["last_date"] = rows["code"].map(all_s[all_s["net"] > 0].groupby("code")["date"].max())
    total = rows["net"].sum()
    rows["share"] = rows["net"] / total if total else None
    return rows.sort_values("net", ascending=False)


def customer_list(snap: dict, period: str) -> dict:
    """همه مشتریان فهرست B2B با فروش دوره و همان بازه سال قبل (برای پرونده یکپارچه نمایندگان در داشبورد unified)"""
    s, r, ly, keep, period = _scope(snap, period, None)
    return {"period": period, "customers": _customer_rows(snap, s, ly, snap["customers"])}


def province(snap: dict, name: str, period: str, brand: str | None) -> dict:
    s, r, ly, keep, period = _scope(snap, period, brand, province=name)
    cust = snap["customers"]
    cust = cust[cust["province"].map(norm).eq(norm(name)) & (cust["brand"].eq(brand) if brand else True)]
    rows = _customer_rows(snap, s, ly, cust)
    cities = rows.groupby("city").agg(net=("net", "sum"), customers=("code", "size"),
                                      active=("net", lambda x: int((x > 0).sum()))).reset_index().rename(columns={"city": "key"})
    return {"province": norm(name), "period": period, "brand": brand, "kpis": _kpis(s, r, ly, cust["code"], _ytd(snap, keep)),
            "customers": rows, "cities": cities.sort_values("net", ascending=False), "brands": _group(s, "brand", ly),
            "categories": _group(s, "cat2"), "monthly": _monthly(snap["lines"], keep, snap["today"])}


def customer(snap: dict, code: str, period: str) -> dict | None:
    info = snap["customers"].set_index("code")
    if code not in info.index:
        return None
    s, r, ly, keep, period = _scope(snap, period, None, code=code)
    cur, _, _ = window(snap, period)
    q = snap["lines"][cur & keep & snap["lines"]["kind"].eq("Q")]
    prods = (s.groupby(["product_code", "product", "cat2"]).agg(net=("net", "sum"), gross=("gross", "sum"), qty=("qty", "sum"),
                                                                cash=("cash", "sum"))
             .reset_index().sort_values("net", ascending=False))
    prods["net_cash"] = prods["net"] + prods["cash"]
    inv = (pd.concat([s, r, q]).groupby(["kind", "inv", "date"])
           .agg(net=("net", "sum"), gross=("gross", "sum"), qty=("qty", "sum"), cash=("cash", "sum"), lines=("product_code", "size"))
           .reset_index().sort_values(["date", "inv"], ascending=False))
    inv["net_cash"] = inv["net"] + inv["cash"]
    inv["kind"] = inv["kind"].map({"S": "فاکتور فروش", "R": "برگشتی", "Q": "درخواست"})
    all_s = snap["lines"][(snap["lines"]["kind"] == "S") & (snap["lines"]["code"] == code)]
    return {"customer": {"code": code, **info.loc[code].to_dict()}, "period": period,
            "kpis": _kpis(s, r, ly, [code], _ytd(snap, keep), q), "first_date": all_s["date"].min() if len(all_s) else None,
            "last_date": all_s["date"].max() if len(all_s) else None,
            "categories": _group(s, "cat2"), "products": prods, "invoices": inv,
            "monthly": _monthly(snap["lines"], keep, snap["today"])}


# ---------------------------------------------------------------- شیت‌های Customer Brand و Total report
METRICS = ("req", "gross", "net", "qty", "cash", "net_cash")


def _block(df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    """ناخالص درخواست، ناخالص و خالص فاکتور و تعداد فروش هر کد مشتری"""
    q = df[mask & df["kind"].eq("Q")].groupby("code")["gross"].sum().rename("req")
    s = df[mask & df["kind"].eq("S")].groupby("code").agg(gross=("gross", "sum"), net=("net", "sum"), qty=("qty", "sum"),
                                                          cash=("cash", "sum"))
    s["net_cash"] = s["net"] + s["cash"]
    return pd.concat([q, s], axis=1).reindex(columns=list(METRICS)).fillna(0.0)


def _sum(b: pd.DataFrame, codes: list[str]) -> dict:
    sub = b.reindex(codes).fillna(0.0)
    return {k: float(sub[k].sum()) for k in METRICS}


def _year_sales(snap: dict) -> pd.DataFrame:
    df, y = snap["lines"], snap["today"][:4]
    return df[df["kind"].eq("S") & df["date"].str.startswith(y)]


def brand_order(snap: dict) -> list[str]:
    """برندها از بیشترین فروش خالص سال جاری (برندهای بدون فروش در انتها)"""
    net = _year_sales(snap).groupby("brand")["net"].sum()
    return sorted(snap["customers"]["brand"].unique(), key=lambda b: (-net.get(b, 0.0), b))


def categories(snap: dict) -> list[str]:
    """گروه‌های کالای (Category 1) دارای فروش در سال جاری، از بیشترین فروش"""
    return _year_sales(snap).groupby("cat1")["net"].sum().sort_values(ascending=False).index.tolist()


def customer_brand(snap: dict, period: str, cat: str | None) -> dict:
    """شیت Customer Brand: هر کد مشتری در یک سطر (نماینده‌ای که با چند برند کار می‌کند برای هر برند کد و سطر جدا دارد)
    و ناخالص درخواست، خالص فاکتور و فروش تعدادی زیر ستون برند همان کد؛ فیلتر گروه کالا (Category 1) و ماه / YTD."""
    df = snap["lines"]
    cur, _, period = window(snap, period)
    blk = _block(df, cur & (df["cat1"].eq(cat) if cat else True))
    cust = snap["customers"]
    rows = []
    for c in cust.itertuples():
        v = _sum(blk, [c.code])
        rows.append({"key": c.code, "code": c.code, "name": c.name, "short": c.short, "city": c.city,
                     "province": c.province, "brand": c.brand, "source": c.source, "brands": {c.brand: v}, **v})
    rows.sort(key=lambda r: (-r["net"], -r["req"], r["province"], r["short"], r["brand"]))
    brands = brand_order(snap)
    totals = {b: _sum(blk, cust.loc[cust["brand"].eq(b), "code"].tolist()) for b in brands}
    return {"period": period, "cat": cat, "brands": brands, "rows": rows, "brand_totals": totals,
            "total": _sum(blk, cust["code"].tolist()), "cat_list": categories(snap)}


def product_list(snap: dict) -> list[dict]:
    """کد و نام کالاهای دارای فاکتور یا درخواست، از بیشترین فروش خالص سال جاری"""
    df, y = snap["lines"], snap["today"][:4]
    d = df[df["kind"].isin(["S", "Q"])]
    net = d[d["kind"].eq("S") & d["date"].str.startswith(y)].groupby("product_code")["net"].sum()
    p = d.drop_duplicates("product_code", keep="last")[["product_code", "product", "cat2"]]
    p = p.assign(net=p["product_code"].map(net).fillna(0.0)).sort_values(["net", "product_code"], ascending=[False, True])
    return [{"code": r.product_code, "name": r.product, "cat": r.cat2} for r in p.itertuples()]


def report_days(snap: dict) -> list[str]:
    """روزهای سال جاری که فاکتور یا درخواست دارند، جدیدترین اول"""
    df, y = snap["lines"], snap["today"][:4]
    return sorted(df.loc[df["kind"].isin(["S", "Q"]) & df["date"].str.startswith(y), "date"].unique(), reverse=True)


def total_report(snap: dict, day: str | None, month: str | None, cats: list[str] | None) -> dict:
    """شیت Total report: برای هر برند جمع برند و سپس نمایندگانش، با سه بلوک روز / ماه / از ابتدای سال
    (ناخالص درخواست، ناخالص، خالص، تعداد) و فروش خالص و تعدادی از ابتدای سال در گروه‌های کالا.
    روز و ماه جدا انتخاب می‌شوند (مثل سلول‌های تاریخ و ماه شیت)؛ سال = سال روز انتخاب‌شده."""
    df = snap["lines"]
    # پیش‌فرض روز گزارش = امروز (حتی اگر هنوز فاکتوری ثبت نشده باشد) و ماه = ماه همان روز
    today = snap["today"]
    days = [today] + [d for d in report_days(snap) if d != today]
    day = day if day in days else today
    month = month if month and re.fullmatch(r"\d{4}/\d{2}", month) else day[:7]
    cats = cats or TOTAL_REPORT_CATS
    year = df["date"].str.startswith(day[:4])
    blocks = {"day": _block(df, df["date"].eq(day)), "mtd": _block(df, df["month"].eq(month)), "ytd": _block(df, year)}
    ys = df[df["kind"].eq("S") & year & df["cat1"].isin(cats)]
    cat_blk = ys.groupby(["code", "cat1"]).agg(net=("net", "sum"), qty=("qty", "sum"))
    cust = snap["customers"].set_index("code")

    def vals(codes: list[str]) -> dict:
        out = {k: _sum(b, codes) for k, b in blocks.items()}
        cb = cat_blk[cat_blk.index.get_level_values(0).isin(codes)].groupby(level=1).sum()
        out["cats"] = {c: {"net": float(cb["net"].get(c, 0.0)), "qty": float(cb["qty"].get(c, 0.0))} for c in cats}
        return out

    groups = []
    for brand in brand_order(snap):
        codes = cust.index[cust["brand"].eq(brand)].tolist()
        # مثل اکسل فقط نمایندگانی که از ابتدای سال درخواست یا فاکتوری دارند
        members = [{"code": c, "short": cust.at[c, "short"], "name": cust.at[c, "name"], "province": cust.at[c, "province"],
                    "city": cust.at[c, "city"], **vals([c])} for c in codes]
        members = [m for m in members if any(m["ytd"].values())]
        if members:
            members.sort(key=lambda r: (-r["ytd"]["net"], -r["ytd"]["req"]))
            groups.append({"brand": brand, **vals(codes), "rows": members})
    months = [today[:7]] + [p["value"] for p in periods(snap)[1:] if p["value"] != today[:7]]
    return {"day": day, "month": month, "days": days, "months": [{"value": m, "label": m} for m in months], "cats": cats, "cat_list": categories(snap),
            "groups": groups, "total": vals(cust.index.tolist())}


# ---------------------------------------------------------------- مقایسه
# بُعد مقایسه ← ستون سطرها؛ «نماینده» = کد مشتری (هر برند یک نماینده کد جدا دارد)
COMPARE_DIMS = {"customer": "code", "brand": "brand", "province": "province", "cat1": "cat1", "cat2": "cat2", "product": "product_code"}
COMPARE_MAX = 8


def _cmp_kpis(d: pd.DataFrame) -> dict:
    """شاخص‌های یک مورد در یک بازه؛ d سطرهای فاکتور، برگشتی و درخواست همان بازه است. تعداد = MajorUnitQuantity."""
    s, r, q = d[d["kind"].eq("S")], d[d["kind"].eq("R")], d[d["kind"].eq("Q")]
    qty, net, gross, cash = (float(s[k].sum()) for k in ("qty", "net", "gross", "cash"))
    inv = int(s.drop_duplicates(["code", "date"]).shape[0])
    req_qty, ret_qty = float(q["qty"].sum()), float(r["qty"].sum())
    return {"qty": qty, "net": net, "gross": gross, "cash": cash, "net_cash": net + cash, "invoices": inv,
            "days": int(s["date"].nunique()), "customers": int(s.loc[s["net"] > 0, "code"].nunique()),
            "skus": int(s.loc[s["qty"] > 0, "product_code"].nunique()),
            "avg_price": net / qty if qty else None, "qty_per_invoice": qty / inv if inv else None,
            "req_qty": req_qty, "req_gross": float(q["gross"].sum()), "fill": qty / req_qty if req_qty else None,
            "ret_qty": ret_qty, "ret_net": float(r["net"].sum()), "ret_rate": ret_qty / qty if qty else None,
            "first_date": s["date"].min() if len(s) else None, "last_date": s["date"].max() if len(s) else None}


def _cmp_daily(d: pd.DataFrame) -> dict:
    """تعداد، خالص و فاکتور فروش هر روز: {تاریخ: [qty, net, inv]}"""
    s = d[d["kind"].eq("S")]
    if not len(s):
        return {}
    g = s.groupby("date").agg(qty=("qty", "sum"), net=("net", "sum"))
    g["inv"] = s.drop_duplicates(["code", "date"]).groupby("date").size()
    return {k: [float(v.qty), float(v.net), int(v.inv)] for k, v in g.fillna(0).iterrows()}


def _cmp_labels(snap: dict, col: str, keys) -> dict:
    """برچسب و توضیح هر مورد بُعد"""
    keys = list(keys)
    if col == "code":
        info = snap["customers"].set_index("code")
        return {k: ({"label": info.at[k, "short"], "sub": f"{info.at[k, 'brand']} · {info.at[k, 'city'] or info.at[k, 'province']} · کد {k}"}
                    if k in info.index else {"label": k, "sub": ""}) for k in keys}
    if col == "product_code":
        p = snap["lines"].drop_duplicates("product_code", keep="last").set_index("product_code")
        return {k: ({"label": p.at[k, "product"], "sub": f"کد {k} · {p.at[k, 'cat2']}"} if k in p.index else {"label": k, "sub": ""})
                for k in keys}
    return {k: {"label": k, "sub": ""} for k in keys}


def compare(snap: dict, dim: str, items: list[str], a: tuple[str, str], b: tuple[str, str] | None,
            bd: str, scope: dict[str, list[str]]) -> dict:
    """مقایسه چند مورد از یک بُعد (نماینده، برند، استان، گروه کالا، زیرگروه یا کالا) در بازه a و در صورت انتخاب بازه b؛
    scope فیلترهای محدوده (برند، استان، گروه کالا) روی همه سطرهاست. بدون مورد انتخابی، items خالی است (پیش‌فرضی انتخاب نمی‌شود)."""
    dim = dim if dim in COMPARE_DIMS else "customer"
    col = COMPARE_DIMS[dim]
    bd = bd if bd in COMPARE_DIMS and COMPARE_DIMS[bd] != col else ("cat2" if col != "cat2" else "product")
    bcol = COMPARE_DIMS[bd]
    df = snap["lines"]
    df = df.assign(province=df["province"].map({p: norm(p) for p in df["province"].unique()}))
    keep = pd.Series(True, index=df.index)
    for k, vals in scope.items():
        if vals and k in COMPARE_DIMS:
            keep &= df[COMPARE_DIMS[k]].isin(vals)
    df = df[keep]
    in_a = df["date"].between(*a)
    in_b = df["date"].between(*b) if b else pd.Series(False, index=df.index)
    sa = df[in_a & df["kind"].eq("S")]
    ranking = sa.groupby(col)["qty"].sum()
    ranking = ranking[ranking > 0].sort_values(ascending=False)
    # فهرست انتخاب: همه موردهای بُعد، پرفروش‌ترها (تعدادی در بازه a) اول
    if col == "code":
        pool = snap["customers"]["code"].tolist()
    else:
        pool = df[col].dropna().unique().tolist()
    pool = sorted(set(pool), key=lambda k: (-ranking.get(k, 0.0), str(k)))
    labels = _cmp_labels(snap, col, pool)
    options = [{"value": k, "label": labels[k]["label"], "group": labels[k]["sub"], "qty": float(ranking.get(k, 0.0))} for k in pool]
    items = [i for i in dict.fromkeys(items) if i in labels][:COMPARE_MAX]
    rank = {k: i + 1 for i, k in enumerate(ranking.index)}
    out = []
    for it in items:
        d = df[df[col].eq(it)]
        out.append({"key": it, **labels.get(it, {"label": it, "sub": ""}), "rank": rank.get(it),
                    "a": _cmp_kpis(d[in_a]), "b": _cmp_kpis(d[in_b]) if b else None, "daily": _cmp_daily(d[in_a | in_b])})
    # تفکیک: تعداد و خالص هر مورد در هر سطر بُعد تفکیک (بازه a) و تعداد بازه b
    sel = df[df[col].isin(items) & df["kind"].eq("S")]
    pa = sel[in_a].groupby([bcol, col]).agg(qty=("qty", "sum"), net=("net", "sum"))
    pb = sel[in_b].groupby([bcol, col])["qty"].sum() if b else pd.Series(dtype=float)
    keys = sorted(set(pa.index.get_level_values(0)) | set(pb.index.get_level_values(0) if len(pb) else []))
    blabels = _cmp_labels(snap, bcol, keys)
    rows = []
    for k in keys:
        row = {"key": k, **blabels[k], "qty": {}, "net": {}, "bqty": {}}
        for it in items:
            if (k, it) in pa.index:
                row["qty"][it], row["net"][it] = float(pa.at[(k, it), "qty"]), float(pa.at[(k, it), "net"])
            if (k, it) in pb.index:
                row["bqty"][it] = float(pb.at[(k, it)])
        rows.append(row)
    rows.sort(key=lambda r: -sum(r["qty"].values()))
    days = df.loc[df["kind"].isin(["S", "Q"]), "date"].unique().tolist()
    return {"dim": dim, "bd": bd, "a": list(a), "b": list(b) if b else None, "items": out, "options": options,
            "ranked": int(len(ranking)), "scope_a": _cmp_kpis(df[in_a]), "scope_b": _cmp_kpis(df[in_b]) if b else None,
            "breakdown": rows, "dates": sorted(days),
            "scope_lists": {"brand": brand_order(snap), "province": sorted(snap["customers"]["province"].map(norm).unique().tolist()),
                            "cat1": categories(snap)}}
