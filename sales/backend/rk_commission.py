"""پورسانت نمایندگان راهکاران (B2B) و مشتریان صادراتی — جدولی مثل «پورسانت» هیبریدها.

هنوز دستورالعمل کامل ندارد: فعلاً ۰٫۲٪ فروش خالص + تخفیف نقدی (اعلام کاربر). مبنای پورسانت (ناخالص / خالص / خالص + نقدی، با یا بدون کسر برگشتی)، نرخ پیش‌فرض، ذخیره و
نرخ جدای هر کد در تنظیمات همان ماه (data/rk_commission/<کانال>/YYYY-MM.json) ذخیره می‌شوند؛ ماه تازه تنظیمات آخرین
ماه قبل را می‌گیرد. هیچ چیز در راهکاران نوشته نمی‌شود.

داده: سطرهای فاکتور، برگشتی و درخواست همان FactorySourceهای rahkaran_sales و rahkaran_export.
  ناخالص = InvoiceItem.Price ، خالص = NetPrice (پس از همه تخفیف‌ها، با مالیات) ، تخفیف نقدی / مدیریتی / مالیات از
  سیاست‌های فروش هر قلم؛ سایر تخفیف‌ها = ناخالص + مالیات − خالص − نقدی − مدیریتی.
  صادرات: مبالغ به دلار تبدیل شده‌اند (rahkaran_export._to_usd)؛ اینجا با نرخ ریالی همان سطر (rial_rate) به ریال
  برمی‌گردند تا جدول با B2B یکی باشد. ستون‌های دلاری جدا هم هست. صادرات برگشتی ندارد (در داده صادرات نیست).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

WHOLESALE_INVOICE = 7000 * 1e6   # فاکتور بالای ۷۰۰ میلیون تومان (مثل پورسانت هیبریدها)
CHANNELS = {"b2b": "نمایندگان B2B", "export": "صادرات"}
BASES = {"gross": "فروش ناخالص", "net": "فروش خالص", "net_cash": "فروش خالص + تخفیف نقدی"}
# نرخ پورسانت نمایندگان و صادرات: ۰٫۲٪ فروش خالص + تخفیف نقدی (برگشتی کسر شده) — اعلام کاربر، تا دستورالعمل کامل
DEFAULTS = {"base": "net_cash", "subtract_returns": True, "default_rate": 0.002, "reserve": 0.0, "rates": {}}


# ---------------------------------------------------------------- تنظیمات ماهانه
class Store:
    def __init__(self, folder: Path):
        self.folder = folder

    def _path(self, channel: str, month: str) -> Path:
        return self.folder / channel / f"{month.replace('/', '-')}.json"

    def get(self, channel: str, month: str) -> dict:
        p = self._path(channel, month)
        if p.is_file():
            return {**DEFAULTS, **json.loads(p.read_text(encoding="utf-8")), "saved": True}
        d = self.folder / channel
        prev = sorted(x.stem.replace("-", "/") for x in d.glob("1*.json") if x.stem.replace("-", "/") < month) if d.is_dir() else []
        src = json.loads(self._path(channel, prev[-1]).read_text(encoding="utf-8")) if prev else {}
        src.pop("updated_at", None)
        return {**DEFAULTS, **src, "saved": False, "from": prev[-1] if prev else None}

    def put(self, channel: str, month: str, s: dict) -> dict:
        p = self._path(channel, month)
        p.parent.mkdir(parents=True, exist_ok=True)
        keep = {k: s[k] for k in DEFAULTS if k in s}
        keep["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
        return {**DEFAULTS, **keep, "saved": True}


def clean_settings(body: dict) -> dict:
    """ورودی ذخیره ← تنظیمات معتبر (نرخ‌ها کسر اعشاری، ۰ تا ۱)."""
    rate = lambda v: min(max(float(v), 0.0), 1.0)
    out = {"base": body.get("base") if body.get("base") in BASES else DEFAULTS["base"],
           "subtract_returns": bool(body.get("subtract_returns", True)),
           "default_rate": rate(body.get("default_rate") or 0), "reserve": rate(body.get("reserve") or 0), "rates": {}}
    for code, v in (body.get("rates") or {}).items():
        if v is not None and v != "" and re.fullmatch(r"[\w-]+", str(code)):
            out["rates"][str(code)] = rate(v)
    return out


# ---------------------------------------------------------------- محاسبه
def months(lines: pd.DataFrame, today: str) -> list[str]:
    """ماه‌های دارای فاکتور از ابتدای سال قبل تا ماه جاری، جدیدترین اول."""
    y = int(today[:4])
    ms = set(lines.loc[lines["kind"].eq("S"), "date"].str[:7])
    ms.add(today[:7])
    return sorted((m for m in ms if int(m[:4]) >= y - 1 and m <= today[:7]), reverse=True)


def _ensure(df: pd.DataFrame) -> pd.DataFrame:
    for k in ("cash", "mgmt", "tax", "req"):
        if k not in df:
            df = df.assign(**{k: 0.0})
    return df


def _aggregate(df: pd.DataFrame, month: str, rial: bool) -> pd.DataFrame:
    """جمع‌های هر کد مشتری در ماه. rial=True: سطرهای دلاری صادرات با rial_rate به ریال (ستون‌های *_usd جدا)."""
    df = _ensure(df)
    m = df[df["date"].str[:7].eq(month)]
    money = ["gross", "net", "cash", "mgmt", "tax", "req"]
    if rial:
        usd = m[["gross", "net"]].rename(columns=lambda c: c + "_usd")
        m = m.assign(**{k: m[k] * m["rial_rate"] for k in money}).join(usd)
    s, r = m[m["kind"].eq("S")], m[m["kind"].eq("R")]
    g = s.groupby("code").agg(gross=("gross", "sum"), net=("net", "sum"), cash=("cash", "sum"), mgmt=("mgmt", "sum"),
                              tax=("tax", "sum"), qty=("qty", "sum"), invoices=("inv", "nunique"),
                              skus=("product_code", "nunique"))
    if rial:
        g = g.join(s.groupby("code")[["gross_usd", "net_usd"]].sum())
    # درخواست: B2B سطرهای Q (ناخالص)، صادرات ستون req سطرهای Q
    q = m[m["kind"].eq("Q")]
    g = g.join((q["req"] if rial else q["gross"]).groupby(q["code"]).sum().rename("req"), how="outer")
    g = g.join(r["net"].abs().groupby(r["code"]).sum().rename("returns"), how="outer")
    # فاکتورها: عمده (ناخالص بالای ۷۰۰ م تومان) و دارای تخفیف مدیریتی
    inv = s.groupby(["code", "inv"]).agg(gross=("gross", "sum"), net=("net", "sum"), cash=("cash", "sum"), mgmt=("mgmt", "sum"))
    big = inv[inv["gross"] > WHOLESALE_INVOICE]
    md = inv[inv["mgmt"] > 0]
    g = g.join(big.groupby(level=0).size().rename("wholesale_n"), how="left")
    g = g.join(big["gross"].groupby(level=0).sum().rename("wholesale_gross"), how="left")
    g = g.join(md.groupby(level=0).size().rename("mgmt_n"), how="left")
    g = g.join(md["gross"].groupby(level=0).sum().rename("mgmt_inv_gross"), how="left")
    g = g.join((md["net"] + md["cash"]).groupby(level=0).sum().rename("mgmt_inv_net_cash"), how="left")
    return g.fillna(0.0)


def _ytd(df: pd.DataFrame, month: str, rial: bool) -> pd.DataFrame:
    """فروش ناخالص و خالص هر کد از ابتدای سال همین ماه تا پایان آن (برای تایید اعتباری مثل هیبریدها).
    خالص = خالص فاکتورها − خالص برگشتی‌های همان بازه؛ ناخالص فقط فاکتورها."""
    df = _ensure(df)
    y = df[df["kind"].isin(["S", "R"]) & df["date"].str[:4].eq(month[:4]) & (df["date"].str[:7] <= month)]
    if rial:
        y = y.assign(gross=y["gross"] * y["rial_rate"], net=y["net"] * y["rial_rate"], cash=y["cash"] * y["rial_rate"])
    sign = y["kind"].map({"S": 1.0, "R": -1.0})
    y = y.assign(gross=y["gross"].where(y["kind"].eq("S"), 0.0), net=y["net"].abs() * sign, cash=y["cash"].where(y["kind"].eq("S"), 0.0))
    g = y.groupby("code").agg(gross_ytd=("gross", "sum"), net_ytd=("net", "sum"), cash_ytd=("cash", "sum"))
    g["net_cash_ytd"] = g["net_ytd"] + g["cash_ytd"]
    return g.drop(columns="cash_ytd")


def _ly(df: pd.DataFrame, month: str, today: str, rial: bool) -> pd.Series:
    """فروش خالص همان ماه سال قبل (ماه جاری: تا همین روز ماه)."""
    lm = f"{int(month[:4]) - 1}{month[4:]}"
    d = df[df["kind"].eq("S") & df["date"].str[:7].eq(lm)]
    if month == today[:7]:
        d = d[d["date"].str[8:] <= today[8:]]
    v = d["net"] * d["rial_rate"] if rial else d["net"]
    return v.groupby(d["code"]).sum()


def compute(snap: dict, channel: str, month: str, s: dict) -> dict:
    """یک سطر برای هر کد مشتری فهرست که در ماه یا از ابتدای سال فروش، برگشتی یا درخواست دارد."""
    rial = channel == "export"
    df, today = snap["lines"], snap["today"]
    g = _aggregate(df, month, rial)
    ytd = _ytd(df, month, rial)
    ly = _ly(df, month, today, rial)
    cust = snap["customers"].drop_duplicates("code").set_index("code")
    codes = [c for c in cust.index if c in g.index or (c in ytd.index and ytd.at[c, "net_ytd"] != 0)]
    base_key, sub_ret = s["base"], s["subtract_returns"]
    rows = []
    for c in codes:
        a = g.loc[c] if c in g.index else None
        v = (lambda k: float(a[k]) if a is not None and k in a.index else 0.0)
        info = cust.loc[c]
        gross, inv_net, cash, mgmt, tax = v("gross"), v("net"), v("cash"), v("mgmt"), v("tax")
        returns = v("returns")  # مبلغ خالص برگشتی (مثبت)
        net = inv_net - returns  # فروش خالص = خالص فاکتورها − برگشتی‌های همان ماه
        net_cash = net + cash
        base = {"gross": gross - (returns if sub_ret else 0.0), "net": net, "net_cash": net_cash}[base_key]
        own = s["rates"].get(c)
        rate = own if own is not None else s["default_rate"]
        comm = max(base, 0.0) * rate
        row = {"code": c, "name": str(info.get("name", "")), "short": str(info.get("short", "")),
               "brand": str(info.get("brand", "") if not rial else info.get("account", "")),
               "province": str(info.get("province", "") if not rial else info.get("country", "")),
               "city": "" if rial else str(info.get("city", "")),
               "label": str(info.get("label", "")) if rial else str(info.get("short", "")),
               "invoices": int(v("invoices")), "skus": int(v("skus")), "qty": v("qty"),
               "req": v("req"), "gross": gross, "mgmt": mgmt, "cash": cash, "tax": tax,
               "other_disc": max(gross + tax - inv_net - cash - mgmt, 0.0) if gross else 0.0,
               "disc_total": gross + tax - inv_net if gross else 0.0,
               "inv_net": inv_net, "net": net, "net_cash": net_cash, "returns": returns,
               "mgmt_n": int(v("mgmt_n")), "mgmt_inv_gross": v("mgmt_inv_gross"), "mgmt_inv_net_cash": v("mgmt_inv_net_cash"),
               "mgmt_rate": mgmt / v("mgmt_inv_gross") if v("mgmt_inv_gross") > 0 else None,
               "mgmt_pct": mgmt / gross if gross > 0 else None, "cash_pct": cash / gross if gross > 0 else None,
               "disc_pct": (gross + tax - inv_net) / gross if gross > 0 else None,
               "wholesale_n": int(v("wholesale_n")), "wholesale_gross": v("wholesale_gross"),
               "wholesale_pct": v("wholesale_gross") / gross if gross > 0 else None,
               "ly_net": float(ly.get(c, 0.0)),
               "growth": net / float(ly.get(c)) - 1 if float(ly.get(c, 0.0)) > 0 else None,
               "gross_ytd": float(ytd.at[c, "gross_ytd"]) if c in ytd.index else 0.0,
               "net_ytd": float(ytd.at[c, "net_ytd"]) if c in ytd.index else 0.0,
               "net_cash_ytd": float(ytd.at[c, "net_cash_ytd"]) if c in ytd.index else 0.0,
               "base": base, "rate": rate, "rate_own": own is not None, "commission": comm,
               "reserve": comm * s["reserve"], "payable": comm * (1 - s["reserve"])}
        if rial:
            row.update(gross_usd=v("gross_usd"), net_usd=v("net_usd"))
        rows.append(row)
    rows.sort(key=lambda r: -r["net"])
    return {"rows": rows}

