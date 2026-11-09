"""پیشنهاد ثبت سفارش نمایندگان B2B (هر فرد-برند = یک کد مشتری راهکاران)؛ فقط SELECT.

ایده: هر نماینده ریتم خرید خودش را دارد. از سابقه‌اش می‌فهمیم «معمولاً هر چند روز یک بار سفارش می‌دهد» (چرخه)،
بعد نگاه می‌کنیم از آخرین سفارشش چند روز گذشته. نسبت این دو وضعیت را می‌گوید:
  گذشته ÷ چرخه  < ۰٫۵ ← پوشش دارد | ۰٫۵ تا ۰٫۸ ← نزدیک سفارش | ۰٫۸ تا ۲ ← نیاز به سفارش | بیشتر ← معوق (در خطر ریزش)
  بیش از LOST_DAYS روز بی‌سفارش ← ریزش‌کرده.
آزمون روی گذشته (۲۷ برش ماهانه ۱۴۰۳/۰۶ تا ۱۴۰۵/۰۷، سفارش در ۳۰ روز بعد): پوشش دارد ۲۱٪، نزدیک ۳۱٪، نیاز ۳۳٪،
  معوق ۱۵٪. چرخه بهتر از «پوشش موجودی = مبلغ آخرین سفارش ÷ نرخ فروش» پیش‌بینی کرد (AUC ۰٫۶۳ در برابر ۰٫۵۴).
جزئیات:
  سفارش = درخواست فروش راهکاران (SLS3.SaleRequest، به‌جز باطل‌شده‌ها)؛ درخواست به‌طور میانه ۱۰ روز قبل از فاکتور است.
    کدی که درخواست ندارد، روزهای فاکتورش جای سفارش حساب می‌شود.
  درخواست‌های با فاصله کمتر از EPISODE_GAP روز یک سفارش‌اند (یک سفارش معمولاً چند درخواست پشت‌سرهم است).
  فروردین (تعطیلی نوروز و بستن سال) در هیچ سالی سفارش ندارد؛ روزهایش در شمارش فاصله‌ها حساب نمی‌شود.
  چرخه = میانه فاصله آخرین CYCLE_GAPS سفارش؛ برای کد کمتر از MIN_ORDERS سفارش، میانه چرخه هم‌برندها جایش می‌نشیند.
  درخواست تأییدشده یا در جریان (وضعیت ۲ و ۸) در PENDING_DAYS روز اخیر که هنوز فاکتور نشده ← «سفارش در جریان».
  مبلغ پیشنهادی = میانه مبلغ ۳ سفارش آخر (ناخالص درخواست).
"""
from __future__ import annotations

import datetime as dt
import statistics

import pandas as pd

import rahkaran as RK
import rahkaran_sales as RS
import sql_source

SINCE = "1400/10/01"  # آغاز داده B2B در راهکاران
EPISODE_GAP = 21
CYCLE_GAPS = 8
MIN_ORDERS = 4
PENDING_DAYS = 30
LOST_DAYS = 365
VOID_STATES = "6"  # باطل
OPEN_STATES = (2, 8)
LEVELS = [(0.5, "covered"), (0.8, "soon"), (2.0, "due")]  # بیشتر از آخری ← overdue
STATUS_FA = {"pending": "سفارش در جریان", "covered": "پوشش دارد", "soon": "نزدیک سفارش",
             "due": "نیاز به سفارش", "overdue": "معوق", "lost": "ریزش‌کرده", "none": "بدون سابقه"}

DAYS_SQL = """
SELECT 'S' AS k, c.Number AS code, CAST(i.Date AS date) AS d, 0 AS st, SUM(ii.Price) AS gross, SUM(ii.NetPrice) AS net
FROM SLS3.InvoiceItem ii JOIN SLS3.Invoice i ON i.InvoiceID = ii.InvoiceRef JOIN SLS3.Customer c ON c.CustomerID = i.CustomerRef
WHERE i.Date >= ? AND i.Status IN ({st}) AND c.Number IN ({codes}) GROUP BY c.Number, CAST(i.Date AS date)
UNION ALL
SELECT 'Q', c.Number, CAST(q.Date AS date), q.State, SUM(qi.Price), SUM(qi.NetPrice)
FROM SLS3.SaleRequestItem qi JOIN SLS3.SaleRequest q ON q.SaleRequestID = qi.SaleRequestRef JOIN SLS3.Customer c ON c.CustomerID = q.CustomerRef
WHERE q.Date >= ? AND q.State NOT IN ({void}) AND c.Number IN ({codes}) GROUP BY c.Number, CAST(q.Date AS date), q.State"""


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
        df = RK._read(cn, DAYS_SQL.format(st=RS.STATUSES, void=VOID_STATES, codes=codes), [since] * 2)
        today = RK._read(cn, "SELECT CAST(GETDATE() AS date) AS d", [])["d"].iloc[0]
    finally:
        cn.close()
    return {"days": prepare(df), "customers": cust.reset_index(), "today": pd.Timestamp(today).date()}


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["code"] = df["code"].astype(str).str.strip()
    df["d"] = pd.to_datetime(df["d"]).dt.date
    df["st"] = pd.to_numeric(df["st"], errors="coerce").fillna(0).astype(int)
    for k in ("gross", "net"):
        df[k] = pd.to_numeric(df[k], errors="coerce").fillna(0.0)
    return df


