"""برنامه‌ریزی فروش و تارگت: شعبه × گروه کالا، تعدادی و ریالی.

روش (بدون ML، قابل توضیح برای هر عدد):
  فروش روزانه پایه = میانگین وزنی فروش هر روز کاری در N ماه سالم اخیر شعبه (جدیدتر وزن بیشتر)،
                     پس از حذف اثر فصل (تقسیم بر ضریب فصلی همان ماه)
  پیشنهاد          = فروش روزانه پایه × ضریب فصلی ماه هدف × روز کاری ماه هدف
  تارگت نهایی       = پیشنهاد × (۱ + رشد) — یا عددی که کاربر دستی وارد کرده
  تارگت ریالی       = تارگت تعدادی × قیمت فعلی (آخرین قیمت فروش هر کالا × ترکیب فروش × نسبت خالص به ناخالص)

ضریب فصلی فقط از تاریخچه قدیمی (قبل از history_from) گرفته می‌شود و به سمت ۱ تعدیل می‌شود.
ماه‌های غیرعادی (جنگ، قطعی اینترنت، فروردین‌ها) در هیچ محاسبه‌ای استفاده نمی‌شوند.
تارگت‌ها فقط در data/plans ذخیره می‌شوند؛ هیچ چیز در دیتابیس کارآمد نوشته نمی‌شود.
"""
from __future__ import annotations

import bisect
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

SEP = "\x1f"
OTHERS = "سایر گروه‌ها"
DEFAULTS = {
    # ماه‌های غیرعادی: جنگ (اسفند ۱۴۰۴ تا فروردین ۱۴۰۵)، قطعی اینترنت و اتفاقات داخلی (دی و بهمن ۱۴۰۴)،
    # فروردین ۱۴۰۳ بدون داده
    "abnormal_months": ["1403/01", "1404/10", "1404/11", "1404/12", "1405/01"],
    "farvardin_abnormal": True,   # همه فروردین‌ها (تعطیلات نوروز) غیرعادی‌اند
    "base_months": 3,             # تعداد ماه‌های سالم اخیر برای فروش پایه
    "season": True,               # اعمال ضریب فصلی
    "season_shrink": 0.75,        # چه سهمی از فاصله ضریب تا ۱ اعمال شود (۰ = بدون فصل، ۱ = کامل)؛ با بک‌تست انتخاب شده
    "green": 0.97,                # پیش‌بینی ÷ تارگت ≥ این مقدار: روی مسیر
    "yellow": 0.85,               # ≥ این مقدار: عقب ولی قابل جبران؛ کمتر: قرمز
    "price_alert": 0.03,          # تغییر قیمت بیش از این: هشدار
    "main_share": 0.92,           # گروه‌های پرفروش تا این سهم تجمعی ستون جدا دارند
    "main_min_share": 0.008,
    "main_max": 14,
}
MIN_MIX_QTY = 30           # کمتر از این تعداد در شعبه × گروه: ترکیب کالای کل شرکت استفاده می‌شود
PRICE_WINDOW_DAYS = 7      # قیمت فعلی هر کالا = میانه وزنی قیمت در ۷ روز آخرِ فروش آن کالا
DISC_WINDOW_DAYS = 60      # نسبت خالص به ناخالص از ۶۰ روز اخیر
PREV_PRICE_DAYS = (45, 30)  # قیمت «قبلی» برای تشخیص تغییر قیمت: بازه ۴۵ تا ۳۰ روز پیش


# ---------------------------------------------------------------- تنظیمات و ذخیره
def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("plan") or {})}


def month_add(m: str, k: int) -> str:
    i = int(m[:4]) * 12 + int(m[5:7]) - 1 + k
    return f"{i // 12}/{i % 12 + 1:02d}"


def is_abnormal(m: str, ps: dict) -> bool:
    return m in set(ps["abnormal_months"]) or (bool(ps.get("farvardin_abnormal")) and m[5:7] == "01")


