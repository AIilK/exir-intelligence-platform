"""منطق محاسبه شاخص‌ها روی داده‌های تراکنشی.

تعاریف با گزارش‌های تجمیعی فایل اصلی (TotalReport / Sales rep Ranking / Goods&Group)
تطبیق داده شده است؛ جزئیات در README آمده است.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# ابعاد قابل فیلتر/Drill-down: کلید ← (ستون کلید، ستون نام نمایشی)
DIMS = {
    "branch": ("branch", "branch"),
    "supervisor": ("supervisor", "supervisor"),
    "seller": ("seller_key", "seller"),
    "brand": ("brand", "brand"),
    "category": ("category", "category"),
    "group": ("product_group", "product_group"),   # زیرگروه = گروه کالای کارآمد
    "product": ("product_code", "product"),
    "customer": ("customer_code", "customer"),
    "city": ("city", "city"),
}
FILTER_FIELDS = {
    "branch": "branch",
    "supervisor": "supervisor",
    "seller": "seller_key",
    "brand": "brand",
    "category": "category",
    "group": "product_group",
    "city": "city",
    "payment": "payment",
}


# ---------------------------------------------------------------- helpers
def _num(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: _num(v) for k, v in r.items()} for r in df.to_dict("records")]


def _div(a, b):
    return float(a) / float(b) if b else None


# ---------------------------------------------------------------- filters
def apply_filters(df: pd.DataFrame | None, f: dict, is_sales: bool) -> pd.DataFrame | None:
    if df is None:
        return None
    m = pd.Series(True, index=df.index)
    if f.get("date_from"):
        m &= df["date"] >= f["date_from"]
    if f.get("date_to"):
        m &= df["date"] <= f["date_to"]
    for key, col in FILTER_FIELDS.items():
        vals = f.get(key)
        if vals and col in df.columns:
            m &= df[col].isin(vals)
    if is_sales and f.get("inv_type"):
        m &= df["inv_type"].isin(f["inv_type"])
    return df[m]


def elapsed_days(ctx: dict, f: dict, tx: pd.DataFrame, rq: pd.DataFrame | None) -> tuple[float, bool]:
    """تعداد روز کاری سپری‌شده، مخرج میانگین روزانه.
    بدون فیلتر تاریخ (default_period = ماه جاری): روز کاری ماه جاری و پیش‌بینی ماه محاسبه می‌شود.
    با فیلتر تاریخ: روزهای کاری تقویم (همه به‌جز جمعه) در بازه، برای همه شعب و فیلترها یکسان؛
    اگر بازه امروز را دارد، فقط روزهای کامل‌شده (قبل از امروز) — مثل ماه جاری.
    روزهای دارای داده ملاک نیست، چون چند ثبت در جمعه یا روز بی‌فروش یک شعبه مخرج را عوض می‌کرد."""
    if (f.get("date_from") or f.get("date_to")) and not f.get("default_period"):
        wd, today = ctx.get("workdays"), ctx.get("today")
        if wd is not None and len(wd):
            lo, hi = f.get("date_from") or "", f.get("date_to") or "9999"
            cut = bool(today and lo < today <= hi)
            n = int(np.searchsorted(wd, today if cut else hi, "left" if cut else "right") - np.searchsorted(wd, lo, "left"))
            if n > 0:
                f["_cut_today"] = cut
                return float(n), False
        # بدون تقویم (یا بازه‌ای فقط شامل امروز / جمعه): روزهای دارای داده
        dates = set(tx["date"].unique())
        if rq is not None:
            dates |= set(rq["date"].unique())
        return float(max(len(dates), 1)), False
    return float(ctx["wd_elapsed"]), True


def _cut(f: dict, full_month: bool) -> bool:
    """فروش امروز از مبنای میانگین کنار گذاشته شود؟ (ماه جاری یا بازه‌ای که تا امروز ادامه دارد)"""
    return full_month or bool(f.get("_cut_today"))


def _basis(df: pd.DataFrame | None, ctx: dict, cut: bool) -> pd.DataFrame | None:
    """مبنای میانگین روزانه و پیش‌بینی: وقتی بازه تا امروز ادامه دارد فقط روزهای کامل‌شده (قبل از امروز)،
    چون «روز کاری سپری‌شده» هم امروز را نمی‌شمارد؛ فروش امروز از فردا در میانگین و پیش‌بینی می‌آید."""
    if df is None or not cut or not ctx.get("today"):
        return df
    return df[df["date"] < ctx["today"]]


# ---------------------------------------------------------------- KPIs
INVOICE_KEYS = ["seller_key", "customer_code", "date"]


def _invoice_counts(tx: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame | int:
    """فاکتور مؤثر = سه‌تایی (فروشنده، مشتری، روز) با جمع تعداد مثبت — مطابق TotalReport؛
    در مدل هیبرید هر لاین/فروشنده فاکتور جدای خودش را صادر می‌کند."""
    keys = (by or []) + [k for k in INVOICE_KEYS if k not in (by or [])]
    g = tx.groupby(keys, observed=True)["qty"].sum()
    pos = g[g > 0]
    if not by:
        return int(len(pos))
    return pos.groupby(level=list(range(len(by)))).size()


def _customer_counts(tx: pd.DataFrame, by: list[str] | None = None):
    keys = (by or []) + ["customer_code"]
    g = tx.groupby(keys, observed=True)["qty"].sum()
    pos = g[g > 0]
    if not by:
        return int(len(pos))
    return pos.groupby(level=list(range(len(by)))).size()


def _line_counts(tx: pd.DataFrame, by: list[str] | None = None):
    """سطر فاکتور = سطرهای با تعداد مثبت (مطابق TotalReport؛ «سطر در فاکتور» = این ÷ فاکتور مؤثر)."""
    pos = tx[tx["qty"] > 0]
    if not by:
        return int(len(pos))
    return pos.groupby(by, observed=True).size()


def kpis(tx: pd.DataFrame, rq: pd.DataFrame | None, ctx: dict, f: dict) -> dict:
    sale = tx[~tx["is_return"]]
    ret = tx[tx["is_return"]]
    days, full_month = elapsed_days(ctx, f, tx, rq)
    net = tx["net"].sum()
    out = {
        "net": net,
        "gross": tx["gross"].sum(),
        "disc": tx["disc"].sum(),
        "vat": tx["vat"].sum(),
        "payable": tx["payable"].sum(),
        "qty": tx["qty"].sum(),
        "sales_net": sale["net"].sum(),
        "sales_gross": sale["gross"].sum(),
        "returns_net": -ret["net"].sum(),
        "returns_qty": -ret["qty"].sum(),
        "disc_rate": _div(sale["disc"].sum(), sale["gross"].sum()),
        "vol_disc_rate": _div(sale["vol_disc"].sum(), sale["gross"].sum()),
        "cash_disc_rate": _div(sale["cash_disc"].sum(), sale["gross"].sum()),
        "mgmt_disc_rate": _div(sale["mgmt_disc"].sum(), sale["gross"].sum()),
        "return_rate": _div(-ret["net"].sum(), sale["net"].sum()),
        "invoices": _invoice_counts(tx),
        "customers": _customer_counts(tx),
        "lines": _line_counts(tx),
        "sku": int((tx.groupby("product_code")["qty"].sum() > 0).sum()),
        "sellers_active": int((tx.groupby("seller_key")["net"].sum() > 0).sum()),
        "docs_sale": int(sale["inv_id"].nunique()),
        "docs_return": int(ret["inv_id"].nunique()),
        "days": days,
        "full_month": full_month,
        "wd_total": ctx["wd_total"],
    }
    out["avg_invoice"] = _div(net, out["invoices"])
    out["lines_per_inv"] = _div(out["lines"], out["invoices"])
    cut = _cut(f, full_month)
    base = _basis(tx, ctx, cut)["net"].sum()
    out["daily_avg"] = _div(base, days)
    out["forecast"] = base / days * ctx["wd_total"] if full_month and days else None
    if rq is not None:
        r_net = rq["net"].sum()
        done = rq[rq["status"] == 1]
        out.update({
            "req_net": r_net,
            "req_gross": rq["gross"].sum(),
            "req_qty": rq["qty"].sum(),
            "req_docs": int(rq["inv_id"].nunique()),
            "req_docs_done": int(done["inv_id"].nunique()),
            "req_net_done": done["net"].sum(),
            "req_conv": _div(done["net"].sum(), r_net),
            "req_daily_avg": _div(_basis(rq, ctx, cut)["net"].sum(), days),
            "req_forecast": _basis(rq, ctx, cut)["net"].sum() / days * ctx["wd_total"] if full_month and days else None,
            "sales_to_req": _div(net, r_net),
        })
    return {k: _num(v) for k, v in out.items()}


def group_metrics(tx: pd.DataFrame, rq: pd.DataFrame | None, dim: str, ctx: dict, f: dict,
                  extra: list[str] | None = None) -> pd.DataFrame:
    key, label = DIMS[dim]
    days, full_month = elapsed_days(ctx, f, tx, rq)
    sale = tx[~tx["is_return"]]
    ret = tx[tx["is_return"]]
    g = tx.groupby(key, observed=True).agg(net=("net", "sum"), gross=("gross", "sum"), qty=("qty", "sum"),
                                           disc=("disc", "sum"), payable=("payable", "sum"))
    g["sales_gross"] = sale.groupby(key)["gross"].sum()
    g["sales_disc"] = sale.groupby(key)["disc"].sum()
    g["sales_net"] = sale.groupby(key)["net"].sum()
    g["returns_net"] = -ret.groupby(key)["net"].sum()
    g["invoices"] = _invoice_counts(tx, [key])
    g["customers"] = _customer_counts(tx, [key])
    g["lines"] = _line_counts(tx, [key])
    g["sku"] = tx[tx["qty"] > 0].groupby(key)["product_code"].nunique()
    g["last_date"] = tx.groupby(key)["date"].max()
    g = g.fillna({"sales_gross": 0, "sales_disc": 0, "sales_net": 0, "returns_net": 0,
                  "invoices": 0, "customers": 0, "lines": 0, "sku": 0})
    if rq is not None and len(rq):
        r = rq.groupby(key).agg(req_net=("net", "sum"), req_docs=("inv_id", "nunique"))
        r["req_net_done"] = rq[rq["status"] == 1].groupby(key)["net"].sum()
        g = g.join(r, how="outer")
        g = g.fillna({c: 0 for c in ["net", "gross", "qty", "disc", "payable", "sales_gross", "sales_disc",
                                     "sales_net", "returns_net", "invoices", "customers", "lines", "sku",
                                     "req_net", "req_docs", "req_net_done"]})
        g["req_conv"] = np.where(g["req_net"] != 0, g["req_net_done"] / g["req_net"].replace(0, np.nan), np.nan)
        rb = _basis(rq, ctx, _cut(f, full_month)).groupby(key)["net"].sum().reindex(g.index, fill_value=0)
        g["req_forecast"] = rb / days * ctx["wd_total"] if full_month else np.nan
    g["disc_rate"] = g["sales_disc"] / g["sales_gross"].replace(0, np.nan)
    g["return_rate"] = g["returns_net"] / g["sales_net"].replace(0, np.nan)
    total = tx["net"].sum()
    g["share"] = g["net"] / total if total else np.nan
    g["avg_invoice"] = g["net"] / g["invoices"].replace(0, np.nan)
    b = _basis(tx, ctx, _cut(f, full_month))
    bnet = b.groupby(key)["net"].sum().reindex(g.index, fill_value=0)
    bqty = b.groupby(key)["qty"].sum().reindex(g.index, fill_value=0)
    g["daily_avg"] = bnet / days
    g["forecast"] = bnet / days * ctx["wd_total"] if full_month else np.nan
    g["forecast_qty"] = bqty / days * ctx["wd_total"] if full_month else np.nan
    g["lines_per_inv"] = g["lines"] / g["invoices"].replace(0, np.nan)
    g = g.reset_index().rename(columns={key: "key"})
    # نام نمایشی و ویژگی‌های اضافه
    src = pd.concat([tx, rq]) if rq is not None else tx
    attrs = list(dict.fromkeys(([label] if label != key else []) + (extra or [])))
    if attrs:
        lab = src.groupby(key)[attrs].agg(lambda s: s.value_counts().index[0])
        g = g.merge(lab.reset_index().rename(columns={key: "key"}), on="key", how="left")
    g["label"] = g[label] if label != key else g["key"]
    return g.sort_values("net", ascending=False)


def discount_by(tx: pd.DataFrame, col: str) -> list[dict]:
    """نرخ تخفیف (کل، حجمی، نقدی، مدیریتی) ÷ جمع قبل از تخفیف، فقط فاکتورهای فروش؛ به ترتیب جمع قبل از تخفیف.
    فاکتورهای «نمونه کالا» (۱۰۰٪ تخفیف، فروش نیستند) کنار گذاشته می‌شوند؛ وگرنه نرخ زیرگروه‌های کم‌فروش را تا ۱۰۰٪ بالا می‌برند."""
    sale = tx[~tx["is_return"]]
    if "is_sample" in sale:
        sale = sale[~sale["is_sample"]]
    g = sale.groupby(col, observed=True).agg(gross=("gross", "sum"), vol=("vol_disc", "sum"), cash=("cash_disc", "sum"),
                                             mgmt=("mgmt_disc", "sum"), disc=("disc", "sum")).reset_index().rename(columns={col: "key"})
    gross = g["gross"].replace(0, np.nan)
    for k, c in (("rate", "disc"), ("vol_rate", "vol"), ("cash_rate", "cash"), ("mgmt_rate", "mgmt")):
        g[k] = g[c] / gross
    return records(g.sort_values("gross", ascending=False))


def trend(tx: pd.DataFrame, rq: pd.DataFrame | None) -> list[dict]:
    sale = tx[~tx["is_return"]]
    ret = tx[tx["is_return"]]
    d = pd.DataFrame({
        "net": tx.groupby("date")["net"].sum(),
        "sales_net": sale.groupby("date")["net"].sum(),
        "returns_net": -ret.groupby("date")["net"].sum(),
        "qty": tx.groupby("date")["qty"].sum(),
    })
    d["invoices"] = _invoice_counts(tx, ["date"])
    if rq is not None:
        d = d.join(pd.DataFrame({"req_net": rq.groupby("date")["net"].sum()}), how="outer")
    d = d.fillna(0).sort_index().reset_index().rename(columns={"index": "date"})
    return records(d)


def monthly(tx: pd.DataFrame, rq: pd.DataFrame | None) -> list[dict]:
    """روند ماهانه: فروش خالص، برگشتی، درخواست، فاکتور مؤثر، مشتری فعال و روزهای دارای فروش."""
    sale = tx[~tx["is_return"]]
    ret = tx[tx["is_return"]]
    d = pd.DataFrame({
        "net": tx.groupby("month")["net"].sum(),
        "sales_net": sale.groupby("month")["net"].sum(),
        "returns_net": -ret.groupby("month")["net"].sum(),
        "qty": tx.groupby("month")["qty"].sum(),
        "days": tx.groupby("month")["date"].nunique(),
    })
    d["invoices"] = _invoice_counts(tx, ["month"])
    d["customers"] = _customer_counts(tx, ["month"])
    if rq is not None:
        d = d.join(pd.DataFrame({"req_net": rq.groupby("month")["net"].sum()}), how="outer")
    d["daily_avg"] = d["net"] / d["days"].replace(0, np.nan)
    d = d.fillna({c: 0 for c in d.columns if c != "daily_avg"}).sort_index()
    return records(d.reset_index().rename(columns={"index": "month"}))


def lines(tx: pd.DataFrame, limit: int = 1000) -> dict:
    cols = ["date", "inv_type", "inv_no", "branch", "seller", "customer_code", "customer", "product_code",
            "product", "brand", "category", "product_group", "qty", "unit_price", "gross", "disc", "net", "payment"]
    t = tx.sort_values(["date", "inv_no"], ascending=False)[cols]
    return {"total": int(len(t)), "rows": records(t.head(limit))}


def pareto(g: pd.DataFrame) -> dict:
    """طبقه‌بندی ABC بر اساس سهم تجمعی فروش خالص مثبت (۸۰٪ / ۹۵٪)."""
    p = g[g["net"] > 0].sort_values("net", ascending=False).copy()
    tot = p["net"].sum()
    if not tot:
        return {"classes": [], "curve": []}
    p["cum"] = p["net"].cumsum() / tot
    p["abc"] = np.where(p["cum"].shift(fill_value=0) < 0.8, "A", np.where(p["cum"].shift(fill_value=0) < 0.95, "B", "C"))
    cls = p.groupby("abc").agg(count=("key", "size"), net=("net", "sum")).reset_index()
    cls["share"] = cls["net"] / tot
    n = len(p)
    curve = [{"x": (i + 1) / n, "y": float(c)} for i, c in enumerate(p["cum"].values)]
    if n > 200:
        step = n / 200
        curve = [curve[min(int(i * step), n - 1)] for i in range(200)] + [curve[-1]]
    return {"classes": records(cls), "curve": curve, "abc": dict(zip(p["key"], p["abc"]))}


# ---------------------------------------------------------------- گزارش‌های درختی (مشابه شیت‌های گزارشی اکسل)
SEP = "\x1f"


def _mode(s: pd.Series):
    vc = s.value_counts()
    return vc.index[0] if len(vc) else None


def _grp(df: pd.DataFrame, keycols: list[str]):
    """گروه‌بندی؛ برای سطر «کل» یک ستون ثابت اضافه می‌شود."""
    if keycols:
        return df, keycols
    return df.assign(_all=0), ["_all"]


def _period(df: pd.DataFrame, keycols: list[str]) -> pd.DataFrame:
    t, k = _grp(df, keycols)
    g = t.groupby(k, observed=True).agg(gross=("gross", "sum"), net=("net", "sum"), qty=("qty", "sum"))
    g["invoices"] = _invoice_counts(t, k)
    g["customers"] = _customer_counts(t, k)
    g["lines"] = _line_counts(t, k)
    return g.fillna(0)


def _tree(dims: list[str], src: pd.DataFrame, frame_fn, attrs: dict | None = None) -> dict:
    """گره‌های تخت با id/parent برای سطوح dims؛ frame_fn(keycols) جدول شاخص‌ها را برمی‌گرداند."""
    labels, extra = {}, {}
    for d in dims:
        key, lab = DIMS[d]
        labels[d] = src.groupby(key)[lab].agg(_mode).to_dict() if lab != key else {}
        for a in (attrs or {}).get(d, []):
            extra[(d, a)] = src.groupby(key)[a].agg(_mode).to_dict()
    total, nodes = None, []
    for i in range(len(dims) + 1):
        keycols = [DIMS[d][0] for d in dims[:i]]
        g = frame_fn(keycols).reset_index()
        for rec in records(g):
            keys = [str(rec.pop(k)) for k in keycols]
            rec.pop("_all", None)
            rec.pop("index", None)
            if i == 0:
                total = rec
                continue
            d, k = dims[i - 1], keys[-1]
            rec.update(id=SEP.join(keys), parent=SEP.join(keys[:-1]), level=i - 1, dim=d, key=k,
                       label=labels[d].get(k, k))
            for a in (attrs or {}).get(d, []):
                rec[a] = extra[(d, a)].get(k)
            nodes.append(rec)
    return {"total": total, "nodes": nodes}


def report_tree(tx, rq, ctx, f, dims, report_day) -> dict:
    """میانگین روزانه / روز گزارش / از ابتدای ماه — مشابه TotalReport و Goods&Group."""
    days, full_month = elapsed_days(ctx, f, tx, rq)
    rd = tx[tx["date"] == report_day]
    cut = _cut(f, full_month)
    bt = _basis(tx, ctx, cut)

    def fn(keycols):
        g = _period(tx, keycols).join(_period(rd, keycols).add_prefix("rd_"), how="outer")
        if rq is not None and len(rq):
            t, k = _grp(rq, keycols)
            g = g.join(t.groupby(k, observed=True)["net"].sum().rename("req_net"), how="outer")
        g = g.fillna(0)
        base = _period(bt, keycols).reindex(g.index).fillna(0) if cut else g
        for c in ("gross", "net", "qty", "invoices"):
            g[f"avg_{c}"] = base[c] / days
        g["lines_per_inv"] = g["lines"] / g["invoices"].replace(0, np.nan)
        g["rd_lines_per_inv"] = g["rd_lines"] / g["rd_invoices"].replace(0, np.nan)
        g["forecast"] = base["net"] / days * ctx["wd_total"] if full_month else np.nan
        g["forecast_qty"] = base["qty"] / days * ctx["wd_total"] if full_month else np.nan
        if len(keycols) == len(dims):  # رتبه فقط در سطح آخر (مثل Sales rep Ranking)
            g["rank"] = g["net"].rank(ascending=False, method="min")
            g["rd_rank"] = g["rd_net"].rank(ascending=False, method="min")
        return g

    src = pd.concat([tx, rq]) if rq is not None else tx
    out = _tree(dims, src, fn, {"seller": ["supervisor", "seller_code"]})
    out.update(report_day=report_day, days=days, full_month=full_month)
    return out


def category_matrix(tx, dims, cats) -> dict:
    """فروش تعدادی و سهم ریالی (فروش خالص گروه ÷ فروش خالص کل همان ردیف) برای گروه‌های اصلی."""
    def fn(keycols):
        t, k = _grp(tx, keycols)
        tot = t.groupby(k, observed=True)["net"].sum()
        g = pd.DataFrame({"net": tot, "qty": t.groupby(k, observed=True)["qty"].sum()})
        for i, c in enumerate(cats):
            x = t[t["category"] == c]
            g[f"q{i}"] = x.groupby(k, observed=True)["qty"].sum()
            g[f"s{i}"] = x.groupby(k, observed=True)["net"].sum() / tot.replace(0, np.nan)
        return g.fillna({f"q{i}": 0 for i in range(len(cats))})

    out = _tree(dims, tx, fn, {"seller": ["supervisor"]})
    out["categories"] = cats
    return out


def daily_matrix(df, dims, metric, dates, wd_elapsed) -> dict:
    """روند روزانه هر ردیف (مشابه Trend / Trend2) + روزهای فعال."""
    def fn(keycols):
        t, k = _grp(df, keycols)
        if metric == "invoices":
            per = t.groupby(k + [x for x in INVOICE_KEYS if x not in k], observed=True)["qty"].sum() > 0
            per = per.groupby(level=k + ["date"]).sum()
        else:
            per = t.groupby(k + ["date"], observed=True)[metric].sum()
        pv = per.unstack("date", fill_value=0).reindex(columns=dates, fill_value=0)
        pv.columns = [f"d{i}" for i in range(len(dates))]
        cols = list(pv.columns)
        pv["total"] = pv[cols].sum(axis=1)
        pv["active_days"] = (pv[cols] > 0).sum(axis=1)
        pv["active_pct"] = pv["active_days"] / wd_elapsed if wd_elapsed else np.nan
        return pv

    out = _tree(dims, df, fn, {"seller": ["supervisor"]})
    out.update(dates=dates, metric=metric)
    return out


def brand_share(tx, brands) -> dict:
    """برای هر شعبه: فاکتور به مشتری و سهم از فروش، کل و به تفکیک برند (مشابه پایین TotalReport).
    سهم کل = فروش خالص شعبه ÷ کل؛ سهم برند = فروش خالص برند در شعبه ÷ فروش خالص کل آن برند."""
    def ipc(df):
        # مخرج مطابق اکسل: جفت‌های (فروشنده، مشتری) با خرید مثبت — یعنی میانگین دفعات خرید هر مشتری از هر فروشنده
        if not len(df):
            return pd.Series(dtype=float)
        inv = _invoice_counts(df, ["branch"])
        pairs = df.groupby(["branch", "seller_key", "customer_code"], observed=True)["qty"].sum()
        cu = pairs[pairs > 0].groupby(level=0).size()
        return inv / cu.replace(0, np.nan)

    g = pd.DataFrame({"net": tx.groupby("branch")["net"].sum()})
    total = tx["net"].sum()
    g["ipc"] = ipc(tx)
    g["share"] = g["net"] / total if total else np.nan
    for i, b in enumerate(brands):
        x = tx[tx["brand"] == b]
        bt = x["net"].sum()
        g[f"b{i}_ipc"] = ipc(x)
        g[f"b{i}_share"] = x.groupby("branch")["net"].sum() / bt if bt else np.nan
    g = g.reset_index().rename(columns={"branch": "key"})
    g["label"] = g["key"]
    return {"brands": brands, "rows": records(g.sort_values("net", ascending=False))}
