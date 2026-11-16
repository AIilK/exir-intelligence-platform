"""پیشنهاد ثبت سفارش نمایندگان B2B (هر فرد-برند = یک کد مشتری راهکاران)؛ فقط SELECT.

ایده: هر نماینده ریتم سفارش‌گذاری خودش را دارد. از سابقه‌اش می‌فهمیم «معمولاً هر چند روز یک بار درخواست می‌دهد» (چرخه)،
بعد نگاه می‌کنیم از آخرین درخواستش چند روز گذشته. نسبت این دو وضعیت را می‌گوید:
  گذشته ÷ چرخه  < ۰٫۵ ← پوشش دارد | ۰٫۵ تا ۰٫۸ ← نزدیک سفارش | ۰٫۸ تا ۲ ← نیاز به سفارش | بیشتر ← معوق (در خطر ریزش)
  بیش از LOST_DAYS روز بی‌سفارش ← ریزش‌کرده.
سفارش = هر درخواست فروش راهکاران (SLS3.SaleRequest، به‌جز باطل‌شده‌ها)؛ درخواست‌های هم‌روز یک سفارش‌اند.
  چرخه = میانه فاصله روزهای آخرین CYCLE_GAPS+1 درخواست؛ برای کد کمتر از MIN_ORDERS درخواست، میانه چرخه هم‌برندها جایش
  می‌نشیند. کدی که درخواست ندارد، روزهای فاکتورش (گروه‌های INVOICE_GAP روزه) جای درخواست حساب می‌شود.
  بار هر درخواست در یک یا چند فاکتور می‌رسد (درخواست ← پیش‌فاکتور ← سفارش ← تحویل انبار ← فاکتور). درخواستی که بارش هنوز
  کامل نرسیده ← «سفارش در جریان» (ریتمش با بقیه قابل مقایسه نیست): کامل = FULL_FILL از تعدادش فاکتور شده، یا بخشی فاکتور
  شده و QUIET_DAYS روز فاکتور تازه نیامده؛ درخواستی که NO_INVOICE_DAYS روز هیچ فاکتوری نگرفته کنار می‌رود.
فروردین (تعطیلی نوروز و بستن سال) در شمارش فاصله‌ها حساب نمی‌شود.
آزمون روی گذشته (۲۳ برش ماهانه ۱۴۰۳/۰۹ تا ۱۴۰۵/۰۷، درخواست تازه در ۳۰ روز کاری بعد): نیاز+نزدیک ÷ پوشش دارد = ۱٫۳۹
  (بازه ۹۰٪: ۱٫۱۰ تا ۱٫۸۳)؛ چرخه از رسیدن بار تا رسیدن بار ۱٫۲۱، منطق قدیمی ۱٫۰۷. بدون جدا کردن «در جریان» این عدد پایین می‌آید.
"""
from __future__ import annotations

import datetime as dt
import statistics

import pandas as pd

import rahkaran as RK
import rahkaran_sales as RS
import sql_source

SINCE = "1400/10/01"  # آغاز داده B2B در راهکاران
INVOICE_GAP = 21  # فقط برای کد بدون درخواست: روزهای فاکتور تا این فاصله از اولین روز = یک سفارش
FULL_FILL = 0.9
QUIET_DAYS = 45
NO_INVOICE_DAYS = 60
CYCLE_GAPS = 8
MIN_ORDERS = 4
LOST_DAYS = 365
VOID_STATES = "6"  # باطل
LEVELS = [(0.5, "covered"), (0.8, "soon"), (2.0, "due")]  # بیشتر از آخری ← overdue
STATUS_FA = {"pending": "سفارش در جریان", "covered": "پوشش دارد", "soon": "نزدیک سفارش",
             "due": "نیاز به سفارش", "overdue": "معوق", "lost": "ریزش‌کرده", "none": "بدون سابقه"}

# روزهای فاکتور هر کد (فروش ۱۲ ماه، آخرین فاکتور و جایگزین سفارش برای کد بدون درخواست)
INVOICE_DAYS_SQL = """
SELECT c.Number AS code, CAST(i.Date AS date) AS d, SUM(ii.NetPrice) AS net
FROM SLS3.InvoiceItem ii JOIN SLS3.Invoice i ON i.InvoiceID = ii.InvoiceRef JOIN SLS3.Customer c ON c.CustomerID = i.CustomerRef
WHERE i.Date >= ? AND i.Status IN ({st}) AND c.Number IN ({codes}) GROUP BY c.Number, CAST(i.Date AS date)"""

