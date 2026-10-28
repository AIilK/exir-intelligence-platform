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
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import analytics as A
import chain_store as CS
import inventory as INV
import loader
import planning as PL
import rahkaran as RK
import rahkaran_export as RE
import rahkaran_sales as RS
import remittance as RM
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
INV_SRC = INV.InventorySource(ENV_FILE, lambda: read_config())
FACTORY = RK.FactorySource(ENV_FILE, lambda: read_config())
RK_SALES = RK.FactorySource(ENV_FILE, lambda: read_config(), load=RS.load, sig_sql=RS.SIG_SQL)  # فروش B2B از راهکاران
RK_EXPORT = RK.FactorySource(ENV_FILE, lambda: read_config(), load=RE.load, sig_sql=RS.SIG_SQL)  # فروش صادراتی از راهکاران
RK_REMIT = RK.FactorySource(ENV_FILE, lambda: read_config(), load=RM.load)  # حواله‌های فروش زنجیره‌ای و اینترنتی


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
            changed = STORE.live_step(cfg)
            if changed:
                publish()
            STATE["live_error"] = None
            live_stock(changed)
        except Exception as e:  # قطع اتصال؛ sql_worker هم همین خطا را نشان می‌دهد
            STATE["live_error"] = str(e)
            wait = max(wait, 30)
        time.sleep(wait)


# موجودی شعب در لایو: با هر تغییر فروش (حداکثر هر دقیقه) یا دست‌کم هر ۵ دقیقه، فقط موجودی دوباره خوانده می‌شود
LIVE_STOCK_MIN, LIVE_STOCK_MAX = 60, 300


def live_stock(changed: bool):
    age = time.time() - INV_SRC.stock_at()
    if INV_SRC.snap is None or age < LIVE_STOCK_MIN or (not changed and age < LIVE_STOCK_MAX):
        return
    try:
        INV_SRC.refresh_stock()
    except Exception as e:  # noqa: BLE001 — خطای خواندن موجودی نباید لایو فروش را متوقف کند
        print("live stock:", e)


def rk_live_worker():
    """لایو راهکاران (انبار کارخانه): امضای تغییر هر live_seconds ثانیه؛ با تغییر، داده دوباره خوانده می‌شود."""
    while True:
        wait = float(RK.settings(read_config())["live_seconds"] or 0)
        if wait <= 0 or not RK.configured(ENV_FILE):
            time.sleep(30)
            continue
        for src in (FACTORY, RK_SALES, RK_EXPORT, RK_REMIT):
            try:
                src.live_step()
                src.live_error = None
            except Exception as e:  # قطع اتصال راهکاران؛ داده قبلی می‌ماند
                src.live_error = str(e)
                wait = max(wait, 30)
        time.sleep(wait)