class PlanStore:
    """هر ماه یک فایل JSON: رشد، روز کاری، اصلاحات دستی و (پس از قفل) عکس فوری تارگت‌ها و قیمت‌ها."""

    def __init__(self, folder: Path):
        self.folder = folder

    def _path(self, month: str) -> Path:
        return self.folder / f"{month.replace('/', '-')}.json"

    def get(self, month: str) -> dict:
        p = self._path(month)
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
        return {"month": month, "growth": 0.0, "wd": None, "overrides": {}, "locked": False, "snapshot": None,
                "saved": False}

    def put(self, plan: dict):
        self.folder.mkdir(parents=True, exist_ok=True)
        plan = {**plan, "saved": True, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        tmp = self._path(plan["month"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self._path(plan["month"]))
        return plan

    def months(self) -> list[str]:
        if not self.folder.is_dir():
            return []
        return sorted(p.stem.replace("-", "/") for p in self.folder.glob("*.json"))


# ---------------------------------------------------------------- تقویم
class Calendar:
    """روز کاری = همه روزها به‌جز جمعه (تقویم کارآمد). بدون تقویم: روزهای دارای فروش."""

    def __init__(self, cal: pd.DataFrame | None, sales_dates):
        if cal is not None and len(cal):
            c = cal.sort_values("date")
            self.dates = c["date"].tolist()
            self.work = dict(zip(c["date"], c["workday"].astype(bool)))
            self.available = True
        else:
            self.dates = sorted(set(sales_dates))
            self.work = {d: True for d in self.dates}
            self.available = False
        self.wd: dict[str, int] = {}
        for d in self.dates:
            if self.work[d]:
                self.wd[d[:7]] = self.wd.get(d[:7], 0) + 1

    def wd_month(self, m: str) -> int | None:
        return self.wd.get(m)

    def days_before(self, d: str, n: int) -> str:
        i = bisect.bisect_left(self.dates, d)
        return self.dates[max(0, min(i, len(self.dates) - 1) - n)] if self.dates else d

    def month_dates(self, m: str) -> list[str]:
        i = bisect.bisect_left(self.dates, f"{m}/00")
        out = []
        while i < len(self.dates) and self.dates[i][:7] == m:
            out.append(self.dates[i])
            i += 1
        return out


# ---------------------------------------------------------------- ضریب فصلی
def _season_from(series: pd.Series, cal: Calendar) -> tuple[dict, int] | None:
    """series: ماه ← تعداد. نسبت فروش هر روز کاری به میانگین همان سال؛ میانه سال‌ها برای هر ماه."""
    df = pd.DataFrame({"qty": series})
    df["wd"] = [cal.wd_month(m) or np.nan for m in df.index]
    df["rate"] = df["qty"] / df["wd"]
    df["y"], df["mm"] = df.index.str[:4], df.index.str[5:7]
    parts = []
    for _, g in df.groupby("y"):
        g = g[g["rate"] > 0]
        if len(g) < 3:
            continue
        g = g[g["rate"] >= 0.25 * g["rate"].median()]  # ماه‌های راه‌اندازی یا تقریباً خالی
        if len(g) < 9:
            continue
        parts.append(pd.DataFrame({"mm": g["mm"], "r": g["rate"] / g["rate"].mean()}))
    if len(parts) < 3:
        return None
    r = pd.concat(parts).groupby("mm")["r"].agg(["median", "count"])
    r = r[r["count"] >= 3]["median"]
    if len(r) < 10:
        return None
    return (r / r.mean()).to_dict(), len(parts)


def season_index(old: pd.DataFrame | None, cal: Calendar, ps: dict) -> dict:
    out = {"available": False, "total": {}, "by_cat": {}, "years": 0}
    if old is None or not len(old) or not cal.available:
        return out
    o = old[~old["month"].map(lambda m: is_abnormal(m, ps))]
    tot = o.groupby("month")["qty"].sum()
    t = _season_from(tot, cal)
    if t is None:
        return out
    out.update(available=True, total=t[0], years=t[1], first=o["month"].min(), last=o["month"].max())
    share = o.groupby("category")["qty"].sum() / o["qty"].sum()
    for cat in share[share >= 0.02].index:
        c = _season_from(o[o["category"] == cat].groupby("month")["qty"].sum(), cal)
        if c is not None:
            out["by_cat"][cat] = c[0]
    return out


def season_factor(season: dict, ps: dict, cat: str, mm: str) -> float:
    if not ps.get("season") or not season.get("available"):
        return 1.0
    raw = season["by_cat"].get(cat, season["total"]).get(mm, 1.0)
    return float(min(max(1 + float(ps["season_shrink"]) * (raw - 1), 0.5), 1.8))


# ---------------------------------------------------------------- محاسبات اصلی
def _wmedian(values: np.ndarray, weights: np.ndarray) -> float:
    o = np.argsort(values)
    v, w = values[o], weights[o]
    c = np.cumsum(w)
    return float(v[np.searchsorted(c, c[-1] / 2)])


class Planner:
    def __init__(self, data: dict, cfg: dict, ctx: dict):
        self.ps = settings(cfg)
        self.s = data["sales"]
        self.meta = data["meta"]
        pi = data.get("plan_inputs") or {}
        self.inputs_fetched = pi.get("fetched")
        self.cal = Calendar(pi.get("calendar"), self.s["date"].unique())
        self.cur = self.meta["month"]
        self.today = self.meta.get("today") or self.s["date"].max()
        self.ctx = ctx
        self.season = season_index(pi.get("old"), self.cal, self.ps)
        self.mbc = self.s.groupby(["month", "branch", "category"], observed=True)[["qty", "net", "gross"]].sum()
        self.mbc_df = self.mbc.reset_index()
        self.months = sorted(self.s["month"].unique())
        pos = self.s[self.s["qty"] > 0]
        self.first_month = pos.groupby("branch", observed=True)["month"].min().to_dict()
        self._price = None
        self._curve = None

    # -- روز کاری
    def wd(self, m: str) -> float:
        if m == self.cur and self.ctx.get("wd_total"):
            return float(self.ctx["wd_total"])
        return float(self.cal.wd_month(m) or 26)

    def normal_closed(self, before: str) -> list[str]:
        return [m for m in self.months if m < before and m < self.cur and not is_abnormal(m, self.ps)]

    def main_categories(self) -> list[str]:
        ms = self.normal_closed(self.cur)[-self.ps["base_months"]:]
        net = self.s[self.s["month"].isin(ms)].groupby("category", observed=True)["net"].sum()
        net = net[net > 0].sort_values(ascending=False)
        share = net / net.sum()
        out, cum = [], 0.0
        for c, v in share.items():
            if cum >= self.ps["main_share"] or v < self.ps["main_min_share"] or len(out) >= self.ps["main_max"]:
                break
            out.append(c)
            cum += v
        return out

    # -- پیشنهاد تارگت
    def suggestions(self, target: str, cutoff: str | None = None, season: bool | None = None) -> tuple[pd.DataFrame, dict]:
        """پیشنهاد تعدادی هر شعبه × گروه برای ماه target فقط با داده ماه‌های قبل از cutoff (پیش‌فرض: ماه جاری)."""
        ps = dict(self.ps)
        if season is not None:
            ps["season"] = season
        lim = min(target, cutoff or self.cur)
        closed = [m for m in self.months if m < lim and m < self.cur and not is_abnormal(m, ps)]
        recent = [m for m in self.months if m < lim][-2:]  # شعبه بدون فروش در دو ماه اخیر: غیرفعال
        n = int(ps["base_months"])
        f_t = lambda cat: season_factor(self.season, ps, cat, target[5:7])
        rows, info = [], {"branches": {}, "inactive": []}
        for b, fm in sorted(self.first_month.items()):
            if fm >= lim:
                continue
            if not any((m, b) in self._mb_index() and self._mb_qty(m, b) > 0 for m in recent):
                info["inactive"].append(b)
                continue
            ms = [m for m in closed if m > fm][-n:]  # ماه اول هر شعبه ناقص است
            info["branches"][b] = {"base_months": ms, "first_month": fm, "new": len(ms) < 2}
            if not ms:
                continue
            sub = self.mbc_df[self.mbc_df["month"].isin(ms) & (self.mbc_df["branch"] == b)]
            pv = sub.pivot_table(index="category", columns="month", values="qty", aggfunc="sum",
                                 fill_value=0.0, observed=True).reindex(columns=ms, fill_value=0.0)
            if not len(pv):
                continue
            w = np.arange(1, len(ms) + 1, dtype=float)
            des = np.column_stack([
                pv[m].values / self.wd(m) / np.array([season_factor(self.season, ps, c, m[5:7]) for c in pv.index])
                for m in ms])
            base = (des * w).sum(axis=1) / w.sum()
            for cat, bse, last in zip(pv.index, base, pv[ms[-1]].values):
                sug = max(bse, 0.0) * f_t(cat) * self.wd(target)
                rows.append({"branch": b, "category": cat, "base": max(bse, 0.0), "idx": f_t(cat),
                             "suggest": float(np.round(sug)), "base_last": float(last)})
        df = pd.DataFrame(rows, columns=["branch", "category", "base", "idx", "suggest", "base_last"])
        return df, info

    def _mb_index(self):
        if not hasattr(self, "_mb"):
            self._mb = self.s.groupby(["month", "branch"], observed=True)["qty"].sum()
        return self._mb.index

    def _mb_qty(self, m, b) -> float:
        return float(self._mb.get((m, b), 0.0))

    # -- قیمت‌ها
    def prices(self) -> dict:
        """قیمت فعلی هر کالا، ترکیب فروش، نسبت خالص/ناخالص و تشخیص تغییر قیمت اخیر."""
        if self._price is not None:
            return self._price
        sale = self.s[(~self.s["is_return"]) & (self.s["qty"] > 0) & (self.s["unit_price"] > 0)]
        end = self.today
        recent = sale[sale["date"] >= self.cal.days_before(end, DISC_WINDOW_DAYS)]
        cols = ["product_code", "category", "date", "unit_price", "qty"]
        r = recent[cols].copy()
        last = r.groupby("product_code", observed=True)["date"].max()
        start = {p: self.cal.days_before(d, PRICE_WINDOW_DAYS) for p, d in last.items()}
        r["start"] = r["product_code"].map(start)
        cur_rows = r[r["date"] >= r["start"]]
        now = {p: _wmedian(g["unit_price"].values, g["qty"].values) for p, g in cur_rows.groupby("product_code", observed=True)}
        lo, hi = self.cal.days_before(end, PREV_PRICE_DAYS[0]), self.cal.days_before(end, PREV_PRICE_DAYS[1])
        prev_rows = sale[(sale["date"] >= lo) & (sale["date"] < hi)]
        prev = {p: _wmedian(g["unit_price"].values, g["qty"].values) for p, g in prev_rows.groupby("product_code", observed=True)}
        # تاریخ تقریبی اعمال قیمت جدید: اولین فروش اخیر با قیمت نزدیک به قیمت فعلی
        r["now"] = r["product_code"].map(now)
        near = r[(r["unit_price"] / r["now"] - 1).abs() < 0.005]
        since = near.groupby("product_code", observed=True)["date"].min().to_dict()
        # ترکیب کالا: سهم تعدادی هر کالا در N ماه سالم اخیر
        ms = self.normal_closed(self.cur)[-self.ps["base_months"]:]
        mix_src = sale[sale["month"].isin(ms)]
        mix_bc = {k: g.droplevel([0, 1]) for k, g in
                  mix_src.groupby(["branch", "category", "product_code"], observed=True)["qty"].sum()
                  .groupby(level=[0, 1], observed=True)}
        mix_c = {k: g.droplevel(0) for k, g in
                 mix_src.groupby(["category", "product_code"], observed=True)["qty"].sum().groupby(level=0, observed=True)}
        g = recent.groupby(["branch", "category"], observed=True)[["net", "gross"]].sum()
        gc = recent.groupby("category", observed=True)[["net", "gross"]].sum()
        self._price = {"now": now, "prev": prev, "since": since, "mix_bc": mix_bc, "mix_c": mix_c,
                       "ratio_bc": (g["net"] / g["gross"].replace(0, np.nan)).to_dict(),
                       "ratio_c": (gc["net"] / gc["gross"].replace(0, np.nan)).to_dict(),
                       "end": end, "mix_months": ms}
        return self._price

    @staticmethod
    def _mix_price(mix: pd.Series, price: dict) -> float | None:
        w = mix[mix > 0]
        p = np.array([price.get(k, np.nan) for k in w.index], dtype=float)
        ok = ~np.isnan(p)
        if not ok.any() or w.values[ok].sum() <= 0:
            return None
        return float((w.values[ok] * p[ok]).sum() / w.values[ok].sum())

    def cell_price(self, branch: str, cat: str) -> tuple[float | None, float | None]:
        """(قیمت ناخالص، قیمت خالص) یک واحد برای شعبه × گروه با قیمت‌های فعلی."""
        P = self.prices()
        mix = P["mix_bc"].get((branch, cat))
        if mix is None or mix.sum() < MIN_MIX_QTY:
            mix = P["mix_c"].get(cat)
        if mix is None:
            return None, None
        gross = self._mix_price(mix, P["now"])
        if gross is None:
            return None, None
        ratio = P["ratio_bc"].get((branch, cat))
        if ratio is None or not np.isfinite(ratio):
            ratio = P["ratio_c"].get(cat, 1.0)
        return gross, gross * float(ratio if np.isfinite(ratio) else 1.0)

    def price_changes(self, book: dict | None = None) -> list[dict]:
        """تغییر قیمت هر گروه با ترکیب ثابت: فعلی در برابر قیمت ۳۰ تا ۴۵ روز پیش، یا در برابر عکس فوری زمان قفل."""
        P = self.prices()
        out = []
        cats = book.keys() if book else P["mix_c"].keys()
        for cat in cats:
            if book:
                items = book[cat]
                w = np.array([v[0] for v in items.values()], dtype=float)
                old = np.array([v[1] for v in items.values()], dtype=float)
                new = np.array([P["now"].get(k, np.nan) for k in items], dtype=float)
                keys = list(items)
            else:
                mix = P["mix_c"][cat]
                mix = mix[mix > 0]
                keys = list(mix.index)
                w = mix.values.astype(float)
                old = np.array([P["prev"].get(k, np.nan) for k in keys], dtype=float)
                new = np.array([P["now"].get(k, np.nan) for k in keys], dtype=float)
            ok = ~(np.isnan(old) | np.isnan(new)) & (old > 0)
            if ok.sum() == 0 or w[ok].sum() <= 0:
                continue
            chg = float((w[ok] * new[ok]).sum() / (w[ok] * old[ok]).sum() - 1)
            if abs(chg) < self.ps["price_alert"]:
                continue
            changed = [k for k, o, n_ in zip(np.array(keys)[ok], old[ok], new[ok]) if abs(n_ / o - 1) >= 0.005]
            dates = sorted(P["since"][k] for k in changed if k in P["since"])
            out.append({"category": cat, "change": chg, "since": dates[len(dates) // 2] if dates else None,
                        "products": len(changed)})
        return sorted(out, key=lambda x: -abs(x["change"]))

    def price_book(self) -> dict:
        P = self.prices()
        book = {}
        for cat, mix in P["mix_c"].items():
            book[cat] = {str(k): [float(v), float(P["now"][k])] for k, v in mix.items() if v > 0 and k in P["now"]}
        return book

    # -- منحنی پیشرفت فروش در طول ماه
    def pace_curve(self) -> dict:
        """سهم معمول فروش خالص ماه تا هر نقطه از ماه (بر حسب سهم روزهای کاری سپری‌شده)؛ میانه ماه‌های سالم."""
        if self._curve is not None:
            return self._curve
        grid = np.linspace(0, 1, 27)
        months = self.normal_closed(self.cur)
        daily = self.s[self.s["month"].isin(months)].groupby("date")["net"].sum()
        curves = []
        if self.cal.available:
            for m in months:
                ds = self.cal.month_dates(m)
                tot_wd = self.cal.wd_month(m)
                vals = np.array([daily.get(d, 0.0) for d in ds])
                if not ds or not tot_wd or vals.sum() <= 0:
                    continue
                frac = np.cumsum([self.cal.work[d] for d in ds]) / tot_wd
                cum = np.cumsum(vals) / vals.sum()
                curves.append([float(cum[frac <= g + 1e-9].max()) if (frac <= g + 1e-9).any() else 0.0 for g in grid])
        if len(curves) >= 3:
            c = np.maximum.accumulate(np.median(np.array(curves), axis=0))
            c[0], c[-1] = 0.0, 1.0
            self._curve = {"grid": grid.tolist(), "curve": c.tolist(), "months": len(curves), "linear": False}
        else:
            self._curve = {"grid": grid.tolist(), "curve": grid.tolist(), "months": 0, "linear": True}
        return self._curve

    def expected_share(self, f: float) -> float:
        c = self.pace_curve()
        return float(np.interp(min(max(f, 0.0), 1.0), c["grid"], c["curve"]))

    # -- تارگت یک ماه (پیش‌نویس زنده یا عکس فوری قفل‌شده)
    def target(self, plan: dict) -> dict:
        month = plan["month"]
        main = self.main_categories()
        warnings = []
        wd_cal = float(self.cal.wd_month(month) or 26)
        wd = float(plan.get("wd") or wd_cal)
        if plan.get("locked") and plan.get("snapshot"):
            snap = plan["snapshot"]
            cells = pd.DataFrame(snap["cells"])
            info = snap.get("info", {})
            ch = self.price_changes(snap.get("price_book"))
            for c in ch:
                warnings.append({"level": "warn", "text": (
                    f"قیمت «{c['category']}» از زمان قفل تارگت ({snap['created'][:10]}) {c['change']:+.1%} تغییر کرده"
                    + (f" (از حدود {c['since']})" if c.get("since") else "")
                    + "؛ تارگت ریالی همچنان با قیمت زمان قفل است. برای اعمال قیمت جدید قفل را باز و دوباره قفل کنید.")})
        else:
            cells, info = self.suggestions(month)
            growth = float(plan.get("growth") or 0)
            ov = plan.get("overrides") or {}
            # روز کاری اصلاح‌شده: پیشنهاد به نسبت روز کاری تغییر می‌کند
            cells["suggest"] = np.round(cells["suggest"] * wd / self.wd(month)) if len(cells) else cells["suggest"]
            cells["key"] = cells["branch"] + SEP + cells["category"]
            auto = np.round(cells["suggest"] * (1 + growth))
            cells["override"] = cells["key"].map(lambda k: k in ov)
            cells["final"] = [float(ov[k]) if k in ov else a for k, a in zip(cells["key"], auto)]
            # اصلاح دستی برای ترکیبی که پیشنهاد ندارد (مثلاً گروه جدید در یک شعبه)
            extra = [k for k in ov if k not in set(cells["key"])]
            if extra:
                add = pd.DataFrame([{"branch": k.split(SEP)[0], "category": k.split(SEP)[1], "base": 0.0, "idx": 1.0,
                                     "suggest": 0.0, "base_last": 0.0, "key": k, "override": True,
                                     "final": float(ov[k])} for k in extra])
                cells = pd.concat([cells, add], ignore_index=True)
            prices = [self.cell_price(b, c) for b, c in zip(cells["branch"], cells["category"])]
            cells["price_gross"] = [p[0] for p in prices]
            cells["price_net"] = [p[1] for p in prices]
            ch = self.price_changes()
            P = self.prices()
            warnings.append({"level": "info", "text": (
                f"تارگت ریالی با قیمت‌های فعلی محاسبه شده: آخرین قیمت فروش هر کالا (تا {P['end']})، ترکیب کالای "
                f"ماه‌های {'، '.join(P['mix_months'])} و نسبت خالص به ناخالص {DISC_WINDOW_DAYS} روز اخیر. "
                "با تغییر قیمت‌ها این عدد خودکار به‌روز می‌شود تا وقتی تارگت قفل شود.")})
            for c in ch:
                warnings.append({"level": "warn", "text": (
                    f"قیمت «{c['category']}» در ۴۵ روز اخیر {c['change']:+.1%} تغییر کرده"
                    + (f" (قیمت جدید از حدود {c['since']})" if c.get("since") else "")
                    + "؛ پایه تعدادی از فروش ماه‌های قبل با قیمت قدیم ساخته شده و ممکن است تقاضا تغییر کند.")})
        if not len(cells):
            return {"month": month, "cells": [], "warnings": [{"level": "danger", "text": "داده کافی برای پیشنهاد تارگت نیست."}],
                    "main": main, "wd": wd, "wd_calendar": wd_cal}
        cells["main"] = cells["category"].isin(main)
        cells["target_net"] = cells["final"] * cells["price_net"].fillna(0)
        cells["target_gross"] = cells["final"] * cells["price_gross"].fillna(0)
        # مرجع: ماه قبل و همین ماه سال قبل
        last_m = max([m for m in self.months if m < min(month, self.cur)], default=None)
        ly = month_add(month, -12)
        for col, m in (("last", last_m), ("ly", ly)):
            if m and m in self.months:
                ref = self.mbc.loc[m]
                cells[col] = [float(ref["qty"].get((b, c), 0.0)) for b, c in zip(cells["branch"], cells["category"])]
                cells[col + "_net"] = [float(ref["net"].get((b, c), 0.0)) for b, c in zip(cells["branch"], cells["category"])]
            else:
                cells[col] = np.nan
                cells[col + "_net"] = np.nan
        # هشدارهای داده
        if is_abnormal(month, self.ps):
            warnings.insert(0, {"level": "danger", "text": f"ماه {month} در فهرست ماه‌های غیرعادی است؛ پیشنهاد سیستم برای آن قابل اعتماد نیست و بهتر است تارگت دستی تعیین شود."})
        if not self.season.get("available"):
            warnings.append({"level": "warn", "text": "ضریب فصلی هنوز از دیتابیس خوانده نشده یا داده کافی ندارد؛ پیشنهادها فعلاً بدون اثر فصل‌اند." if self.ps.get("season") else "ضریب فصلی در تنظیمات خاموش است."})
        if not plan.get("wd"):
            warnings.append({"level": "info", "text": f"روز کاری {month} از تقویم کارآمد {int(wd_cal)} روز است (فقط جمعه‌ها کم شده‌اند). اگر تعطیل رسمی دارد، روز کاری را اصلاح کنید."})
        new = [b for b, v in info.get("branches", {}).items() if v.get("new")]
        if new:
            warnings.append({"level": "warn", "text": f"شعبه‌های تازه‌تأسیس با کمتر از ۲ ماه سالم سابقه: {'، '.join(new)}. پیشنهاد آن‌ها کم‌اعتماد است و بهتر است دستی بررسی شود."})
        if info.get("inactive"):
            warnings.append({"level": "info", "text": f"شعبه‌های بدون فروش در دو ماه اخیر کنار گذاشته شدند: {'، '.join(info['inactive'])}."})
        nop = cells[cells["final"] > 0]["price_net"].isna().sum()
        if nop:
            warnings.append({"level": "warn", "text": f"{nop} ترکیب شعبه × گروه قیمت فعلی ندارند (کالایشان اخیراً فروش نداشته)؛ تارگت ریالی آن‌ها صفر حساب شده."})
        if month == self.cur and not plan.get("locked"):
            warnings.append({"level": "info", "text": "این ماه در جریان است؛ پیشنهاد فقط از ماه‌های قبل ساخته شده و فروش همین ماه در آن اثری ندارد."})
        jumps = cells[cells["main"] & (cells["last"] > 50) & ((cells["final"] / cells["last"] > 2.5) | (cells["final"] / cells["last"] < 0.4))]
        if len(jumps):
            warnings.append({"level": "info", "text": f"{len(jumps)} ترکیب از گروه‌های اصلی تارگتی بیش از ۲٫۵ برابر یا کمتر از ۴۰٪ فروش ماه قبل دارند (معمولاً به خاطر نوسان ماه قبل). در جدول با علامت مشخص‌اند."})
        cells["jump"] = cells["key"].isin(set(jumps["key"])) if len(jumps) else False
        return {"month": month, "main": main, "wd": wd, "wd_calendar": wd_cal, "cells": cells,
                "info": info, "warnings": warnings, "last_month": last_m, "ly_month": ly}

    # -- پایش ماه جاری
    def track(self, plan: dict) -> dict:
        t = self.target(plan)
        cells = t["cells"]
        month = self.cur
        wd_total = float(plan.get("wd") or self.ctx.get("wd_total") or self.wd(month))
        elapsed = float(self.ctx.get("wd_elapsed") or 0)
        f = elapsed / wd_total if wd_total else 0.0
        e = self.expected_share(f)
        cur = self.s[self.s["month"] == month]
        basis = cur[cur["date"] < self.today]
        act = cur.groupby(["branch", "category"], observed=True)[["qty", "net"]].sum()
        bas = basis.groupby(["branch", "category"], observed=True)[["qty", "net"]].sum()
        if not len(cells):
            return {**t, "cells": [], "elapsed": elapsed, "wd_total": wd_total, "expected_share": e}
        key = list(zip(cells["branch"], cells["category"]))
        cells["actual"] = [float(act["qty"].get(k, 0.0)) for k in key]
        cells["actual_net"] = [float(act["net"].get(k, 0.0)) for k in key]
        cells["basis"] = [float(bas["qty"].get(k, 0.0)) for k in key]
        cells["basis_net"] = [float(bas["net"].get(k, 0.0)) for k in key]
        # فروشی که تارگت ندارد (ترکیب جدید) هم در جمع‌ها دیده شود
        known = set(key)
        extra = [(b, c) for (b, c) in act.index if (b, c) not in known]
        if extra:
            add = pd.DataFrame([{"branch": b, "category": c, "key": b + SEP + c, "final": 0.0, "suggest": 0.0,
                                 "target_net": 0.0, "target_gross": 0.0, "main": c in t["main"],
                                 "override": False, "jump": False,
                                 "actual": float(act["qty"][(b, c)]), "actual_net": float(act["net"][(b, c)]),
                                 "basis": float(bas["qty"].get((b, c), 0.0)), "basis_net": float(bas["net"].get((b, c), 0.0))}
                                for b, c in extra])
            cells = pd.concat([cells, add], ignore_index=True)
        ok = e > 0.03
        rem = max(wd_total - elapsed, 0.0)

        def pace(df, tq, bq):
            df["expected"] = df[tq] * e
            df["ach" if tq == "final" else "ach_net"] = np.where(df["expected"] > 0, df[bq] / df["expected"].replace(0, np.nan), np.nan)
            fc = df[bq] / e if ok else np.nan
            df["forecast" if tq == "final" else "forecast_net"] = fc
            df["need_daily" if tq == "final" else "need_daily_net"] = (df[tq] - df[bq]).clip(lower=0) / rem if rem else np.nan
            df["cur_daily" if tq == "final" else "cur_daily_net"] = df[bq] / elapsed if elapsed else np.nan
            return df
        cells = pace(cells, "final", "basis")
        cells = pace(cells, "target_net", "basis_net")
        cells = cells.drop(columns=["expected"])
        cells["ratio"] = np.where(cells["final"] > 0, cells["forecast"] / cells["final"].replace(0, np.nan), np.nan)
        cells["status"] = [self._status(r) for r in cells["ratio"]]

        def agg(by):
            g = cells.groupby(by, observed=True)[["target_net", "basis_net", "actual_net", "final", "basis", "actual"]].sum()
            g["ach_net"] = g["basis_net"] / (g["target_net"] * e).replace(0, np.nan)
            g["forecast_net"] = g["basis_net"] / e if ok else np.nan
            g["ratio"] = g["forecast_net"] / g["target_net"].replace(0, np.nan)
            g["need_daily_net"] = (g["target_net"] - g["basis_net"]).clip(lower=0) / rem if rem else np.nan
            g["cur_daily_net"] = g["basis_net"] / elapsed if elapsed else np.nan
            g["status"] = [self._status(r) for r in g["ratio"]]
            return g.reset_index()
        branches = agg("branch")
        cats = agg("category")
        cats["ach"] = cats["basis"] / (cats["final"] * e).replace(0, np.nan)
        cats["forecast"] = cats["basis"] / e if ok else np.nan
        tot = cells[["target_net", "basis_net", "actual_net"]].sum()
        total = {"target_net": float(tot["target_net"]), "actual_net": float(tot["actual_net"]),
                 "basis_net": float(tot["basis_net"]),
                 "ach_net": float(tot["basis_net"] / (tot["target_net"] * e)) if tot["target_net"] and e else None,
                 "forecast_net": float(tot["basis_net"] / e) if ok else None,
                 "need_daily_net": float(max(tot["target_net"] - tot["basis_net"], 0) / rem) if rem else None,
                 "cur_daily_net": float(tot["basis_net"] / elapsed) if elapsed else None}
        total["ratio"] = total["forecast_net"] / total["target_net"] if total["forecast_net"] and total["target_net"] else None
        total["status"] = self._status(total["ratio"])
        warnings = list(t["warnings"])
        if not plan.get("locked"):
            warnings.insert(0, {"level": "warn", "text": "تارگت این ماه قفل نشده؛ پایش بر اساس پیش‌نویس فعلی (پیشنهاد سیستم + اصلاحات) انجام می‌شود و با تغییر داده یا قیمت ممکن است عوض شود."})
        if f < 0.15:
            warnings.append({"level": "info", "text": "کمتر از ۱۵٪ ماه گذشته؛ پیش‌بینی پایان ماه هنوز نوسان زیادی دارد."})
        c = self.pace_curve()
        warnings.append({"level": "info", "text": (
            f"تا امروز {int(elapsed)} از {int(wd_total)} روز کاری گذشته؛ "
            + (f"طبق الگوی {c['months']} ماه سالم قبلی معمولاً {e:.0%} فروش ماه تا این نقطه انجام می‌شود." if not c["linear"]
               else f"الگوی ماه‌های قبل در دسترس نیست؛ انتظار خطی {e:.0%} است.")
            + " فروش امروز از فردا در محاسبه می‌آید.")})
        return {**t, "cells": cells, "branches": branches, "categories": cats, "total": total,
                "elapsed": elapsed, "wd_total": wd_total, "expected_share": e, "warnings": warnings}

    def _status(self, ratio) -> str | None:
        if ratio is None or not np.isfinite(ratio):
            return None
        return "green" if ratio >= self.ps["green"] else "yellow" if ratio >= self.ps["yellow"] else "red"

    # -- مقایسه سالانه
    def compare(self, year: str, categories: list[str], branches: list[str], metric: str, lfl: bool,
                targets: dict[str, dict]) -> dict:
        prev = str(int(year) - 1)
        s = self.s
        if categories:
            s = s[s["category"].isin(categories)]
        if branches:
            s = s[s["branch"].isin(branches)]
        col = {"qty": "qty", "net": "net", "gross": "gross"}[metric]
        mb = s.groupby(["month", "branch"], observed=True)[col].sum()
        active = self.s[self.s["qty"] > 0].groupby(["month", "branch"], observed=True).size()
        lvl = lambda ser, m: ser.loc[m] if m in ser.index.get_level_values(0) else None
        rows = []
        for i in range(1, 13):
            mm = f"{i:02d}"
            a, b = f"{year}/{mm}", f"{prev}/{mm}"
            va, vb = lvl(mb, a), lvl(mb, b)
            if lfl and va is not None and vb is not None:
                # فقط شعبه‌هایی که در هر دو ماه فروش داشته‌اند
                both = set(getattr(lvl(active, a), "index", [])) & set(getattr(lvl(active, b), "index", []))
                va = va[va.index.isin(both)]
                vb = vb[vb.index.isin(both)]
            cur_v = float(va.sum()) if va is not None and a in self.months else None
            prev_v = float(vb.sum()) if vb is not None and b in self.months else None
            tgt = None
            if a in targets:
                tc = targets[a]
                if categories:
                    tc = tc[tc["category"].isin(categories)]
                if branches:
                    tc = tc[tc["branch"].isin(branches)]
                tgt = float(tc[{"qty": "final", "net": "target_net", "gross": "target_gross"}[metric]].sum())
            rows.append({"mm": mm, "cur": cur_v, "prev": prev_v, "target": tgt,
                         "partial": a == self.cur, "abn_cur": is_abnormal(a, self.ps), "abn_prev": is_abnormal(b, self.ps),
                         "wd_cur": self.cal.wd_month(a), "wd_prev": self.cal.wd_month(b)})
        last = max([r["mm"] for r in rows if r["cur"] is not None and not r["partial"]], default=None)
        ytd_c = sum(r["cur"] or 0 for r in rows if last and r["mm"] <= last)
        ytd_p = sum(r["prev"] or 0 for r in rows if last and r["mm"] <= last)
        return {"year": year, "prev": prev, "rows": rows, "ytd_month": last, "ytd_cur": ytd_c, "ytd_prev": ytd_p,
                "ytd_growth": (ytd_c / ytd_p - 1) if ytd_p else None, "metric": metric, "lfl": lfl}

    # -- ارزیابی روش (بک‌تست)
    def backtest(self, k: int = 6) -> dict:
        months = self.normal_closed(self.cur)
        months = [m for m in months if len(self.normal_closed(m)) >= 2][-k:]
        out = []
        for m in months:
            act = self.mbc.loc[m]
            cat_price = act.groupby(level="category")["net"].sum() / act.groupby(level="category")["qty"].sum().replace(0, np.nan)

            def score(df: pd.DataFrame, name: str):
                if not len(df):
                    return
                a = np.array([float(act["qty"].get((b, c), 0.0)) for b, c in zip(df["branch"], df["category"])])
                an = np.array([float(act["net"].get((b, c), 0.0)) for b, c in zip(df["branch"], df["category"])])
                p = np.where(a > 0, an / np.where(a > 0, a, 1), df["category"].map(cat_price).fillna(0).values)
                p = np.nan_to_num(np.clip(p, 0, None))
                s_r, a_r = df["suggest"].values * p, np.clip(a, 0, None) * p
                den = a_r.sum()
                bdf = pd.DataFrame({"b": df["branch"].values, "s": s_r, "a": a_r}).groupby("b").sum()
                out.append({"month": m, "method": name,
                            "cell": float(np.abs(s_r - a_r).sum() / den) if den else None,
                            "branch": float((bdf["s"] - bdf["a"]).abs().sum() / den) if den else None,
                            "total": float(s_r.sum() / den - 1) if den else None,
                            "actual_net": float(den), "suggest_net": float(s_r.sum())})
            score(self.suggestions(m, cutoff=m)[0], "model")
            score(self.suggestions(m, cutoff=m, season=False)[0], "no_season")
            # ساده: فروش هر روز کاری آخرین ماه سالم × روز کاری ماه
            lm = self.normal_closed(m)[-1]
            prev = self.mbc.loc[lm].reset_index()
            prev["suggest"] = prev["qty"].clip(lower=0) / self.wd(lm) * self.wd(m)
            score(prev, "naive")
        df = pd.DataFrame(out)
        summary = []
        if len(df):
            for name, g in df.groupby("method"):
                summary.append({"method": name, "cell": float(g["cell"].mean()), "branch": float(g["branch"].mean()),
                                "total": float(g["total"].abs().mean()), "bias": float(g["total"].mean())})
        return {"rows": out, "summary": summary, "months": months}