REQUESTS_SQL = """
SELECT q.SaleRequestID AS rid, c.Number AS code, CAST(q.Date AS date) AS d, SUM(qi.MajorUnitQuantity) AS qty
FROM SLS3.SaleRequestItem qi JOIN SLS3.SaleRequest q ON q.SaleRequestID = qi.SaleRequestRef JOIN SLS3.Customer c ON c.CustomerID = q.CustomerRef
WHERE q.Date >= ? AND q.State NOT IN ({void}) AND c.Number IN ({codes}) GROUP BY q.SaleRequestID, c.Number, CAST(q.Date AS date)"""

# تعداد فاکتورشده هر درخواست در هر روز: ردیف فاکتور ← مجوز صدور فاکتور ← تحویل انبار ← ردیف سفارش ← پیش‌فاکتور ← درخواست
FILLS_SQL = """
SELECT ri.SaleRequestRef AS rid, CAST(i.Date AS date) AS d, SUM(ii.MajorUnitQuantity) AS qty
FROM SLS3.InvoiceItem ii JOIN SLS3.Invoice i ON i.InvoiceID = ii.InvoiceRef JOIN SLS3.Customer c ON c.CustomerID = i.CustomerRef
JOIN SLS3.ProductInvoicePermit pp ON pp.ProductInvoicePermitID = ii.ReferenceRef
CROSS APPLY (SELECT TOP 1 r.value('.', 'bigint') AS pref FROM pp.RreferenceRefs.nodes('/ReferenceRefs/Ref') t(r)) x
JOIN SLS3.PartInvoicePermit pa ON pa.PartInvoicePermitID = x.pref AND pa.ProductSourceType = 1057
JOIN SLS3.OrderItem oi ON oi.OrderItemID = pa.ProductSourceRef AND oi.ProductRef = ii.ProductRef
JOIN SLS3.QuotationItem qu ON qu.QuotationItemID = oi.ReferenceRef AND qu.ProductRef = oi.ProductRef
JOIN SLS3.SaleRequestItem ri ON ri.SaleRequestItemID = qu.ReferenceRef AND ri.ProductRef = qu.ProductRef
WHERE i.Date >= ? AND i.Status IN ({st}) AND c.Number IN ({codes})
GROUP BY ri.SaleRequestRef, CAST(i.Date AS date)"""


# ---------------------------------------------------------------- تاریخ
def to_jalali(d: dt.date) -> str:
    gy, gm, gd = d.year, d.month, d.day
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
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def _greg(j: str) -> dt.date:
    return dt.date.fromisoformat(RS.to_gregorian(j))


_FARV: dict[int, tuple[dt.date, dt.date]] = {}


def _farvardin(gy: int) -> tuple[dt.date, dt.date]:
    """بازه فروردین سالی که در سال میلادی gy شروع می‌شود [آغاز، پایان)"""
    if gy not in _FARV:
        start = _greg(f"{gy - 621}/01/01")
        _FARV[gy] = (start, _greg(f"{gy - 621}/02/01"))
    return _FARV[gy]


def work_days(a: dt.date, b: dt.date) -> int:
    """روزهای از a تا b بدون روزهای فروردین"""
    if b <= a:
        return 0
    n = (b - a).days
    for y in range(a.year, b.year + 1):
        s, e = _farvardin(y)
        lo, hi = max(a, s), min(b, e)
        if hi > lo:
            n -= (hi - lo).days
    return n


def add_work_days(a: dt.date, n: int) -> dt.date:
    """a + n روز کاری (فروردین پریده می‌شود)"""
    d = a + dt.timedelta(days=n)
    while work_days(a, d) < n:
        d += dt.timedelta(days=n - work_days(a, d))
    s, e = _farvardin(d.year)
    return e if s <= d < e else d


