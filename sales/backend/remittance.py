"""حواله‌های فروش زنجیره‌ای و اینترنتی از راهکاران (SLS3.[Order]، همان فهرست «حواله فروش») و پیشنهاد تأیید هر کالا؛ فقط SELECT.

کانال هر حواله از نام مشتری راهکاران: «انبار پخش (برند) - زنجیره ای» ← شعبه «زنجیره ای» کارآمد،
«. فروش اینترنتی(برند)» ← شعبه «اینترنتی» کارآمد. موجودی و فروش همان شعبه در کارآمد معیار تصمیم است.
وضعیت حواله در راهکاران: ۱ ثبت‌شده، ۲ تأییدشده، ۳ در حال استفاده، ۴ بسته، ۵ معلق، ۶ باطل.

برای هر کالای حواله ثبت‌شده:
  مانده حواله      = مقدار حواله − خارج‌شده از انبار کارخانه
  موجود شعبه       = موجودی کارآمد (همه انبارهای خود شعبه) − درخواست باز؛ منفی = صفر
                     (حواله‌های دیگر و بار در راه حساب نمی‌شوند؛ تصمیم کاربر)
  جا برای ارسال    = سطح هدف کنترل موجودی همان شعبه (فروش پیش‌بینی‌شده تا سفارش بعدی + رسیدن بار + ذخیره) − موجود شعبه
  تأیید: مانده حواله ≤ جا برای ارسال + تلورانس (یک کارتن یا tolerance × سطح هدف، هر کدام بیشتر)
  تأیید با کاهش: جا هست ولی کمتر از حواله (مقدار پیشنهادی به کارتن گرد می‌شود)
  رد: موجودی شعبه برای این دوره کافی است، یا کالا راکد یا مازاد است
موجودی کارخانه در تصمیم نیست (تصمیم کاربر).
  بدون فروش ۹۰ روز اخیر در شعبه: موجودی صفر ← تأیید؛ موجودی دارد ← بررسی دستی
"""
from __future__ import annotations

import math
import warnings

import pandas as pd

import loader
import rahkaran as RK
import sql_source

CHANNELS = [
    {"key": "chain", "label": "زنجیره‌ای", "match": "زنجیره", "branch": "زنجیره ای"},
    {"key": "online", "label": "اینترنتی", "match": "فروش اینترنتی", "branch": "اینترنتی"},
]
STATE_LABEL = {1: "ثبت‌شده", 2: "تأییدشده", 3: "در حال استفاده"}
DEFAULTS = {
    "open_days": 60,      # حواله باز قدیمی‌تر از این تعداد روز حساب نمی‌شود
    "tolerance": 0.2,     # بیش از سطح هدف تا این نسبت (یا یک کارتن) هنوز «تأیید» است
}
VERDICT_LABEL = {"approve": "تأیید", "reduce": "تأیید با کاهش", "reject": "رد", "review": "بررسی دستی"}

# سطرهای حواله‌های باز زنجیره‌ای و اینترنتی؛ مانده = مقدار − خروج انبار (حواله ← مجوز خروج ← حواله انبار)
LINES_SQL = """
SELECT o.OrderID AS oid, o.Number AS number, CAST(o.Date AS date) AS d, o.State AS state, o.Description AS descr,
       c.Number AS cust_code, p.FullName AS cust, st.Code AS store, st.Name AS store_name,
       pt.Code AS code, pt.Name AS name, d.MajorUnitQuantity AS ordered, ISNULL(x.issued, 0) AS issued
FROM SLS3.[Order] o
JOIN SLS3.OrderItemProductDetail d ON d.OrderRef = o.OrderID
JOIN LGS3.Part pt ON pt.PartID = d.PartRef
JOIN SLS3.Customer c ON c.CustomerID = o.CustomerRef JOIN GNR3.Party p ON p.PartyID = c.PartyRef
LEFT JOIN LGS3.Store st ON st.StoreID = o.InventoryRef
OUTER APPLY (SELECT SUM(v.MajorUnitQuantity) AS issued
             FROM LGS3.IssuePermitItem ipi
             JOIN LGS3.InventoryVoucherItem v ON v.ReferenceRef = ipi.IssuePermitItemID AND v.PartRef = ipi.PartRef
             WHERE ipi.ReferenceRef = d.OrderItemProductDetailID) x
WHERE o.State IN (1, 2, 3) AND o.Date >= DATEADD(day, -?, CAST(GETDATE() AS date))
  AND (p.FullName LIKE N'%زنجیره%' OR p.FullName LIKE N'%فروش اینترنتی%')"""