def start():
    STORE.load_cache(sql_cfg(read_config()))
    publish()
    threading.Thread(target=sql_worker, daemon=True).start()
    threading.Thread(target=live_worker, daemon=True).start()
    threading.Thread(target=rk_live_worker, daemon=True).start()


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
    # live: آخرین بررسی لایو تازه و بدون خطا (حداکثر ۳ برابر فاصله بررسی، دست‌کم ۳۰ ثانیه)
    wait = float(sql_cfg(read_config()).get("live_seconds") or 0)
    live = wait > 0 and not STATE.get("live_error") and time.time() - STORE.live_checked <= max(30.0, 3 * wait)
    return {"stamp": STATE["stamp"], "live": live, "rk_stamp": FACTORY.stamp, "rk_live": FACTORY.is_live(),
            "rks_stamp": RK_SALES.stamp, "rks_live": RK_SALES.is_live(), "rke_stamp": RK_EXPORT.stamp, "rkr_stamp": RK_REMIT.stamp, "inv_stamp": INV_SRC.stock_at()}


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
    heat = tx.groupby(["branch", "date"])[["net", "qty"]].sum().reset_index()
    # درخواست خالص (بدون باطل‌شده‌ها) هر شعبه در هر روز
    heat_req = rq.groupby(["branch", "date"])[["net", "qty"]].sum().reset_index() if rq is not None and len(rq) else heat.iloc[0:0]
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
    abc_cat = A.pareto(cats)
    abc_cat.pop("abc", None)
    return {"kpis": A.kpis(tx, rq, c, f), "pareto_cat": abc_cat,
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
INV_OVERVIEW: dict = {"key": None, "data": None, "at": 0.0}
# در حالت لایو stamp مدام عوض می‌شود؛ نمای کلی شعب (محاسبه همه شعب) حداکثر هر چند دقیقه یک بار دوباره ساخته می‌شود
INV_OVERVIEW_MIN_SECONDS = 300
INV_LOCK = threading.Lock()


@app.get("/api/inventory/branches")
def inventory_branches():
    """فهرست شعب هیبرید برای فیلتر شعبه (بدون محاسبه؛ حتی اگر محاسبه یک شعبه خطا بدهد)."""
    d = STATE["data"]
    ctx()
    branches = INV.inventory_branches(d)
    return {"branches": branches, "labels": INV.branch_labels(branches), "default": INV.settings(read_config())["branch"]}


def _inv_selection(d, cfg, branch, store) -> tuple[list[str], list[int] | None]:
    """شعب انتخابی (یک یا چند، با پارامتر branch تکراری) و انبارهای انتخابی (store تکراری؛ خالی = همه انبارها)."""
    branches = INV.inventory_branches(d)
    sel = [b for b in dict.fromkeys(branch or []) if b] or [INV.settings(cfg)["branch"]]
    bad = [b for b in sel if b not in branches]
    if bad:
        raise HTTPException(400, f"شعبه «{'، '.join(bad)}» در داده فروش نیست.")
    return sel, [int(x) for x in store] if store else None


@app.get("/api/inventory")
def inventory(branch: list[str] | None = Query(None), store: list[int] | None = Query(None), refresh: bool = False):
    d = STATE["data"]
    ctx()
    cfg = read_config()
    branches = INV.inventory_branches(d)
    sel, stores = _inv_selection(d, cfg, branch, store)
    try:
        src = INV_SRC.get(sel, force=refresh, stores=stores)
        r = INV.compute(d, src, cfg, branch=sel)
    except loader.DataError as e:
        raise HTTPException(409, str(e))
    return {**r, "rows": A.records(r["rows"]), "suppliers": A.records(r["suppliers"]), "branches": branches,
            "labels": INV.branch_labels(branches)}


@app.get("/api/inventory/overview")
def inventory_overview(refresh: bool = False):
    """خلاصه همه شعب هیبرید؛ تا تغییر داده، تنظیمات یا موجودی کش می‌شود."""
    d = STATE["data"]
    ctx()
    cfg = read_config()
    with INV_LOCK:
        branches = INV.inventory_branches(d)
        if refresh:
            INV_SRC.get(branches[0], force=True)
        fetched = INV_SRC.get(branches[0])["fetched"]
        key = (STATE["stamp"], json.dumps(cfg.get("inventory") or {}, sort_keys=True),
               json.dumps(cfg.get("plan") or {}, sort_keys=True), fetched)
        old = INV_OVERVIEW["key"]
        if old == key:
            return INV_OVERVIEW["data"]
        # فقط داده لایو (فروش یا موجودی) عوض شده و تنظیمات همان است: تا چند دقیقه محاسبه سفارش قبلی کافی است،
        # ولی ستون‌های موجودی و ارزش انبار از آخرین موجودی خوانده‌شده تازه می‌شوند (سبک است)
        if (not refresh and old and old[1:3] == key[1:3]
                and time.time() - INV_OVERVIEW["at"] < INV_OVERVIEW_MIN_SECONDS):
            res = dict(INV_OVERVIEW["data"])
            res["branches"] = [{**r, **INV.stock_totals(INV_SRC.get(r["branch"]))} for r in res["branches"]]
            res["fetched"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(fetched))
            return res
        out = []
        for b in branches:
            row = {"branch": b}
            try:
                src = INV_SRC.get(b)
                row.update(INV.stock_totals(src))
                # نمای کلی فقط با داده کارآمد: سفارش باز و بار در راه راهکاران در این جدول نیست
                r = INV.compute(d, {**src, "rk": None, "rk_error": None}, cfg, branch=b)
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
        res = {"branches": A.records(pd.DataFrame(out)), "labels": INV.branch_labels(branches), "today": d["meta"].get("today"),
               "fetched": time.strftime("%Y-%m-%d %H:%M", time.localtime(fetched))}
        INV_OVERVIEW.update(key=key, data=res, at=time.time())
        return res


class InvSettings(BaseModel):
    branch: list[str] | str | None = None  # شعبه(های)ی که بعد از ذخیره نمایش داده می‌شود (تنظیمات برای همه شعب یکی است)
    store: list[int] | None = None
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
    c_regular_months: int | None = None
    c_order_months: float | None = None
    return_keep_months: float | None = None
    return_keep_months_c: float | None = None
    return_keep_dead: int | None = None


@app.put("/api/inventory/settings")
def inventory_settings(body: InvSettings):
    cfg = read_config()
    s = dict(cfg.get("inventory") or {})
    for k, v in body.model_dump(exclude_none=True, exclude={"branch", "store"}).items():
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
        elif k == "c_regular_months":
            v = min(max(int(v), 1), 6)
        elif k == "c_order_months":
            v = min(max(float(v), 0.25), 6.0)
        elif k in ("return_keep_months", "return_keep_months_c"):
            v = min(max(float(v), 0.0), 12.0)
        elif k == "return_keep_dead":
            v = min(max(int(v), 0), 1000)
        s[k] = v
    cfg["inventory"] = s
    write_config(cfg)
    return inventory(branch=[body.branch] if isinstance(body.branch, str) else body.branch, store=body.store)


# ---------------------------------------------------------------- انبار کارخانه از راهکاران (جدا از محاسبه شعب)
KIND_LABEL = {"product": "انبار محصول", "chain": "زنجیره‌ای", "sample": "نمونه", "stale": "راکد", "waste": "ضایعات",
              "raw": "مواد اولیه و بسته‌بندی", "other": "سایر"}
FINISHED = ["product", "chain", "sample", "stale", "other"]  # انبارهای کالای ساخته‌شده


@app.get("/api/inventory/factory")
def inventory_factory(refresh: bool = False, branch: list[str] | None = Query(None), store: list[int] | None = Query(None)):
    """موجودی انبارهای کارخانه (راهکاران) کنار موجودی و فروش جمع شعب هیبرید (کارآمد)."""
    d = STATE["data"]
    ctx()
    try:
        f = FACTORY.get(force=refresh)
        branches = INV.hybrid_branches(d)
        INV_SRC.get(branches[0])  # کالا، قیمت و موجودی شعب از کارآمد
    except loader.DataError as e:
        raise HTTPException(409, str(e))
    sn = INV_SRC.snap
    st = f["stock"].copy()
    st["q"] = st["qty"].clip(lower=0)  # مانده منفی (ثبت دیرتر رسید) صفر حساب می‌شود
    prod = st[st["is_product"]]
    by = prod.pivot_table(index="code", columns="kind", values="q", aggfunc="sum", fill_value=0.0)
    by = by.reindex(columns=list(KIND_LABEL), fill_value=0.0)
    opn = f["open"]
    open_all = opn.groupby("code")["open"].sum()
    open_hyb = opn[opn["hybrid"]].groupby("code")["open"].sum()
    # جمع موجودی شعب هیبرید در کارآمد (بدون ضایعات) و میانگین فروش خالص ماهانه آن‌ها در ۳ ماه بسته اخیر
    hb = {sn["branches"][b] for b in branches if b in sn["branches"]}
    ks = sn["stock"][sn["stock"]["bid"].isin(hb) & ~sn["stock"]["waste"]]
    kq = ks.groupby(["bid", "code"])["qty"].sum().clip(lower=0)
    hyb_stock = kq.groupby(level=1).sum()
    # ارزش موجودی شعب هیبرید مثل «ارزش انبار» گزارش کارآمد: هر شعبه با میانگین قیمت خرید خودش
    avg = pd.concat({sn["branches"][b]: INV_SRC.get(b)["avg_price"] for b in branches if b in sn["branches"]}, names=["bid", "code"])
    hyb_val = (kq * avg.reindex(kq.index).fillna(0.0)).groupby(level=1).sum()
    sales = d["sales"][d["sales"]["branch"].isin(branches) & ~d["sales"]["is_sample"]]
    cur = (d["meta"].get("today") or sales["date"].max())[:7]
    last3 = sorted(m for m in sales["month"].unique() if m < cur)[-3:]
    hyb_month = sales[sales["month"].isin(last3)].groupby("product_code", observed=True)["qty"].sum() / max(len(last3), 1)
    # شعبه انتخاب‌شده در صفحه: موجودی و فروش ماهانه همان شعبه کنار جمع هیبریدها
    # (یک یا چند شعبه و انبارهای انتخابی؛ شعبه زنجیره‌ای جزو جمع هیبریدها نیست ولی انتخاب‌شدنی است)
    sel = [x for x in (branch or []) if x in INV.inventory_branches(d)]
    bid = sel or None
    if bid is not None:
        try:
            br_stock = INV_SRC.get(sel, stores=[int(x) for x in store] if store else None)["stock"].clip(lower=0)
        except loader.DataError as e:
            raise HTTPException(409, str(e))
        bs = d["sales"][d["sales"]["branch"].isin(sel) & ~d["sales"]["is_sample"] & d["sales"]["month"].isin(last3)]
        br_month = bs.groupby("product_code", observed=True)["qty"].sum() / max(len(last3), 1)
    # همه انبارهای راهکاران، حتی بدون مانده؛ ترتیب ستون‌ها: نوع انبار، بعد کد
    order = {k: i for i, k in enumerate(KIND_LABEL)}
    slist = f["stores"].assign(o=f["stores"]["kind"].map(order), n=pd.to_numeric(f["stores"]["store"], errors="coerce"))
    slist = slist.sort_values(["o", "n"])
    per_store = st.pivot_table(index="code", columns="store", values="q", aggfunc="sum", fill_value=0.0)
    codes = sorted(set(per_store.index[per_store.sum(axis=1) > 0]) | set(open_all.index) | set(hyb_stock.index[hyb_stock > 0]))
    g = sn["goods"].reindex(codes)
    names = st.sort_values("is_product", ascending=False).drop_duplicates("code").set_index("code")
    price = INV_SRC._any_price().reindex(codes)
    df = pd.DataFrame(index=pd.Index(codes, name="code"))
    df["product"] = g["name"].fillna(names["name"].reindex(codes))
    df["brand"] = g["brand"].fillna(loader.UNKNOWN)
    # گروه کالا از category_map.json، مثل بقیه داشبورد: کد کالا ← گروه کارآمد ← fallback
    cmap = sql_source._load_map()
    pmap = {k: v[0] for k, v in cmap.get("products", {}).items()}
    cat = pd.Series(codes, index=df.index).map(pmap).fillna(g["grp"].map(cmap.get("groups", {})))
    df["category"] = cat.fillna(cmap.get("fallback", loader.UNKNOWN))
    df["unit"] = names["unit"].reindex(codes)
    # کالای قابل فروش (تعریف‌شده در فروش راهکاران)؛ کالایی که فقط سفارش باز دارد هم قابل فروش است
    df["is_product"] = names["is_product"].reindex(codes).fillna(True).astype(bool)
    for k in KIND_LABEL:
        df["k_" + k] = by[k].reindex(codes).fillna(0.0)
    for sc in slist["store"]:
        df["s_" + sc] = per_store[sc].reindex(codes).fillna(0.0) if sc in per_store.columns else 0.0
    df["total"] = per_store.sum(axis=1).reindex(codes).fillna(0.0)  # جمع همه انبارها (واحد اصلی هر کالا)
    # جمع هر نوع انبار برای همه اقلام (k_ فقط کالای قابل فروش است و در آزاد و ارزش به کار می‌رود)
    for k in KIND_LABEL:
        sc = ["s_" + x for x in slist.loc[slist["kind"] == k, "store"]]
        df["t_" + k] = df[sc].sum(axis=1) if sc else 0.0
    df["open_all"] = open_all.reindex(codes).fillna(0.0)
    df["open_hybrid"] = open_hyb.reindex(codes).fillna(0.0)
    df["free"] = (df["k_product"] - df["open_all"]).clip(lower=0)
    df["short"] = df["open_all"] > df["k_product"]
    df["hybrid_stock"] = hyb_stock.reindex(codes).fillna(0.0)
    df["hybrid_monthly"] = hyb_month.reindex(codes).fillna(0.0).clip(lower=0)
    df["grand_total"] = df["total"] + df["hybrid_stock"]  # کارخانه (همه انبارها) + شعب هیبرید؛ کالای در راه در هیچ‌کدام نیست
    if bid is not None:
        df["branch_stock"] = br_stock.reindex(codes).fillna(0.0)
        df["branch_monthly"] = br_month.reindex(codes).fillna(0.0).clip(lower=0)
    df["price"] = price
    df["value"] = df["k_product"] * price.fillna(0.0)
    df["free_value"] = df["free"] * price.fillna(0.0)
    df["hybrid_value"] = hyb_val.reindex(codes).fillna(0.0)
    agg = (st.groupby("store")
           .apply(lambda x: pd.Series({"items": int((x["q"] > 0).sum()), "product_items": int(((x["q"] > 0) & x["is_product"]).sum()),
                                       "product_units": float(x.loc[x["is_product"], "q"].sum()),
                                       "units": float(x["q"].sum()), "negative": int((x["qty"] < 0).sum())}), include_groups=False))
    stores = slist[["store", "store_name", "kind"]].merge(agg, left_on="store", right_index=True, how="left").fillna(0)
    stores["value"] = [float((prod[prod["store"] == s]["q"] * INV_SRC._any_price().reindex(prod[prod["store"] == s]["code"]).fillna(0).values).sum())
                       for s in stores["store"]]
    stores["kind_label"] = stores["kind"].map(KIND_LABEL)
    k = {"product_units": float(df["k_product"].sum()), "product_value": float(df["value"].sum()),
         "product_skus": int((df["k_product"] > 0).sum()), "open_all": float(df["open_all"].sum()),
         "open_hybrid": float(df["open_hybrid"].sum()), "free_units": float(df["free"].sum()), "free_value": float(df["free_value"].sum()),
         "short_skus": int(df["short"].sum()), "other_units": float(df[["k_" + k for k in FINISHED if k != "product"]].sum().sum()),
         "hybrid_units": float(df["hybrid_stock"].sum()), "hybrid_value": float(df["hybrid_value"].sum()),
         "no_price": int(((df["k_product"] > 0) & df["price"].isna()).sum())}
    return {"kpis": k, "rows": A.records(df.reset_index().replace([np.inf, -np.inf], np.nan)),
            "stores": A.records(stores.sort_values("product_units", ascending=False)),
            "store_cols": A.records(slist[["store", "store_name", "kind"]]),
            "kinds": KIND_LABEL, "sellable_stores": f["settings"]["factory_stores"], "open_days": f["settings"]["open_days"],
            "last3": last3, "today": d["meta"].get("today"), "branch": "، ".join(sel) if bid is not None else None,
            "fetched": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f["fetched"])), "live": FACTORY.is_live()}


