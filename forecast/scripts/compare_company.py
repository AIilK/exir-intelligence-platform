"""Compare the company forecaster's method with ours on the same products and months.

Company method (from forcast14050818.xlsx, Forecast sheet), at the latest month O of the data:
  Forecast_Base = 0.5 x Avg_3M + 0.3 x Avg_6M + 0.2 x Avg_12M, same number for every future month
  windows are written on YYYYMM numbers: Avg_kM = average of months with YYYYMM between O-(k-1) and O.
  Across a year boundary this cuts the window short (e.g. O = 140506: O-11 = 140495 -> only 1405 months),
  so "Avg_12M" equals Avg_6M there. Replicated exactly ("company"), and also with true calendar windows
  ("company, fixed windows").
Sales = company total (Hybrid + B2B + Export, company rules), all months included (their file includes the
outage months). Evaluation on our backtest origins 1403/07..1405/06, horizons 1-3, normal target months only,
products in their Forecast sheet. Also: their actual file forecast (made at 1405/06) vs actual 1405/07.
Output: forecast/company_vs_ours.xlsx
"""
import json

import numpy as np
import openpyxl
import pandas as pd

import channels as C
import forecast_lab2 as L2

F = C.F
PATH = r"C:\Users\Part Laptop\Downloads\forcast14050818 - Copy.xlsx"

# ---- their products, classes and current forecast
wb = openpyxl.load_workbook(PATH, data_only=True, read_only=True)
fc = pd.DataFrame(list(wb["Forecast"].values))
fc.columns = fc.iloc[0]
fc = fc[1:].dropna(subset=["Product_Code"])
fc["code"] = fc["Product_Code"].map(lambda v: "".join(ch for ch in str(v) if ch.isdigit()))   # some codes carry hidden marks
fc = fc.drop_duplicates("code").set_index("code")
their_codes = list(fc.index)

# ---- company-total sales, all months (no exclusions), on a union code list
k = pd.read_csv(F.DATA / "kdb_sales_monthly.csv", dtype={"code": str})
k["mi"] = k["pm"].map(F.mon)
inv = pd.read_csv(F.DATA / "rk_invoices_daily.csv", dtype={"code": str})
ret = pd.read_csv(F.DATA / "rk_returns_daily.csv", dtype={"code": str})
ret = ret[ret["status"] == 11].assign(qty=lambda d: -d["qty"])
rk = pd.concat([inv, ret])
rk["ch"] = rk["cust"].map(C.channel_of)
rk = rk[rk["ch"].isin(["b2b", "export"])]
rk["mi"] = C._pm_index(rk["d"])
allc = pd.concat([k[["code", "mi", "net_qty"]].rename(columns={"net_qty": "qty"}), rk[["code", "mi", "qty"]]])
codes = sorted(set(allc["code"]) | set(their_codes))
kix = {c: i for i, c in enumerate(codes)}
TOT = allc.pivot_table(index="mi", columns="code", values="qty", aggfunc="sum").reindex(F.idx).reindex(columns=codes).fillna(0).values
first_sale = np.argmax(TOT != 0, axis=0)          # row of first activity per product (rows exist from there on)

