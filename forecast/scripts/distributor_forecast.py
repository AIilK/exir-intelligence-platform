"""Build Top-N parent-distributor x brand B2B forecasts and SKU baskets."""
import re
from pathlib import Path

import jdatetime
import numpy as np
import pandas as pd

from channel_rules import channel_of, normalize
from production_dashboard_data import load_goods, read

MANUAL_EXCLUDE = {
    "1396/02", "1396/03", "1396/04", "1397/01", "1398/01", "1399/01", "1401/01",
    "1403/01", "1404/10", "1404/11", "1404/12", "1405/01",
}


def mon(label: str) -> int:
    return int(label[:4]) * 12 + int(label[5:]) - 1


def plabel(idx: int) -> str:
    y, m = divmod(int(idx), 12)
    return f"{y:04d}/{m + 1:02d}"


def parent_name(raw_name: str) -> str:
    """Collapse split brand/city Rahkaran customer accounts to their parent distributor."""
    s = normalize(raw_name)
    s = re.sub(r"^[\s.\-]+", "", s)
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\s*-\s*[^-]+$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .-")
    return s or normalize(raw_name)


def _pm_series(dates: pd.Series) -> pd.Series:
    uniq = {d: jdatetime.date.fromgregorian(date=pd.Timestamp(d).date()) for d in pd.unique(dates)}
    return dates.map(lambda d: uniq[d].year * 12 + uniq[d].month - 1)


def _finite(val, default=0.0):
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    return f if np.isfinite(f) else default


