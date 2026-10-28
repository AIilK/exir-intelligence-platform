"""فروش صادراتی از دیتابیس راهکاران؛ فقط SELECT. معادل فایل «Export SalesReport 1405».

فهرست مشتریان صادراتی (کد، نام کوتاه، کشور) از شیت MAP همان فایل در data/rahkaran/export_customers.csv است؛
گروه و برند کالا مثل فروش B2B از data/rahkaran/products.csv (شیت draft / MAP).
  فروش دلاری = InvoiceItem.NetPrice ، ناخالص = InvoiceItem.Price ، تعداد = MajorUnitQuantity
  فاکتورهای با وضعیت ۲ و ۱۱، مثل شیت رکوردها؛ سطرهای وضعیت ۲ (نمونه و هدیه) مبلغ ندارند ولی در تعداد می‌آیند.
  با این قاعده فروش دلاری هر ماه ۱۴۰۴/۰۵ تا ۱۴۰۵/۰۶ دقیقاً برابر شیت رکوردهاست.
درخواست فروش = SLS3.SaleRequestItem (Price و MajorUnitQuantity)، وضعیت «تأییدشده» و «بسته‌شده» مثل فروش B2B.
از ۱۴۰۰ خوانده می‌شود؛ تا ۱۴۰۳ بخشی از فاکتورها و درخواست‌ها ریالی‌اند (نرخ ۱). مبلغ هر سند غیردلاری
  با نرخ خودش به ریال و سپس با میانگین نرخ دلار اسناد دلاری همان ماه به دلار تبدیل می‌شود.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

import loader
import rahkaran as RK
import rahkaran_sales as RS
import sql_source

ROOT = Path(__file__).resolve().parent.parent
CUSTOMERS_FILE = ROOT / "data" / "rahkaran" / "export_customers.csv"
DEFAULT_FROM = "1400/01/01"
USD = 3  # GNR3.Currency
MAX_UNIT_USD = 1000  # بیشترین قیمت واحد معقول یک کالا به دلار
# برند کالا در products.csv انگلیسی و با چند املاست؛ نام فارسی مثل بقیه داشبورد
BRANDS = {"padina": "پادینا", "base": "بیس", "jevo": "جوو", "arkia": "آرکیا", "vina": "وینا", "oradent": "اورادنت",
          "tacori": "تاکوری", "kalyon": "کالیون", "mulhens": "مولهنس", "lorient": "لورینت", "upsky": "آپ اسکای",
          "adonis": "آدونیس", "rozetti": "روزتی", "laser": "لیزر", "unbranded": "بدون برند"}

LINES_SQL = """
SELECT 'S' AS kind, c.Number AS code, FORMAT(i.Date, 'yyyy/MM/dd', 'fa-IR') AS date, i.Number AS inv,
       pr.Number AS product_code, pr.Name AS product, ii.MajorUnitQuantity AS qty, ii.Price AS gross, ii.NetPrice AS net,
       CASE WHEN i.Status = 11 THEN 1 ELSE 0 END AS final, i.CurrencyRef AS cur, i.OperationalCurrencyExchangeRate AS rate
FROM SLS3.InvoiceItem ii JOIN SLS3.Invoice i ON i.InvoiceID = ii.InvoiceRef
JOIN SLS3.Customer c ON c.CustomerID = i.CustomerRef JOIN SLS3.Product pr ON pr.ProductID = ii.ProductRef
WHERE i.Date >= ? AND i.Status IN ({st}) AND c.Number IN ({codes})
UNION ALL
SELECT 'Q', c.Number, FORMAT(q.Date, 'yyyy/MM/dd', 'fa-IR'), q.Number,
       pr.Number, pr.Name, qi.MajorUnitQuantity, qi.Price, qi.NetPrice, 1, q.CurrencyRef, q.OperationalCurrencyExchangeRate