# ---------------------------------------------------------------- حواله‌های فروش زنجیره‌ای و اینترنتی (remittance.py)
@app.get("/api/inventory/remittances")
def inventory_remittances(refresh: bool = False, all_states: bool = False):
    """حواله‌های فروش ثبت‌شده زنجیره‌ای و اینترنتی در راهکاران، با پیشنهاد تأیید هر کالا از موجودی و فروش همان شعبه در کارآمد.
    all_states: تأییدشده و در حال استفاده هم (برای بررسی پیشنهادها روی حواله‌های قبلی)."""
    d = STATE["data"]
    ctx()
    cfg = read_config()
    try:
        snap = RK_REMIT.get(force=refresh)
    except loader.DataError as e:
        raise HTTPException(409, str(e))
    today = d["meta"].get("today") or d["sales"]["date"].max()
    frames, channels = {}, []
    for ch in RM.CHANNELS:
        info = {**ch, "error": None, "simple": False}
        try:
            # موجودی = همه انبارهای خود شعبه در کارآمد، حتی ضایعات (مثل گزارش موجودی کارآمد برای همین شعبه):
            # زنجیره‌ای: انبار زنجیره ای و هایپر می؛ اینترنتی: هیبرید همدان، ضایعات هیبرید همدان و سایت اینترنتی.
            # انبارهای شعب دیگر (مثل دیجی کالا زیر هیبرید تهران) حساب نمی‌شوند.
            src = INV_SRC.get(ch["branch"])
            src = {**src, "stock": src["stock"].add(src["waste"], fill_value=0.0), "waste": src["waste"].iloc[:0]}
            info["stores"] = [x["name"] for x in src["stores"]]
        except loader.DataError as e:
            info["error"] = str(e)
            channels.append(info)
            continue
        try:
            rows = INV.compute(d, src, cfg, branch=ch["branch"])["rows"]
        except loader.DataError as e:  # سابقه کم: آمار ساده (میانگین ۳ ماه)
            rows, info["simple"], info["error"] = None, True, str(e)
        frames[ch["key"]] = RM.branch_frame(rows, src, d["sales"], ch["branch"], today)
        channels.append(info)
    r = RM.evaluate(snap, frames, [1, 2, 3] if all_states else [1])
    lines = r["lines"]
    return {"orders": r["orders"], "lines": A.records(lines.replace([np.inf, -np.inf], np.nan)) if len(lines) else [],
            "channels": channels, "verdicts": RM.VERDICT_LABEL, "states": RM.STATE_LABEL, "settings": r["settings"],
            "today": today,
            "fetched": _ts(snap["fetched"]), "live": RK_REMIT.is_live()}


