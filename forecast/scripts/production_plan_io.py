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
    fields = [f"{ch}_{value}" for ch in channels for value in ("3m", "rmse")]
    plan = plan.fillna({key: 0 for key in fields})
    plan["factory_stock_1_4"] = factory_stock.reindex(plan.index).fillna(0)
    plan["branch_stock"] = branch_stock.reindex(plan.index).fillna(0)
    plan["demand_3m"] = plan[[f"{ch}_3m" for ch in channels]].sum(axis=1)
    classes = plan[[f"{ch}_class" for ch in channels]]
    z = np.select([classes.eq("A").any(axis=1), classes.eq("B").any(axis=1)], [1.645, 1.282], default=0)
    plan["safety"] = z * np.sqrt(plan[[f"{ch}_rmse" for ch in channels]].pow(2).sum(axis=1)) * np.sqrt(3)
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