# ---------------------------------------------------------------- الگوریتم
def episodes(days: list[tuple[dt.date, float]]) -> list[tuple[dt.date, float]]:
    """روزهای سفارشِ نزدیک به هم ← یک سفارش (تاریخ اولین روز، جمع مبلغ)"""
    out: list[list] = []
    for d, amt in sorted(days):
        if out and (d - out[-1][2]).days <= EPISODE_GAP:
            out[-1][1] += amt
            out[-1][2] = d
        else:
            out.append([d, amt, d])
    return [(a, b) for a, b, _ in out]


def _orders(g: pd.DataFrame) -> list[tuple[dt.date, float]]:
    q = g[g["k"] == "Q"]
    src = q if len(q) else g[g["k"] == "S"]
    return episodes(list(zip(src["d"], src["gross"])))


def _level(ratio: float) -> str:
    for lim, name in LEVELS:
        if ratio < lim:
            return name
    return "overdue"


def analyze(days: pd.DataFrame, cust: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """یک سطر برای هر کد مشتری فهرست B2B؛ فقط داده قبل از today دیده می‌شود (برای آزمون روی گذشته هم)"""
    days = days[days["d"] < today]
    by = dict(tuple(days.groupby("code")))
    rows = []
    for c in cust.itertuples():
        g = by.get(c.code)
        r = {"code": c.code, "short": c.short, "name": c.name, "brand": c.brand, "province": c.province, "orders": 0}
        if g is None or g.empty:
            rows.append({**r, "status": "none"})
            continue
        eps = _orders(g)
        gaps = [work_days(a[0], b[0]) for a, b in zip(eps, eps[1:])][-CYCLE_GAPS:]
        last = eps[-1][0]
        s = g[g["k"] == "S"]
        y1 = s[s["d"] >= today - dt.timedelta(days=365)]
        q = g[(g["k"] == "Q") & g["st"].isin(OPEN_STATES) & (g["d"] >= today - dt.timedelta(days=PENDING_DAYS))]
        pending = bool(len(q)) and not (s["d"] >= q["d"].min()).any()
        r.update(status=None, orders=len(eps), last_order=last, elapsed=work_days(last, today),
                 own_cycle=statistics.median(gaps) if gaps else None,
                 last_amount=eps[-1][1], typical_amount=statistics.median(a for _, a in eps[-3:]),
                 sales_12m=float(y1["net"].sum()), last_invoice=s["d"].max() if len(s) else None, pending=pending)
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
        cycle = peer.get(r["brand"], overall) if few or not r.get("own_cycle") else r["own_cycle"]
        cycle = max(float(cycle), 7.0)
        ratio = r["elapsed"] / cycle
        status = ("lost" if r["elapsed"] > LOST_DAYS else "pending" if r.get("pending") or r["elapsed"] <= EPISODE_GAP
                  else _level(ratio))
        nxt = add_work_days(r["last_order"], round(cycle))
        out.append({**r, "status": status, "cycle": round(cycle), "ratio": round(ratio, 2), "few": few,
                    "next_order": nxt, "days_left": work_days(today, nxt) if nxt > today else -work_days(nxt, today)})
    return pd.DataFrame(out)


STATUS_ORDER = ["due", "overdue", "soon", "pending", "covered", "lost", "none"]


def report(snap: dict, brand: str | None = None, province: str | None = None) -> dict:
    df = analyze(snap["days"], snap["customers"], snap["today"])
    if brand:
        df = df[df["brand"] == brand]
    if province:
        df = df[df["province"] == province]
    df = df.assign(rank=df["status"].map(STATUS_ORDER.index)).sort_values(["rank", "ratio", "sales_12m"], ascending=[True, False, False])
    for k in ("last_order", "next_order", "last_invoice"):
        if k in df:
            df[k] = df[k].map(lambda d: to_jalali(d) if isinstance(d, dt.date) else None)
    df["status_fa"] = df["status"].map(STATUS_FA)
    counts = df["status"].value_counts().reindex(STATUS_ORDER, fill_value=0)
    return {"rows": df.drop(columns=["rank"]), "counts": [{"status": k, "label": STATUS_FA[k], "n": int(v)} for k, v in counts.items()],
            "today": to_jalali(snap["today"]), "since": SINCE,
            "brands": sorted(snap["customers"]["brand"].dropna().unique().tolist()),
            "provinces": sorted(snap["customers"]["province"].dropna().unique().tolist()),
            "params": {"levels": LEVELS, "episode_gap": EPISODE_GAP, "min_orders": MIN_ORDERS, "pending_days": PENDING_DAYS}}


def backtest(snap: dict, months: list[str], horizon: int = 30) -> pd.DataFrame:
    """برای هر تاریخ برش (اول ماه جلالی): وضعیت با داده قبل از آن، و اینکه آیا ظرف horizon روز کاری بعد سفارش آمد"""
    days, cust = snap["days"], snap["customers"]
    eps = {c: [d for d, _ in _orders(g)] for c, g in days.groupby("code")}
    out = []
    for m in months:
        cut = _greg(f"{m}/01")
        end = add_work_days(cut, horizon)
        a = analyze(days, cust, cut)
        a = a[~a["status"].isin(["none", "lost"])]
        a["ordered"] = a["code"].map(lambda c: any(cut <= d < end for d in eps.get(c, [])))
        a["cut"] = m
        out.append(a[["cut", "code", "brand", "status", "ratio", "few", "ordered"]])
    return pd.concat(out)
