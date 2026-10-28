"""آزمون تاریخی سیستم موجودی روی همه شعب هیبرید با همان کد inventory.compute.

در هر تاریخ بررسی (اول و نیمه ماه‌های اخیر) فقط داده قبل از آن تاریخ دیده می‌شود: فروش تا آن روز، و موجودی همان روز
که از دفتر موجودی کارآمد (vwStockLines، فقط SELECT) بازسازی می‌شود. بعد پیشنهاد سیستم با فروش واقعی روزهای بعد مقایسه می‌شود.
درخواست‌های باز گذشته قابل بازسازی نیستند و صفر فرض می‌شوند؛ معیار درستی فروش ثبت‌شده است (کمبودها کمتر از واقع دیده می‌شوند).
"""
from __future__ import annotations

import copy
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import inventory as INV
import loader
import planning as PL
import sql_source

LEDGER_SQL = """
SELECT l.BranchRef AS bid, g.Code AS code, l.StoreRef AS store, c.PersianDate AS date, l.Kind AS kind, l.TotalT AS qty
FROM dbo.vwStockLines l JOIN dbo.tblGoods g ON g.ID = l.GoodsRef JOIN dbo.tblCalendar c ON c.GregorianDate = l.DateE
WHERE l.FiscalYear = (SELECT MAX(FiscalYear) FROM dbo.vwStockFull)"""
SIGN = {"K": 1, "B": 1, "I": 1, "M": 1, "F": -1, "E": -1, "O": -1}
HORIZON = 22  # روزهای بعد از هر تاریخ که سفارش باید پوشش دهد (۱۵ تا سفارش بعد + ۷ رسیدن بار)

# حالت‌هایی که با هم مقایسه می‌شوند (روی تنظیمات فعلی اعمال می‌شوند)
VARIANTS = {
    "current": {},
    "z_1.65": {"a_safety": "data", "z_a": 1.65},
    "z_1.0": {"a_safety": "data", "z_a": 1.0},
    "safety_customers": {"a_safety": "breadth"},
    "no_break": {"break_detect": False},
}
VARIANT_LABEL = {"current": "تنظیمات فعلی", "z_1.65": "safety کالای A از نوسان، z = ۱٫۶۵",
                 "z_1.3": "safety کالای A از نوسان، z = ۱٫۳", "z_1.0": "safety کالای A از نوسان، z = ۱",
                 "safety_customers": "safety کالای A بر اساس مشتری", "b_25": "safety کالای B برابر ۲۵٪",
                 "no_break": "بدون تشخیص تغییر ساختاری"}


def review_dates(cal: pd.DataFrame, today: str, n_months: int = 5) -> list[str]:
    """اول و نیمه هر ماه، n ماه کامل اخیر؛ فقط تاریخ‌هایی که ۲۲ روز بعدشان گذشته است."""
    dates = sorted(cal["date"])
    i = dates.index(today) if today in dates else len(dates) - 1
    limit = dates[max(i - HORIZON, 0)]
    out, m = [], today[:7]
    for _ in range(n_months + 1):
        for d in ("16", "01"):
            x = f"{m}/{d}"
            if x <= limit:
                out.append(x)
        m = PL.month_add(m, -1)
    return sorted(out)[-2 * n_months:]


class Backtest:
    def __init__(self, root: Path, env_file: Path):
        self.file = root / "data" / "inventory" / "backtest.json"
        self.env_file = env_file
        self.lock = threading.Lock()
        self.state = {"running": False, "progress": None, "error": None}

    def result(self) -> dict | None:
        if self.file.is_file():
            return json.loads(self.file.read_text(encoding="utf-8"))
        return None

    def start(self, data: dict, cfg: dict) -> bool:
        if self.state["running"]:
            return False
        self.state.update(running=True, progress="خواندن دفتر موجودی شعب از کارآمد…", error=None)
        threading.Thread(target=self._run, args=(data, cfg), daemon=True).start()
        return True

    def _run(self, data: dict, cfg: dict):
        try:
            out = run(data, cfg, self.env_file, progress=lambda t: self.state.update(progress=t))
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.file)
        except Exception as e:  # خطای اتصال یا داده؛ نتیجه قبلی می‌ماند
            self.state["error"] = str(e)
        finally:
            self.state.update(running=False, progress=None)


