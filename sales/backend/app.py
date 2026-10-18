"""API داشبورد فروش. اجرا: python backend/app.py

داده فقط از دیتابیس کارآمد (SQL Server) خوانده می‌شود؛ جزئیات در sql_source.py.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import analytics as A
import chain_store as CS
import inventory as INV
import loader
import planning as PL
import sql_source

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
ENV_FILE = ROOT / ".env"
DIST = ROOT / "frontend" / "dist"
DEFAULT_SQL = {"branch_like": "هیبرید", "refresh_minutes": 30, "history_months": 12, "history_from": "1404/01",
               "history_refresh_hours": 24, "live_seconds": 5}
DEFAULT_CONFIG = {"wd_elapsed": None, "wd_total": None, "sql": DEFAULT_SQL, "host": "127.0.0.1", "port": 8000}

app = FastAPI(title="Sales Dashboard")
STORE = sql_source.SqlStore(ENV_FILE)
# stamp با هر تغییر داده زیاد می‌شود تا فرانت‌اند داده تازه را بگیرد
STATE: dict = {"data": None, "error": "در حال دریافت داده از SQL…", "sql_error": None, "stamp": 0,
               "busy": False, "meta_cache": None, "planner": None}
PLANS = PL.PlanStore(ROOT / "data" / "plans")
INV_SRC = INV.InventorySource(ENV_FILE)


# ---------------------------------------------------------------- config
def read_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def sql_cfg(cfg: dict) -> dict:
    return {**DEFAULT_SQL, **(cfg.get("sql") or {})}


def write_config(cfg: dict):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- بارگذاری از SQL
PUBLISH_LOCK = threading.Lock()  # sql_worker و live_worker هر دو منتشر می‌کنند


def publish():
    with PUBLISH_LOCK:
        data = STORE.build()
        if data is not None:
            STATE["data"], STATE["error"] = data, None
            STATE["stamp"] += 1


def sql_worker():
    """در پس‌زمینه: ابتدا ماه جاری، سپس مشتریان و ماه‌های قبل؛ هر گام یک ماه."""
    while True:
        cfg = sql_cfg(read_config())
        STATE["busy"] = True
        try:
            done = STORE.refresh_step(cfg)
            STATE["sql_error"] = None
        except Exception as e:  # قطع اتصال یا خطای کوئری؛ داده قبلی می‌ماند
            STATE["sql_error"] = str(e)
            if STATE["data"] is None:
                STATE["error"] = f"اتصال به SQL برقرار نشد: {e}"
            STATE["busy"] = False
            time.sleep(60)
            continue
        STATE["busy"] = False
        if done:
            # تا داده تازه منتشر نشده، ماه «در حال دریافت» نمایش داده شود
            STATE["publishing"] = done
            try:
                publish()
            finally:
                STATE["publishing"] = None
        else:
            time.sleep(15)


def live_worker():
    """لایو: هر live_seconds ثانیه روزهای تغییرکرده را پیدا و فقط همان‌ها را دوباره می‌خواند (sql_source.live_step).
    جدا از sql_worker، تا خواندن چنددقیقه‌ای یک ماه کامل، داده لحظه‌ای را معطل نکند. live_seconds = 0 یعنی خاموش."""
    while True:
        cfg = sql_cfg(read_config())
        wait = float(cfg.get("live_seconds") or 0)
        if wait <= 0:
            time.sleep(30)
            continue
        try:
            if STORE.live_step(cfg):
                publish()
            STATE["live_error"] = None
        except Exception as e:  # قطع اتصال؛ sql_worker هم همین خطا را نشان می‌دهد
            STATE["live_error"] = str(e)
            wait = max(wait, 30)
        time.sleep(wait)


def start():
    STORE.load_cache(sql_cfg(read_config()))
    publish()
    threading.Thread(target=sql_worker, daemon=True).start()
    threading.Thread(target=live_worker, daemon=True).start()


def ctx() -> dict:
    d = STATE["data"]
    if d is None:
        raise HTTPException(409, STATE["error"] or "داده‌ای بارگذاری نشده است.")
    cfg = read_config()
    m = d["meta"]
    return {
        "wd_elapsed": cfg.get("wd_elapsed") or m.get("wd_elapsed_file") or 1,
        "wd_total": cfg.get("wd_total") or m.get("wd_total_file") or 26,
        "today": m.get("today"),  # میانگین و پیش‌بینی ماه جاری فقط از روزهای کامل‌شده (قبل از امروز)
        "workdays": workdays(d),  # مخرج میانگین روزانه برای بازه‌های دلخواه
    }


def workdays(d: dict):
    """روزهای کاری تقویم کارآمد (همه به‌جز جمعه)، مرتب؛ None اگر تقویم هنوز خوانده نشده."""
    p = d.get("plan_inputs")
    if not p or p.get("calendar") is None:
        return None
    cal = p["calendar"]
    c = STATE.get("workdays")
    if not c or c[0] is not cal:
        c = (cal, np.sort(cal.loc[cal["workday"], "date"].to_numpy(dtype=object)))
        STATE["workdays"] = c
    return c[1]


def filters(req: Request) -> dict:
    q = req.query_params
    f = {"date_from": q.get("date_from") or None, "date_to": q.get("date_to") or None, "vat": q.get("vat") == "1"}
    for k in list(A.FILTER_FIELDS) + ["inv_type"]:
        vals = q.getlist(k)
        if vals:
            f[k] = vals
    if not f["date_from"] and not f["date_to"] and STATE["data"] is not None:
        # بدون فیلتر تاریخ = ماه جاری (با پیش‌بینی پایان ماه)
        m = STATE["data"]["meta"]
        f.update(date_from=m["month_from"], date_to=m["month_to"], default_period=True)
    return f


def with_vat(df: pd.DataFrame | None, f: dict) -> pd.DataFrame | None:
    """حالت «با ارزش افزوده»: مبلغ خالص هر سطر = قابل پرداخت کارآمد (PriceP، پس از همه تخفیف‌ها + ارزش افزوده)،
    تا فروش، برگشتی و درخواست با «مبلغ کل» گزارش‌های کارآمد یکی شوند. ناخالص و تخفیف‌ها تغییر نمی‌کنند."""
    if df is None or not f.get("vat"):
        return df
    return df.assign(net=df["payable"])


def frames(req: Request):
    d = STATE["data"]
    c = ctx()
    f = filters(req)
    tx = with_vat(A.apply_filters(d["sales"], f, True), f)
    rq = with_vat(A.apply_filters(d["requests"], f, False), f)
    if f.get("inv_type") and rq is not None and "فروش" not in f["inv_type"]:
        rq = rq.iloc[0:0]
    return tx, rq, c, f


def top(g: pd.DataFrame, n: int, cols: list[str]) -> list[dict]:
    return A.records(g.head(n)[[c for c in cols if c in g.columns]])


# ---------------------------------------------------------------- دسته شعب (A / B)
DEFAULT_TIERS = {"A": ["هیبرید تهران", "هیبرید آذربایجان غربی", "هیبرید خراسان", "هیبرید کرمان", "هیبرید اصفهان"]}


def branch_tiers() -> dict:
    return read_config().get("branch_tiers") or DEFAULT_TIERS


def tier_of(branch: str, tiers: dict | None = None) -> str:
    """A: شعب فهرست‌شده در config؛ B: بقیه هیبریدها؛ «سایر»: شعب غیرهیبرید (زنجیره‌ای، اینترنتی، ...)."""
    tiers = tiers or branch_tiers()
    for t, names in tiers.items():
        if branch in names:
            return t
    return "B" if "هیبرید" in str(branch) else "سایر"


def top_by_tier(g: pd.DataFrame, n: int, cols: list[str]) -> dict:
    """n مورد برتر کل و هر دسته شعبه؛ g باید ستون branch داشته باشد."""
    tiers = branch_tiers()
    g = g.assign(tier=g["branch"].map(lambda b: tier_of(b, tiers)))
    out = {"all": top(g, n, cols + ["tier"])}
    for t in sorted(set(g["tier"])):
        out[t] = top(g[g["tier"] == t], n, cols + ["tier"])
    return out


BASE_COLS = ["key", "label", "net", "gross", "qty", "sales_net", "returns_net", "return_rate", "disc_rate",
             "invoices", "customers", "sku", "share", "avg_invoice", "daily_avg", "forecast",
             "req_net", "req_docs", "req_conv", "req_forecast", "last_date"]


# ---------------------------------------------------------------- data source endpoints
def _ts(t: float) -> str | None:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) if t else None


@app.get("/api/sources")
def sources():
    cfg = read_config()
    d = STATE["data"]
    try:
        s = sql_source.settings(sql_source.read_env(ENV_FILE))
        conn = {"server": s["server"], "database": s["database"], "username": s["username"]}
    except loader.DataError as e:
        conn = {"conn_error": str(e)}
    return {"meta": d["meta"] if d else None, "error": STATE["error"],
            "wd_elapsed": cfg.get("wd_elapsed"), "wd_total": cfg.get("wd_total"),
            "sql": {**sql_cfg(cfg), **conn, "error": STATE["sql_error"], "busy": STATE["busy"],
                    "fetching": STORE.fetching or STATE.get("publishing"),
                    "queued": sorted(STORE.force_months | ({STORE.months[0]["month"]} if STORE.force_current and STORE.months else set())),
                    "live_checked": _ts(STORE.live_checked), "live_changed": _ts(STORE.live_changed),
                    "live_error": STATE.get("live_error")},
            "stamp": STATE["stamp"]}


@app.get("/api/stamp")
def stamp():
    return {"stamp": STATE["stamp"]}


class SqlReq(BaseModel):
    branch_like: str | None = None
    refresh_minutes: float | None = None
    history_months: int | None = None
    history_from: str | None = None


@app.post("/api/sources/sql")
def save_sql(body: SqlReq):
    cfg = read_config()
    sc = sql_cfg(cfg)
    if body.branch_like is not None:
        sc["branch_like"] = body.branch_like.strip()
    if body.refresh_minutes is not None:
        sc["refresh_minutes"] = max(0.0, body.refresh_minutes)
    if body.history_months is not None:
        sc["history_months"] = min(max(1, body.history_months), 60)
    if body.history_from is not None:
        sc["history_from"] = body.history_from.strip()
    cfg["sql"] = sc
    write_config(cfg)
    STORE.request_refresh()
    return sources()


@app.post("/api/sources/refresh")
def refresh_now():
    """ماه جاری در اولین فرصت دوباره خوانده می‌شود (اگر ماه دیگری در حال دریافت باشد، بعد از آن)."""
    STORE.request_refresh()
    return sources()


class MonthsReq(BaseModel):
    months: list[str] | None = None   # خالی = همه ماه‌های تاریخچه


@app.post("/api/sources/refresh_months")
def refresh_months(body: MonthsReq):
    """ماه‌های انتخاب‌شده (مثلاً ماه قبل که هنوز تسویه و اصلاح می‌شود) به صف خواندن دوباره اضافه می‌شوند."""
    known = [m["month"] for m in STORE.months]
    months = body.months or known
    bad = [m for m in months if m not in known]
    if bad:
        raise HTTPException(400, f"ماه نامعتبر: {', '.join(bad)}")
    STORE.request_months(months)
    return sources()


class Settings(BaseModel):
    wd_elapsed: float | None = None
    wd_total: float | None = None


@app.put("/api/settings")
def settings(body: Settings):
    cfg = read_config()
    cfg["wd_elapsed"] = body.wd_elapsed or None
    cfg["wd_total"] = body.wd_total or None
    write_config(cfg)
    return sources()


# ---------------------------------------------------------------- dashboard endpoints
def _meta_payload(d: dict) -> dict:
    s, r = d["sales"], d["requests"]
    both = pd.concat([s, r]) if r is not None else s

    def opts(col, key=None):
        key = key or col
        g = both.groupby(key)[col].agg(lambda x: x.value_counts().index[0]).sort_values()
        return [{"value": k, "label": v} for k, v in g.items()]

    mode = lambda x: x.value_counts().index[0]
    sellers = both.groupby("seller_key").agg(label=("seller", mode), branch=("branch", mode),
                                             code=("seller_code", "first"),
                                             supervisors=("supervisor", lambda x: sorted(set(x))))
    sup_branch = both.groupby("supervisor")["branch"].agg(mode)
    return {
        "file": d["meta"],
        "dates": sorted(both["date"].unique().tolist()),
        "sales_dates": sorted(s["date"].unique().tolist()),
        "options": {
            "branch": opts("branch"),
            # سرپرست با شعبه‌اش و فروشنده با شعبه و سرپرست‌هایش، تا فهرست‌ها با فیلتر والد محدود شوند
            "supervisor": [{"value": k, "label": k, "group": v} for k, v in sup_branch.sort_index().items()],
            "seller": [{"value": k, "label": f"{v.label} ({v.code})", "group": v.branch, "supervisors": v.supervisors}
                       for k, v in sellers.sort_values("label").iterrows()],
            "brand": opts("brand"),
            "category": opts("category"),
            # زیرگروه‌ها با گروه کلی‌شان، تا فهرست با فیلتر گروه کالا محدود شود
            "group": [{"value": k, "label": k, "group": v} for k, v in
                      both.groupby("product_group")["category"].agg(lambda x: x.value_counts().index[0]).sort_index().items()],
            "city": opts("city"),
            "payment": opts("payment"),
            "inv_type": [{"value": v, "label": v} for v in sorted(s["inv_type"].unique())],
        },
    }


@app.get("/api/meta")
def meta():
    d = STATE["data"]
    c = ctx()
    # گزینه‌های فیلتر روی کل تاریخچه محاسبه و تا تغییر بعدی داده کش می‌شوند
    mc = STATE["meta_cache"]
    if not mc or mc[0] != STATE["stamp"]:
        mc = (STATE["stamp"], _meta_payload(d))
        STATE["meta_cache"] = mc
    tiers = branch_tiers()
    return {**mc[1], "ctx": {k: v for k, v in c.items() if k != "workdays"},
            "branch_tier": {o["value"]: tier_of(o["value"], tiers) for o in mc[1]["options"]["branch"]}}


@app.get("/api/monthly")
def monthly(req: Request):
    """روند ماهانه کل تاریخچه با همه فیلترها به‌جز تاریخ."""
    d = STATE["data"]
    ctx()
    f = {k: v for k, v in filters(req).items() if k not in ("date_from", "date_to", "default_period")}
    return {"months": A.monthly(with_vat(A.apply_filters(d["sales"], f, True), f),
                                with_vat(A.apply_filters(d["requests"], f, False), f)),
            "current": d["meta"]["month"]}


@app.get("/api/overview")
def overview(req: Request):
    tx, rq, c, f = frames(req)
    cols = ["key", "label", "net", "share", "req_net"]
    return {
        "kpis": A.kpis(tx, rq, c, f),
        "trend": A.trend(tx, rq),
        "branches": top(A.group_metrics(tx, rq, "branch", c, f), 40, cols),
        "brands": top(A.group_metrics(tx, None, "brand", c, f), 40, cols),
        # همه گروه‌ها با تعداد؛ فرانت‌اند ۱۲ گروه برتر را بر اساس تعداد یا مبلغ جدا می‌کند
        "categories": top(A.group_metrics(tx, None, "category", c, f), 200, cols + ["qty"]),
        # برترین‌ها: کل و جدا برای هر دسته شعبه (A / B / سایر)
        "sellers": top_by_tier(A.group_metrics(tx, None, "seller", c, f, ["branch"]), 10, cols + ["branch"]),
        "customers": top_by_tier(A.group_metrics(tx, None, "customer", c, f, ["branch", "city"]), 10, cols + ["branch"]),
        "discounts": {k: A.discount_by(tx, col) for k, col in
                      (("branch", "branch"), ("category", "category"), ("group", "product_group"))},
    }


@app.get("/api/hybrid")
def hybrid(req: Request):
    tx, rq, c, f = frames(req)
    g = A.group_metrics(tx, rq, "branch", c, f, ["supervisor"])
    heat = tx.groupby(["branch", "date"])["net"].sum().reset_index()
    # درخواست خالص (بدون باطل‌شده‌ها) هر شعبه در هر روز
    heat_req = rq.groupby(["branch", "date"])["net"].sum().reset_index() if rq is not None and len(rq) else heat.iloc[0:0]
    sup = A.group_metrics(tx, rq, "supervisor", c, f, ["branch"])
    return {"kpis": A.kpis(tx, rq, c, f), "branches": A.records(g[[x for x in BASE_COLS + ["supervisor"] if x in g]]),
            "supervisors": A.records(sup[[x for x in BASE_COLS + ["branch"] if x in sup]]),
            "heat": A.records(heat), "heat_req": A.records(heat_req)}


@app.get("/api/team")
def team(req: Request):
    tx, rq, c, f = frames(req)
    g = A.group_metrics(tx, rq, "seller", c, f, ["branch", "supervisor", "seller_code"])
    g["rank"] = g["net"].rank(ascending=False, method="min")
    sup = A.group_metrics(tx, rq, "supervisor", c, f)
    return {"kpis": A.kpis(tx, rq, c, f),
            "sellers": A.records(g[[x for x in BASE_COLS + ["branch", "supervisor", "seller_code", "rank"] if x in g]]),
            "supervisors": A.records(sup[[x for x in BASE_COLS if x in sup]])}


@app.get("/api/inactive")
def inactive(req: Request):
    """فروشندگان غیرفعال: از ۱۴۰۴ درخواست داشته‌اند ولی از ماه since (پیش‌فرض اردیبهشت ۱۴۰۵) هیچ درخواستی ندارند.
    کل تاریخچه بارگذاری‌شده بررسی می‌شود (فیلتر تاریخ اعمال نمی‌شود؛ بقیه فیلترها و ارزش افزوده بله)."""
    d = STATE["data"]
    ctx()
    since = (req.query_params.get("since") or "1405/02")[:7] + "/01"
    f = {k: v for k, v in filters(req).items() if k not in ("date_from", "date_to", "default_period")}
    s = with_vat(A.apply_filters(d["sales"], f, True), f)
    r = with_vat(A.apply_filters(d["requests"], f, False), f)
    if r is None or not len(r):
        return {"since": since, "rows": [], "months": [], "active": 0, "no_request": 0}
    key = "seller_key"
    mode = lambda x: x.value_counts().index[0]
    both = pd.concat([s[[key, "seller", "seller_code", "branch", "supervisor", "date"]],
                      r[[key, "seller", "seller_code", "branch", "supervisor", "date"]]])
    g = both.groupby(key, observed=True).agg(label=("seller", mode), seller_code=("seller_code", "first"),
                                             branch=("branch", mode), supervisor=("supervisor", mode),
                                             first_date=("date", "min"), last_any=("date", "max"))
    sale, ret = s[~s["is_return"]], s[s["is_return"]]
    g["last_req"] = r.groupby(key, observed=True)["date"].max()
    g["last_sale"] = sale.groupby(key, observed=True)["date"].max()
    g["last_return"] = ret.groupby(key, observed=True)["date"].max()
    g["req_docs"] = r.groupby(key, observed=True)["inv_id"].nunique()
    g["net"] = s.groupby(key, observed=True)["net"].sum()
    g["req_net"] = r.groupby(key, observed=True)["net"].sum()
    after = s[s["date"] >= since]
    g["sales_after"] = after[~after["is_return"]].groupby(key, observed=True)["net"].sum()
    g["returns_after"] = -after[after["is_return"]].groupby(key, observed=True)["net"].sum()
    g = g.fillna({"req_docs": 0, "net": 0, "req_net": 0, "sales_after": 0, "returns_after": 0})
    had = g[g["req_docs"] > 0]
    out = had[had["last_req"] < since].copy()
    out["status"] = np.where(out["sales_after"] > 0, "فاکتور مستقیم بدون درخواست",
                             np.where(out["returns_after"] > 0, "فقط برگشتی", "بدون فعالیت"))
    out = out.sort_values("last_req", ascending=False)

    # تاریخچه ماهانه هر فروشنده غیرفعال
    months = sorted(set(s["month"]) | set(r["month"]))
    ks = set(out.index)
    ss, rr = s[s[key].isin(ks)], r[r[key].isin(ks)]
    piv = lambda df, val, fn: df.pivot_table(index=key, columns="month", values=val, aggfunc=fn, fill_value=0, observed=True) \
        .reindex(index=out.index, columns=months, fill_value=0)
    h_net = piv(ss, "net", "sum")
    h_ret = piv(ss[ss["is_return"]].assign(net=lambda x: -x["net"]), "net", "sum")
    h_req = piv(rr, "inv_id", "nunique")
    h_reqnet = piv(rr, "net", "sum")
    h_inv = A._invoice_counts(ss, [key, "month"]).unstack(fill_value=0).reindex(index=out.index, columns=months, fill_value=0) \
        if len(ss) else h_req * 0
    rows = A.records(out.reset_index().rename(columns={key: "key"}))
    for row in rows:
        k = row["key"]
        row["hist"] = {"net": [float(x) for x in h_net.loc[k]], "returns": [float(x) for x in h_ret.loc[k]],
                       "req": [int(x) for x in h_req.loc[k]], "req_net": [float(x) for x in h_reqnet.loc[k]],
                       "invoices": [int(x) for x in h_inv.loc[k]]}
    return {"since": since, "months": months, "rows": rows,
            "active": int((had["last_req"] >= since).sum()), "no_request": int((g["req_docs"] == 0).sum())}


@app.get("/api/products")
def products(req: Request):
    tx, rq, c, f = frames(req)
    p = A.group_metrics(tx, rq, "product", c, f, ["brand", "category", "product_group"])
    abc = A.pareto(p)
    p["abc"] = p["key"].map(abc.pop("abc", {})).fillna("-")
    bc = tx.groupby(["brand", "category"])["net"].sum().reset_index()
    brands = A.group_metrics(tx, rq, "brand", c, f)
    cats = A.group_metrics(tx, rq, "category", c, f)
    groups = A.group_metrics(tx, rq, "group", c, f, ["category", "brand"])
    return {"kpis": A.kpis(tx, rq, c, f),
            "brands": A.records(brands[[x for x in BASE_COLS if x in brands]]),
            "categories": A.records(cats[[x for x in BASE_COLS if x in cats]]),
            "groups": A.records(groups[[x for x in BASE_COLS + ["category", "brand"] if x in groups]]),
            "products": A.records(p[[x for x in BASE_COLS + ["brand", "category", "product_group", "abc"] if x in p]]),
            "brand_category": A.records(bc[bc["net"] > 0]), "pareto": abc}


@app.get("/api/customers")
def customers(req: Request):
    tx, rq, c, f = frames(req)
    g = A.group_metrics(tx, rq, "customer", c, f, ["branch", "city", "seller"])
    # اولین خرید هر مشتری در کل تاریخچه بارگذاری‌شده (فقط فاکتور فروش با تعداد مثبت)
    s_all = STATE["data"]["sales"]
    first = s_all[~s_all["is_return"] & (s_all["qty"] > 0)].groupby("customer_code")["date"].min()
    g["first_date"] = g["key"].map(first)
    lo, hi = f.get("date_from") or "", f.get("date_to") or "9999"
    new_customers = int(((g["first_date"] >= lo) & (g["first_date"] <= hi) & (g["net"] > 0)).sum())
    g["days_active"] = g["key"].map(tx.groupby("customer_code")["date"].nunique()).fillna(0)
    ab = A.pareto(g)
    g["abc"] = g["key"].map(ab.pop("abc", {})).fillna("-")
    # توزیع مشتریان بر اساس دفعات خرید (روزهای دارای فاکتور مؤثر)
    freq = g[g["invoices"] > 0]["invoices"].clip(upper=5).value_counts().sort_index()
    master = None
    cm = STATE["data"]["customers"]
    if cm is not None and len(cm):
        # فقط شعبه‌های فیلترشده؛ خرید و درخواست در محدوده همه فیلترهای فعال (تاریخ، برند، ...)
        listed = sorted(cm["branch"].unique())
        if f.get("branch"):
            cm = cm[cm["branch"].isin(f["branch"])]
        if len(cm):
            pos = tx.groupby("customer_code")["qty"].sum()
            bought = set(pos[pos > 0].index)
            asked = set(rq["customer_code"]) if rq is not None else set()
            per = cm.groupby("branch").agg(
                registered=("customer_code", "size"),
                purchased=("customer_code", lambda s: int(s.isin(bought).sum())),
                requested=("customer_code", lambda s: int(s.isin(asked).sum())),
                active=("customer_code", lambda s: int(s.isin(bought | asked).sum())))
            master = {"by_branch": A.records(per.reset_index()),
                      "by_trade": A.records(cm.groupby("trade").size().rename("count").reset_index()
                                            .sort_values("count", ascending=False)) if "trade" in cm else []}
        else:
            master = {"by_branch": [], "by_trade": [], "listed_branches": listed}
    return {"kpis": A.kpis(tx, rq, c, f), "new_customers": new_customers, "history_from": s_all["date"].min(),
            "customers": A.records(g[[x for x in BASE_COLS + ["branch", "city", "seller", "first_date",
                                                               "days_active", "abc"] if x in g]]),
            "pareto": ab,
            "frequency": [{"k": int(k), "count": int(v)} for k, v in freq.items()],
            "cities": A.records(A.group_metrics(tx, None, "city", c, f).head(20)[["key", "label", "net", "customers"]]),
            "master": master}


@app.get("/api/analysis")
def analysis(req: Request):
    tx, rq, c, f = frames(req)
    sale = tx[~tx["is_return"]]
    ret = tx[tx["is_return"]]

    disc_by = lambda col: A.discount_by(tx, col)

    def ret_by(col, label=None):
        label = label or col
        g = ret.groupby(col).agg(label=(label, "first"), returns=("net", lambda s: -s.sum()),
                                 qty=("qty", lambda s: -s.sum())).reset_index().rename(columns={col: "key"})
        s = sale.groupby(col)["net"].sum()
        g["rate"] = g["returns"] / g["key"].map(s).replace(0, np.nan)
        return A.records(g.sort_values("returns", ascending=False).head(25))

    pay = tx.groupby("payment").agg(net=("net", "sum"), invoices=("customer_code", "size")).reset_index()
    pay["invoices"] = pay["payment"].map(A._invoice_counts(tx, ["payment"])).fillna(0)
    status = None
    if rq is not None and len(rq):
        st = rq.groupby(["branch", "status"])["net"].sum().unstack(fill_value=0)
        st = st.rename(columns={0: "open", 1: "done"}).reset_index()
        for k in ("open", "done"):
            if k not in st:
                st[k] = 0
        status = A.records(st.sort_values("done", ascending=False))
    price = sale[sale["qty"] > 0].copy()
    price["eff_price"] = price["net"] / price["qty"]
    bins = [0, 1e6, 2e6, 3e6, 5e6, 1e7, 5e7, np.inf]
    # مرزها به ریال؛ برچسب‌ها به تومان (۱ تومان = ۱۰ ریال)
    labels = ["< ۱۰۰ هزار", "۱۰۰–۲۰۰ هزار", "۲۰۰–۳۰۰ هزار", "۳۰۰–۵۰۰ هزار", "۵۰۰ هزار–۱ میلیون",
              "۱–۵ میلیون", "> ۵ میلیون"]
    price["band"] = pd.cut(price["eff_price"], bins=bins, labels=labels, right=False)
    pb = price.groupby("band", observed=False).agg(net=("net", "sum"), qty=("qty", "sum")).reset_index()
    return {"kpis": A.kpis(tx, rq, c, f),
            "disc_category": disc_by("category"), "disc_group": disc_by("product_group"), "disc_branch": disc_by("branch"),
            "ret_branch": ret_by("branch"), "ret_category": ret_by("category"), "ret_group": ret_by("product_group"),
            "ret_product": ret_by("product_code", "product"),
            "payment": A.records(pay.sort_values("net", ascending=False)),
            "req_status": status, "price_bands": A.records(pb.rename(columns={"band": "key"})),
            "trend": A.trend(tx, rq)}


@app.get("/api/detail/{dim}")
def detail(dim: str, key: str, req: Request):
    if dim not in A.DIMS:
        raise HTTPException(404, "بعد نامعتبر")
    tx, rq, c, f = frames(req)
    col, labcol = A.DIMS[dim]
    t = tx[tx[col] == key]
    r = rq[rq[col] == key] if rq is not None else None
    # محدوده والد، مثلاً گروه «اسپری مو» فقط در برند «پادینا»: within=brand:پادینا
    within = []
    for w in req.query_params.getlist("within"):
        wd, _, wk = w.partition(":")
        if wd not in A.DIMS or wd == dim or not wk:
            raise HTTPException(400, "محدوده نامعتبر")
        wcol, wlab = A.DIMS[wd]
        t = t[t[wcol] == wk]
        r = r[r[wcol] == wk] if r is not None else None
        within.append({"dim": wd, "key": wk})
    src = t if len(t) else (r if r is not None else t)
    if not len(src):
        raise HTTPException(404, "برای این مورد در محدوده فیلتر داده‌ای نیست.")
    label = src[labcol].value_counts().index[0]
    for w in within:
        w["label"] = src[A.DIMS[w["dim"]][1]].value_counts().index[0]
    scoped = {w["dim"] for w in within}
    # همه مقادیر هر بعد: تعداد کل و مهم‌ترین‌ها بر اساس فروش خالص (نه تعداد سطر)
    info = {}
    for k, (kc, lc) in (("branch", ("branch", "branch")), ("supervisor", ("supervisor", "supervisor")),
                        ("seller", ("seller_key", "seller")), ("brand", ("brand", "brand")),
                        ("category", ("category", "category")), ("group", ("product_group", "product_group")),
                        ("city", ("city", "city")),
                        ("route", ("route", "route")), ("payment", ("payment", "payment"))):
        if k == dim or k in scoped or kc not in src:
            continue
        g = src.groupby(kc).agg(net=("net", "sum"), label=(lc, "first")).sort_values("net", ascending=False)
        info[k] = {"count": int(len(g)),
                   "top": [{"key": str(i), "label": v} for i, v in g["label"].head(3).items()]}
    breakdowns = {}
    cols = ["key", "label", "net", "qty", "invoices", "customers", "share", "returns_net"]
    for d in ("branch", "supervisor", "seller", "brand", "category", "group", "product", "customer", "city"):
        if d == dim or d in scoped:
            continue
        g = A.group_metrics(t, None, d, c, f)
        if g["key"].nunique() > 1 or d in ("product", "customer"):
            breakdowns[d] = top(g, len(g), cols)  # همه موارد؛ نمودار ۱۲ مورد اول را نشان می‌دهد
    extra = {}
    if dim == "customer":
        cm = STATE["data"]["customers"]
        if cm is not None:
            m = cm[cm["customer_code"] == key]
            if len(m):
                extra["master"] = A.records(m.head(1))[0]
    code = src["seller_code"].iat[0] if dim == "seller" else (key if dim in ("product", "customer") else None)
    return {"dim": dim, "key": key, "code": code, "label": label, "within": within, "info": info, "kpis": A.kpis(t, r, c, f),
            "trend": A.trend(t, r), "breakdowns": breakdowns, "lines": A.lines(t), **extra}


# ---------------------------------------------------------------- گزارش‌های مشابه شیت‌های اکسل
def _dims(req: Request, default: str) -> list[str]:
    dims = [d for d in (req.query_params.get("dims") or default).split(",") if d]
    if not dims or any(d not in A.DIMS for d in dims):
        raise HTTPException(400, "ابعاد نامعتبر")
    return dims


def _report_day(req: Request, tx: pd.DataFrame) -> str:
    """روز گزارش؛ پیش‌فرض آخرین روز دارای فاکتور فروش در بازه انتخاب‌شده."""
    rd = req.query_params.get("report_day")
    dates = tx["date"] if len(tx) else STATE["data"]["sales"]["date"]
    return rd if rd else dates.max()


def _dates(f: dict) -> list[str]:
    d = STATE["data"]
    both = pd.concat([d["sales"]["date"], d["requests"]["date"]]) if d["requests"] is not None else d["sales"]["date"]
    ds = sorted(both.unique())
    return [x for x in ds if (not f.get("date_from") or x >= f["date_from"]) and (not f.get("date_to") or x <= f["date_to"])]


@app.get("/api/report_tree")
def report_tree(req: Request):
    tx, rq, c, f = frames(req)
    return A.report_tree(tx, rq, c, f, _dims(req, "branch,seller"), _report_day(req, tx))


@app.get("/api/category_matrix")
def category_matrix(req: Request):
    tx, rq, c, f = frames(req)
    cats = STATE["data"]["meta"].get("core_categories") or []
    return A.category_matrix(tx, _dims(req, "branch,seller"), cats)


@app.get("/api/daily_matrix")
def daily_matrix(req: Request):
    tx, rq, c, f = frames(req)
    metric = req.query_params.get("metric", "net")
    if metric not in ("net", "qty", "invoices"):
        raise HTTPException(400, "شاخص نامعتبر")
    source = req.query_params.get("source", "sales")
    df = rq if source == "requests" else tx
    if df is None:
        raise HTTPException(404, "شیت درخواست در فایل نیست.")
    days, _ = A.elapsed_days(c, f, tx, rq)
    return A.daily_matrix(df, _dims(req, "branch,seller"), metric, _dates(f), days)


@app.get("/api/brand_share")
def brand_share(req: Request):
    tx, rq, c, f = frames(req)
    brands = tx.groupby("brand")["net"].sum().sort_values(ascending=False)
    return A.brand_share(tx, [b for b in brands.index if b != loader.UNKNOWN])


# ---------------------------------------------------------------- برنامه‌ریزی و تارگت (planning.py)
def planner() -> PL.Planner:
    """یک Planner برای هر نسخه داده و تنظیمات؛ قیمت‌ها، منحنی ماه و بک‌تست داخل آن کش می‌شوند."""
    c = ctx()
    cfg = read_config()
    key = (STATE["stamp"], json.dumps(cfg.get("plan") or {}, sort_keys=True), c["wd_total"], c["wd_elapsed"])
    p = STATE["planner"]
    if not p or p[0] != key:
        p = (key, PL.Planner(STATE["data"], cfg, c))
        STATE["planner"] = p
    return p[1]


def plan_months(pl: PL.Planner) -> list[str]:
    """ماه‌های قابل برنامه‌ریزی: ماه جاری و دو ماه بعد."""
    return [PL.month_add(pl.cur, k) for k in range(3)]


def _check_month(pl: PL.Planner, month: str | None) -> str:
    month = month or pl.cur
    if month not in plan_months(pl) and month not in PLANS.months():
        raise HTTPException(400, "ماه نامعتبر")
    return month


CELL_COLS = ["key", "branch", "category", "main", "base", "idx", "suggest", "final", "override", "jump",
             "last", "last_net", "ly", "ly_net", "price_net", "price_gross", "target_net", "target_gross"]


def _plan_payload(pl: PL.Planner, plan: dict, t: dict) -> dict:
    cells = t["cells"]
    out = {"month": t["month"], "main": t["main"], "wd": t["wd"], "wd_calendar": t["wd_calendar"],
           "warnings": t["warnings"], "last_month": t.get("last_month"), "ly_month": t.get("ly_month"),
           "plan": {k: plan.get(k) for k in ("growth", "wd", "locked", "locked_at", "updated_at", "saved")},
           "n_overrides": len(plan.get("overrides") or {}),
           "base_months": {b: v["base_months"] for b, v in (t.get("info") or {}).get("branches", {}).items()},
           "season": {"available": pl.season.get("available"), "factor_mm": t["month"][5:7]}}
    if not len(cells):
        return {**out, "cells": [], "branches": [], "categories": []}
    cols = [c for c in CELL_COLS if c in cells]
    out["cells"] = A.records(cells[cols])
    sums = ["target_net", "target_gross", "last_net", "ly_net"]
    b = cells.groupby("branch")[sums].sum().reset_index()
    b["overrides"] = b["branch"].map(cells[cells["override"].astype(bool)].groupby("branch").size()).fillna(0)
    out["branches"] = A.records(b.sort_values("target_net", ascending=False))
    cg = cells.groupby("category")[["suggest", "final", "last", "ly"] + sums].sum().reset_index()
    cg["main"] = cg["category"].isin(t["main"])
    out["categories"] = A.records(cg.sort_values("target_net", ascending=False))
    out["total"] = {k: float(cells[k].sum()) for k in sums}
    return out


@app.get("/api/plan/overview")
def plan_overview():
    pl = planner()
    months = []
    for m in plan_months(pl):
        p = PLANS.get(m)
        months.append({"month": m, "saved": p.get("saved", False), "locked": p.get("locked", False),
                       "current": m == pl.cur, "wd_calendar": pl.cal.wd_month(m), "abnormal": PL.is_abnormal(m, pl.ps)})
    se = pl.season
    return {"current": pl.cur, "today": pl.today, "months": months, "saved_months": PLANS.months(),
            "settings": pl.ps, "defaults": PL.DEFAULTS, "inputs_fetched": pl.inputs_fetched,
            "season": {"available": se.get("available"), "years": se.get("years"), "first": se.get("first"),
                       "last": se.get("last"), "total": se.get("total"), "by_cat": se.get("by_cat"),
                       "applied": {mm: PL.season_factor(se, pl.ps, "", mm) for mm in (f"{i:02d}" for i in range(1, 13))}},
            "curve": pl.pace_curve(), "main": pl.main_categories(),
            "branches": sorted(pl.first_month), "categories": sorted(pl.s["category"].unique().tolist())}


@app.get("/api/plan/target")
def plan_target(month: str | None = None):
    pl = planner()
    month = _check_month(pl, month)
    plan = PLANS.get(month)
    return _plan_payload(pl, plan, pl.target(plan))


class PlanReq(BaseModel):
    month: str
    growth: float | None = None
    wd: float | None = None
    clear_wd: bool = False
    overrides: dict[str, float | None] | None = None
    action: str | None = None   # lock | unlock | reset


@app.put("/api/plan/target")
def plan_save(body: PlanReq):
    pl = planner()
    month = _check_month(pl, body.month)
    plan = PLANS.get(month)
    if body.action == "unlock":
        plan.update(locked=False, locked_at=None, snapshot=None)
    elif plan.get("locked"):
        raise HTTPException(409, "تارگت این ماه قفل است؛ برای تغییر، اول قفل را باز کنید.")
    else:
        if body.growth is not None:
            plan["growth"] = min(max(body.growth, -0.9), 5.0)
        if body.wd is not None:
            plan["wd"] = min(max(body.wd, 1.0), 31.0)
        if body.clear_wd:
            plan["wd"] = None
        if body.overrides:
            ov = dict(plan.get("overrides") or {})
            for k, v in body.overrides.items():
                if PL.SEP not in k:
                    raise HTTPException(400, "کلید نامعتبر")
                if v is None:
                    ov.pop(k, None)
                else:
                    ov[k] = max(float(v), 0.0)
            plan["overrides"] = ov
        if body.action == "reset":
            plan["overrides"] = {}
        if body.action == "lock":
            t = pl.target(plan)
            if not len(t["cells"]):
                raise HTTPException(409, "تارگتی برای قفل کردن وجود ندارد.")
            keep = ["key", "branch", "category", "base", "idx", "suggest", "final", "override", "price_net", "price_gross"]
            now = time.strftime("%Y-%m-%d %H:%M")
            plan.update(locked=True, locked_at=now, snapshot={
                "created": now, "cells": A.records(t["cells"][keep]), "price_book": pl.price_book(),
                "info": t.get("info"), "wd": t["wd"], "main": t["main"]})
    plan = PLANS.put(plan)
    return _plan_payload(pl, plan, pl.target(plan))


@app.get("/api/plan/track")
def plan_track():
    pl = planner()
    plan = PLANS.get(pl.cur)
    t = pl.track(plan)
    out = _plan_payload(pl, plan, t)
    if len(t["cells"]):
        cols = CELL_COLS + ["actual", "actual_net", "basis", "basis_net", "ach", "ach_net", "forecast", "forecast_net",
                            "need_daily", "need_daily_net", "cur_daily", "cur_daily_net", "ratio", "status"]
        out["cells"] = A.records(t["cells"][[c for c in cols if c in t["cells"]]])
        out["branches"] = A.records(t["branches"].sort_values("target_net", ascending=False))
        out["categories"] = A.records(t["categories"].sort_values("target_net", ascending=False))
        out["total"] = t["total"]
    out.update(elapsed=t["elapsed"], wd_total=t["wd_total"], expected_share=t["expected_share"],
               thresholds={"green": pl.ps["green"], "yellow": pl.ps["yellow"]})
    return out


@app.get("/api/plan/compare")
def plan_compare(req: Request):
    pl = planner()
    q = req.query_params
    metric = q.get("metric", "qty")
    if metric not in ("qty", "net", "gross"):
        raise HTTPException(400, "شاخص نامعتبر")
    year = q.get("year") or pl.cur[:4]
    # تارگت ماه‌هایی که تارگت ذخیره‌شده دارند، به‌علاوه پیش‌نویس ماه جاری
    targets = {}
    for m in sorted(set(PLANS.months()) | {pl.cur}):
        if m[:4] == year:
            t = pl.target(PLANS.get(m))
            if len(t["cells"]):
                targets[m] = t["cells"]
    return pl.compare(year, q.getlist("category"), q.getlist("branch"), metric, q.get("lfl") == "1", targets)


@app.get("/api/plan/eval")
def plan_eval():
    pl = planner()
    if not hasattr(pl, "_bt"):
        pl._bt = pl.backtest(8)
    # تاریخچه تحقق: ماه‌های بسته‌ای که تارگت ذخیره‌شده دارند
    history = []
    for m in PLANS.months():
        if m >= pl.cur or m not in pl.months:
            continue
        p = PLANS.get(m)
        t = pl.target(p)
        if not len(t["cells"]):
            continue
        act = pl.mbc.loc[m].groupby(level="branch")["net"].sum()
        g = t["cells"].groupby("branch")["target_net"].sum()
        for b, v in g.items():
            history.append({"month": m, "branch": b, "target_net": float(v), "actual_net": float(act.get(b, 0.0)),
                            "ach": float(act.get(b, 0.0) / v) if v else None, "locked": bool(p.get("locked"))})
    return {"backtest": pl._bt, "history": history, "curve": pl.pace_curve()}


class PlanSettings(BaseModel):
    abnormal_months: list[str] | None = None
    farvardin_abnormal: bool | None = None
    base_months: int | None = None
    season: bool | None = None
    season_shrink: float | None = None
    green: float | None = None
    yellow: float | None = None
    price_alert: float | None = None


@app.put("/api/plan/settings")
def plan_settings(body: PlanSettings):
    cfg = read_config()
    ps = dict(cfg.get("plan") or {})
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "abnormal_months":
            v = sorted({m.strip().replace("-", "/")[:7] for m in v if len(m.strip()) >= 7})
        elif k == "base_months":
            v = min(max(int(v), 1), 6)
        elif k in ("season_shrink", "green", "yellow", "price_alert"):
            v = min(max(float(v), 0.0), 2.0)
        ps[k] = v
    cfg["plan"] = ps
    write_config(cfg)
    return plan_overview()


# ---------------------------------------------------------------- موجودی و پیشنهاد سفارش (inventory.py)
INV_OVERVIEW: dict = {"key": None, "data": None}
INV_LOCK = threading.Lock()


@app.get("/api/inventory")
def inventory(branch: str | None = None, refresh: bool = False):
    d = STATE["data"]
    ctx()
    cfg = read_config()
    branches = INV.hybrid_branches(d)
    branch = branch or INV.settings(cfg)["branch"]
    if branch not in branches:
        raise HTTPException(400, f"شعبه «{branch}» در داده فروش نیست.")
    try:
        src = INV_SRC.get(branch, force=refresh)
        r = INV.compute(d, src, cfg, branch=branch)
    except loader.DataError as e:
        raise HTTPException(409, str(e))
    return {**r, "rows": A.records(r["rows"]), "suppliers": A.records(r["suppliers"]), "branches": branches}


@app.get("/api/inventory/overview")
def inventory_overview(refresh: bool = False):
    """خلاصه همه شعب هیبرید؛ تا تغییر داده، تنظیمات یا موجودی کش می‌شود."""
    d = STATE["data"]
    ctx()
    cfg = read_config()
    with INV_LOCK:
        branches = INV.hybrid_branches(d)
        if refresh:
            INV_SRC.get(branches[0], force=True)
        fetched = INV_SRC.get(branches[0])["fetched"]
        key = (STATE["stamp"], json.dumps(cfg.get("inventory") or {}, sort_keys=True),
               json.dumps(cfg.get("plan") or {}, sort_keys=True), fetched)
        if INV_OVERVIEW["key"] == key:
            return INV_OVERVIEW["data"]
        out = []
        for b in branches:
            row = {"branch": b}
            try:
                r = INV.compute(d, INV_SRC.get(b), cfg, branch=b)
                k = r["kpis"]
                rows = r["rows"]
                row.update(k)
                row.update(inactive=r["inactive"], last_sale=r["last_branch_sale"], break_month=r["break_month"],
                           data_issue=r["data_issue"],
                           base_months=r["base_months"], deadline=r["orders"]["deadline"],
                           days_to_deadline=r["orders"]["days_to_deadline"],
                           items_a=int((rows["abc"] == "A").sum()), items_b=int((rows["abc"] == "B").sum()),
                           monthly_demand=float(rows["fc_now"].sum()),
                           cover_a=float(rows.loc[rows["abc"] == "A", "stock"].clip(lower=0).sum()
                                         / max(rows.loc[rows["abc"] == "A", "fc_now"].sum(), 1e-9)))
            except loader.DataError as e:
                row["error"] = str(e)
            out.append(row)
        res = {"branches": A.records(pd.DataFrame(out)), "today": d["meta"].get("today"),
               "fetched": time.strftime("%Y-%m-%d %H:%M", time.localtime(fetched))}
        INV_OVERVIEW.update(key=key, data=res)
        return res


class InvSettings(BaseModel):
    branch: str | None = None      # شعبه‌ای که بعد از ذخیره نمایش داده می‌شود (تنظیمات برای همه شعب یکی است)
    lead_days: int | None = None
    orders_per_month: int | None = None
    base_months: int | None = None
    a_safety: str | None = None
    z_a: float | None = None
    b_pct: float | None = None
    breadth: list[float] | None = None
    dead_days: int | None = None
    excess_months: float | None = None
    min_months_sold: int | None = None
    ly_weight: float | None = None
    break_detect: bool | None = None
    break_ratio: float | None = None
    inactive_days: int | None = None
    min_order_cartons: float | None = None
    min_gap_pct: float | None = None


@app.put("/api/inventory/settings")
def inventory_settings(body: InvSettings):
    cfg = read_config()
    s = dict(cfg.get("inventory") or {})
    for k, v in body.model_dump(exclude_none=True, exclude={"branch"}).items():
        if k == "lead_days":
            v = min(max(int(v), 0), 60)
        elif k == "orders_per_month":
            v = min(max(int(v), 1), 8)
        elif k == "base_months":
            v = min(max(int(v), 2), 12)
        elif k == "a_safety" and v not in ("data", "breadth"):
            raise HTTPException(400, "حالت safety نامعتبر")
        elif k == "z_a":
            v = min(max(float(v), 0.0), 3.0)
        elif k == "b_pct":
            v = min(max(float(v), 0.0), 2.0)
        elif k == "breadth":
            if len(v) != 3:
                raise HTTPException(400, "سه درصد برای safety بر اساس مشتری لازم است.")
            v = [min(max(float(x), 0.0), 2.0) for x in v]
        elif k == "dead_days":
            v = min(max(int(v), 15), 720)
        elif k == "excess_months":
            v = min(max(float(v), 1.0), 36.0)
        elif k == "min_months_sold":
            v = min(max(int(v), 1), 6)
        elif k == "ly_weight":
            v = min(max(float(v), 0.0), 1.0)
        elif k == "break_ratio":
            v = min(max(float(v), 0.1), 0.9)
        elif k == "inactive_days":
            v = min(max(int(v), 3), 120)
        elif k == "min_order_cartons":
            v = min(max(float(v), 0.0), 10.0)
        elif k == "min_gap_pct":
            v = min(max(float(v), 0.0), 0.9)
        s[k] = v
    cfg["inventory"] = s
    write_config(cfg)
    return inventory(branch=body.branch)


# ---------------------------------------------------------------- فروش زنجیره‌ای به مصرف‌کننده (sell-out)
SELLOUT = CS.SelloutStore(ROOT / "data" / "chain_store", ROOT / "data" / "cache" / "sql", ENV_FILE)
NO_MATCH = "بدون تطبیق در کارآمد"


def _product_info(d: dict | None) -> pd.DataFrame:
    """نام، برند و گروه هر کد کالا از فروش کارآمد (آخرین مقدار)."""
    if d is None:
        return pd.DataFrame(columns=["product", "brand", "category"])
    c = STATE.get("prod_info")
    if c and c[0] == STATE["stamp"]:
        return c[1]
    s = d["sales"][["product_code", "product", "brand", "brand_raw", "category"]]
    info = s.drop_duplicates("product_code", keep="last").set_index("product_code")
    STATE["prod_info"] = (STATE["stamp"], info)
    return info


def _guess_brand(name: str, aliases: dict) -> str:
    n = CS.norm(name).lower()
    for a, b in aliases.items():
        if a and a in n:
            return b
    return "سایر"


def _sellout_group(so: pd.DataFrame, si: pd.DataFrame, by: list[str], label: str) -> pd.DataFrame:
    """جمع sell-out و sell-in با کلید by؛ ستون label نام نمایشی."""
    a = so.groupby(by, dropna=False).agg(value=("value", "sum"), qty=("qty", "sum"), disc=("disc", "sum"),
                                         sku=("key", "nunique")).reset_index()
    if si is not None and len(si):
        b = si.groupby(by, dropna=False).agg(sellin_net=("net", "sum"), sellin_qty=("qty", "sum")).reset_index()
        a = a.merge(b, on=by, how="outer")
    else:
        a = a.assign(sellin_net=np.nan, sellin_qty=np.nan)
    for k in ("value", "qty", "disc", "sku"):
        a[k] = a[k].fillna(0)
    tot = a["value"].sum()
    a["share"] = a["value"] / tot if tot else np.nan
    a["sell_through"] = np.where(a["sellin_qty"] > 0, a["qty"] / a["sellin_qty"], np.nan)
    a["avg_price"] = np.where(a["qty"] > 0, a["value"] / a["qty"], np.nan)
    a["label"] = a[label].astype(str)
    a["key"] = a["label"] if len(by) == 1 else a[by].astype(str).agg("\x1f".join, axis=1)
    return a.sort_values(["value", "sellin_net"], ascending=False)


@app.get("/api/chain_sellout")
def chain_sellout(month: str | None = None, chain: str | None = None):
    cfg = read_config()
    d = STATE["data"]
    today = (d["meta"].get("today") if d else None) or CS.jalali_today()
    files = SELLOUT.sync(cfg, today)
    so = SELLOUT.frame.copy()
    months = sorted(so["month"].unique().tolist())
    base = {"months": months, "files": files, "chains": sorted(so["chain"].unique().tolist()),
            "folder": str(SELLOUT.folder), "barcode_error": SELLOUT.bc_error}
    if not months:
        return {**base, "month": None}
    if month not in months and month != "all":
        month = months[-1]

    # کالا: بارکد → کد کارآمد → نام/برند/گروه کارآمد؛ بدون تطبیق: نام فایل زنجیره و برند از روی نام
    bc = SELLOUT.barcodes()
    info = _product_info(d)
    aliases = {}
    if len(info):
        aliases = {CS.norm(r).lower(): b for r, b in zip(info["brand_raw"], info["brand"]) if isinstance(r, str) and len(r) > 2}
        aliases.update({CS.norm(b).lower(): b for b in info["brand"].dropna().unique() if len(str(b)) > 2})
    so["code"] = so["barcode"].map(bc)
    so["product"] = so["code"].map(info["product"]).fillna(so["name"])
    so["brand"] = so["code"].map(info["brand"])
    so["brand"] = so["brand"].fillna(so["name"].map(lambda n: _guess_brand(n, aliases)))
    so["category"] = so["code"].map(info["category"]).fillna(NO_MATCH)
    so["key"] = so["code"].fillna("bc:" + so["barcode"].where(so["barcode"] != "", so["name"]))

    # sell-in: فروش خالص (بدون ارزش افزوده) کارآمد به مشتری‌های هر زنجیره، فقط زنجیره‌هایی که آن ماه فایل دارند
    cust = {str(c): ch["name"] for ch in CS.chains(cfg) for c in ch.get("customers", [])}
    si = None
    if d is not None and cust:
        s = d["sales"]
        s = s[s["customer_code"].astype(str).isin(cust)]
        si = s.assign(chain=s["customer_code"].astype(str).map(cust), month=s["date"].str[:7],
                      key=s["product_code"])[["chain", "month", "key", "product", "brand", "category", "net", "qty"]]
        have = set(zip(so["month"], so["chain"]))
        trend_si = si.groupby(["month", "chain"]).agg(sellin_net=("net", "sum"), sellin_qty=("qty", "sum")).reset_index()
        si = si[[(m, c) in have for m, c in zip(si["month"], si["chain"])]]
    else:
        trend_si = pd.DataFrame(columns=["month", "chain", "sellin_net", "sellin_qty"])

    # روند ماهانه همه ماه‌ها (برای هر زنجیره)، پیش از فیلتر ماه
    tr = so.groupby(["month", "chain"]).agg(value=("value", "sum"), qty=("qty", "sum")).reset_index()
    tr = tr.merge(trend_si, on=["month", "chain"], how="left")
    if chain:
        tr = tr[tr["chain"] == chain]

    if month != "all":
        so = so[so["month"] == month]
        si = si[si["month"] == month] if si is not None else None
    if chain:
        so = so[so["chain"] == chain]
        si = si[si["chain"] == chain] if si is not None else None

    chains_t = _sellout_group(so, si, ["chain"], "chain")
    stores = so[so["store"] != ""]
    stores_t = _sellout_group(stores, None, ["chain", "store"], "store") if len(stores) else pd.DataFrame()
    brands_t = _sellout_group(so, si, ["brand"], "brand")
    cats_t = _sellout_group(so, si, ["category"], "category")
    # کالا: sell-in کالاهایی که در فایل نیامده‌اند هم می‌آید (فروخته‌شده به زنجیره ولی بدون فروش در فروشگاه)
    prod = _sellout_group(so, si, ["key"], "key")
    meta_cols = pd.concat([so[["key", "product", "brand", "category", "barcode"]],
                           si[["key", "product", "brand", "category"]].assign(barcode="") if si is not None else None])
    pm = meta_cols.drop_duplicates("key").set_index("key")
    prod_bc = so[so["barcode"] != ""].drop_duplicates("key").set_index("key")["barcode"]
    prod = prod.assign(label=prod["key"].map(pm["product"]), brand=prod["key"].map(pm["brand"]),
                       category=prod["key"].map(pm["category"]), barcode=prod["key"].map(prod_bc).fillna(""),
                       code=prod["key"].where(~prod["key"].astype(str).str.startswith("bc:"), ""),
                       chains=prod["key"].map(so.groupby("key")["chain"].nunique()).fillna(0),
                       stores=prod["key"].map(stores.groupby("key")["store"].nunique()).fillna(0))
    by_chain = so.pivot_table(index="key", columns="chain", values="qty", aggfunc="sum")
    prod_rows = A.records(prod.drop(columns=[c for c in ("chain",) if c in prod.columns]))
    for r in prod_rows:
        if r["key"] in by_chain.index:
            r["by_chain"] = {c: A._num(v) for c, v in by_chain.loc[r["key"]].items() if pd.notna(v)}

    k = {"value": float(so["value"].sum()), "qty": float(so["qty"].sum()), "disc": float(so["disc"].sum()),
         "sku": int(so["key"].nunique()), "chains": int(so["chain"].nunique()),
         "stores": int(stores.groupby(["chain", "store"]).ngroups) if len(stores) else 0,
         "unmatched": int(so.loc[so["code"].isna(), "key"].nunique()),
         "sellin_net": float(si["net"].sum()) if si is not None else None,
         "sellin_qty": float(si["qty"].sum()) if si is not None else None}
    k["sell_through"] = k["qty"] / k["sellin_qty"] if k["sellin_qty"] else None
    # زنجیره‌های تعریف‌شده که sell-in دارند ولی فایل sell-out این ماه را ندارند
    missing = []
    if d is not None and month != "all":
        s = d["sales"]
        for ch in CS.chains(cfg):
            if ch["name"] in set(so["chain"]) or (chain and ch["name"] != chain):
                continue
            m = s["customer_code"].astype(str).isin([str(c) for c in ch.get("customers", [])]) & (s["date"].str[:7] == month)
            if m.any():
                missing.append({"chain": ch["name"], "sellin_net": float(s.loc[m, "net"].sum())})
    return {**base, "month": month, "chain": chain, "kpis": k, "missing": missing,
            "by_chain": A.records(chains_t), "stores": A.records(stores_t), "brands": A.records(brands_t),
            "categories": A.records(cats_t), "products": prod_rows, "trend": A.records(tr.sort_values(["month", "chain"]))}


# ---------------------------------------------------------------- frontend
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        # index.html نباید کش شود تا پس از هر build نسخه جدید باندل بارگذاری شود
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})


start()

if __name__ == "__main__":
    cfg = read_config()
    if not CONFIG.exists():
        write_config(cfg)
    print(f"Dashboard: http://{cfg['host']}:{cfg['port']}")
    uvicorn.run(app, host=cfg["host"], port=int(cfg["port"]))