# ---------------------------------------------------------------- فروش B2B (نمایندگان استانی) از راهکاران
def _rk_sales(refresh: bool = False) -> dict:
    try:
        return RK_SALES.get(force=refresh)
    except loader.DataError as e:
        raise HTTPException(409, str(e))


def _by_product(snap: dict, req: Request) -> dict:
    """فیلتر کالا (پارامتر تکراری product = کد کالا) روی همه محاسبات؛ برای مقایسه با گزارش «فروش محصول به تفکیک مشتری» راهکاران"""
    codes = [c for c in req.query_params.getlist("product") if c]
    return {**snap, "lines": snap["lines"][snap["lines"]["product_code"].isin(codes)]} if codes else snap


def _rk_payload(snap: dict, out: dict) -> dict:
    """جدول‌های DataFrame به رکورد، به‌علاوه زمان خواندن و وضعیت لایو"""
    out = {k: A.records(v) if isinstance(v, pd.DataFrame) else v for k, v in out.items()}
    return {**out, "today": snap["today"], "since": snap["since"], "periods": RS.periods(snap),
            "fetched": _ts(snap["fetched"]), "live": RK_SALES.is_live()}


@app.get("/api/rk_sales")
def rk_sales(req: Request, period: str = "YTD", brand: str | None = None, refresh: bool = False):
    """نمای اصلی: KPIها، حباب استان‌ها، سهم برند، مشتریان ۸۰٪ فروش (شیت Bubble Chart)"""
    snap = _rk_sales(refresh)
    out = RS.summary(_by_product(snap, req), period, brand or None)
    out["brand_list"] = sorted(snap["customers"]["brand"].unique().tolist())
    return _rk_payload(snap, out)


