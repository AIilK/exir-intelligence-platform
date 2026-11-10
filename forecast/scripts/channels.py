"""Sales per channel (Hybrid / B2B / Export) with the company's own counting rules, plus price and inflation inputs.

Rules (they reproduced the company's figures within 3-20 units):
  Hybrid  = net branch sales in KDB (sales minus returns)                -> forecast_lab.Y
  B2B     = Rahkaran invoices (all statuses) to domestic non-branch customers, minus returns with Status 11
  Export  = same for foreign customers (export list + country names in the customer name)
  Dropped = own branches (هیبرید/زنجیره/اینترنت: internal moves), gifts (اهدایی), raw-material buyers (مواد)
Price inputs
  company price index = chained, quantity-weighted monthly change of KDB list prices (gross / qty) per product
  official inflation  = point-to-point CPI figures reported in the news for 1404 (context for the LLM only)
"""
from pathlib import Path

import jdatetime
import numpy as np
import pandas as pd

import forecast_lab as F

ROOT = F.ROOT
EXPORT_LIST = ROOT / "sales" / "data" / "rahkaran" / "export_customers.csv"
COUNTRY = ["عراق", "بغداد", "اربیل", "سلیمانیه", "افغانستان", "هرات", "کابل", "مزار", "ارمنستان", "یروان", "ایروان",
           "تاجکستان", "آذربایجان", "باکو", "روسیه", "سنگال", "ترکیه", "عمان", "امارات", "دبی", "قطر", "کویت",
           "ترکمنستان", "ازبکستان", "گرجستان"]
OFFICIAL_INFLATION = {  # point-to-point household CPI inflation, as reported in the news (SCI / CBI)
    "1404/04": 41.2, "1404/05": 42.4, "1404/06": 45.3, "1404/07": 48.6, "1404/08": 49.4,
    "1404/10": 60.0, "1404/11": 68.1, "1404/12": 71.8}

norm = lambda s: str(s).replace("ي", "ی").replace("ك", "ک").strip()
_export_names = set(map(norm, pd.read_csv(EXPORT_LIST, encoding="utf-8-sig")["name"]))


def channel_of(name):
    c = norm(name)
    if any(k in c for k in ("هیبرید", "زنجیره", "اینترنت")):
        return "own"
    if "اهدایی" in c or "مواد" in c:
        return "drop"
    if c in _export_names or any(k in c for k in COUNTRY):
        return "export"
    return "b2b"


def _pm_index(dates):
    u = {d: jdatetime.date.fromgregorian(date=pd.Timestamp(d).date()) for d in pd.unique(dates)}
    return dates.map(lambda d: u[d].year * 12 + u[d].month - 1)


def rahkaran_channels():
    """dict channel -> (Y matrix T x n with NaN for unknown/excluded months, codes)."""
    prod_codes = set(pd.read_csv(F.DATA / "rk_production_daily.csv", dtype={"code": str})["code"])
    finished = set(F.goods.index) | prod_codes
    inv = pd.read_csv(F.DATA / "rk_invoices_daily.csv", dtype={"code": str})
    ret = pd.read_csv(F.DATA / "rk_returns_daily.csv", dtype={"code": str})
    ret = ret[ret["status"] == 11].copy()
    ret["qty"] = -ret["qty"]
    both = pd.concat([inv, ret], ignore_index=True)
    both = both[both["code"].isin(finished)]
    both["ch"] = both["cust"].map(channel_of)
    both["mi"] = _pm_index(both["d"])
    first = int(inv.assign(mi=_pm_index(inv["d"]))["mi"].min())
    out = {}
    for ch in ("b2b", "export"):
        sub = both[both["ch"] == ch]
        P = sub.pivot_table(index="mi", columns="code", values="qty", aggfunc="sum").reindex(F.idx).fillna(0.0)
        codes = sorted(P.columns)
        Y = P[codes].to_numpy(copy=True)
        Y[F.idx < first] = np.nan
        Y[~F.valid_row] = np.nan
        out[ch] = (Y, codes)
    return out, first


def company_price_index():
    """monthly company price index from KDB list prices; returns dict of per-row series."""
    disc = pd.read_csv(F.DATA / "kdb_discount_monthly.csv", dtype={"code": str})
    disc["mi"] = disc["pm"].map(F.mon)
    disc = disc[(disc["qty"] > 0) & (disc["gross"] > 0)]
    P = (disc.pivot_table(index="mi", columns="code", values="gross", aggfunc="sum") /
         disc.pivot_table(index="mi", columns="code", values="qty", aggfunc="sum")).reindex(F.idx)
    Q = disc.pivot_table(index="mi", columns="code", values="qty", aggfunc="sum").reindex(F.idx).fillna(0)
    ratio = (P / P.shift(1)).clip(0.5, 3.0)
    lr = np.log(ratio)
    w = Q.where(lr.notna(), 0)
    link = np.exp((lr.fillna(0) * w).sum(1) / w.sum(1).replace(0, np.nan)).fillna(1.0)
    index = link.cumprod().values
    s = pd.Series(index)
    return {"index": index,
            "mom": (link.values - 1),
            "q3": (s / s.shift(3) - 1).fillna(0).values,
            "yoy": (s / s.shift(12) - 1).fillna(0).values}


def product_price_features(codes):
    """discount rate and recent list-price change per product (KDB prices), aligned to `codes`."""
    disc = pd.read_csv(F.DATA / "kdb_discount_monthly.csv", dtype={"code": str})
    disc["mi"] = disc["pm"].map(F.mon)
    pv = lambda col: disc.pivot_table(index="mi", columns="code", values=col, aggfunc="sum").reindex(F.idx).reindex(columns=codes)
    g, d, q = pv("gross"), pv("discount"), pv("qty")
    price = g / q.replace(0, np.nan)
    pch = (price / price.shift(1).rolling(3, min_periods=1).mean() - 1).clip(-1, 3)
    return (d / g.replace(0, np.nan)).values, pch.values


PI = company_price_index()
RK, RK_FIRST = rahkaran_channels()

if __name__ == "__main__":
    F.log("channels:", {k: (v[0].shape, int(np.nansum(v[0]))) for k, v in RK.items()}, "| first Rahkaran month:", F.plabel(RK_FIRST))
    yy = {F.plabel(i)[:4]: round(float(PI["yoy"][F.R(i)]) * 100, 1) for i in F.idx if F.plabel(i).endswith("/12")}
    F.log("company price index, change over 12 months at each Esfand (%):", yy)
