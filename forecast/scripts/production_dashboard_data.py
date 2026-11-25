"""Build the small, publishable datasets consumed by the production dashboard."""
import json
import os
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from production_plan_io import production_quantities

TEHRAN = ZoneInfo("Asia/Tehran")
CHANNELS = ("hybrid", "b2b")
HORIZONS = (1, 3, 6, 12)
STORE_CODES = ("1", "2", "3", "4")
FLAGS = ("missing_inventory_record", "missing_product_status", "missing_safety_history")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
        try:
            json.dump(value, out, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        except BaseException:
            out.close()
            Path(out.name).unlink(missing_ok=True)
            raise
    try:
        os.replace(out.name, path)
    finally:
        Path(out.name).unlink(missing_ok=True)


def records(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False, double_precision=12))


def read(source, name, **kwargs):
    return pd.read_csv(source / name, encoding="utf-8-sig", **kwargs)


def inventory(source):
    factory = read(source, "rk_factory_stock.csv", dtype={"code": str, "store": str})
    factory = factory.loc[factory.store.isin(STORE_CODES), ["code", "store", "qty"]]
    branches = read(source, "kdb_branch_stock.csv", dtype={"code": str}, usecols=["code", "branch", "qty"])
    return factory, branches


def publish_plan(model, source, root, closed_month, inventory_at, *, model_at=None):
    model = pd.read_csv(model, dtype={"code": str}, index_col="code")
    if not model.index.is_unique:
        raise ValueError("Duplicate product codes in the forecast")
    months = sorted(key.removeprefix("hybrid_") for key in model if key.startswith("hybrid_") and "/" in key)
    if len(months) != 3 or not all(f"b2b_{month}" in model for month in months):
        raise ValueError("Incomplete production forecast horizon")
    goods = read(source, "kdb_goods.csv", dtype={"code": str}).drop_duplicates("code").set_index("code")
    factory, branches = inventory(source)
    factories = factory.groupby("code").qty.sum()
    branch_stock = branches.groupby("code").qty.sum()
    keep = [f"{ch}_{field}" for ch in CHANNELS for field in ("class", "model", "rmse", "3m", *months)]
    plan = model[keep].copy()
    # Keep stock-only codes in inventory, and give them no production recommendation.
    plan = plan.reindex(plan.index.union(factories.index).union(branch_stock.index)).rename_axis("code")
    is_forecast = plan.index.isin(model.index)
    safety_class = plan[[f"{ch}_class" for ch in CHANNELS]].isin(("A", "B")).any(axis=1)
    plan["missing_safety_history"] = safety_class & np.logical_or.reduce([
        plan[f"{ch}_class"].notna() & plan[f"{ch}_rmse"].isna() for ch in CHANNELS
    ])
    plan = production_quantities(plan, CHANNELS, goods, factories, branch_stock)
    plan["has_forecast"] = plan.index.isin(model.index)
    plan.loc[~plan.has_forecast, "production_need"] = 0
    plan["missing_inventory_record"] = ~plan.index.isin(factories.index.union(branch_stock.index))
    plan["missing_product_status"] = goods.active.reindex(plan.index).isna()
    for ch in CHANNELS:
        for month in months:
            plan[f"{ch}_{month}"] = plan[f"{ch}_{month}"].fillna(0)
    for horizon in HORIZONS:
        plan[f"safety_{horizon}"] = plan.safety * np.sqrt(horizon / 3)
    missing_names = plan.name.eq("")
    plan.loc[missing_names, "name"] = model.name.reindex(plan.index).loc[missing_names].fillna("")
    plan["category"] = goods.category.reindex(plan.index).fillna("")
    plan["review"] = plan[list(FLAGS)].any(axis=1)
    published = datetime.now(TEHRAN).isoformat(timespec="seconds")
    totals = {key: float(plan[key].sum()) for key in [
        "hybrid_3m", "b2b_3m", "demand_3m", "production_need", "factory_stock_1_4", "branch_stock",
        *(f"safety_{h}" for h in HORIZONS),
    ]}
    assert np.isfinite(list(totals.values())).all()
    stock_factory = factory.groupby(["code", "store"], as_index=False).qty.sum()
    stock_branch = branches.groupby(["code", "branch"], as_index=False).qty.sum()
    factory_details = {k: records(v[["store", "qty"]]) for k, v in stock_factory.groupby("code")}
    branch_details = {k: records(v[["branch", "qty"]]) for k, v in stock_branch.groupby("code")}
    write_json(root / "plan.json", {
        "overview": {
            "closed_month": closed_month, "months": months, "model_at": model_at or published,
            "model_file": model_file_name(closed_month), "inventory_at": inventory_at, "published_at": published,
            "totals": totals, "sku_count": int(is_forecast.sum()), "inventory_skus": len(factories.index.union(branch_stock.index)),
            "production_skus": int(plan.production_need.gt(0).sum()),
            "review_skus": int((plan.production_need.gt(0) & plan.review).sum()),
            "monthly": [{"month": month, **{ch: float(plan[f"{ch}_{month}"].sum()) for ch in CHANNELS}} for month in months],
        },
        "products": records(plan.reset_index()),
        "factory_details": factory_details,
        "branch_details": branch_details,
    })