def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("remittance") or {})}


def channel_of(cust: str) -> str | None:
    c = RK._norm(cust)
    for ch in CHANNELS:
        if ch["match"] in c:
            return ch["key"]
    return None


def _read(cn, sql, params):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return pd.read_sql(sql, cn, params=params)


def load(env_file, cfg: dict) -> dict:
    """حواله‌های باز زنجیره‌ای و اینترنتی."""
    s = settings(cfg)
    cn = sql_source.connect(sql_source.settings(sql_source.read_env(env_file), prefix=RK.ENV_PREFIX))
    try:
        cur = cn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur.close()
        lines = _read(cn, LINES_SQL, [int(s["open_days"])])
    finally:
        cn.close()
    lines["code"] = lines["code"].map(loader._clean_code)
    lines["store"] = lines["store"].map(loader._clean_code)
    for k in ("cust", "name", "store_name", "descr", "number", "cust_code"):
        lines[k] = lines[k].map(loader._clean_text)
    lines["d"] = pd.to_datetime(lines["d"]).dt.strftime("%Y-%m-%d")
    lines["state"] = pd.to_numeric(lines["state"], errors="coerce").fillna(0).astype(int)
    lines["rem"] = (pd.to_numeric(lines["ordered"], errors="coerce").fillna(0)
                    - pd.to_numeric(lines["issued"], errors="coerce").fillna(0)).clip(lower=0)
    lines["channel"] = lines["cust"].map(channel_of)
    return {"lines": lines, "settings": s}


def branch_frame(rows: pd.DataFrame | None, src: dict, sales: pd.DataFrame, branch: str, today: str) -> pd.DataFrame:
    """آمار هر کالای شعبه برای تصمیم. rows: خروجی کنترل موجودی (inventory.compute)؛ اگر محاسبه ممکن نبود
    (مثلاً سابقه کم)، ساده: میانگین فروش خالص ۳ ماه بسته اخیر و سطح هدف = فروش یک ماه."""
    if rows is not None:
        return rows.set_index("code")
    sb = sales[(sales["branch"] == branch) & ~sales["is_sample"]]
    cur = today[:7]
    last3 = sorted(m for m in sb["month"].unique() if m < cur)[-3:]
    mon = sb[sb["month"].isin(last3)].groupby("product_code", observed=True)["qty"].sum() / max(len(last3), 1)
    codes = sorted(set(src["stock"].index) | set(mon.index))
    g = src["goods"].reindex(codes)
    df = pd.DataFrame(index=pd.Index(codes, name="code"))
    df["product"] = g["name"]
    df["unity"] = pd.to_numeric(g["unity"], errors="coerce").fillna(1.0).clip(lower=1.0)
    df["stock"] = src["stock"].reindex(codes).fillna(0.0)
    df["open_req"] = 0.0
    df["fc_now"] = mon.reindex(codes).fillna(0.0).clip(lower=0)
    df["target"] = df["fc_now"]
    df["daily"] = df["fc_now"] / 30
    df["sold_90"] = df["fc_now"] * 3
    df["ytd"] = sb[sb["month"].str[:4] == cur[:4]].groupby("product_code", observed=True)["qty"].sum().reindex(codes).fillna(0.0)
    df["cur_month"] = sb[sb["month"] == cur].groupby("product_code", observed=True)["qty"].sum().reindex(codes).fillna(0.0)
    df["status"], df["abc"] = "nodata", "-"
    return df


def _carton(q: float, unity: float) -> float:
    """مقدار پیشنهادی: از نیم کارتن به بالا کارتن کامل، کمتر از آن به عدد."""
    if q <= 0:
        return 0.0
    if unity > 1 and q >= 0.5 * unity:
        return float(math.ceil(q / unity - 1e-9) * unity)
    return float(math.ceil(q - 1e-9))