# ---------------------------------------------------------------- داده
def load(env_file, cfg: dict) -> dict:
    cust = RS.customers()
    codes = ",".join(f"'{c}'" for c in cust.index if c.isdigit())
    since = RS.to_gregorian(SINCE)
    cn = sql_source.connect(sql_source.settings(sql_source.read_env(env_file), prefix=RK.ENV_PREFIX))
    try:
        cur = cn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur.close()
        inv = RK._read(cn, INVOICE_DAYS_SQL.format(st=RS.STATUSES, codes=codes), [since])
        req = RK._read(cn, REQUESTS_SQL.format(void=VOID_STATES, codes=codes), [since])
        fills = RK._read(cn, FILLS_SQL.format(st=RS.STATUSES, codes=codes), [since])
        today = RK._read(cn, "SELECT CAST(GETDATE() AS date) AS d", [])["d"].iloc[0]
    finally:
        cn.close()
    return {**prepare(inv, req, fills), "customers": cust.reset_index(), "today": pd.Timestamp(today).date()}


def prepare(inv: pd.DataFrame, req: pd.DataFrame, fills: pd.DataFrame) -> dict:
    inv, req, fills = inv.copy(), req.copy(), fills.copy()
    for df in (inv, req):
        df["code"] = df["code"].astype(str).str.strip()
    for df in (inv, req, fills):
        df["d"] = pd.to_datetime(df["d"]).dt.date
    inv["net"] = pd.to_numeric(inv["net"], errors="coerce").fillna(0.0)
    for df in (req, fills):
        df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
    return {"invoices": inv, "requests": req, "fills": fills}