@app.get("/api/rk_sales/province")
def rk_sales_province(req: Request, name: str, period: str = "YTD", brand: str | None = None):
    snap = _rk_sales()
    return _rk_payload(snap, RS.province(_by_product(snap, req), name, period, brand or None))


@app.get("/api/rk_sales/customers")
def rk_sales_customers(req: Request, period: str = "YTD"):
    """همه نمایندگان B2B با فروش دوره (هر مشتری یک سطر، حتی بدون خرید)"""
    snap = _rk_sales()
    return _rk_payload(snap, RS.customer_list(_by_product(snap, req), period))


@app.get("/api/rk_sales/customer")
def rk_sales_customer(req: Request, code: str, period: str = "YTD"):
    snap = _rk_sales()
    out = RS.customer(_by_product(snap, req), code, period)
    if out is None:
        raise HTTPException(404, f"مشتری {code} در فهرست مشتریان B2B نیست.")
    return _rk_payload(snap, out)


@app.get("/api/rk_sales/customer_brand")
def rk_sales_customer_brand(req: Request, period: str = "YTD", cat: str | None = None):
    """شیت Customer Brand: نماینده × برند (ناخالص درخواست، خالص فاکتور، تعداد)"""
    snap = _rk_sales()
    return _rk_payload(snap, RS.customer_brand(_by_product(snap, req), period, cat or None))


