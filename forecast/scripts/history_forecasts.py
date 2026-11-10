"""Past forecasts for every product: what the chosen model would have predicted for each past month, using only
the data available at the time, next to the actual sales.

For every month o: forecasts for o+1, o+2, o+3 (1, 2 and 3 months ahead) with the model of the product's class
in that channel. LightGBM / neural network are retrained at the end of each Persian year (expanding window) and a
forecast only uses a model trained before its origin; before the first training cut, statistical models stand in
(median/mean ensembles fall back to the weighted average). Excluded months (outage / broken data) are skipped.
Output: forecast/forecast_history_per_product.xlsx
"""
import json

import numpy as np
import pandas as pd

import channels as C
import forecast_lab2 as L2

F = C.F
FA = {"WMA": "میانگین وزنی ۳ ماه", "SES": "هموارسازی نمایی", "SN": "همان ماه سال قبل", "SBA": "کروستون",
      "TSB": "TSB", "ADIDA": "ADIDA", "TD_BRAND": "سطح برند", "ML": "LightGBM", "DL": "شبکه عصبی",
      "MED4": "میانه ۴ مدل", "MEAN4": "میانگین ۴ مدل", "MED_ALL": "میانه همه مدل‌ها"}
CHS = (("hybrid", "هیبرید"), ("b2b", "B2B"), ("export", "صادرات"))
names = {c: F.goods.loc[c, "name"] for c in F.goods.index}

