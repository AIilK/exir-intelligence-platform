"""One complete row per product: sales history, forecast per channel, model used, its error, stock, safety, need.

Main forecast = the model of the product's ABC class in each channel (validated: it beat every per-product
choice rule on the later test months). For export A/B products the LLM hybrid is used (it won on both halves).
Side columns show each product's own best past model and its forecast, for reference only.
Output: forecast/forecast_complete_per_product.xlsx
"""
import json

import numpy as np
import pandas as pd

import channels as C
import forecast_lab2 as L2

F = C.F
MODELS = ["WMA", "SES", "SN", "SBA", "TSB", "ADIDA", "TD_BRAND", "ML", "DL", "MED4", "MEAN4", "MED_ALL"]
FA = {"WMA": "میانگین وزنی ۳ ماه", "SES": "هموارسازی نمایی", "SN": "همان ماه سال قبل", "SBA": "کروستون",
      "TSB": "TSB", "ADIDA": "ADIDA", "TD_BRAND": "سطح برند", "ML": "LightGBM", "DL": "شبکه عصبی",
      "MED4": "میانه ۴ مدل", "MEAN4": "میانگین ۴ مدل", "MED_ALL": "میانه همه مدل‌ها", "ENS_LLM": "ترکیب LLM و مدل‌ها", "": ""}
CHS = (("hybrid", "هیبرید"), ("b2b", "B2B"), ("export", "صادرات"))
need_j = [j for j, t in enumerate(F.FINAL_TARGETS) if t in F.NEED_MONTHS]
plan = pd.read_csv(F.ROOT / "forecast" / "production_plan_channels.csv", dtype={"code": str})
plan = plan.rename(columns={plan.columns[0]: "code"}).set_index("code")

# actual sales of the last 12 months (1404/08..1405/07), company counting rules, all months included
last12 = [F.plabel(i) for i in range(F.mon("1404/08"), F.mon("1405/07") + 1)]
k = pd.read_csv(F.DATA / "kdb_sales_monthly.csv", dtype={"code": str})
sales12 = {"hybrid": k[k["pm"].isin(last12)].groupby("code")["net_qty"].sum()}
inv = pd.read_csv(F.DATA / "rk_invoices_daily.csv", dtype={"code": str})
ret = pd.read_csv(F.DATA / "rk_returns_daily.csv", dtype={"code": str})
ret = ret[ret["status"] == 11].assign(qty=lambda d: -d["qty"])
rk = pd.concat([inv, ret])
rk["ch"] = rk["cust"].map(C.channel_of)
rk["pm"] = [F.plabel(i) for i in C._pm_index(rk["d"])]
rk = rk[rk["pm"].isin(last12)]
for ch in ("b2b", "export"):
    sales12[ch] = rk[rk["ch"] == ch].groupby("code")["qty"].sum()
prod = pd.read_csv(F.DATA / "rk_production_daily.csv", dtype={"code": str}, parse_dates=["d"])
produced12 = prod[prod["d"] >= pd.Timestamp("2025-10-23")].groupby("code")["qty"].sum()   # 1404/08/01 onward

rows = {}
for ch, fa in CHS:
    fz = np.load(F.LAB / f"final_{ch}.npz", allow_pickle=True)
    bz = np.load(F.LAB / f"backtest_{ch}.npz")
    codes = [str(c) for c in fz["codes"]]
    X = type("X", (), {"ORIG": bz["ORIG"], "ACT": bz["ACT"], "CLS_P": bz["CLS_P"]})()
    tm = {m: L2.three_month(X, bz[m]) for m in MODELS}
    A3 = tm["WMA"][1]
    choice = json.loads((F.LAB / f"choice_{ch}.json").read_text(encoding="utf-8"))["chosen"]
    err = np.stack([np.abs(tm[m][0] - A3).sum(0) for m in MODELS])          # models x products, all windows
    act_sum = A3.sum(0)
    own = err.argmin(0)
    for j, c in enumerate(codes):
        cl = F.CLASSES[fz["CLS_NOW"][j]]
        used = plan.loc[c, f"{ch}_model"] if c in plan.index and isinstance(plan.loc[c, f"{ch}_model"], str) else choice[cl]
        base_model = choice[cl]
        e_used = err[MODELS.index(base_model), j] / act_sum[j] if act_sum[j] > 0 else np.nan
        r = rows.setdefault(c, {})
        r[f"{fa} | کلاس"] = cl
        r[f"{fa} | فروش ۱۲ ماه اخیر"] = round(float(sales12[ch].get(c, 0.0)))
        r[f"{fa} | مدل استفاده‌شده"] = FA.get(used, used)
        r[f"{fa} | خطای گذشته (جمع ۳ ماهه)"] = round(float(e_used), 3) if e_used == e_used else None
        for t in F.FINAL_TARGETS:
            r[f"{fa} | {t}"] = round(float(plan.loc[c, f"{ch}_{t}"])) if c in plan.index else 0
        r[f"{fa} | جمع آذر-بهمن"] = round(float(plan.loc[c, f"{ch}_3m"])) if c in plan.index else 0
        r[f"{fa} | بهترین مدل خودِ کالا در گذشته"] = FA[MODELS[own[j]]] if act_sum[j] > 0 else ""
        r[f"{fa} | پیش‌بینی با آن مدل (آذر-بهمن)"] = round(float(fz[MODELS[own[j]]][need_j, j].sum())) if act_sum[j] > 0 else 0