@app.get("/api/rk_sales/total_report")
def rk_sales_total_report(req: Request, day: str | None = None, month: str | None = None):
    """شیت Total report: برند ← نماینده، بلوک‌های روز / ماه / سال و گروه‌های کالا"""
    snap = _rk_sales()
    return _rk_payload(snap, RS.total_report(_by_product(snap, req), day, month, req.query_params.getlist("cat") or None))


@app.get("/api/rk_sales/compare")
def rk_sales_compare(req: Request, dim: str = "customer", a_from: str | None = None, a_to: str | None = None,
                     b_from: str | None = None, b_to: str | None = None, bd: str = "cat2"):
    """مقایسه چند نماینده / برند / استان / گروه کالا / کالا در یک بازه و در صورت انتخاب، در بازه دوم.
    item تکراری = موردهای مقایسه؛ s_brand، s_province و s_cat1 محدوده؛ product فیلتر کالا. پیش‌فرض بازه: از ابتدای سال تا امروز"""
    snap = _rk_sales()
    today = snap["today"]
    a = (a_from or f"{today[:4]}/01/01", a_to or today)
    b = (b_from, b_to) if b_from and b_to else None
    p = req.query_params
    scope = {k: p.getlist(f"s_{k}") for k in ("brand", "province", "cat1")}
    return _rk_payload(snap, RS.compare(_by_product(snap, req), dim, p.getlist("item"), a, b, bd, scope))