def build_distributor_forecast(
    source: Path, months: list[str], closed_month: str, top_n: int = 30, *, goods_source: Path | None = None
) -> dict:
    """Aggregate finished-goods B2B sales to Top-N parent distributors and forecast each brand."""
    g_dir = goods_source or source
    kdb_goods = read(g_dir, "kdb_goods.csv", dtype={"code": str}).drop_duplicates("code").set_index("code")
    goods = load_goods(g_dir)
    prod_path = source / "rk_production_daily.csv"
    prod_codes = set(pd.read_csv(prod_path, dtype={"code": str})["code"]) if prod_path.is_file() else set()
    finished = set(kdb_goods.index) | prod_codes

    inv = pd.read_csv(source / "rk_invoices_daily.csv", dtype={"code": str})
    ret_path = source / "rk_returns_daily.csv"
    if ret_path.is_file():
        ret = pd.read_csv(ret_path, dtype={"code": str})
        ret = ret[ret["status"] == 11].copy()
        ret["qty"] = -ret["qty"]
        df = pd.concat([inv, ret], ignore_index=True)
    else:
        df = inv.copy()

    df = df.loc[df["code"].isin(finished)].copy()
    df["cust_n"] = df["cust"].map(normalize)
    df = df.loc[df["cust_n"].map(channel_of) == "b2b"].copy()
    df["mi"] = _pm_series(df["d"])
    closed_mi = mon(closed_month)
    df = df.loc[df["mi"] <= closed_mi].copy()
    df["parent"] = df["cust_n"].map(parent_name)
    brand_map = goods["brand"].fillna("").astype(str).str.strip().to_dict()
    df["brand"] = df["code"].map(lambda c: brand_map.get(c) or "سایر")

    if df.empty:
        return {
            "closed_month": closed_month,
            "months": list(months),
            "top_n": top_n,
            "summary": {
                "unique_parents": 0, "top20_share": 0.0, "top30_share": 0.0,
                "row_count": 0, "overdue_count": 0, "due_soon_count": 0, "total_baseline_forecast": 0.0,
            },
            "rows": [],
        }

    mi_24 = closed_mi - 23
    mi_12 = closed_mi - 11
    mi_3 = closed_mi - 2

    df24 = df.loc[df["mi"] >= mi_24]
    parent_tot24 = df24.groupby("parent")["qty"].sum().clip(lower=0).sort_values(ascending=False)
    tot24_sum = float(parent_tot24.sum()) or 1.0
    unique_parents = int((parent_tot24 > 0).sum())
    top_parents = list(parent_tot24.head(top_n).index)
    top20_share = float(parent_tot24.head(20).sum() / tot24_sum)
    top30_share = float(parent_tot24.head(30).sum() / tot24_sum)

    sub = df.loc[df["parent"].isin(top_parents)].copy()
    min_mi = int(sub["mi"].min())
    all_mis = np.arange(min_mi, closed_mi + 1)
    excl_mis = {mon(m) for m in MANUAL_EXCLUDE}
    valid_mask = np.array([m not in excl_mis for m in all_mis], dtype=bool)
    mod_idx = all_mis % 12
    target_mis = [mon(m) for m in months]

    monthly_pb = sub.groupby(["parent", "brand", "mi"])["qty"].sum().unstack(fill_value=0.0).reindex(columns=all_mis, fill_value=0.0)
    accounts_pb = sub.groupby(["parent", "brand"])["cust_n"].unique().to_dict()

    sub12 = sub.loc[sub["mi"] >= mi_12]
    sku12_pb = sub12.groupby(["parent", "brand", "code"])["qty"].sum()

    rows = []
    for (parent, brand), series in monthly_pb.iterrows():
        hist = np.clip(series.to_numpy(dtype=np.float64), 0.0, None)
        last_12m = float(hist[-12:].sum())
        if last_12m <= 0:
            continue
        last_3m = float(hist[-3:].sum())

        active_pos = np.flatnonzero(hist > 0)
        if len(active_pos):
            last_order_mi = int(all_mis[active_pos[-1]])
            last_order_month = plabel(last_order_mi)
            since = int(closed_mi - last_order_mi)
            gaps = np.diff(all_mis[active_pos])
            med_gap = float(np.median(gaps)) if len(gaps) else None
            due_ratio = min(since / max(med_gap, 1.0), 3.0) if med_gap else 0.0
        else:
            last_order_month = None
            since = 0
            med_gap = None
            due_ratio = 0.0

        status = "overdue" if due_ratio >= 1.1 else ("due_soon" if due_ratio >= 0.75 else "normal")

        # Shrunk 12-month seasonal factors over valid months
        vhist = hist[valid_mask]
        vmod = mod_idx[valid_mask]
        mean_all = float(np.mean(vhist)) if len(vhist) else 0.0
        season = np.ones(12, dtype=np.float64)
        if mean_all > 0:
            for m in range(12):
                mask_m = vmod == m
                cnt = int(mask_m.sum())
                sm = float(vhist[mask_m].sum()) if cnt else 0.0
                if cnt > 0:
                    season[m] = (sm + 2.0 * mean_all) / ((cnt + 2.0) * mean_all)
            season /= max(float(season.mean()), 1e-9)

        deseas = vhist / season[vmod] if len(vhist) else np.array([0.0])
        lvl12 = float(np.mean(deseas[-12:])) if len(deseas) else 0.0
        lvl3 = float(np.mean(deseas[-3:])) if len(deseas) else 0.0
        lvl = 0.5 * lvl3 + 0.5 * lvl12
        fc = {m_str: round(_finite(max(0.0, lvl * season[mi_val % 12])), 1) for m_str, mi_val in zip(months, target_mis)}

        # Trailing 12m SKU basket shares inside (parent, brand)
        basket_series = sku12_pb.loc[(parent, brand)] if (parent, brand) in sku12_pb.index else pd.Series(dtype=float)
        basket_pos = basket_series[basket_series > 0].sort_values(ascending=False)
        b_tot = float(basket_pos.sum())
        basket = (
            [{"code": str(code), "share": round(float(qty / b_tot), 6)} for code, qty in basket_pos.items()]
            if b_tot > 0 else []
        )

        rows.append({
            "key": f"{parent}||{brand}",
            "distributor": parent,
            "brand": brand,
            "accounts": sorted(str(x) for x in accounts_pb.get((parent, brand), [])),
            "last_12m": round(_finite(last_12m), 1),
            "last_3m": round(_finite(last_3m), 1),
            "last_order_month": last_order_month,
            "months_since_last": since,
            "median_gap": round(_finite(med_gap), 2) if med_gap is not None else None,
            "reorder_due_ratio": round(_finite(due_ratio), 2),
            "reorder_status": status,
            "forecast": fc,
            "total_forecast": round(_finite(sum(fc.values())), 1),
            "sku_basket": basket,
        })

    rows.sort(key=lambda r: (r["last_12m"], r["total_forecast"]), reverse=True)
    return {
        "closed_month": closed_month,
        "months": list(months),
        "top_n": top_n,
        "summary": {
            "unique_parents": unique_parents,
            "top20_share": round(_finite(top20_share), 4),
            "top30_share": round(_finite(top30_share), 4),
            "row_count": len(rows),
            "overdue_count": sum(1 for r in rows if r["reorder_status"] == "overdue"),
            "due_soon_count": sum(1 for r in rows if r["reorder_status"] == "due_soon"),
            "total_baseline_forecast": round(sum(r["total_forecast"] for r in rows), 1),
        },
        "rows": rows,
    }