out = pd.DataFrame.from_dict(rows, orient="index")
out.index.name = "کد کالا"
info = pd.DataFrame({
    "نام کالا": [F.goods.loc[c, "name"] if c in F.goods.index else "" for c in out.index],
    "برند": [F.goods.loc[c, "brand"] if c in F.goods.index else "" for c in out.index],
    "گروه": [F.goods.loc[c, "category"] if c in F.goods.index else "" for c in out.index],
    "فعال": [bool(F.goods.loc[c, "active"]) if c in F.goods.index else None for c in out.index]}, index=out.index)
tot = pd.DataFrame(index=out.index)
for t in F.FINAL_TARGETS:
    tot[f"جمع کانال‌ها | {t}"] = out[[f"{fa} | {t}" for _, fa in CHS if f"{fa} | {t}" in out]].fillna(0).sum(axis=1)
tot["جمع کانال‌ها | آذر-بهمن"] = out[[f"{fa} | جمع آذر-بهمن" for _, fa in CHS]].fillna(0).sum(axis=1)
tot["فروش ۱۲ ماه اخیر (همه کانال‌ها)"] = out[[f"{fa} | فروش ۱۲ ماه اخیر" for _, fa in CHS]].fillna(0).sum(axis=1)
pl = plan.reindex(out.index)
stock = pd.DataFrame({
    "سفارش باز B2B": pl["b2b_open_orders"].fillna(0).round(0), "سفارش باز صادرات": pl["export_open_orders"].fillna(0).round(0),
    "تقاضای استفاده‌شده (۳ ماه)": pl["demand_3m"].fillna(0).round(0), "ذخیره اطمینان": pl["safety"].fillna(0).round(0),
    "موجودی کارخانه (انبار ۱-۴)": pl["factory_stock_1_4"].fillna(0).round(0), "موجودی شعب": pl["branch_stock"].fillna(0).round(0),
    "نیاز تولید": pl["production_need"].fillna(0).round(0),
    "تولید ۱۲ ماه اخیر": [round(float(produced12.get(c, 0.0))) for c in out.index]}, index=out.index)
full = pd.concat([info, tot, stock, out], axis=1)
full = full[(full["جمع کانال‌ها | آذر-بهمن"] > 0) | (full["فروش ۱۲ ماه اخیر (همه کانال‌ها)"] > 0) | (full["نیاز تولید"] > 0)]
full = full.sort_values("جمع کانال‌ها | آذر-بهمن", ascending=False)

guide = pd.DataFrame({"ستون": [
    "جمع کانال‌ها", "تقاضای استفاده‌شده", "ذخیره اطمینان", "نیاز تولید", "<کانال> | کلاس", "<کانال> | مدل استفاده‌شده",
    "<کانال> | خطای گذشته", "<کانال> | بهترین مدل خودِ کالا در گذشته", "فروش ۱۲ ماه اخیر", "تولید ۱۲ ماه اخیر"],
    "توضیح": [
    "پیش‌بینی هیبرید + B2B + صادرات برای هر ماه؛ آبان = کل ماه.",
    "هیبرید + بیشترِ (پیش‌بینی، سفارش باز) برای B2B و صادرات، آذر تا بهمن 1405.",
    "سطح سرویس A ۹۵٪ و B ۹۰٪، از خطای واقعی پیش‌بینی همین کالا در گذشته.",
    "تقاضا + ذخیره − موجودی کارخانه − موجودی شعب؛ کالای غیرفعال = ۰.",
    "A = ۸۰٪ فروش، B = ۱۵٪ بعدی، C = بقیه، N = بدون فروش؛ در هر کانال جدا.",
    "مدل کلاس کالا در آن کانال؛ آزمون نشان داد این از انتخاب مدل جدا برای هر کالا دقیق‌تر است.",
    "خطای همین کالا با مدل استفاده‌شده روی جمع‌های ۳ ماهه‌ی گذشته (|خطا| ÷ فروش).",
    "فقط برای مقایسه؛ روی ماه‌های جدید معمولاً بدتر از مدل کلاس عمل کرده است.",
    "1404/08 تا 1405/07 طبق تعریف شرکت (خالص، بدون اهدایی، برگشتی قطعی کم شده).",
    "دریافت از تولید راهکاران از 1404/08/01."]})
test = pd.DataFrame({"کانال": ["هیبرید", "B2B", "صادرات"],
                     "مدل کلاس (استفاده‌شده)": [0.415, 0.726, 1.073],
                     "بهترین مدل هر کالا (همه مدل‌ها)": [0.565, 0.898, 1.211],
                     "بهترین مدل هر کالا (۶ مدل مطمئن، با ۵۰٪ برتری)": [0.418, 0.730, 1.098]})
with pd.ExcelWriter(F.ROOT / "forecast" / "forecast_complete_per_product.xlsx") as xw:
    full.reset_index().to_excel(xw, sheet_name="کالاها", index=False)
    guide.to_excel(xw, sheet_name="راهنما", index=False)
    test.to_excel(xw, sheet_name="آزمون انتخاب مدل", index=False)
F.log("products:", len(full), "| columns:", full.shape[1], "| 3m total:", int(full["جمع کانال‌ها | آذر-بهمن"].sum()),
      "| production need:", int(full["نیاز تولید"].sum()))