ym = (F.idx // 12) * 100 + (F.idx % 12) + 1      # YYYYMM code per row


def company_forecast(p, buggy=True):
    out = {}
    for kk in (3, 6, 12):
        if buggy:
            rows = np.where((ym >= ym[p] - (kk - 1)) & (ym <= ym[p]))[0]
        else:
            rows = np.arange(max(p - kk + 1, 0), p + 1)
        M = TOT[rows]
        exists = rows[:, None] >= first_sale[None, :]
        cnt = exists.sum(0)
        out[kk] = np.where(cnt > 0, (M * exists).sum(0) / np.maximum(cnt, 1), 0.0)
    return 0.5 * out[3] + 0.3 * out[6] + 0.2 * out[12]


# ---- our forecast per product = sum over channels of the chosen model per class
ref = np.load(F.LAB / "backtest_hybrid.npz")
ORIG, TARG = ref["ORIG"], ref["TARG"]
LATE = ref["LATE"]
OURS = np.zeros((len(ORIG), len(codes)))
for ch, ch_codes in (("hybrid", F.codes), ("b2b", C.RK["b2b"][1]), ("export", C.RK["export"][1])):
    z = np.load(F.LAB / f"backtest_{ch}.npz")
    assert (z["ORIG"] == ORIG).all() and (z["TARG"] == TARG).all()
    choice = json.loads((F.LAB / f"choice_{ch}.json").read_text(encoding="utf-8"))["chosen"]
    pick = np.zeros_like(z["ACT"])
    for ci, cl in enumerate(F.CLASSES):
        pick = np.where(z["CLS_P"] == ci, z[choice[cl]], pick)
    idx_map = np.array([kix[c] for c in ch_codes])
    OURS[:, idx_map] += pick

COMP = np.stack([company_forecast(F.R(o)) for o in ORIG])
COMP_FIX = np.stack([company_forecast(F.R(o), buggy=False) for o in ORIG])
ACT = np.clip(np.stack([TOT[F.R(t)] for t in TARG]), 0, None)
sel = np.array([c in fc.index for c in codes])
their_cls = np.array([fc.loc[c, "ABC_Class"] if c in fc.index else "" for c in codes])

rows = []
methods = {"company formula (as in the file)": COMP, "company formula, fixed windows": COMP_FIX, "our models": OURS}
for half, hm in (("all", np.ones(len(ORIG), bool)), ("early (1403/07-1404/06)", ~LATE), ("late (1404/07-1405/06)", LATE)):
    for cl in ["A", "B", "C", "ALL"]:
        pm = sel & ((their_cls == cl) if cl != "ALL" else True)
        mask = hm[:, None] & pm[None, :]
        for name, P in methods.items():
            r = L2.metrics(P, ACT, mask)
            # 3-month totals
            P3, A3, L3 = [], [], []
            for o in sorted(set(ORIG)):
                rr = np.where(ORIG == o)[0]
                if len(rr) == 3 and hm[rr[0]]:
                    P3.append(P[rr].sum(0)); A3.append(ACT[rr].sum(0))
            r3 = L2.metrics(np.array(P3), np.array(A3), np.broadcast_to(pm, (len(P3), len(codes)))) if P3 else {}
            rows.append({"period": half, "their class": cl, "method": name, "products": int(pm.sum()),
                         "monthly WAPE": round(r["WAPE"], 3), "monthly tolWAPE": round(r["tolWAPE"], 3),
                         "bias": round(r["bias"], 3), "3-month WAPE": round(r3.get("WAPE", np.nan), 3),
                         "3-month tolWAPE": round(r3.get("tolWAPE", np.nan), 3), "3-month bias": round(r3.get("bias", np.nan), 3)})
res = pd.DataFrame(rows)

# ---- their real file forecast (made at 1405/06) vs actual 1405/07, and ours from the same origin
t = F.R(F.mon("1405/07"))
act7 = np.clip(TOT[t], 0, None)
their7 = np.array([float(fc.loc[c, "Forecast_Base"] or 0) if c in fc.index else 0.0 for c in codes])
r_o = np.where((ORIG == F.mon("1405/06")) & (TARG == F.mon("1405/07")))[0]
ours7 = OURS[r_o[0]] if len(r_o) else np.zeros(len(codes))
real = []
for cl in ["A", "B", "C", "ALL"]:
    pm = sel & ((their_cls == cl) if cl != "ALL" else True)
    for name, P in (("company file (Forecast_Base)", their7), ("our models", ours7)):
        r = L2.metrics(P[None], act7[None], pm[None])
        real.append({"their class": cl, "method": name, "products": int(pm.sum()), "forecast total": round(float(P[pm].sum())),
                     "actual 1405/07": round(float(act7[pm].sum())), "WAPE": round(r["WAPE"], 3),
                     "tolWAPE": round(r["tolWAPE"], 3), "bias": round(r["bias"], 3)})
real = pd.DataFrame(real)
with pd.ExcelWriter(F.ROOT / "forecast" / "company_vs_ours.xlsx") as xw:
    res.to_excel(xw, sheet_name="Backtest comparison", index=False)
    real.to_excel(xw, sheet_name="Real file vs 1405-07", index=False)
pd.set_option("display.width", 220)
print(res[res["their class"] == "ALL"].to_string(index=False))
print()
print(res[(res["period"] == "late (1404/07-1405/06)")].to_string(index=False))
print()
print(real.to_string(index=False))