FROM SLS3.SaleRequestItem qi JOIN SLS3.SaleRequest q ON q.SaleRequestID = qi.SaleRequestRef
JOIN SLS3.Customer c ON c.CustomerID = q.CustomerRef JOIN SLS3.Product pr ON pr.ProductID = qi.ProductRef
WHERE q.Date >= ? AND q.State IN ({rq}) AND c.Number IN ({codes})"""


# برند هر کد مشتری از نام حسابش («آرام (بیس)- عراق»)؛ هر برند یک کد جداست
ACCOUNT_BRANDS = [("آپ اسکای", "آپ اسکای"), ("اپ اسکای", "آپ اسکای"), ("پادینا", "پادینا"), ("بیس", "بیس"), ("جوو", "جوو"),
                  ("آرکیا", "آرکیا"), ("ارکیا", "آرکیا"), ("وینا", "وینا"), ("اورادنت", "اورادنت"), ("اوردانت", "اورادنت"),
                  ("تاکوری", "تاکوری"), ("کالیون", "کالیون"), ("مولهنس", "مولهنس"), ("لورینت", "لورینت")]


def _account_brand(name: str) -> str:
    return next((b for key, b in ACCOUNT_BRANDS if key in name), "")


def customers() -> pd.DataFrame:
    """هر کد مشتری یک حساب: نام کوتاه، کشور و برند حساب؛ label برای نمایش («آرام (بیس)»)"""
    c = pd.read_csv(CUSTOMERS_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    c["code"] = c["code"].map(loader._clean_code)
    for k in ("name", "short", "country"):
        c[k] = c[k].map(RS.norm)
    c["short"] = c["short"].where(c["short"] != "", c["name"])
    c["account"] = c["name"].map(_account_brand)
    c["label"] = [f"{s} ({b})" if b else f"{s} - {code}" for s, b, code in zip(c["short"], c["account"], c["code"])]
    return c.drop_duplicates("code")


def product_brands() -> pd.Series:
    p = pd.read_csv(RS.PRODUCTS_FILE, dtype=str, encoding="utf-8-sig").fillna("")
    p["code"] = p["code"].map(loader._clean_code)
    b = p["brand"].map(lambda x: BRANDS.get(RS.norm(x).lower().replace(" ", ""), RS.norm(x) or RS.OTHER))
    return pd.Series(b.values, index=p["code"]).groupby(level=0).first()


def new_accounts(found: pd.DataFrame, cust: pd.DataFrame) -> pd.DataFrame:
    """کدهای صادراتی جدید (خارج از شیت MAP): حساب نماینده‌ای که نام کشور خارجی دارد («فراس (مولهنس) - عراق»)"""
    found = found.assign(code=found["code"].map(loader._clean_code), name=found["name"].map(RS.norm))
    found = found[~found["code"].isin(cust["code"]) & found["code"].map(RS.code_brand).ne("")
                  & found["name"].map(RS.foreign_country).ne("")
                  & ~found["name"].map(lambda n: any(w in n for w in RS.NOT_REP))].drop_duplicates("code")
    rows = []
    for r in found.itertuples():
        short = RS.short_name(r.name)
        account = _account_brand(r.name) or RS.code_brand(r.code)
        rows.append({"code": r.code, "name": r.name.strip(" ."), "short": short, "country": RS.foreign_country(r.name),
                     "channel": "export", "account": account, "label": f"{short} ({account})", "source": "auto"})
    return pd.DataFrame(rows, columns=list(cust.columns))


def load(env_file, cfg: dict) -> dict:
    s = RK.settings(cfg)
    cust = customers().assign(source="map")
    since = RS.to_gregorian(s.get("export_from") or DEFAULT_FROM)
    cn = sql_source.connect(sql_source.settings(sql_source.read_env(env_file), prefix=RK.ENV_PREFIX))
    try:
        cur = cn.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cur.close()
        found = RK._read(cn, RS.CANDIDATES_SQL.format(st=RS.STATUSES, rq=RS.REQUEST_STATES), [since] * 2)
        cust = pd.concat([cust, new_accounts(found, cust)], ignore_index=True)
        codes = ",".join(f"'{c}'" for c in cust["code"] if c.isdigit())
        df = RK._read(cn, LINES_SQL.format(st=RS.STATUSES, rq=RS.REQUEST_STATES, codes=codes), [since] * 2)
        today = RK._read(cn, RS.TODAY_SQL, [])["d"].iloc[0]
    finally:
        cn.close()
    for k in ("code", "product_code"):
        df[k] = df[k].map(loader._clean_code)
    df["product"] = df["product"].map(loader._clean_text)
    df["inv"] = df["inv"].astype(str)
    df["year"] = df["date"].str[:4]
    df["mm"] = df["date"].str[5:7]
    for k in ("qty", "gross", "net", "rate", "cur"):
        df[k] = pd.to_numeric(df[k], errors="coerce").fillna(0.0)
    _to_usd(df)
    # سطرهای وضعیت ۲ گاهی به ریال‌اند (نمونه رایگان)؛ مبلغشان صفر است و دلار حساب نمی‌شوند
    df[["gross", "net"]] = df[["gross", "net"]].where(df["final"].eq(1), 0.0)
    # درخواست در ستون‌های جدا تا همه جمع‌های فروش فقط از فاکتور باشند
    q = df["kind"].eq("Q")
    df["req"] = df["gross"].where(q, 0.0)
    df["req_pcs"] = df["qty"].where(q, 0.0)
    df.loc[q, ["qty", "gross", "net"]] = 0.0
    cat = RS.products().reindex(df["product_code"])
    df["cat1"] = cat["cat1"].fillna(RS.OTHER).values
    df["cat2"] = cat["cat2"].fillna(RS.OTHER).values
    df["brand"] = df["product_code"].map(product_brands()).fillna(RS.OTHER)
    info = cust.set_index("code").reindex(df["code"])
    df["short"] = info["short"].values
    df["country"] = info["country"].values
    return {"lines": df, "customers": cust, "today": today}


def _to_usd(df: pd.DataFrame) -> None:
    """مبلغ سندهای غیردلاری ← دلار: با نرخ سند به ریال، سپس ÷ میانگین نرخ دلار اسناد دلاری همان ماه
    (ماه بدون سند دلاری: نزدیک‌ترین ماه قبل، وگرنه بعد).
    سطر دلاری با قیمت واحد بیش از MAX_UNIT_USD اشتباه ریالی ثبت شده (مثل درخواست ۲۳۳۱۷)؛ با نرخ همان سند به دلار می‌رود."""
    wrong = df["cur"].eq(USD) & df["rate"].gt(1) & (df["gross"] > MAX_UNIT_USD * df["qty"].clip(lower=1))
    for k in ("gross", "net"):
        df.loc[wrong, k] = df.loc[wrong, k] / df.loc[wrong, "rate"]
    ym = df["date"].str[:7]
    usd = df["cur"].eq(USD)
    ok = usd & df["rate"].gt(1)
    rates = df.loc[ok, "rate"].groupby(ym[ok]).mean()
    if rates.empty:
        return
    rates = rates.reindex(sorted(set(ym) | set(rates.index))).ffill().bfill()
    factor = (df["rate"].where(df["rate"] > 0, 1.0) / ym.map(rates)).where(~usd, 1.0)
    for k in ("gross", "net"):
        df[k] = df[k] * factor


# ---------------------------------------------------------------- محاسبه
METRICS = ("net", "gross", "pcs", "req", "req_pcs")


def _agg(d: pd.DataFrame, by) -> pd.DataFrame:
    return d.groupby(by).agg(net=("net", "sum"), gross=("gross", "sum"), pcs=("qty", "sum"),
                             req=("req", "sum"), req_pcs=("req_pcs", "sum"))


def _years(snap: dict, f: dict) -> tuple[str, str, str]:
    """سال انتخابی، سال قبل و روز مرز مقایسه (امروز برای سال جاری، پایان سال برای سال‌های گذشته)"""
    today = snap["today"]
    y = f.get("year")
    if not y or y >= today[:4] or y not in set(snap["lines"]["year"]):
        return today[:4], str(int(today[:4]) - 1), today
    return y, str(int(y) - 1), f"{y}/12/31"


def _monthly(cur: pd.DataFrame, prev: pd.DataFrame) -> list[dict]:
    """۱۲ ماه با مقدار و انباشته هر شاخص در دو سال"""
    m1, m0 = _agg(cur, "mm"), _agg(prev, "mm")
    acc, rows = {}, []
    for i in range(1, 13):
        mm = f"{i:02d}"
        row = {"mm": mm}
        for m in METRICS:
            row[m], row[m + "_ly"] = float(m1[m].get(mm, 0.0)), float(m0[m].get(mm, 0.0))
        for key in [k for k in row if k != "mm"]:
            acc[key] = acc.get(key, 0.0) + row[key]
            row["cum_" + key] = acc[key]
        rows.append(row)
    return rows


def _filter(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    """فیلترهای اسلایسر: ماه‌ها (هر دو سال)، برند، گروه کالا، کشور، مشتری (کد)، کالا"""
    m = pd.Series(True, index=df.index)
    if f.get("months"):
        m &= df["mm"].isin(f["months"])
    for k, col in (("brand", "brand"), ("cat", "cat1"), ("country", "country"), ("customer", "code"), ("product", "product_code")):
        if f.get(k):
            m &= df[col].isin(f[k])
    return df[m]


def _scope_codes(snap: dict, f: dict) -> pd.Index:
    """کدهای مشتری یکتای فهرست صادراتی در محدوده فیلتر کشور و مشتری"""
    c = snap["customers"]
    if f.get("country"):
        c = c[c["country"].isin(f["country"])]
    if f.get("customer"):
        c = c[c["code"].isin(f["customer"])]
    return pd.Index(c["code"].unique())


def _two_years(d: pd.DataFrame, by: str, y: str, ly: str) -> pd.DataFrame:
    """۱۴۰۴ و ۱۴۰۵ کنار هم، مثل جدول‌های شیت Country"""
    cur, prev = _agg(d[d["year"] == y], by), _agg(d[d["year"] == ly], by)
    g = cur.join(prev, how="outer", lsuffix="", rsuffix="_ly").fillna(0.0)
    g["growth"] = [n / p - 1 if p else None for n, p in zip(g["net"], g["net_ly"])]
    g["share"] = g["net"] / g["net"].sum() if g["net"].sum() else None
    return g.reset_index().rename(columns={by: "key"}).sort_values(["net", "net_ly"], ascending=False)


def report(snap: dict, f: dict) -> dict:
    df = snap["lines"]
    y, ly, today = _years(snap, f)
    d = _filter(df, f)
    cur = d[d["year"] == y]
    # مقایسه منصفانه: همان بازه سال قبل (تا همین روز از سال)
    same = d[(d["year"] == ly) & (d["date"].str[5:] <= today[5:])]
    k = {"net": float(cur["net"].sum()), "pcs": float(cur["qty"].sum()), "gross": float(cur["gross"].sum()),
         "req": float(cur["req"].sum()), "req_pcs": float(cur["req_pcs"].sum()),
         "net_ly_same": float(same["net"].sum()), "pcs_ly_same": float(same["qty"].sum()),
         "gross_ly_same": float(same["gross"].sum()), "req_ly_same": float(same["req"].sum()),
         "net_ly_full": float(d.loc[d["year"] == ly, "net"].sum()), "pcs_ly_full": float(d.loc[d["year"] == ly, "qty"].sum()),
         "customers": int(cur.loc[cur["qty"] > 0, "code"].nunique()), "countries": int(cur.loc[cur["qty"] > 0, "country"].nunique()),
         # تعداد مشتری = کد یکتا (با فیلتر کشور / مشتری)؛ فعال = خرید از ابتدای سال، بقیه بدون خرید
         "customers_total": int(_scope_codes(snap, f).size),
         "invoices": int(cur[cur["net"] != 0].drop_duplicates(["code", "date"]).shape[0]), "skus": int(cur["product_code"].nunique())}
    k["customers_inactive"] = k["customers_total"] - k["customers"]
    k["growth"] = k["net"] / k["net_ly_same"] - 1 if k["net_ly_same"] else None
    k["growth_pcs"] = k["pcs"] / k["pcs_ly_same"] - 1 if k["pcs_ly_same"] else None
    k["growth_gross"] = k["gross"] / k["gross_ly_same"] - 1 if k["gross_ly_same"] else None
    k["growth_req"] = k["req"] / k["req_ly_same"] - 1 if k["req_ly_same"] else None
    k["disc_rate"] = 1 - k["net"] / k["gross"] if k["gross"] else None
    k["fill"] = k["pcs"] / k["req_pcs"] if k["req_pcs"] else None
    k["avg_invoice"] = k["net"] / k["invoices"] if k["invoices"] else None
    # کشور ← کد مشتری (شیت Country)؛ هر کد (هر برند یک مشتری) یک سطر
    countries = _two_years(d, "country", y, ly)
    by_cust = _two_years(d, "code", y, ly)
    info = snap["customers"].set_index("code")
    for col in ("label", "short", "name", "country", "account", "source"):
        by_cust[col] = by_cust["key"].map(info[col])
    clean = by_cust.astype(object).where(by_cust.notna(), None)  # رشد بدون سال قبل = None (NaN در JSON نمی‌آید)
    countries["customers"] = [clean[clean["country"] == c].to_dict("records") for c in countries["key"]]
    # روند YTD: ماهانه و انباشته هر دو سال (شیت YTD Trend)
    trend = [{**r, "future": r["mm"] > today[5:7]} for r in _monthly(cur, d[d["year"] == ly])]
    # مشتری ← گروه ← کالا (شیت SKU&Category)
    sku = (cur[cur["kind"] == "S"].groupby(["code", "cat2", "product_code", "product"]).agg(net=("net", "sum"), pcs=("qty", "sum")).reset_index())
    sku["label"] = sku["code"].map(info["label"])
    base = df[df["year"].isin([y, ly])]
    return {"year": y, "ly": ly, "today": today, "current": y == snap["today"][:4],
            "years": sorted(df["year"].unique().tolist(), reverse=True), "kpis": k,
            "brands": _two_years(d, "brand", y, ly), "categories": _two_years(d, "cat1", y, ly),
            "categories2": _two_years(d, "cat2", y, ly), "customers": by_cust, "countries": countries,
            "trend": trend, "sku": sku,
            "options": {"brand": sorted(base["brand"].unique().tolist()), "cat": sorted(base["cat1"].unique().tolist()),
                        "country": sorted(snap["customers"]["country"].unique().tolist()),
                        "customer": [{"code": r.code, "label": r.label, "country": r.country}
                                     for r in snap["customers"].sort_values(["label", "code"]).itertuples()],
                        "product": _product_options(df, y)}}


def _product_options(df: pd.DataFrame, y: str) -> list[dict]:
    """کالاهای صادرشده، از بیشترین فروش دلاری سال جاری"""
    net = df[df["year"] == y].groupby("product_code")["net"].sum()
    p = df.drop_duplicates("product_code", keep="last")[["product_code", "product", "cat2"]]
    p = p.assign(net=p["product_code"].map(net).fillna(0.0)).sort_values(["net", "product_code"], ascending=[False, True])
    return [{"code": r.product_code, "name": r.product, "cat": r.cat2} for r in p.itertuples()]


def customer(snap: dict, code: str, f: dict) -> dict | None:
    """پرونده یک کد مشتری صادراتی: روند ماهانه دو سال، گروه‌ها، کالاها و فاکتورها"""
    cust = snap["customers"]
    acc = cust[cust["code"] == code]
    if acc.empty:
        return None
    df = snap["lines"]
    y, ly, today = _years(snap, f)
    d = _filter(df[df["code"].isin(acc["code"])], {**f, "customer": None})
    cur = d[d["year"] == y]
    monthly = _monthly(cur, d[d["year"] == ly])
    # فاکتور و درخواست در یک جدول: مبلغ فاکتور خالص، مبلغ درخواست ناخالص
    inv = (d.assign(amount=d["net"] + d["req"], n=d["qty"] + d["req_pcs"])
           .groupby(["kind", "inv", "date", "code"]).agg(net=("amount", "sum"), pcs=("n", "sum"), lines=("product_code", "size"))
           .reset_index().sort_values(["date", "inv"], ascending=False))
    inv["kind"] = inv["kind"].map({"S": "فاکتور", "Q": "درخواست"})
    prods = (cur[cur["kind"] == "S"].groupby(["product_code", "product", "brand", "cat2"]).agg(net=("net", "sum"), pcs=("qty", "sum"))
             .reset_index().sort_values(["net", "pcs"], ascending=False))
    same = d[(d["year"] == ly) & (d["date"].str[5:] <= today[5:])]
    k = {"net": float(cur["net"].sum()), "pcs": float(cur["qty"].sum()), "gross": float(cur["gross"].sum()),
         "req": float(cur["req"].sum()), "req_pcs": float(cur["req_pcs"].sum()), "net_ly_same": float(same["net"].sum()),
         "net_ly_full": float(d.loc[d["year"] == ly, "net"].sum()), "pcs_ly_full": float(d.loc[d["year"] == ly, "qty"].sum()),
         "invoices": int(cur[cur["net"] != 0].drop_duplicates(["code", "date"]).shape[0])}
    k["growth"] = k["net"] / k["net_ly_same"] - 1 if k["net_ly_same"] else None
    all_d = df[df["code"].isin(acc["code"]) & df["qty"].gt(0)]
    return {"code": code, "short": acc["short"].iloc[0], "label": acc["label"].iloc[0], "name": acc["name"].iloc[0],
            "account": acc["account"].iloc[0], "country": acc["country"].iloc[0], "year": y, "ly": ly,
            "accounts": acc[["code", "name"]].to_dict("records"), "kpis": k, "monthly": monthly,
            "last_date": all_d["date"].max() if len(all_d) else None,
            "brands": _two_years(d, "brand", y, ly), "categories": _two_years(d, "cat2", y, ly),
            "products": prods, "invoices": inv}


def parse_filters(qp) -> dict:
    """پارامترهای تکراری درخواست ← فیلتر"""
    year = qp.get("year") or ""
    return {"year": year if re.fullmatch(r"\d{4}", year) else None,
            "months": [m for m in qp.getlist("month") if re.fullmatch(r"\d{2}", m)],
            "brand": qp.getlist("brand"), "cat": qp.getlist("cat"), "country": qp.getlist("country"),
            "customer": qp.getlist("customer"), "product": qp.getlist("product")}
