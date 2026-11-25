"""Refit the validated Hybrid and B2B demand models and build the production plan."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import channels as C
import forecast_lab2 as L
from production_plan_io import production_quantities

F = C.F
CHANNELS = ("hybrid", "b2b")


def saved_rmse(name, choices):
    with np.load(F.LAB / f"final_{name}.npz", allow_pickle=True) as saved, np.load(F.LAB / f"backtest_{name}.npz") as run:
        codes = pd.Index(saved["codes"].astype(str), name="code")
        actual, classes = run["ACT"], run["CLS_P"]
        chosen = np.zeros_like(actual)
        for i, cls in enumerate(F.CLASSES):
            chosen = np.where(classes == i, run[choices[cls]], chosen)
        return pd.Series(np.sqrt(np.mean((chosen - actual) ** 2, axis=0)), index=codes)


def forecast(name, history, codes, valid, targets, last):
    reference = json.loads((F.LAB / f"choice_{name}.json").read_text(encoding="utf-8"))
    config, choices = L.CFGS[reference["config"]], reference["chosen"]
    channel = L.Channel(name, history, codes, valid_months=valid, season_cutoff=last)
    stat = L.Stat(channel, channel.history(config))
    row = F.R(last)
    variants = stat.forecast(row, targets)
    if name == "b2b":
        F.log("fitting B2B LightGBM and neural network on closed months")
        learner = L.Learn(L.Feats(channel, stat.D, config), last, batch_size=1024)
        variants.update(learner.forecast(row, targets))
        variants = F.ensembles(variants)
    classes = channel.CLS[row]
    monthly = np.stack([np.choose(classes, [variants[choices[cls]][j] for cls in F.CLASSES])
                        for j in range(len(targets))])
    if not np.isfinite(monthly).all() or (monthly < 0).any():
        raise ValueError(f"Invalid {name} demand predictions")
    labels = np.array(F.CLASSES)[classes]
    out = pd.DataFrame({f"{name}_class": labels, f"{name}_model": [choices[label] for label in labels],
                        **{f"{name}_{F.plabel(target)}": values for target, values in zip(targets, monthly)},
                        f"{name}_3m": monthly.sum(axis=0)}, index=pd.Index(codes, name="code"))
    out[f"{name}_rmse"] = saved_rmse(name, choices).reindex(out.index)
    return out


def export(plan, out_dir, targets, last):
    label = ", ".join(map(F.plabel, targets))
    total = lambda key: round(float(plan[key].sum()))
    flags = plan.loc[plan.production_need.gt(0)]
    summary = pd.DataFrame([
        ("آخرین ماه کامل فروش", F.plabel(last)),
        ("ماه‌های برنامه", label),
        ("پیش‌بینی هیبرید", total("hybrid_3m")),
        ("پیش‌بینی B2B", total("b2b_3m")),
        ("جمع پیش‌بینی فروش", total("demand_3m")),
        ("ذخیره اطمینان", total("safety")),
        ("موجودی کارخانه در انبارهای ۱ تا ۴", total("factory_stock_1_4")),
        ("موجودی شعب", total("branch_stock")),
        ("نیاز تولید", total("production_need")),
        ("تعداد کالاهای نیازمند تولید", len(flags)),
        ("کالاهای نیازمند تولید بدون سابقهٔ خطا در یک کانال فعال", int(flags.missing_safety_history.sum())),
        ("کالاهای نیازمند تولید بدون رکورد موجودی در هر دو منبع", int(flags.missing_inventory_record.sum())),
        ("کالاهای نیازمند تولید بدون وضعیت فعالیت", int(flags.missing_product_status.sum())),
        ("منبع موجودی", F.SNAPSHOT.parent.name + "/" + F.SNAPSHOT.name if F.SNAPSHOT else "برداشت ذخیره‌شدهٔ پروژه"),
    ], columns=["شاخص", "مقدار"])
    plan.to_csv(out_dir / "production_plan_hybrid_b2b.csv", encoding="utf-8-sig")
    with pd.ExcelWriter(out_dir / "production_plan_hybrid_b2b.xlsx", engine="xlsxwriter") as writer:
        summary.to_excel(writer, sheet_name="خلاصه", index=False)
        plan.reset_index().to_excel(writer, sheet_name="برنامه تولید", index=False)
        sheet = writer.sheets["خلاصه"]
        sheet.right_to_left()
        sheet.set_column(0, 0, 57)
        sheet.set_column(1, 1, 43)
        product = writer.sheets["برنامه تولید"]
        product.right_to_left()
        product.set_column(0, 0, 16)
        product.set_column(1, 1, 50)
        product.set_column(2, len(plan.columns), 24)
        product.freeze_panes(1, 3)
        product.autofilter(0, 0, len(plan), len(plan.columns))
    print(summary.to_string(index=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    F.LGB_PARAMS.update(n_jobs=args.threads, n_estimators=160)
    last = F.mon(F.LAST_FULL)
    targets = [last + horizon for horizon in (2, 3, 4)]
    valid = ~np.isin(F.idx, [F.mon(m) for m in F.MANUAL_EXCLUDE])
    hybrid = F.net.reindex(columns=F.codes).to_numpy(copy=True)
    hybrid[~valid] = np.nan
    b2b, b2b_codes = C.rahkaran_channels(valid)[0]["b2b"]
    forecast_rows = [forecast(name, hist, codes, valid, targets, last)
                     for name, hist, codes in (("hybrid", hybrid, F.codes), ("b2b", b2b, b2b_codes))]
    panel = pd.concat(forecast_rows, axis=1)
    for ch in CHANNELS:
        for target in targets:
            field = f"{ch}_{F.plabel(target)}"
            panel[field] = panel[field].fillna(0)
    has_safety_class = panel[[f"{ch}_class" for ch in CHANNELS]].isin(("A", "B")).any(axis=1)
    panel["missing_safety_history"] = has_safety_class & np.logical_or.reduce([
        panel[f"{ch}_class"].notna() & panel[f"{ch}_rmse"].isna() for ch in CHANNELS
    ])
    factory = pd.read_csv(F.data_path("rk_factory_stock.csv"), dtype={"code": str, "store": str})
    factory_stock = factory.loc[factory.store.isin(F.FACTORY_STORES)].groupby("code").qty.sum()
    branch_stock = pd.read_csv(F.data_path("kdb_branch_stock.csv"), dtype={"code": str}).groupby("code").qty.sum()
    panel["missing_inventory_record"] = ~panel.index.isin(factory_stock.index.union(branch_stock.index))
    panel["missing_product_status"] = F.goods.active.reindex(panel.index).isna()
    plan = production_quantities(panel, CHANNELS, F.goods, factory_stock, branch_stock)
    export(plan, args.output_dir, targets, last)


if __name__ == "__main__":
    main()