def model_file_name(closed_month):
    return "model_" + closed_month.replace("/", "-") + ".csv"


def historical_prices(directory):
    tables = [pd.read_csv(directory / name, dtype={"product_id": str})
              for name in ("torob_expanded_rival_price_history.csv", "torob_price_history.csv")]
    hist = pd.concat(tables, ignore_index=True).drop_duplicates(["product_id", "date"]).sort_values("date")
    hist = hist.loc[hist.seller_median_toman.gt(0)].copy()
    latest = hist.drop_duplicates("product_id", keep="last").rename(columns={"seller_median_toman": "price"})
    latest = latest.assign(source="Torob", channel="retail")
    comparable = hist.loc[hist.pack_size.gt(0) & hist.size_unit.eq(np.where(hist.category.eq("bleach powder"), "g", "ml"))].copy()
    comparable = comparable.loc[comparable.category.ne("hair color") | comparable.pack_size.eq(100)]
    comparable["per100"] = 100 * comparable.seller_median_toman / comparable.pack_size
    per_product = comparable.groupby(["pmonth", "category", "company", "product_id"], as_index=False).per100.median()
    trend = per_product.groupby(["pmonth", "category", "company"], as_index=False).per100.agg(
        per100="median", samples="size")
    wholesale = pd.read_csv(directory / "wholesale_marketplace_offers.csv")
    wholesale = wholesale.rename(columns={"snapshot_date": "date", "unit_price_toman": "price", "unit_size_ml_or_g": "pack_size"})
    wholesale = wholesale.loc[wholesale.price.gt(0)].assign(channel="wholesale", size_unit=None)
    columns = ["company", "brand", "category", "title", "source", "source_url", "date", "pmonth", "price", "pack_size", "size_unit", "channel"]
    return {
        "retail_history": records(trend),
        "products": records(pd.concat([latest[columns], wholesale[columns]], ignore_index=True)),
        "torob_observations": len(hist),
        "torob_last_date": str(hist.date.max()),
    }


def live_listings(path, sources):
    raw = pd.read_csv(path, encoding="utf-8-sig")
    catalog = pd.read_csv(sources, encoding="utf-8-sig").set_index("source").url
    raw = raw.loc[raw.unit_price.gt(0) & raw.date.eq(raw.date.max())].copy()
    if raw.empty:
        raise ValueError("No current offers received")
    raw["source_url"] = raw.source.map(catalog)
    raw = raw.rename(columns={"unit_price": "price", "size_ml": "pack_size"})
    raw["size_unit"] = np.where(raw.category.eq("bleach powder"), "g", "ml")
    columns = ["company", "brand", "category", "title", "source", "source_url", "date", "pmonth", "price", "pack_size", "size_unit", "channel"]
    return records(raw[columns].drop_duplicates())


def external(usd_path, promo_path=None):
    usd = pd.read_csv(usd_path, encoding="utf-8-sig").sort_values("date")
    usd = usd.loc[usd.close.gt(0)].copy()
    usd["month"] = usd.pdate.str[:7].str.replace("-", "/", regex=False)
    trend = usd.groupby("month", as_index=False).close.mean().tail(12)
    last = usd.iloc[-1]
    campaign = []
    if promo_path and promo_path.is_file():
        rules = pd.read_csv(promo_path, encoding="utf-8-sig", dtype=str)
        campaign = records(rules.loc[rules.campaign_month.notna()].groupby("campaign_month", as_index=False).size())
    return {"usd": {"rial": float(last.close), "date": str(last.date), "trend": records(trend),
                    "source": "https://www.tgju.org/profile/price_dollar_rl"}, "campaign_months": campaign}
