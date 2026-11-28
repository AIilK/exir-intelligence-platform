"""Average monthly prices of rival companies' brands vs ours, retail and wholesale, from several online sources.

Sources (data/price_sources.csv; edit to add or drop shops):
  basalam            Basalam marketplace search, retail listings (many independent sellers)
  basalam_wholesale  Basalam wholesale section; carton/pack listings are divided down to a unit price
  woo shops          shops with an open WooCommerce product feed (rangmooo, mahtika, ajigol, arianpro, ...)
Brands and companies: data/rival_brands.csv (one row per brand; owner = our / rival).

How the average is built (per month x category x company x channel):
  1. every listing -> price per 100 ml/g (size parsed from the title; wholesale packs -> per unit)
  2. average per seller and brand (so one seller listing 30 shades counts once)
  3. 10%-trimmed mean across sellers, plus median and the number of sellers
A month's figure uses every run in that Persian month (run it once or several times a month).
Past months cannot be recovered from these sources; history starts with the first run.

  collect  -> appends to data/rival_price_listings.csv
  report   -> lab/rival_prices.xlsx and data/rival_price_monthly.csv
Run: <venv python> rival_prices.py [collect] [report]
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import jdatetime
import numpy as np
import pandas as pd
from scipy.stats import trim_mean

try:
    import truststore  # use the Windows certificate store (needed on this network)
    truststore.inject_into_ssl()
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
LAB = HERE.parent / "lab"
LISTINGS = DATA / "rival_price_listings.csv"
BRANDS = DATA / "rival_brands.csv"
SOURCES = DATA / "price_sources.csv"
CATEGORIES = {"hair color": "رنگ مو", "oxidant": "اکسیدان", "hair spray": "اسپری مو", "bleach powder": "دکلره"}
CAT_WORDS = {"hair color": ["رنگ مو", "رنگ موی", "رنگمو"], "oxidant": ["اکسیدان", "اکسیدانت"],
             "hair spray": ["اسپری مو", "اسپری حالت", "اسپری نگهدارنده", "اسپری چسب", "چسب مو", "تافت"],
             "bleach powder": ["دکلره"]}
# accessories and other products whose titles mention a category word
EXCLUDE = re.compile(r"ابرو|کاسه|فرچه|دستکش|شانه|کلاه|سشوار|خوشبو|بدن|دوفاز|دو فاز|گره\s*باز|ناخن|ریمل|مژه|شامپو|ماسک|سرم")
PAUSE = 0.8
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")
ML_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:میلی\s*لیتر|میلی‌لیتر|میل|ml|cc|سی\s*سی|گرم|گرمی|gr|g)(?![a-z])", re.I)
L_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:لیتر|لیتری|liter|litre|lit)(?![a-z])", re.I)
PACK_RE = re.compile(r"(?:(\d+)\s*(?:عددی|عدد|تایی|تا|دانه)|(?:پک|بسته|کارتن|کارتنی)\s*(\d+))")
UNIT_PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*هزار\s*تومان")


def fetch(url, tries=2):
    for k in range(tries):
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode("utf-8-sig"))
            time.sleep(PAUSE)
            return d
        except Exception as e:
            wait = 30 * (k + 1) if getattr(e, "code", None) in (429, 490) else 5 * (k + 1)
            print(f"   retry in {wait}s ({str(e)[:60]})", flush=True)
            time.sleep(wait)
    return None


def norm(t):
    return str(t).translate(FA_DIGITS).replace("ي", "ی").replace("ك", "ک")


def size_ml(title):
    t = norm(title)
    s = [float(x) for x in ML_RE.findall(t) if 10 <= float(x) <= 1000]
    s += [float(x) * 1000 for x in L_RE.findall(t) if 0.1 <= float(x) <= 20]
    return max(s) if s else np.nan


def pack_count(title):
    t = norm(title)
    n = [int(a or b) for a, b in PACK_RE.findall(t) if 2 <= int(a or b) <= 500]
    return max(n) if n else np.nan


def category_of(title):
    t = norm(title)
    if EXCLUDE.search(t):
        return None
    best, pos = None, 10 ** 6
    for cat, words in CAT_WORDS.items():
        for w in words:
            i = t.find(w)
            if 0 <= i < pos:
                best, pos = cat, i
    return best


def load_brands():
    b = pd.read_csv(BRANDS, encoding="utf-8-sig", dtype=str).fillna("")
    b = b[b["match"] != ""].copy()
    b["rx"] = [re.compile(rf"(?<!\w)(?:{m})(?!\w)", re.I) for m in b["match"]]
    return b


def brand_of(title, cfg):
    t = norm(title)
    for r in cfg.itertuples():
        if r.rx.search(t):
            return r.owner, r.company, r.brand
    return None


def row(src, channel, title, price_toman, seller, cfg, today, pm, extra=None):
    b = brand_of(title, cfg)
    cat = category_of(title)
    if b is None or cat is None or not price_toman or price_toman <= 0:
        return None
    sz, pk = size_ml(title), pack_count(title) if channel == "wholesale" else np.nan
    unit = price_toman
    up = UNIT_PRICE_RE.findall(norm(title))
    if channel == "wholesale":
        if up:                                   # "... 292 هزار تومان" in the title = stated unit price
            unit = float(up[0]) * 1000
        elif pk == pk:
            unit = price_toman / pk
        else:
            unit = np.nan                        # pack size unknown: kept, but not averaged
    return dict(date=today, pmonth=pm, source=src, channel=channel, owner=b[0], company=b[1], brand=b[2], category=cat,
                title=title, seller=seller, price=price_toman, pack=pk, unit_price=unit, size_ml=sz,
                per100=unit / sz * 100 if sz == sz and unit == unit else np.nan, **(extra or {}))


def basalam(src, wholesale, cfg, today, pm):
    rows = []
    base = "https://search.basalam.com/ai-engine/api/v2.0/product/search?"
    if wholesale:   # the wholesale section is small: read it whole per category and match brands in titles
        jobs = [(cat, {"q": fa}) for cat, fa in CATEGORIES.items()]
    else:
        jobs = [(cat, {"q": f"{fa} {r.brand}"}) for cat, fa in CATEGORIES.items() for r in cfg.itertuples()]
    seen, failures = set(), 0
    for k, (cat, q) in enumerate(jobs):
        if failures >= 3:
            print(f"   {src}: stopping early after {failures} consecutive failed requests", flush=True)
            break
        for frm in (0, 48) if wholesale else (0,):
            p = {**q, "from": frm, "size": 48}
            if wholesale:
                p["filters.isWholesale"] = "true"
            d = fetch(base + urllib.parse.urlencode(p))
            if d is None:
                failures += 1
                break
            failures = 0
            if not d.get("products"):
                break
            for x in d["products"]:
                if x["id"] in seen or bool(x.get("is_wholesale")) != wholesale or not x.get("IsAvailable", True):
                    continue
                seen.add(x["id"])
                r = row(src, "wholesale" if wholesale else "retail", x.get("name", ""), (x.get("price") or 0) / 10,
                        (x.get("vendor") or {}).get("name", ""), cfg, today, pm,
                        {"list_price": (x.get("primaryPrice") or 0) / 10, "sales_count": x.get("sales_count")})
                if r:
                    rows.append(r)
        if (k + 1) % 40 == 0:
            print(f"   {src}: {k + 1}/{len(jobs)} searches, {len(rows)} matching listings", flush=True)
    return rows


def woo(src, url, channel, cfg, today, pm):
    rows, page, started = [], 1, time.time()
    while page <= 30 and time.time() - started <= 90:
        d = fetch(f"{url}/wp-json/wc/store/v1/products?per_page=100&page={page}")
        if not d:
            break
        for x in d:
            if not x.get("is_in_stock", True):
                continue
            pr = x.get("prices") or {}
            price = float(pr.get("price") or 0) / (10 ** int(pr.get("currency_minor_unit") or 0))
            if pr.get("currency_code") == "IRR":
                price /= 10
            r = row(src, channel, x.get("name", ""), price, src, cfg, today, pm)
            if r:
                rows.append(r)
        if len(d) < 100:
            break
        page += 1
    return rows


def collect():
    cfg = load_brands()
    srcs = pd.read_csv(SOURCES, encoding="utf-8-sig", dtype=str)
    today = date.today().isoformat()
    j = jdatetime.date.today()
    pm = f"{j.year}/{j.month:02d}"
    rows = []
    for s in srcs.itertuples():
        t0 = time.time()
        try:
            if s.kind == "basalam":
                got = basalam(s.source, s.channel == "wholesale", cfg, today, pm)
            else:
                got = woo(s.source, s.url, s.channel, cfg, today, pm)
        except Exception as e:
            print(f"!! {s.source}: {e}", flush=True)
            got = []
        print(f"{s.source:18s} {len(got):5d} listings for our/rival brands ({time.time() - t0:.0f}s)", flush=True)
        rows += got
    new = pd.DataFrame(rows)
    if LISTINGS.exists():
        old = pd.read_csv(LISTINGS, encoding="utf-8-sig")
        new = pd.concat([old[old.date != today], new], ignore_index=True)
    new.to_csv(LISTINGS, index=False, encoding="utf-8-sig")
    print(f"collected {len(rows):,} listings on {today} ({pm}) -> {LISTINGS.name}", flush=True)


def tmean(x):
    x = np.asarray(x, float)
    return trim_mean(x, 0.1) if len(x) >= 5 else x.mean()


def report():
    L = pd.read_csv(LISTINGS, encoding="utf-8-sig")
    L["category"] = L.title.map(category_of)          # re-apply the current category rules to stored listings
    L = L[L.category.notna() & L.per100.notna() & (L.per100 > 0)]
    # drop listings far from their brand's median in the month (wrong size parse, bundles, typos)
    med = L.groupby(["pmonth", "category", "brand", "channel"]).per100.transform("median")
    L = L[(L.per100 > med / 3) & (L.per100 < med * 3)]
    S = (L.groupby(["pmonth", "category", "channel", "owner", "company", "brand", "source", "seller"])
         .per100.mean().reset_index())                                                   # one value per seller and brand
    agg = lambda g: pd.Series({"sellers": len(g), "brands": g.brand.nunique() if "brand" in g else 1, "avg_per100": tmean(g.per100),
                               "median_per100": g.per100.median(), "p25": g.per100.quantile(.25), "p75": g.per100.quantile(.75)})
    C = S.groupby(["pmonth", "category", "channel", "company"]).apply(agg, include_groups=False).reset_index()
    ex = C[C.company == "Exir"].set_index(["pmonth", "category", "channel"]).avg_per100
    C["exir_vs_company"] = [ex.get((p, c, ch), np.nan) / a for p, c, ch, a in zip(C.pmonth, C.category, C.channel, C.avg_per100)]
    C = C.sort_values(["category", "channel", "pmonth", "avg_per100"])
    B = S.groupby(["pmonth", "category", "channel", "company", "brand"]).apply(agg, include_groups=False).reset_index()
    B = B.drop(columns="brands").sort_values(["category", "channel", "company", "avg_per100"])

    # retail vs wholesale gap per company (a proxy for the trade margin the distributor leaves to shops)
    W = C.pivot_table(index=["pmonth", "category", "company"], columns="channel", values="avg_per100").reset_index()
    if {"retail", "wholesale"} <= set(W.columns):
        W["wholesale_vs_retail"] = W.wholesale / W.retail

    # month-on-month change of the average (once 2+ months exist)
    C = C.sort_values(["category", "channel", "company", "pmonth"])
    C["change_vs_prev_month"] = C.groupby(["category", "channel", "company"]).avg_per100.pct_change()
    C.to_csv(DATA / "rival_price_monthly.csv", index=False, encoding="utf-8-sig")
    cov = (L.groupby(["pmonth", "source", "channel"]).agg(listings=("title", "size"), sellers=("seller", "nunique"),
                                                          brands=("brand", "nunique")).reset_index())
    with pd.ExcelWriter(LAB / "rival_prices.xlsx") as xw:
        C.round(3).to_excel(xw, sheet_name="Company monthly avg", index=False)
        B.round(0).to_excel(xw, sheet_name="Brand monthly avg", index=False)
        W.round(3).to_excel(xw, sheet_name="Retail vs wholesale", index=False)
        cov.to_excel(xw, sheet_name="Coverage", index=False)
        L.sort_values(["category", "channel", "company", "brand", "per100"]).to_excel(xw, sheet_name="Listings", index=False)
    pd.set_option("display.width", 230, "display.max_rows", 300)
    cols = ["pmonth", "channel", "company", "sellers", "brands", "avg_per100", "median_per100", "exir_vs_company"]
    for cat in CATEGORIES:
        d = C[C.category == cat]
        if len(d):
            print(f"\n== {cat} (toman per 100 ml/g; exir_vs_company > 1: Exir is dearer)\n",
                  d[cols].round(2).to_string(index=False))
    print("\n== Coverage\n", cov.to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="*", default=["collect", "report"])
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if "collect" in a.what:
        collect()
    if "report" in a.what:
        report()