def evaluate(snap: dict, frames: dict, states: list[int]) -> dict:
    """frames: کلید کانال ← آمار کالاهای شعبه کارآمد (branch_frame)."""
    s = snap["settings"]
    tol = float(s["tolerance"])
    lines = snap["lines"].copy()
    show = lines[lines["channel"].notna() & lines["state"].isin(states) & (lines["rem"] > 0)]
    out_lines = [_decide(r, frames.get(r.channel), tol) for r in show.itertuples()]
    res = pd.DataFrame(out_lines)
    orders = []
    if len(res):
        for oid, g in res.groupby("oid", sort=False):
            v = set(g["verdict"])
            verdict = ("approve" if v == {"approve"} else "reject" if v == {"reject"}
                       else "review" if "review" in v and v <= {"review", "approve"} else "reduce")
            h = g.iloc[0]
            orders.append({"oid": int(oid), "number": h["number"], "d": h["d"], "state": int(h["state"]),
                           "state_label": STATE_LABEL.get(int(h["state"]), ""), "channel": h["channel"],
                           "cust": h["cust"], "cust_code": h["cust_code"], "store": h["store"], "store_name": h["store_name"],
                           "descr": h["descr"], "verdict": verdict, "lines": len(g), "qty": float(g["qty"].sum()),
                           "suggested": float(g["suggested"].sum()),
                           "counts": {k: int((g["verdict"] == k).sum()) for k in VERDICT_LABEL}})
        orders.sort(key=lambda o: (o["state"] == 1, o["d"], o["oid"]), reverse=True)  # ثبت‌شده‌ها اول، تازه‌ترین بالا
    return {"orders": orders, "lines": res, "settings": s}


def _decide(r, kb: pd.DataFrame | None, tol: float) -> dict:
    base = {"oid": r.oid, "number": r.number, "d": r.d, "state": r.state, "channel": r.channel, "cust": r.cust,
            "cust_code": r.cust_code, "store": r.store, "store_name": r.store_name, "descr": r.descr,
            "code": r.code, "product": r.name, "qty": float(r.rem), "ordered": float(r.ordered), "issued": float(r.issued)}
    k = kb.loc[r.code] if kb is not None and r.code in kb.index else None
    unity = float(k["unity"]) if k is not None else 1.0
    stock = float(k["stock"]) if k is not None else 0.0
    open_req = float(k["open_req"]) if k is not None else 0.0
    monthly = float(k["fc_now"]) if k is not None and pd.notna(k["fc_now"]) else 0.0
    target = float(k["target"]) if k is not None and pd.notna(k["target"]) else 0.0
    daily = float(k["daily"]) if k is not None and pd.notna(k["daily"]) else 0.0
    sold_90 = float(k["sold_90"]) if k is not None and pd.notna(k["sold_90"]) else 0.0
    ytd = float(k["ytd"]) if k is not None and pd.notna(k["ytd"]) else 0.0  # فروش خالص از ابتدای سال جاری
    status = k["status"] if k is not None else "nodata"
    avail = max(stock - open_req, 0.0)
    room = target - avail
    qty = float(r.rem)
    allow = max(unity, tol * target)
    cover = lambda q: (q / daily) if daily > 0 else None
    why = []
    if k is not None and k["product"] and isinstance(k["product"], str):
        base["product"] = base["product"] or k["product"]
    if monthly <= 0 and sold_90 <= 0 and stock <= 0:
        verdict, sug = "approve", qty
        why.append("در کارآمد این شعبه در ۹۰ روز اخیر فروشی ثبت نشده و موجودی صفر است؛ تأیید (تصمیم کاربر).")
    elif monthly <= 0 and sold_90 <= 0:
        verdict, sug = "review", qty
        why.append(f"در کارآمد این شعبه در ۹۰ روز اخیر فروشی ثبت نشده ولی {stock:,.0f} عدد موجودی دارد؛ تصمیم با کارشناس فروش.")
    elif status in ("dead", "excess"):
        verdict, sug = "reject", 0.0
        why.append(f"کالا در این شعبه {'راکد' if status == 'dead' else 'مازاد'} است؛ موجودی {stock:,.0f} عدد.")
    elif room <= 0:
        verdict, sug = "reject", 0.0
        why.append(f"موجودی شعبه {stock:,.0f} عدد، بیش از سطح هدف {target:,.0f} (فروش ماهانه پیش‌بینی‌شده {monthly:,.0f}) است.")
    elif qty <= room + allow:
        verdict, sug = "approve", qty
        why.append(f"جا برای {room:,.0f} عدد تا سطح هدف {target:,.0f} (فروش ماهانه پیش‌بینی‌شده {monthly:,.0f}).")
    else:
        sug = _carton(room, unity)
        verdict = "reduce"
        why.append(f"حواله {qty:,.0f} عدد ولی تا سطح هدف {target:,.0f} فقط {room:,.0f} عدد جا هست.")
    return {**base, "unity": unity, "stock": stock, "open_req": open_req, "monthly": monthly, "target": target,
            "sold_90": sold_90, "ytd": ytd, "status": status, "room": room, "suggested": float(sug), "verdict": verdict,
            "cover_now": cover(avail), "cover_after": cover(avail + sug), "why": " ".join(why)}
