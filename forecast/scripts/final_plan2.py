"""Production plan per channel (Hybrid, B2B, Export) with the company's counting rules.

Per channel: model per ABC class from the channel lab (choice_<ch>.json); for A/B products the LLM or the
LLM hybrid replaces it where llm_eval.py found it better on both early and late months.
Safety stock (A 95%, B 90%) = z x product's backtest RMSE in that channel x sqrt(3).
Production need = max(0, sum over channels of max(3-month forecast, open orders of that channel) + safety
                  - factory stock (stores 1-4) - branch stock); inactive products get 0.
Output: forecast/forecast_output_channels.xlsx, production_plan_channels.csv
"""
import json

import numpy as np
import pandas as pd

import channels as C
import llm_forecaster as LF

F = C.F
Z = {"A": 1.645, "B": 1.282}
CH = ("hybrid", "b2b", "export")
need_j = [j for j, t in enumerate(F.FINAL_TARGETS) if t in F.NEED_MONTHS]
llm = json.loads(LF.OUT.read_text(encoding="utf-8")) if LF.OUT.exists() else {}
llm_dec = json.loads((F.LAB / "llm_decision.json").read_text(encoding="utf-8")) if (F.LAB / "llm_decision.json").exists() else {}

per = {}
for ch in CH:
    fz = np.load(F.LAB / f"final_{ch}.npz", allow_pickle=True)
    bz = np.load(F.LAB / f"backtest_{ch}.npz")
    codes = [str(c) for c in fz["codes"]]
    cls_now = fz["CLS_NOW"]
    choice = json.loads((F.LAB / f"choice_{ch}.json").read_text(encoding="utf-8"))["chosen"]
    fc = np.zeros((len(F.FINAL_TARGETS), len(codes)))
    model_name = np.empty(len(codes), dtype=object)
    for ci, cl in enumerate(F.CLASSES):
        m = cls_now == ci
        fc[:, m] = fz[choice[cl]][:, m]
        model_name[m] = choice[cl]
    dec = llm_dec.get(ch, "none")
    if dec != "none":
        lf = llm.get(ch, {}).get(LF.FINAL_ORIGIN, {})
        for k, c in enumerate(codes):
            if F.CLASSES[cls_now[k]] in ("A", "B") and c in lf:
                v = np.array(lf[c][:len(F.FINAL_TARGETS)], float)
                if dec == "LLM":
                    fc[:, k] = v
                else:
                    fc[:, k] = np.median(np.stack([fz["WMA"][:, k], fz["SES"][:, k], fz["ML"][:, k], fz["DL"][:, k], v]), axis=0)
                model_name[k] = dec
    # safety from the chosen model's backtest error in this channel
    chosen_bt = np.zeros_like(bz["ACT"])
    for ci, cl in enumerate(F.CLASSES):
        chosen_bt = np.where(bz["CLS_P"] == ci, bz[choice[cl]], chosen_bt)
    rmse = np.sqrt(np.mean((chosen_bt - bz["ACT"]) ** 2, axis=0))
    per[ch] = pd.DataFrame({"code": codes, f"{ch}_class": [F.CLASSES[c] for c in cls_now], f"{ch}_model": model_name,
                            **{f"{ch}_{t}": np.round(fc[j], 0) for j, t in enumerate(F.FINAL_TARGETS)},
                            f"{ch}_3m": fc[need_j].sum(0), f"{ch}_rmse": rmse}).set_index("code")

plan = pd.concat(per.values(), axis=1)
oo = pd.read_csv(F.DATA / "rk_open_orders_lines.csv", dtype={"code": str})
oo["open_qty"] = oo["ordered"] - oo["issued"]
oo["ch"] = oo["cust"].map(C.channel_of)
for ch in ("b2b", "export"):
    plan[f"{ch}_open_orders"] = oo[oo["ch"] == ch].groupby("code")["open_qty"].sum().reindex(plan.index).fillna(0)
fs = pd.read_csv(F.DATA / "rk_factory_stock.csv", dtype={"code": str, "store": str})
plan["factory_stock_1_4"] = fs[fs["store"].isin(F.FACTORY_STORES)].groupby("code")["qty"].sum().reindex(plan.index).fillna(0)
plan["branch_stock"] = pd.read_csv(F.DATA / "kdb_branch_stock.csv", dtype={"code": str}).groupby("code")["qty"].sum().reindex(plan.index).fillna(0)
plan = plan.fillna({c: 0 for c in plan.columns if c.endswith(("_3m", "_rmse", "_open_orders"))})
plan["demand_3m"] = (plan["hybrid_3m"] + np.maximum(plan["b2b_3m"], plan["b2b_open_orders"])
                     + np.maximum(plan["export_3m"], plan["export_open_orders"]))
# safety: channel errors combined as sqrt of the sum of squares (they partly cancel); z from the best class in any channel
cls_cols = [f"{ch}_class" for ch in CH]
z = plan[cls_cols].apply(lambda r: 1.645 if "A" in r.values else (1.282 if "B" in r.values else 0.0), axis=1)
plan["safety"] = z * np.sqrt((plan[[f"{ch}_rmse" for ch in CH]] ** 2).sum(1)) * np.sqrt(3)
plan["inactive"] = [c in F.goods.index and str(F.goods.loc[c, "active"]).lower() in ("false", "0") for c in plan.index]
plan["production_need"] = np.where(plan["inactive"], 0,
                                   np.maximum(0, plan["demand_3m"] + plan["safety"] - plan["factory_stock_1_4"] - plan["branch_stock"])).round(0)
plan.insert(0, "name", [F.goods.loc[c, "name"] if c in F.goods.index else "" for c in plan.index])
plan.insert(1, "brand", [F.goods.loc[c, "brand"] if c in F.goods.index else "" for c in plan.index])
plan = plan.sort_values("production_need", ascending=False)
s = lambda c: round(float(plan[c].sum()))
summary = pd.DataFrame([
    ("Hybrid demand 3 months (1405/09-11)", s("hybrid_3m")), ("B2B demand 3 months", s("b2b_3m")),
    ("Export demand 3 months", s("export_3m")), ("B2B open orders", s("b2b_open_orders")),
    ("Export open orders", s("export_open_orders")), ("Total demand used (forecast or open orders, whichever is larger)", s("demand_3m")),
    ("Safety stock", s("safety")), ("Factory stock stores 1-4", s("factory_stock_1_4")), ("Branch stock", s("branch_stock")),
    ("PRODUCTION NEED", s("production_need")), ("Products with need > 0", int((plan["production_need"] > 0).sum())),
    ("LLM used for", ", ".join(f"{k}: {v}" for k, v in llm_dec.items()) or "not evaluated"),
], columns=["item", "value"])
with pd.ExcelWriter(F.ROOT / "forecast" / "forecast_output_channels.xlsx") as xw:
    summary.to_excel(xw, sheet_name="Summary", index=False)
    plan.reset_index().rename(columns={"index": "code"}).to_excel(xw, sheet_name="Production plan", index=False)
plan.to_csv(F.ROOT / "forecast" / "production_plan_channels.csv", encoding="utf-8-sig")
print(summary.to_string(index=False))