@app.get("/api/rk_sales/products")
def rk_sales_products():
    """کالاهای فروخته یا درخواست‌شده به نمایندگان B2B، برای فیلتر کالا"""
    return {"products": RS.product_list(_rk_sales())}


# ---------------------------------------------------------------- فروش صادراتی از راهکاران (فایل Export SalesReport)
def _rk_export() -> dict:
    try:
        return RK_EXPORT.get()
    except loader.DataError as e:
        raise HTTPException(409, str(e))


def _rke_payload(snap: dict, out: dict) -> dict:
    out = {k: A.records(v) if isinstance(v, pd.DataFrame) else v for k, v in out.items()}
    return {**out, "fetched": _ts(snap["fetched"]), "live": RK_EXPORT.is_live()}


@app.get("/api/rk_export")
def rk_export(req: Request):
    """شیت‌های Dashboard، Customer، SKU&Category، Country و YTD Trend با فیلترهای اسلایسر"""
    snap = _rk_export()
    return _rke_payload(snap, RE.report(snap, RE.parse_filters(req.query_params)))


@app.get("/api/rk_export/customer")
def rk_export_customer(code: str, req: Request):
    snap = _rk_export()
    out = RE.customer(snap, code, RE.parse_filters(req.query_params))
    if out is None:
        raise HTTPException(404, f"کد مشتری صادراتی {code} در فهرست نیست.")
    return _rke_payload(snap, out)


# ---------------------------------------------------------------- فروش زنجیره‌ای به مصرف‌کننده (sell-out)
SELLOUT = CS.SelloutStore(ROOT / "data" / "chain_store", ROOT / "data" / "cache" / "sql", ENV_FILE)
# فروشگاه‌های اینترنتی (خانومی، اسنپ): همان روش زنجیره‌ای‌ها، پوشه و فهرست جدا
ONLINE = CS.SelloutStore(ROOT / "data" / "online_sale", ROOT / "data" / "cache" / "sql", ENV_FILE, CS.online_shops)
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
    return _sellout(SELLOUT, month, chain)


@app.get("/api/online_sellout")
def online_sellout(month: str | None = None, chain: str | None = None):
    return _sellout(ONLINE, month, chain)


