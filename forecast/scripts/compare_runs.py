"""Compare baseline and improved backtests on identical rows (same origin, target month, product, model).

Scores: WAPE (sum |forecast - actual| / sum actual) and bias, per ABC class.
Row sets:
  all        every rolling-backtest row (origins 1403/07..1405/06, horizons 1-3)
  late       origins after 1404/06 (the period the improved run used to choose models)
  in_stock   rows whose target month had at least 70% branch availability (stockouts would
             make the actual sales lower than real demand)
Output: forecast/comparison.xlsx
"""
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "forecast" / "data"
HERE = pathlib.Path(__file__).resolve().parent

base = pd.read_csv(DATA / "backtest_rows_baseline.csv", dtype={"code": str})
imp = pd.read_csv(DATA / "backtest_rows_improved.csv", dtype={"code": str})
keys = ["origin", "target", "code", "model"]
both = base.merge(imp[keys + ["pred"]], on=keys, suffixes=("_base", "_imp"))

# availability per product and month (same calculation as the improved run)
src = (HERE / "build_forecast_v3.py").read_text(encoding="utf-8")
ns = {"__file__": str(HERE / "build_forecast_v3.py")}
exec(compile(src[:src.index("# history used by the models")].split("# ---------------- simple models")[0], "av", "exec"), ns)
AV, pos, k_idx, plabel, idx = ns["AV"], ns["pos"], ns["k_idx"], ns["plabel"], ns["idx"]
mon = ns["mon"]
both["avail"] = [AV[pos[mon(t)], k_idx[c]] if c in k_idx else 1.0 for t, c in zip(both["target"], both["code"])]


def score(df):
    out = []
    for cl in ["A", "B", "C", "ALL"]:
        for m in sorted(df["model"].unique()):
            s = df[df["model"] == m] if cl == "ALL" else df[(df["model"] == m) & (df["class"] == cl)]
            a = s["act"].sum()
            if a <= 0:
                continue
            row = {"class": cl, "model": m, "rows": len(s)}
            for tag in ("base", "imp"):
                p = s[f"pred_{tag}"]
                row[f"WAPE_{tag}"] = round(float((p - s["act"]).abs().sum() / a), 4)
                row[f"bias_{tag}"] = round(float((p - s["act"]).sum() / a), 4)
            row["WAPE_change"] = round(row["WAPE_imp"] - row["WAPE_base"], 4)
            out.append(row)
    return pd.DataFrame(out)


sets = {
    "all": both,
    "late": both[both["origin"] > "1404/06"],
    "in_stock": both[both["avail"] >= 0.7],
    "late_in_stock": both[(both["origin"] > "1404/06") & (both["avail"] >= 0.7)],
}
tables = {name: score(df) for name, df in sets.items()}

# chosen model per class in each run, scored on the late origins
late_b = base[base["origin"] > "1404/06"]
late_i = imp[imp["origin"] > "1404/06"]


def best_by_class(df, models):
    res = {}
    for cl in ["A", "B", "C"]:
        sc = []
        for m in models:
            s = df[(df["model"] == m) & (df["class"] == cl)]
            a = s["act"].sum()
            if a > 0:
                sc.append(((s["pred"] - s["act"]).abs().sum() / a, m))
        res[cl] = min(sc)
    return res


bb = best_by_class(late_b, ["SN", "WMA", "SES", "SBA", "ML", "DL", "ENS_STAT"])
bi = best_by_class(late_i, ["SN", "WMA", "SES", "SBA", "ML", "DL", "ENS_STAT", "ENS_W"])
chosen = pd.DataFrame([{"class": cl, "baseline_model": bb[cl][1], "baseline_WAPE": round(bb[cl][0], 4),
                        "improved_model": bi[cl][1], "improved_WAPE": round(bi[cl][0], 4),
                        "change": round(bi[cl][0] - bb[cl][0], 4)} for cl in ["A", "B", "C"]])

with pd.ExcelWriter(ROOT / "forecast" / "comparison.xlsx") as xw:
    chosen.to_excel(xw, sheet_name="Chosen model per class", index=False)
    for name, t in tables.items():
        t.to_excel(xw, sheet_name=f"By model - {name}", index=False)

pd.set_option("display.width", 200)
print("CHOSEN MODEL PER CLASS (late origins, lower WAPE is better):")
print(chosen.to_string(index=False))
for name in ("all", "late_in_stock"):
    print(f"\nBY MODEL - {name}:")
    print(tables[name].to_string(index=False))
