"""Final forecast and production plan, using the setup the lab kept (forecast/lab/final_config.json).

Steps
  1. model per ABC class = lowest error over all backtest months for the kept setup
  2. ML/DL retrained on all months up to 1405/07, forecasts for 1405/08..1405/11
  3. external customers (distributors, export) forecast from Rahkaran invoices with the statistical models,
     model chosen on early backtest months
  4. safety stock = empirical quantile of past 3-month forecast errors per class (A 95%, B 90%, C/N none)
  5. production need = max(0, branch demand 3m + max(external 3m, external open orders) + safety
                           - factory stock (stores 1-4) - branch stock); inactive products get 0
Output: forecast/forecast_output_final.xlsx and production_plan_final.csv
"""
import json

import numpy as np
import pandas as pd

import forecast_lab as F

cfgj = json.loads((F.LAB / "final_config.json").read_text(encoding="utf-8"))
cfg, pool = cfgj["cfg"], cfgj["pool"]
bt = dict(np.load(F.LAB / "final_backtest.npz"))
F.log("final setup:", {k: v for k, v in cfg.items() if k != "name"}, "| pool:", pool)

# 1) model per class on all backtest rows
choice, choice_rows = {}, []
for ci, cl in enumerate(F.CLASSES):
    mask = F.CLS_P == ci
    sc = {m: F.wape(bt[m], mask) for m in pool}
    choice[cl] = min(sc, key=lambda m: np.inf if np.isnan(sc[m][0]) else sc[m][0])
    for m in pool:
        choice_rows.append({"class": cl, "model": m, "WAPE_all_backtest": round(sc[m][0], 4),
                            "bias": round(sc[m][1], 4), "chosen": m == choice[cl]})
F.log("chosen per class:", choice)

# 2) final forecast from 1405/07
YH = F.history(cfg)
stat = F.StatModels(YH)
feats = F.Features(stat.D, cfg["features"])
learners = F.Learners(cfg, feats, F.mon(F.LAST_FULL))
p_last = F.R(F.mon(F.LAST_FULL))
tg = [F.mon(t) for t in F.FINAL_TARGETS]
fc = stat.forecast(p_last, tg)
fc.update(learners.forecast(p_last, tg))
fc = F.ensembles(fc)
cls_now = F.CLS[p_last]
final = np.zeros((len(tg), F.n))
for ci, cl in enumerate(F.CLASSES):
    m = cls_now == ci
    final[:, m] = fc[choice[cl]][:, m]
need_j = [j for j, t in enumerate(F.FINAL_TARGETS) if t in F.NEED_MONTHS]
dem3 = final[need_j].sum(axis=0)

# 4) safety stock from each product's own forecast error in the backtest:
#    RMSE of its monthly errors (chosen model) x sqrt(3) for a 3-month horizon x z for the service level.
#    (A class-wide empirical quantile was tried first: it was dominated by small products and tripled demand.)
Z_OF = {0.95: 1.645, 0.90: 1.282}
safety = np.zeros(F.n)
q_rows = []
for ci, cl in enumerate(F.CLASSES):
    q = F.SAFETY_Q[cl]
    if q is None:
        continue
    m_cls = cls_now == ci
    err = bt[choice[cl]] - F.ACT                     # (pairs, products) monthly errors
    rmse = np.sqrt(np.mean(err ** 2, axis=0))
    safety[m_cls] = Z_OF[q] * rmse[m_cls] * np.sqrt(3)
    q_rows.append({"class": cl, "service_level": q, "z": Z_OF[q], "products": int(m_cls.sum()),
                   "safety_units": round(float(safety[m_cls].sum())), "demand_3m": round(float(dem3[m_cls].sum())),
                   "safety_as_share_of_demand": round(float(safety[m_cls].sum() / max(dem3[m_cls].sum(), 1)), 3)})