def _sellout(store: CS.SelloutStore, month: str | None, chain: str | None) -> dict:
    """فروش فروشگاه به مشتری (فایل‌های ماهانه) کنار فروش ما به همان فروشگاه (کارآمد)؛ زنجیره‌ای‌ها یا فروشگاه‌های اینترنتی."""
    cfg = read_config()
    d = STATE["data"]
    today = (d["meta"].get("today") if d else None) or CS.jalali_today()
    files = store.sync(cfg, today)
    so = store.frame.copy()
    months = sorted(so["month"].unique().tolist())
    base = {"months": months, "files": files, "chains": sorted(so["chain"].unique().tolist()),
            "folder": str(store.folder), "barcode_error": store.bc_error}
    if not months:
        return {**base, "month": None}
    if month not in months and month != "all":
        month = months[-1]

    # کالا: بارکد → کد کارآمد → نام/برند/گروه کارآمد؛ بدون تطبیق: نام فایل زنجیره و برند از روی نام
    bc = {**store.barcodes(), **store.sku_map()}
    info = _product_info(d)
    aliases = {}
    if len(info):
        aliases = {CS.norm(r).lower(): b for r, b in zip(info["brand_raw"], info["brand"]) if isinstance(r, str) and len(r) > 2}
        aliases.update({CS.norm(b).lower(): b for b in info["brand"].dropna().unique() if len(str(b)) > 2})
    so["code"] = so["barcode"].map(bc)
    so["product"] = so["code"].map(info["product"]).fillna(so["name"])
    so["brand"] = so["code"].map(info["brand"])
    # برند ستون فایل (فروشگاه‌های اینترنتی) با نام برند کارآمد یکی می‌شود؛ وگرنه از روی نام کالا
    if "brand" in store.frame.columns:
        fb = store.frame["brand"].fillna("").map(lambda b: aliases.get(CS.norm(b).lower(), b) if b else None)
        so["brand"] = so["brand"].fillna(fb.reindex(so.index))
    so["brand"] = so["brand"].fillna(so["name"].map(lambda n: _guess_brand(n, aliases)))
    so["category"] = so["code"].map(info["category"]).fillna(NO_MATCH)
    so["key"] = so["code"].fillna("bc:" + so["barcode"].where(so["barcode"] != "", so["name"]))

    # sell-in: فروش خالص (بدون ارزش افزوده) کارآمد به مشتری‌های هر زنجیره، فقط زنجیره‌هایی که آن ماه فایل دارند
    cust = {str(c): ch["name"] for ch in store.chain_list(cfg) for c in ch.get("customers", [])}
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
    # تحلیل شعبه‌ای (فقط زنجیره‌هایی که ستون شعبه دارند، مثل هایپر می): برند و کالای هر شعبه
    store_rows, store_products = A.records(stores_t), []
    if len(stores):
        bq = stores.pivot_table(index=["chain", "store"], columns="brand", values="qty", aggfunc="sum")
        bv = stores.pivot_table(index=["chain", "store"], columns="brand", values="value", aggfunc="sum")
        for r in store_rows:
            ix = (r["chain"], r["store"])
            r["brand_qty"] = {b: A._num(v) for b, v in bq.loc[ix].items() if pd.notna(v)}
            r["brand_value"] = {b: A._num(v) for b, v in bv.loc[ix].items() if pd.notna(v)}
        sp = stores.groupby(["chain", "store", "key"]).agg(product=("product", "first"), brand=("brand", "first"),
                                                         category=("category", "first"), qty=("qty", "sum"),
                                                         value=("value", "sum")).reset_index()
        store_products = A.records(sp.rename(columns={"product": "label"}).sort_values("value", ascending=False))
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
    # یک زنجیره: جمع هر ستون عددی فایل اکسل خودش (با همان نام)، برای کارت‌هایی که با فایل تطبیق‌پذیرند
    file_columns, file_stats = [], None
    if chain:
        keys = sorted(set(zip(so["month"], so["chain"])))
        cols = []
        file_stats = {"lines": 0, "return_lines": 0, "files": 0}
        ret: dict = {}
        for key in keys:
            m = store.meta.get(key) or {}
            cols += [c for c in m.get("raw_columns", []) if c not in cols]
            st = m.get("stats") or {}
            file_stats["lines"] += st.get("lines", 0)
            file_stats["return_lines"] += st.get("return_lines", 0)
            file_stats["files"] += 1
            for c, v in (st.get("return_raw") or {}).items():
                ret[c] = ret.get(c, 0) + v
        raw = so["raw"] if "raw" in so.columns else pd.Series([], dtype=object)
        for c in cols:
            tot = float(sum((r or {}).get(c, 0) for r in raw if isinstance(r, dict)))
            file_columns.append({"label": c, "total": tot, "returns": ret.get(c, 0.0)})
    # زنجیره‌های تعریف‌شده که sell-in دارند ولی فایل sell-out این ماه را ندارند
    missing = []
    if d is not None and month != "all":
        s = d["sales"]
        for ch in store.chain_list(cfg):
            if ch["name"] in set(so["chain"]) or (chain and ch["name"] != chain):
                continue
            m = s["customer_code"].astype(str).isin([str(c) for c in ch.get("customers", [])]) & (s["date"].str[:7] == month)
            if m.any():
                missing.append({"chain": ch["name"], "sellin_net": float(s.loc[m, "net"].sum())})
    return {**base, "month": month, "chain": chain, "kpis": k, "missing": missing,
            "file_columns": file_columns, "file_stats": file_stats,
            "by_chain": A.records(chains_t), "stores": store_rows, "store_products": store_products, "brands": A.records(brands_t),
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