# ---------------------------------------------------------------- الگوریتم
def requests_state(req: pd.DataFrame, fills: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """هر درخواست تا پیش از today: done = تاریخ انجام‌شدن (یا خالی)، open = بار در راه، left = تعداد فاکتورنشده"""
    r = req[req["d"] < today]
    f = fills[(fills["d"] < today) & fills["rid"].isin(r["rid"])].sort_values("d")
    f = f.merge(r[["rid", "qty"]].rename(columns={"qty": "want"}), on="rid")
    f["cum"] = f.groupby("rid")["qty"].cumsum()
    full = f[f["cum"] >= FULL_FILL * f["want"]].groupby("rid")["d"].min()
    last = f.groupby("rid")["d"].max()
    got = f.groupby("rid")["qty"].sum()
    r = r.assign(full=r["rid"].map(full), last=r["rid"].map(last), got=r["rid"].map(got).fillna(0.0))
    quiet = r["last"].map(lambda d: isinstance(d, dt.date) and (today - d).days > QUIET_DAYS)
    r["done"] = r["full"].where(r["full"].notna(), r["last"].where(quiet))
    young = r["d"].map(lambda d: (today - d).days <= NO_INVOICE_DAYS)
    r["open"] = r["done"].isna() & (r["last"].notna() | young)
    r["left"] = (r["qty"] - r["got"]).clip(lower=0)
    return r


def invoice_orders(days: list[dt.date]) -> list[dt.date]:
    """کد بدون درخواست: روزهای فاکتوری که تا INVOICE_GAP روز بعد از اولین روز آمده‌اند یک سفارش‌اند"""
    out: list[dt.date] = []
    for d in sorted(days):
        if not out or (d - out[-1]).days > INVOICE_GAP:
            out.append(d)
    return out


def _level(ratio: float) -> str:
    for lim, name in LEVELS:
        if ratio < lim:
            return name
    return "overdue"


def analyze(snap: dict, today: dt.date) -> pd.DataFrame:
    """یک سطر برای هر کد مشتری فهرست B2B؛ فقط داده قبل از today دیده می‌شود (برای آزمون روی گذشته هم)"""
    cust, inv = snap["customers"], snap["invoices"]
    inv = inv[inv["d"] < today]
    rs = requests_state(snap["requests"], snap["fills"], today)
    by_inv = dict(tuple(inv.groupby("code")))
    by_req = dict(tuple(rs.groupby("code")))
    rows = []
    for c in cust.itertuples():
        r = {"code": c.code, "short": c.short, "name": c.name, "brand": c.brand, "province": c.province, "orders": 0,
             "open_reqs": 0, "open_left": 0.0}
        g, q = by_inv.get(c.code), by_req.get(c.code)
        s_days = sorted(set(g["d"])) if g is not None else []
        if s_days:
            y1 = g[g["d"] >= today - dt.timedelta(days=365)]
            r.update(sales_12m=float(y1["net"].sum()), last_invoice=s_days[-1])
        if q is not None and len(q):
            eps = sorted(set(q["d"]))  # روزهای ثبت درخواست؛ درخواست‌های هم‌روز یک سفارش‌اند
            done = q["done"].dropna()
            op = q[q["open"]]
            r.update(last_arrival=max(done) if len(done) else None, open_reqs=int(len(op)),
                     open_left=float(op["left"].sum()))
        else:
            eps = invoice_orders(s_days)
        if not eps:
            rows.append({**r, "status": "none"})
            continue
        gaps = [work_days(a, b) for a, b in zip(eps, eps[1:])][-CYCLE_GAPS:]
        r.update(status=None, orders=len(eps), last_order=eps[-1], elapsed=work_days(eps[-1], today),
                 own_cycle=statistics.median(gaps) if gaps else None)
        rows.append(r)
    df = pd.DataFrame(rows)
    # هم‌برندهای پرسابقه ← چرخه جایگزین برای کم‌داده‌ها
    rich = df[df["orders"] >= MIN_ORDERS]
    peer = rich.groupby("brand")["own_cycle"].median().to_dict()
    overall = float(rich["own_cycle"].median()) if len(rich) else 60.0
    out = []
    for r in df.to_dict("records"):
        if r["status"] == "none":
            out.append({**r, "ratio": None, "few": True})
            continue
        few = r["orders"] < MIN_ORDERS
        own = r.get("own_cycle")
        cycle = max(float(peer.get(r["brand"], overall) if few or not own or own != own else own), 7.0)
        ratio = r["elapsed"] / cycle
        status = "pending" if r["open_reqs"] else "lost" if r["elapsed"] > LOST_DAYS else _level(ratio)
        nxt = add_work_days(r["last_order"], round(cycle))
        out.append({**r, "status": status, "cycle": round(cycle), "ratio": round(ratio, 2), "few": few,
                    "next_order": nxt, "days_left": work_days(today, nxt) if nxt > today else -work_days(nxt, today)})
    return pd.DataFrame(out)


STATUS_ORDER = ["due", "overdue", "soon", "pending", "covered", "lost", "none"]


def report(snap: dict, brand: str | None = None, province: str | None = None) -> dict:
    df = analyze(snap, snap["today"])
    if brand:
        df = df[df["brand"] == brand]
    if province:
        df = df[df["province"] == province]
    df = df.assign(rank=df["status"].map(STATUS_ORDER.index)).sort_values(["rank", "ratio", "sales_12m"], ascending=[True, False, False])
    for k in ("last_order", "next_order", "last_invoice", "last_arrival"):
        if k in df:
            df[k] = df[k].map(lambda d: to_jalali(d) if isinstance(d, dt.date) else None)
    df["status_fa"] = df["status"].map(STATUS_FA)
    counts = df["status"].value_counts().reindex(STATUS_ORDER, fill_value=0)
    return {"rows": df.drop(columns=["rank"]), "counts": [{"status": k, "label": STATUS_FA[k], "n": int(v)} for k, v in counts.items()],
            "today": to_jalali(snap["today"]), "since": SINCE,
            "brands": sorted(snap["customers"]["brand"].dropna().unique().tolist()),
            "provinces": sorted(snap["customers"]["province"].dropna().unique().tolist()),
            "params": {"levels": LEVELS, "full_fill": FULL_FILL, "quiet_days": QUIET_DAYS, "no_invoice_days": NO_INVOICE_DAYS,
                       "min_orders": MIN_ORDERS}}


def backtest(snap: dict, months: list[str], horizon: int = 30) -> pd.DataFrame:
    """برای هر تاریخ برش (اول ماه جلالی): وضعیت با داده قبل از آن، و اینکه آیا ظرف horizon روز کاری بعد درخواست تازه آمد"""
    reqs = {c: sorted(set(g["d"])) for c, g in snap["requests"].groupby("code")}
    out = []
    for m in months:
        cut = _greg(f"{m}/01")
        end = add_work_days(cut, horizon)
        a = analyze(snap, cut)
        a = a[~a["status"].isin(["none", "lost"])]
        a["ordered"] = a["code"].map(lambda c: any(cut <= d < end for d in reqs.get(c, [])))
        a["cut"] = m
        out.append(a[["cut", "code", "brand", "status", "ratio", "few", "ordered"]])
    return pd.concat(out)
