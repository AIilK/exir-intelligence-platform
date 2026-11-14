"""مسابقه‌های فروش: هر مسابقه بازه تاریخ، فهرست کالا (کد کالا)، دسته شعب (A / B) و تارگت ویزیتورها دارد.
تعریف‌ها در data/contests.json ذخیره می‌شوند و پس از پایان مسابقه حذف می‌شوند.
تعداد و مبلغ از درخواست‌های ثبت‌شده در کارآمد (بدون باطل‌شده‌ها، چه فاکتور شده باشند چه نه) حساب می‌شود؛
ورود به مسابقه هم با همین عدد درخواست است، نه فاکتور."""
from __future__ import annotations

import io
import json
import re
import threading
import time
import uuid
from pathlib import Path

import pandas as pd

FILE = Path(__file__).resolve().parent.parent / "data" / "contests.json"
_lock = threading.Lock()
DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")


# ---------------------------------------------------------------- ذخیره
def load() -> list[dict]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write(items: list[dict]):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(FILE)


def get(cid: str) -> dict | None:
    return next((c for c in load() if c["id"] == cid), None)


def save(body: dict) -> dict:
    """ساخت یا ویرایش؛ فیلدهای نیامده در ویرایش دست نمی‌خورند."""
    with _lock:
        items = load()
        cur = next((c for c in items if c["id"] == body.get("id")), None) if body.get("id") else None
        c = dict(cur or {"id": uuid.uuid4().hex[:10], "created": time.strftime("%Y-%m-%d %H:%M"),
                         "targets": [], "tiers": {}, "target_unit": "qty"})
        for k in ("name", "date_from", "date_to", "default_from", "products", "target_unit", "targets", "tiers", "note"):
            if k in body and body[k] is not None:
                c[k] = body[k]
        c["name"] = str(c.get("name") or "").strip()
        if not c["name"]:
            raise ValueError("نام مسابقه خالی است.")
        for k in ("date_from", "date_to"):
            if not DATE_RE.match(str(c.get(k) or "")):
                raise ValueError("تاریخ شروع و پایان را به شکل ۱۴۰۵/۰۸/۰۱ وارد کنید.")
        if c["date_from"] > c["date_to"]:
            raise ValueError("تاریخ شروع بعد از تاریخ پایان است.")
        c["products"] = [str(p) for p in c.get("products") or []]
        if not c["products"]:
            raise ValueError("حداقل یک کالا انتخاب کنید.")
        if c.get("target_unit") not in ("qty", "net"):
            c["target_unit"] = "qty"
        c["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        items = [x for x in items if x["id"] != c["id"]] + [c]
        _write(items)
        return c


def delete(cid: str) -> bool:
    with _lock:
        items = load()
        rest = [c for c in items if c["id"] != cid]
        if len(rest) == len(items):
            return False
        _write(rest)
        return True


# ---------------------------------------------------------------- فایل تارگت
def _norm(s) -> str:
    """نام شعبه/فرد برای تطبیق: ی/ک عربی، فاصله‌های اضافه، «هیبریدی» ← «هیبرید»."""
    s = str(s or "").replace("ي", "ی").replace("ك", "ک").replace("\xa0", " ").replace("‌", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace("هیبریدی ", "هیبرید ")


def _clean_name(s) -> str:
    """نام فروشنده در فایل تارگت شماره تلفن هم دارد: «اسمعیل الطافی / 09338705861» ← «اسمعیل الطافی»."""
    s = _norm(s)
    s = re.sub(r"[/\-–]?\s*[\d۰-۹]{7,}.*$", "", s).strip(" /-–")
    return re.sub(r"^آقای\s+|^خانم\s+", "", s).strip()


def _code(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    s = s[:-2] if s.endswith(".0") else s
    return s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


def parse_targets(data: bytes) -> dict:
    """فایل اکسل تارگت: ستون‌های گروه (A/B)، هیبرید، کد فروشنده، نام فروشنده، تارگت (هر برگه‌ای که این سرستون‌ها را دارد)."""
    xl = pd.ExcelFile(io.BytesIO(data))
    need = {"هیبرید": "branch", "کد فروشنده": "code", "نام فروشنده": "name", "تارگت": "target", "گروه": "tier"}
    for sh in xl.sheet_names:
        raw = xl.parse(sh, header=None, dtype=object)
        for i in range(min(len(raw), 15)):
            heads = {_norm(v): j for j, v in enumerate(raw.iloc[i]) if isinstance(v, str)}
            cols = {k: next((j for h, j in heads.items() if h == name or h.startswith(name)), None) for name, k in need.items()}
            if cols["branch"] is None or cols["target"] is None or cols["name"] is None:
                continue
            targets, tiers = [], {}
            for _, r in raw.iloc[i + 1:].iterrows():
                br = _norm(r.iloc[cols["branch"]])
                tg = pd.to_numeric(r.iloc[cols["target"]], errors="coerce")
                if not br or "total" in br.lower() or pd.isna(tg):
                    continue
                tier = _norm(r.iloc[cols["tier"]]).upper() if cols["tier"] is not None else ""
                if tier in ("A", "B"):
                    tiers[br] = tier
                targets.append({"branch": br, "code": _code(r.iloc[cols["code"]]) if cols["code"] is not None else "",
                                "name": _clean_name(r.iloc[cols["name"]]), "target": float(tg)})
            if targets:
                return {"targets": targets, "tiers": tiers}
    raise ValueError("سرستون‌های «هیبرید»، «نام فروشنده» و «تارگت» در فایل پیدا نشد.")


# ---------------------------------------------------------------- محاسبه
def _name_fits(target_name: str, seller: str) -> bool:
    """همه بخش‌های نام فایل تارگت در نام کارآمد باشد (بدون فاصله، تا «صحبتلو» با «صحبت لو» یکی شود)."""
    s = _norm(seller).replace(" ", "")
    parts = [p for p in _norm(target_name).split(" ") if len(p) > 1]
    return bool(parts) and all(p in s for p in parts)


def _match_targets(c: dict, roster: pd.DataFrame) -> tuple[dict, list[dict]]:
    """تارگت هر seller_key از فهرست فروشندگان شعب (roster): کد فروشنده در همان شعبه اگر نامش هم بخواند؛
    وگرنه نام یکتا در همان شعبه؛ وگرنه همان کد. خروجی: {seller_key: (target, نام فایل، تطبیق با کد بدون نام؟)}، تارگت‌های پیدانشده."""
    roster = roster.assign(_b=roster["branch"].map(_norm), _c=roster["seller_code"].map(_code))
    out, missing = {}, []
    for t in c.get("targets") or []:
        br = _norm(t["branch"])
        inb = roster[roster["_b"] == br]
        by_code = inb[inb["_c"] == t["code"]] if t.get("code") else inb.iloc[0:0]
        by_name = inb[inb["seller"].map(lambda s: _name_fits(t.get("name") or "", s))]
        key, loose = None, False
        if len(by_code) and (not t.get("name") or _name_fits(t["name"], by_code["seller"].iat[0])):
            key = by_code["seller_key"].iat[0]
        elif len(by_name) == 1:
            key = by_name["seller_key"].iat[0]
        elif len(by_code):
            key, loose = by_code["seller_key"].iat[0], True
        if key is None or key in out:
            missing.append(t)
        else:
            out[key] = (t["target"], t.get("name") or "", loose)
    return out, missing


def compute(c: dict, sales: pd.DataFrame, requests: pd.DataFrame | None, tier_of, vat: bool,
            period: tuple[str, str] | None = None) -> dict:
    """ردیف‌های فروشنده × کالا از درخواست‌ها (برای فیلتر و تجمیع در صفحه) و تارگت فروشندگان.
    period: بخشی از بازه مسابقه؛ فهرست فروشندگان (تطبیق تارگت) همیشه از کل بازه مسابقه است."""
    lo, hi = period or (c["date_from"], c["date_to"])
    tiers = {_norm(k): v for k, v in (c.get("tiers") or {}).items()}
    hyb_of = lambda df: df[df["branch"].astype(str).str.contains("هیبرید") & (df["date"] <= c["date_to"])]
    req = hyb_of(requests) if requests is not None and len(requests) else None
    # فهرست فروشندگان از فاکتور و درخواست با هم، تا ویزیتوری که فقط درخواست دارد هم پیدا شود
    hyb = pd.concat([x for x in (hyb_of(sales), req) if x is not None], ignore_index=True)
    # فهرست فروشندگان شعب: سه ماه پیش از شروع تا پایان مسابقه، تا ویزیتور تارگت‌دار بی‌فروش هم با نام کارآمدش بیاید
    y, m = int(c["date_from"][:4]), int(c["date_from"][5:7]) - 3
    since = f"{y - (m < 1)}/{(m - 1) % 12 + 1:02d}/01"
    roster = hyb[hyb["date"] >= since].sort_values("date").drop_duplicates("seller_key", keep="last")[
        ["branch", "seller_key", "seller", "seller_code", "supervisor"]]
    s = req if req is not None else hyb.iloc[0:0]
    s = s[(s["date"] >= lo) & (s["date"] <= hi) & s["product_code"].isin(c["products"])]
    if "is_sample" in s:
        s = s[~s["is_sample"]]
    if vat:
        s = s.assign(net=s["payable"])
    # status: 0 درخواست باز، 1 فاکتور شده (باطل‌شده‌ها در خواندن حذف شده‌اند)
    s = s.assign(done_qty=s["qty"].where(s["status"] == 1, 0) if "status" in s else 0)
    g = s.groupby(["branch", "seller_key", "product_code"], observed=True).agg(
        seller=("seller", "first"), seller_code=("seller_code", "first"), supervisor=("supervisor", "first"),
        product=("product", "first"), category=("category", "first"), brand=("brand", "first"),
        qty=("qty", "sum"), done_qty=("done_qty", "sum"), net=("net", "sum"),
        customers=("customer_code", "nunique"), requests=("inv_no", "nunique")).reset_index()
    tmap, missing = _match_targets(c, roster)
    tier = lambda b: tiers.get(_norm(b)) or tier_of(b)
    info = roster.set_index("seller_key")
    bnames = {_norm(b): b for b in roster["branch"].unique()}
    nm = lambda s: _clean_name(s) or str(s)  # نام بدون شماره تلفن
    rows = [{"branch": r.branch, "tier": tier(r.branch), "seller_key": r.seller_key, "seller": nm(r.seller),
             "seller_code": str(r.seller_code), "supervisor": r.supervisor, "product_code": r.product_code,
             "product": r.product, "category": r.category, "brand": r.brand, "qty": float(r.qty),
             "done_qty": float(r.done_qty), "net": float(r.net),
             "customers": int(r.customers), "requests": int(r.requests)} for r in g.itertuples()]
    # همه ویزیتورهای تارگت‌دار (حتی بی‌فروش) با مشخصاتشان؛ تارگت‌هایی که در کارآمد پیدا نشدند جدا علامت می‌خورند
    people = []
    for k, (tg, fname, loose) in tmap.items():
        r = info.loc[k]
        people.append({"seller_key": k, "target": tg, "branch": r["branch"], "tier": tier(r["branch"]),
                       "seller": nm(r["seller"]), "seller_code": str(r["seller_code"]), "supervisor": r["supervisor"],
                       "file_name": fname, "loose": loose})
    for i, t in enumerate(missing):
        br = bnames.get(_norm(t["branch"]), t["branch"])
        people.append({"seller_key": f"t:{i}", "target": t["target"], "branch": br, "seller": t["name"],
                       "seller_code": t.get("code") or "", "tier": tier(br), "unmatched": True})
    days = sorted(s["date"].unique())
    return {"rows": rows, "people": people, "last_date": days[-1] if days else None}


def seller_totals(rows: list[dict]) -> dict:
    """جمع تعداد و مبلغ خالص هر ویزیتور روی همه کالاهای مسابقه: {seller_key: {qty, net}}."""
    out: dict[str, dict] = {}
    for r in rows:
        t = out.setdefault(r["seller_key"], {"qty": 0.0, "net": 0.0})
        t["qty"] += r["qty"]
        t["net"] += r["net"]
    return out