sheets, acc = {}, []
for ch_name, fa in CHS:
    Y, codes = (F.Y, F.codes) if ch_name == "hybrid" else C.RK[ch_name]
    ch = L2.Channel(ch_name, Y, codes)
    cj = json.loads((F.LAB / f"choice_{ch_name}.json").read_text(encoding="utf-8"))
    cfg, choice = L2.CFGS[cj["config"]], cj["chosen"]
    stat = L2.Stat(ch, ch.history(cfg))
    feats = L2.Feats(ch, stat.D, cfg)
    first_year = F.idx[ch.first_row] // 12 + 1
    cuts = [y * 12 + 11 for y in range(first_year, F.idx[-1] // 12)]          # end of each Persian year
    learners = {}
    for c in cuts:
        learners[c] = L2.Learn(feats, c)
        F.log(f"{ch_name}: trained up to {F.plabel(c)} ({learners[c].rows:,} rows)")
    FC = {h: np.full((F.T, ch.n), np.nan) for h in (1, 2, 3)}
    MODEL1 = np.full((F.T, ch.n), "", dtype=object)
    origins = [o for o in F.idx if F.R(o) >= ch.first_row + 12 and ch.valid[F.R(o)] and o < F.i_last]
    for o in origins:
        p = F.R(o)
        tg = [t for t in (o + 1, o + 2, o + 3) if t <= F.i_last and ch.valid[F.R(t)]]
        if not tg:
            continue
        fc = stat.forecast(p, tg)
        usable = [c for c in cuts if c <= o]
        if usable:
            fc.update(learners[max(usable)].forecast(p, tg))
        else:
            fc["ML"], fc["DL"] = fc["WMA"], fc["WMA"]
        fc = F.ensembles(fc)
        cls = ch.CLS[p]
        for j, t in enumerate(tg):
            h = t - o
            pick = np.zeros(ch.n)
            for ci, cl in enumerate(F.CLASSES):
                m = cls == ci
                pick[m] = fc[choice[cl]][j, m]
                if h == 1:
                    MODEL1[F.R(t), m] = FA[choice[cl]]
            FC[h][F.R(t)] = pick
    F.log(f"{ch_name}: past forecasts done for {len(origins)} origins")
    # long table
    rows = []
    for t in F.idx:
        r = F.R(t)
        if not ch.valid[r] or np.isnan(FC[1][r]).all():
            continue
        act = np.clip(np.nan_to_num(Y[r]), 0, None)
        f1, f2, f3 = (np.nan_to_num(FC[h][r]) for h in (1, 2, 3))
        keep = (act > 0) | (f1 >= 0.5) | (f2 >= 0.5) | (f3 >= 0.5)
        for k in np.where(keep)[0]:
            rows.append((codes[k], names.get(codes[k], ""), F.plabel(t), F.CLASSES[ch.CLS[r - 1, k]], round(float(act[k])),
                         round(float(f1[k])), round(float(f2[k])), round(float(f3[k])), MODEL1[r, k]))
        a = act.sum()
        acc.append({"کانال": fa, "ماه": F.plabel(t), "فروش واقعی": round(float(a)),
                    "پیش‌بینی ۱ ماه قبل": round(float(f1.sum())), "پیش‌بینی ۳ ماه قبل": round(float(f3.sum())),
                    "خطای کالا به کالا (۱ ماه قبل)": round(float(np.abs(f1 - act).sum() / a), 3) if a > 0 else None,
                    "خطای جمع کل کانال (۱ ماه قبل)": round(float(abs(f1.sum() - a) / a), 3) if a > 0 else None})
    sheets[fa] = pd.DataFrame(rows, columns=["کد کالا", "نام کالا", "ماه", "کلاس", "فروش واقعی", "پیش‌بینی ۱ ماه قبل",
                                             "پیش‌بینی ۲ ماه قبل", "پیش‌بینی ۳ ماه قبل", "مدل (۱ ماه قبل)"])
    F.log(f"{ch_name}: {len(rows):,} product-month rows")

acc_df = pd.DataFrame(acc)
acc_df["سال"] = acc_df["ماه"].str[:4]
yearly = acc_df.groupby(["کانال", "سال"]).apply(lambda d: pd.Series({
    "فروش واقعی": d["فروش واقعی"].sum(), "پیش‌بینی ۱ ماه قبل": d["پیش‌بینی ۱ ماه قبل"].sum(),
    "میانگین خطای کالا به کالا": round(float((d["خطای کالا به کالا (۱ ماه قبل)"] * d["فروش واقعی"]).sum() / d["فروش واقعی"].sum()), 3)
}), include_groups=False).reset_index()
guide = pd.DataFrame({"توضیح": [
    "هر ردیف: یک کالا در یک ماه گذشته. «پیش‌بینی ۱ ماه قبل» یعنی عددی که مدل یک ماه قبل از آن ماه، فقط با داده‌های تا آن زمان، می‌داد.",
    "مدل هر کالا = مدل کلاس آن کالا در همان کانال (همان مدل برنامه‌ی فعلی). LightGBM و شبکه‌ی عصبی هر سال با داده‌های تا پایان سال قبل دوباره آموزش دیده‌اند.",
    "قبل از اولین آموزش (هیبرید تا 1398، B2B و صادرات تا 1401) فقط مدل‌های آماری استفاده شده‌اند.",
    "ماه‌های قطعی اینترنت و داده‌های خراب (مثل 1404/10 تا 1405/01) نیامده‌اند.",
    "فروش واقعی طبق تعریف شرکت است؛ B2B و صادرات از 1400/10 (شروع داده‌های راهکاران).",
    "شیت «دقت ماهانه»: جمع فروش و پیش‌بینی هر کانال در هر ماه و خطا؛ «دقت سالانه»: همان به تفکیک سال."]})
with pd.ExcelWriter(F.ROOT / "forecast" / "forecast_history_per_product.xlsx") as xw:
    guide.to_excel(xw, sheet_name="راهنما", index=False)
    yearly.to_excel(xw, sheet_name="دقت سالانه", index=False)
    acc_df.drop(columns="سال").to_excel(xw, sheet_name="دقت ماهانه", index=False)
    for fa, df in sheets.items():
        df.to_excel(xw, sheet_name=fa, index=False)
print(yearly.to_string(index=False))