# 3) external customers
inv = pd.read_csv(F.DATA / "rk_invoices_daily.csv", dtype={"code": str})
prod = pd.read_csv(F.DATA / "rk_production_daily.csv", dtype={"code": str}, parse_dates=["d"])
prod_codes = set(prod["code"].unique())
finished = set(F.goods.index) | prod_codes
inv = inv[inv["code"].isin(finished) & ~inv["cust"].astype(str).str.contains("هیبرید|زنجیره|اینترنت|مواد", regex=True)]
_jd = {d: F.jdatetime.date.fromgregorian(date=F.date.fromisoformat(d)) for d in inv["d"].unique()}
inv["mi"] = inv["d"].map(lambda d: _jd[d].year * 12 + _jd[d].month - 1)
ext_codes = sorted(inv["code"].unique())
first_ext = int(inv["mi"].min())
Ev = inv.pivot_table(index="mi", columns="code", values="qty", aggfunc="sum").reindex(F.idx).reindex(columns=ext_codes).fillna(0.0).to_numpy(copy=True)
Ev[F.idx < first_ext] = np.nan
Ev[~F.valid_row] = np.nan
tot = np.where(np.isnan(Ev).all(1), np.nan, np.nansum(Ev, 1))
rat = {m: [] for m in range(12)}
for yy in range(F.idx[0] // 12, F.idx[-1] // 12 + 1):
    rr = [F.R(i) for i in range(yy * 12, yy * 12 + 12) if F.i_start <= i <= F.i_last and not np.isnan(tot[F.R(i)])]
    if len(rr) >= 10:
        for r in rr:
            rat[F.idx[r] % 12].append(tot[r] / np.nanmean(tot[rr]))
S_ext = np.array([np.mean(rat[m]) if rat[m] else 1.0 for m in range(12)])
S_ext = S_ext / S_ext.mean()
est = F.StatModels(Ev, Sx=S_ext, brand=False)
EXT_POOL = ["WMA", "SES", "SBA", "TSB", "ADIDA", "SN", "MED_STAT"]
ext_err = {m: {"early": [0.0, 0.0, 0.0], "late": [0.0, 0.0, 0.0]} for m in EXT_POOL + ["NAIVE"]}
for o in F.ROLL:
    if o < first_ext + 12:
        continue
    t3 = [t for t in (o + 1, o + 2, o + 3) if t <= F.i_last and F.valid_row[F.R(t)]]
    if not t3:
        continue
    f = est.forecast(F.R(o), t3)
    f["MED_STAT"] = np.median(np.stack([f[m] for m in ["WMA", "SES", "SBA", "TSB", "ADIDA", "SN"]]), 0)
    half = "late" if F.plabel(o) > F.SPLIT else "early"
    for j, t in enumerate(t3):
        a = np.nan_to_num(Ev[F.R(t)])
        for m in ext_err:
            ext_err[m][half][0] += np.abs(f[m][j] - a).sum()
            ext_err[m][half][1] += a.sum()
            ext_err[m][half][2] += (f[m][j] - a).sum()
ext_bt = pd.DataFrame([{"model": m, "WAPE_early": round(v["early"][0] / v["early"][1], 4),
                        "WAPE_late": round(v["late"][0] / v["late"][1], 4),
                        "bias_late": round(v["late"][2] / v["late"][1], 4)} for m, v in ext_err.items()])
ext_best = ext_bt[ext_bt["model"] != "NAIVE"].sort_values("WAPE_early").iloc[0]["model"]
fe = est.forecast(p_last, tg)
fe["MED_STAT"] = np.median(np.stack([fe[m] for m in ["WMA", "SES", "SBA", "TSB", "ADIDA", "SN"]]), 0)
ext3 = dict(zip(ext_codes, fe[ext_best][need_j].sum(0)))
F.log("external model:", ext_best)

# 5) production need
bstock = pd.read_csv(F.DATA / "kdb_branch_stock.csv", dtype={"code": str}).groupby("code")["qty"].sum()
fs = pd.read_csv(F.DATA / "rk_factory_stock.csv", dtype={"code": str, "store": str})
fstock = fs[fs["store"].isin(F.FACTORY_STORES)].groupby("code")["qty"].sum()
oo = pd.read_csv(F.DATA / "rk_open_orders_lines.csv", dtype={"code": str})
oo["open_qty"] = oo["ordered"] - oo["issued"]
to_branch = oo["cust"].astype(str).str.contains("هیبرید|زنجیره|اینترنت", regex=True)
open_ext = oo[~to_branch].groupby("code")["open_qty"].sum()
open_br = oo[to_branch].groupby("code")["open_qty"].sum()
last12 = prod[prod["d"] >= pd.Timestamp("2025-11-09")].groupby("code")["qty"].sum()
g = lambda s, c: float(s.get(c, 0.0))
sold12 = np.nansum(F.Y[max(p_last - 11, 0):p_last + 1], 0)

ids = sorted(set(F.codes) | set(ext_codes) | set(fstock.index) | set(open_ext.index))
rows = []
cls_name = {i: c for i, c in enumerate(F.CLASSES)}
for c in ids:
    k = F.k_idx.get(c)
    cl = cls_name[int(cls_now[k])] if k is not None else "N"
    d3 = float(dem3[k]) if k is not None else 0.0
    sf = float(safety[k]) if k is not None else 0.0
    e3, oe = float(ext3.get(c, 0.0)), g(open_ext, c)
    fstk, bstk = g(fstock, c), g(bstock, c)
    inactive = c in F.goods.index and str(F.goods.loc[c, "active"]).lower() in ("false", "0")
    need = 0.0 if inactive else max(0.0, d3 + max(e3, oe) + sf - fstk - bstk)
    rows.append({
        "code": c, "name": F.goods.loc[c, "name"] if c in F.goods.index else "",
        "brand": F.goods.loc[c, "brand"] if c in F.goods.index else "",
        "category": F.goods.loc[c, "category"] if c in F.goods.index else "",
        "class": cl, "model": choice.get(cl, "") if k is not None else "",
        "sold_last12m": round(float(sold12[k]), 0) if k is not None else 0.0,
        **{f"forecast_{t}": round(float(final[j, k]), 0) if k is not None else 0.0 for j, t in enumerate(F.FINAL_TARGETS)},
        "branch_demand_3m": round(d3, 0), "external_demand_3m": round(e3, 0), "external_open_orders": round(oe, 0),
        "branch_open_orders": round(g(open_br, c), 0), "safety_stock": round(sf, 0),
        "factory_stock_stores_1_4": round(fstk, 0), "branch_stock": round(bstk, 0),
        "production_need": round(need, 0), "availability_1405/07": round(float(F.AV[p_last, k]), 2) if k is not None else None,
        "inactive_product": inactive, "produced_last12m": round(g(last12, c), 0),
        "in_kdb_goods": c in F.goods.index,
    })
plan = pd.DataFrame(rows)
plan["o"] = plan["class"].map({"A": 0, "B": 1, "C": 2, "N": 3})
plan = plan.sort_values(["o", "production_need"], ascending=[True, False]).drop(columns="o")
own = plan["in_kdb_goods"].astype(bool)
s = lambda df, col: round(float(df[col].sum()))
summary = pd.DataFrame([
    ("branch demand next 3 months (1405/09-11)", s(plan, "branch_demand_3m")),
    ("external customer demand next 3 months", s(plan, "external_demand_3m")),
    ("safety stock", s(plan, "safety_stock")),
    ("factory stock stores 1-4", s(plan, "factory_stock_stores_1_4")),
    ("branch stock", s(plan, "branch_stock")),
    ("PRODUCTION NEED total", s(plan, "production_need")),
    ("  of which own (KDB) products", s(plan[own], "production_need")),
    ("  of which Rahkaran-only codes", s(plan[~own], "production_need")),
    ("  of which from external demand only (need without external)", s(plan, "production_need") - round(float(
        np.maximum(0, plan["branch_demand_3m"] + plan["safety_stock"] - plan["factory_stock_stores_1_4"] - plan["branch_stock"]).where(~plan["inactive_product"].astype(bool), 0).sum()))),
    ("codes with production need > 0", int((plan["production_need"] > 0).sum())),
], columns=["item", "units"])

notes = pd.DataFrame({"note": [
    "Setup kept by the lab (decided on early backtest months only): " + ", ".join(f"{k}={v}" for k, v in cfgj["decisions"].items()),
    "Model per class (lowest error over all backtest months): " + ", ".join(f"{k}={v}" for k, v in choice.items()),
    f"External customers forecast with {ext_best}; their accuracy is low (see External backtest).",
    "Safety stock = z x product's backtest RMSE x sqrt(3); A 95% (z 1.645), B 90% (z 1.282), C and N none.",
    "Production need = max(0, branch demand 3m + max(external 3m, external open orders) + safety - factory stock 1-4 - branch stock).",
    "Factory-to-branch open orders are internal moves and are not added. Inactive products get 0.",
    "Excluded months (internet outage and broken data): " + ", ".join(F.plabel(i) for i in sorted(F.excluded) if i >= F.i_start),
]})
with pd.ExcelWriter(F.ROOT / "forecast" / "forecast_output_final.xlsx") as xw:
    summary.to_excel(xw, sheet_name="Summary", index=False)
    plan.to_excel(xw, sheet_name="Production plan", index=False)
    pd.DataFrame(choice_rows).to_excel(xw, sheet_name="Model choice", index=False)
    pd.DataFrame(q_rows).to_excel(xw, sheet_name="Safety quantiles", index=False)
    ext_bt.to_excel(xw, sheet_name="External backtest", index=False)
    notes.to_excel(xw, sheet_name="Notes", index=False)
plan.to_csv(F.ROOT / "forecast" / "production_plan_final.csv", index=False, encoding="utf-8-sig")
print(summary.to_string(index=False))
print(pd.DataFrame(q_rows).to_string(index=False))
print(ext_bt.to_string(index=False))