def _ledgers(env_file) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    cn = sql_source.connect(sql_source.settings(sql_source.read_env(env_file)))
    try:
        L = INV._read(cn, LEDGER_SQL, [])
        br = INV._read(cn, "SELECT ID, Name FROM dbo.tblBranch", [])
        stores = INV._read(cn, "SELECT ID, Name, IsWastage FROM dbo.tblStore", [])
    finally:
        cn.close()
    stores["name"] = stores["Name"].map(loader._clean_text)
    waste = set(stores.loc[INV.is_waste_store(stores["name"]), "ID"])
    L = L[~L["store"].isin(waste)].copy()
    L["code"] = L["code"].map(loader._clean_code)
    L["q"] = pd.to_numeric(L["qty"], errors="coerce").fillna(0.0) * L["kind"].map(SIGN).fillna(0.0)
    return L[["bid", "code", "date", "q"]], dict(zip(br["Name"].map(loader._clean_text), br["ID"].astype(int))), stores


def run(data: dict, cfg: dict, env_file, branches: list[str] | None = None, variants: dict | None = None,
        progress=lambda t: None) -> dict:
    t_start = time.time()
    variants = variants or VARIANTS
    L, bids, _ = _ledgers(env_file)
    branches = branches or INV.hybrid_branches(data)
    S_all = data["sales"]
    today = data["meta"].get("today") or S_all["date"].max()
    cal = data["plan_inputs"]["calendar"]
    dates = sorted(cal["date"])
    pos = {d: i for i, d in enumerate(dates)}
    add = lambda d, k: dates[min(pos[d] + k, len(dates) - 1)]
    reviews = review_dates(cal, today)
    src0 = INV.InventorySource(env_file)
    rows, mrows, notes = [], [], {}
    for bi, b in enumerate(branches):
        progress(f"شعبه {bi + 1} از {len(branches)}: {b}")
        if b not in bids:
            continue
        Lb = L[L["bid"] == bids[b]]
        live = src0.get(b)  # فقط برای کالا و قیمت
        sb = S_all[(S_all["branch"] == b) & ~S_all["is_sample"]]
        # شعبه‌ای که خریدش ثبت نمی‌شود، موجودی بازسازی‌شده‌اش واقعی نیست؛ در سنجش نمی‌آید
        recent = sb[sb["date"] >= dates[max(pos.get(today, len(dates) - 1) - 90, 0)]]
        sold90, bought90 = float(recent["qty"].sum()), float(live["purch"]["qty"].sum())
        if sold90 > 0 and bought90 < 0.1 * sold90:
            notes[b] = "خرید این شعبه در کارآمد ثبت نمی‌شود؛ موجودی قابل اعتماد نیست و در سنجش نیامد."
            continue
        for t in reviews:
            stock = Lb[Lb["date"] < t].groupby("code")["q"].sum()
            src = {"fetched": time.time(), "stock": stock, "waste": pd.Series(dtype=float), "goods": live["goods"],
                   "price": live["price"],
                   "purch": pd.DataFrame({"code": pd.Series(dtype=object), "date": pd.Series(dtype=object), "qty": pd.Series(dtype=float)})}
            d = dict(data)
            d["sales"] = sb[sb["date"] < t]  # compute فقط فروش همین شعبه را لازم دارد
            d["requests"] = None
            d["meta"] = {**data["meta"], "today": t}
            fut = sb[sb["date"] >= t]
            a22 = fut[fut["date"] < add(t, HORIZON)].groupby("product_code", observed=True)["qty"].sum().clip(lower=0)
            am = fut[fut["month"] == t[:7]].groupby("product_code", observed=True)["qty"].sum().clip(lower=0)
            active_after = float(a22.sum()) > 0
            for vn, over in variants.items():
                c = copy.deepcopy(cfg)
                c["inventory"] = {**(cfg.get("inventory") or {}), **over}
                try:
                    r = INV.compute(d, src, c, branch=b)
                except loader.DataError as ex:
                    notes[b] = str(ex)
                    continue
                if r["inactive"] or not active_after:
                    continue  # شعبه غیرفعال یا بعد از این تاریخ بدون فروش: در سنجش نمی‌آید
                R = r["rows"].set_index("code")
                R["a22"] = a22.reindex(R.index).fillna(0.0)
                R["stk"] = R["stock"].clip(lower=0)
                R["supply"] = R["stk"] + R["order"]
                for grp in ("A", "B"):
                    g = R[R["abc"] == grp]
                    short = g["stk"] < g["a22"]
                    flag = g["status"].isin(["red", "orange"])
                    rows.append({"branch": b, "review": t, "variant": vn, "grp": grp, "items": int(len(g)),
                                 "short": int(short.sum()), "caught": int((flag & short).sum()), "flagged": int(flag.sum()),
                                 "demand": float(g["a22"].sum()), "fill0": float(np.minimum(g["stk"], g["a22"]).sum()),
                                 "fill1": float(np.minimum(g["supply"], g["a22"]).sum()), "order": float(g["order"].sum()),
                                 "order_value": float((g["order"] * g["price"].fillna(0)).sum())})
                if t.endswith("/01") and vn == "current":
                    A = R[R["abc"] == "A"]
                    act = am.reindex(R.index).fillna(0.0)
                    mrows.append({"branch": b, "month": t[:7], "fc": float(R["fc_now"].sum()), "actual": float(act.sum()),
                                  "fc_A": float(A["fc_now"].sum()), "abs_err_A": float((A["fc_now"] - act[A.index]).abs().sum()),
                                  "actual_A": float(act[A.index].sum()),
                                  "within30_A": float((act[A.index] / A["fc_now"].replace(0, np.nan)).between(0.7, 1.3).mean())
                                  if len(A) else None,
                                  "break_month": r["break_month"]})
    B = pd.DataFrame(rows)
    M = pd.DataFrame(mrows)

    def summarize(df: pd.DataFrame, keys: list[str]) -> list[dict]:
        if not len(df):
            return []
        g = df.groupby(keys).agg(short=("short", "sum"), caught=("caught", "sum"), flagged=("flagged", "sum"),
                                 demand=("demand", "sum"), fill0=("fill0", "sum"), fill1=("fill1", "sum"),
                                 order=("order", "sum"), order_value=("order_value", "sum"), reviews=("review", "nunique"))
        g["recall"] = g["caught"] / g["short"].replace(0, np.nan)
        g["precision"] = g["caught"] / g["flagged"].replace(0, np.nan)
        g["fill_no_order"] = g["fill0"] / g["demand"].replace(0, np.nan)
        g["fill_system"] = g["fill1"] / g["demand"].replace(0, np.nan)
        g["order_ratio"] = g["order"] / g["demand"].replace(0, np.nan)
        return json.loads(g.reset_index().replace([np.inf, -np.inf], np.nan).to_json(orient="records", force_ascii=False))

    monthly = []
    if len(M):
        M["bias"] = M["fc"] / M["actual"].replace(0, np.nan) - 1
        M["wape_A"] = M["abs_err_A"] / M["actual_A"].replace(0, np.nan)
        monthly = json.loads(M.replace([np.inf, -np.inf], np.nan).to_json(orient="records", force_ascii=False))
    return {"created": datetime.now().strftime("%Y-%m-%d %H:%M"), "seconds": round(time.time() - t_start),
            "today": today, "reviews": reviews, "horizon": HORIZON, "settings": INV.settings(cfg),
            "variants": {k: VARIANT_LABEL.get(k, k) for k in variants},
            "by_branch": summarize(B, ["branch", "variant", "grp"]),
            "overall": summarize(B, ["variant", "grp"]),
            "monthly": monthly, "notes": notes}
