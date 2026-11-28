"""Read a saved channel plan using forecast demand as the production basis."""
import numpy as np
import pandas as pd


CHANNEL_FORECASTS = ["hybrid_3m", "b2b_3m", "export_3m"]
LEGACY_ORDER_FIELDS = [
    "order_only", "order_only_status_missing", "order_only_stock_record_missing",
    "b2b_open_orders", "export_open_orders",
]


def production_quantities(plan, channels, goods, factory_stock, branch_stock):
    """Calculate production from channel demand, backtest error and inventory."""
    fields = [f"{ch}_3m" for ch in channels]
    plan = plan.fillna({key: 0 for key in fields})
    plan["factory_stock_1_4"] = factory_stock.reindex(plan.index).fillna(0)
    plan["branch_stock"] = branch_stock.reindex(plan.index).fillna(0)
    plan["demand_3m"] = plan[[f"{ch}_3m" for ch in channels]].sum(axis=1)
    classes = plan[[f"{ch}_class" for ch in channels]]
    z = np.select([classes.eq("A").any(axis=1), classes.eq("B").any(axis=1)], [1.645, 1.282], default=0)
    if "safety_calibrated_3m" in plan:
        # Stock-only rows have no forecast and require no buffer.
        buffer = plan.safety_calibrated_3m.where(classes.notna().any(axis=1), 0)
        if buffer.isna().any() or not np.isfinite(buffer).all() or buffer.lt(0).any():
            raise ValueError("Missing or invalid calibrated safety stock")
        plan["safety"] = buffer
    else:
        # Compatibility for old saved plans: missing SKU error uses a pool,
        # never a zero that implies evidence of perfect accuracy.
        errors = plan[[f"{ch}_rmse" for ch in channels]].copy()
        for ch in channels:
            key = f"{ch}_rmse"
            known = errors[key].where(errors[key].gt(0)).median()
            missing = errors[key].isna() & plan[f"{ch}_class"].notna() & (z > 0)
            if missing.any() and not np.isfinite(known):
                raise ValueError("No safety error history or calibration available")
            errors.loc[missing, key] = known
        horizon_months = len([k for k in plan.columns if k.startswith(f"{channels[0]}_") and "/" in k]) or 3
        plan["safety"] = z * np.sqrt(errors.fillna(0).pow(2).sum(axis=1)) * np.sqrt(horizon_months)
        plan["safety_method"] = "legacy_rmse_unvalidated"
    active = goods["active"].reindex(plan.index)
    plan["inactive"] = active.astype(str).str.lower().isin(("false", "0"))
    need = plan.demand_3m + plan.safety - plan.factory_stock_1_4 - plan.branch_stock
    plan["production_need"] = need.clip(lower=0).where(~plan.inactive, 0).round()
    plan.insert(0, "name", goods["name"].reindex(plan.index).fillna(""))
    plan.insert(1, "brand", goods["brand"].reindex(plan.index).fillna(""))
    return plan.sort_values("production_need", ascending=False)


def read_channel_plan(path):
    plan = pd.read_csv(path, converters={0: str}, index_col=0, encoding="utf-8-sig").rename_axis("code")
    if any(field in plan for field in LEGACY_ORDER_FIELDS):
        if "order_only" in plan:
            plan = plan.loc[~plan["order_only"].eq(True)]
        plan = plan.drop(columns=LEGACY_ORDER_FIELDS, errors="ignore")
        plan["demand_3m"] = plan[CHANNEL_FORECASTS].sum(axis=1)
        need = plan["demand_3m"] + plan["safety"] - plan["factory_stock_1_4"] - plan["branch_stock"]
        plan["production_need"] = need.clip(lower=0).where(~plan["inactive"], 0).round()
    return plan
