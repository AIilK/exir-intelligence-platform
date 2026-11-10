"""سود و زیان (P&L) لایو از SQL — همان چیدمان اکسل‌های B2B / صادرات / هیبرید، ولی اعداد از دیتابیس.

منبع هر ردیف (همه مبالغ میلیون ریال):
- B2B و صادرات (راهکاران، FIN3 به تفکیک تفصیلی سطح ۴ = مشتری):
    فروش ناخالص   611001 (B2B) / 611017 (صادرات) — بستانکار منهای بدهکار
    برگشت از فروش 611011
    تخفیفات       611012 (B2B) / 611016 (صادرات)؛ نوع تخفیف = تفصیلی سطح ۵
    تعداد         فاکتور فروش منهای برگشت از فروش (SLS3) به تفکیک کالا
    بهای تمام شده تعداد خالص هر کالا × بهای واحد «روش دوم» (شیت Cost) × ضریب ۱.۲ اکسل
    هزینه‌ها (فقط B2B، تخصیص به نسبت تعداد): 7110 دفاتر تهران (حقوق)، 7130 مراکز هزینه B2B، 712022 کارمزد بانکی
- هیبرید (کارآمد، dbo.vwFactorFBLinesFull، فقط شعبه‌های «هیبرید» — همان شیت sales 1405 اکسل):
    فروش ناخالص = جمع قبل تخفیف، برگشت = برگشت از فروش به تاریخ برگشت، تخفیف = حجمی + نقدی (خالص برگشت)،
    ارزش افزوده، تعداد خالص، بهای تمام شده مثل بالا.
    هزینه‌ها از اسناد حسابداری کارآمد (tblVoucherLines، کل 81/83/85/87 شعبه‌های هیبرید)؛
    پورسانت = معین 8138، بهره‌وری = 8137 و 8704 (همان دسته‌بندی شیت «هزینه ها» اکسل).
- مالیات ۲۵٪ سود قبل مالیات (مثل اکسل).

نگاشت مشتری ← کانال/برند و کالا ← بهای واحد از شیت‌های Map و Cost اکسل‌ها (داده پایه، نه عدد گزارش) خوانده و کش می‌شود.
بهای واحد «روش دوم» در خود اکسل هم از کارپوشه دستی برنامه‌ریزی می‌آید
(//isa-server/planning/1.Manager/1404/Cost of goods- manual 1405.xlsx)، نه از SQL.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.services import pnl_service

COGS_FACTOR = 1.2
TAX_RATE = 0.25
BRANDS = ["Padina", "Base", "Arkia", "Lorient", "Kalyon", "Vina", "Jevo", "MULHENS", "Tacori", "Oradent"]
HYBRID_BRANDS = BRANDS + ["UpSky", "Rozetti"]
BRAND_ALIASES = {
    "padina": "Padina", "پادینا": "Padina", "base": "Base", "بیس": "Base", "arkia": "Arkia", "آرکیا": "Arkia", "ارکیا": "Arkia",
    "lorient": "Lorient", "لورینت": "Lorient", "kalyon": "Kalyon", "کالیون": "Kalyon", "vina": "Vina", "وینا": "Vina",
    "jevo": "Jevo", "جوو": "Jevo", "mulhens": "MULHENS", "مولهنس": "MULHENS", "tacori": "Tacori", "تاکوری": "Tacori",
    "oradent": "Oradent", "اورادنت": "Oradent", "upsky": "UpSky", "آپ اسکای": "UpSky", "آپاسکای": "UpSky",
    "rozetti": "Rozetti", "رزتی": "Rozetti",
}
B2B_SALARY_DLS = ("500004", "501001", "501010")             # 7110 دفاتر تهران کادوس / اکسیر / فراز بهداشت
B2B_SGA_DLS = ("570000", "521007", "104265", "580000")      # 7130 مراکز هزینه B2B
CHANNEL_GL = {"b2b": {"gross": "611001", "discount": "611012", "return": "611011", "channel": "b2b"},
              "export": {"gross": "611017", "discount": "611016", "return": None, "channel": "export"}}
QUARTERS = {1: ("01", "03"), 2: ("04", "06"), 3: ("07", "09"), 4: ("10", "12")}
CACHE_SECONDS = 600
MASTER_VERSION = 1

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_results: dict[str, tuple[float, dict[str, Any]]] = {}


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("ي", "ی").replace("ك", "ک").replace("‌", "")).strip().lower()


def _brand(name: Any) -> str | None:
    n = _norm(name)
    if n in BRAND_ALIASES:
        return BRAND_ALIASES[n]
    for alias, brand in BRAND_ALIASES.items():   # «. گردانی (مولهنس) - اهواز» ← برند داخل عنوان
        if len(alias) > 2 and alias in n:
            return brand
    return None


def _code(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v or "").strip()


# ------------------------------------------------------------------ دوره‌ها (شمسی ← میلادی با تقویم کارآمد)
def _karamad():
    from app.database.karamad_sqlserver import get_karamad_sqlserver_engine
    return get_karamad_sqlserver_engine()


def _rahkaran():
    from app.database.sqlserver import get_sqlserver_engine
    return get_sqlserver_engine()


_range_cache: dict[tuple[int, str, str], tuple[date, date] | None] = {}


def _jalali_range(year: int, m_from: str, m_to: str) -> tuple[date, date] | None:
    k = (year, m_from, m_to)
    if k in _range_cache:
        return _range_cache[k]
    with _karamad().connect() as c:
        row = c.execute(text("SELECT MIN(GregorianDate), MAX(GregorianDate) FROM dbo.tblCalendar "
                             "WHERE PersianDate >= :a AND PersianDate < :b"),
                        {"a": f"{year}/{m_from}/01", "b": f"{year}/{m_to}/99"}).first()
    if not row or not row[0]:
        _range_cache[k] = None
        return None
    to_d = row[1].date() if isinstance(row[1], datetime) else row[1]
    from_d = row[0].date() if isinstance(row[0], datetime) else row[0]
    _range_cache[k] = (from_d, to_d)
    return from_d, to_d


def last_closed_quarter() -> tuple[int, int]:
    """آخرین فصلی که پورسانتش پرداخت و ثبت شده (تنظیم PNL_LAST_CLOSED_QUARTER، مثل 1405-Q2)."""
    from app.core.config import settings
    m = re.match(r"(\d{4})-Q([1-4])$", (settings.pnl_last_closed_quarter or "").strip())
    if not m:
        t = date.today()
        return t.year - 621, 1
    return int(m.group(1)), int(m.group(2))


def _year_periods(year: int) -> list[dict[str, Any]]:
    """فصل‌های بسته‌شده سال + «کل سال» (اگر سال کامل بسته نشده: از ابتدای سال تا پایان آخرین فصل بسته‌شده)."""
    cy, cq = last_closed_quarter()
    out = []
    for q, (a, b) in QUARTERS.items():
        if (year, q) > (cy, cq):
            continue
        rng = _jalali_range(year, a, b)
        if rng:
            out.append({"key": f"{year}-Q{q}", "label": f"{year} Q{q}", "from": rng[0].isoformat(), "to": rng[1].isoformat(),
                        "complete": True, "quarters": [q]})
    if out:
        qs = [p["quarters"][0] for p in out]
        label = f"{year}" if len(qs) == 4 else f"{year} (Q1–Q{qs[-1]})"
        out.append({"key": f"{year}", "label": label, "from": out[0]["from"], "to": out[-1]["to"], "complete": True, "quarters": qs})
    return out


def periods(year: int | None = None) -> list[dict[str, Any]]:
    """دوره‌های P&L: فقط فصل‌های بسته‌شده (پورسانت پرداخت‌شده) سال جاری و سال قبل، و «کل سال» هرکدام.
    پیش‌فرض: جمع فصل‌های بسته‌شده سال جاری (با ستون جدای هر فصل و کل سال قبل)."""
    cy, _ = last_closed_quarter()
    out = []
    for y in ([year] if year else [cy, cy - 1]):
        out += _year_periods(y)
    default = f"{cy}" if any(p["key"] == f"{cy}" for p in out) else (out[0]["key"] if out else None)
    return [dict(p, default=p["key"] == default) for p in out]


def _period(key: str | None) -> dict[str, Any]:
    year = int(re.match(r"(\d{4})", key).group(1)) if key else None
    for p in periods(year) if year else periods():
        if p["key"] == key or (not key and p["default"]):
            return p
    raise KeyError(f"{key}: این دوره بسته نشده (پورسانتش ثبت نشده) یا وجود ندارد")


# ------------------------------------------------------------------ داده پایه از اکسل B2B (Map / Cost)
def master() -> dict[str, Any]:
    path = pnl_service.find_files().get("b2b")
    cache = pnl_service.CACHE_DIR / "live_master.json"
    fp = ({k: [f.name, f.stat().st_mtime] for k, f in pnl_service.find_files().items() if f} | {"v": MASTER_VERSION}) if path else None
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if fp is None or data.get("source") == fp:
                return data
        except (OSError, ValueError):
            pass
    if path is None:
        return {"source": None, "channel": {}, "brand": {}, "product_brand": {}, "unit_cost": {}}
    channel, brand, product_brand, unit_cost = {}, {}, {}, {}
    for i, r in enumerate(pnl_service._rows(path, "Map")):
        if i == 0 or not r:
            continue
        if len(r) > 3 and r[0] not in (None, "") and r[3]:
            channel[_code(r[0])] = _norm(r[3])
        if len(r) > 7 and r[5] not in (None, "") and r[7]:
            product_brand[_code(r[5])] = _brand(r[7]) or str(r[7])
        if len(r) > 19 and r[17] not in (None, "") and r[19]:
            brand[_code(r[17])] = _brand(r[19]) or str(r[19])
    files = pnl_service.find_files()
    for key in ("b2b", "export", "hybrid"):
        src = files.get(key)
        if src is None:
            continue
        sheet = next((n for n in pnl_service._sheet_names(src) if _norm(n) == "cost"), None)
        if not sheet:
            continue
        code_col = cost_col = None
        for i, r in enumerate(pnl_service._rows(src, sheet)):
            if code_col is None:
                heads = [_norm(x) for x in r]
                if "روش دوم" not in heads:
                    continue
                cost_col = heads.index("روش دوم")
                code_col = max(j for j, h in enumerate(heads[:cost_col]) if h == "کد")
                continue
            if r and len(r) > cost_col and r[code_col] not in (None, ""):
                v = r[cost_col]
                if isinstance(v, (int, float)) and v > 0:
                    unit_cost.setdefault(_code(r[code_col]), float(v))
    data = {"source": fp, "channel": channel, "brand": brand, "product_brand": product_brand, "unit_cost": unit_cost}
    pnl_service.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# ------------------------------------------------------------------ ساخت گزارش در قالب اکسل
class Report:
    def __init__(self, brands: list[str]):
        self.brands = brands
        self.rows: list[dict[str, Any]] = []

    def add(self, label: str, values: dict[str, float], kind: str = "line", canon: str | None = None,
            group: str | None = None, source: str | None = None, ratio_base: str | None = None) -> dict[str, float]:
        vals = {b: round(values.get(b, 0.0), 2) for b in self.brands}
        self.rows.append({"label": label, "code": None, "kind": kind, "canon": canon, "group": group, "source": source,
                          "ratio_base": ratio_base, "values": vals, "periods": {"p0": {"value": round(sum(vals.values()), 2), "ratio": None}}})
        return vals

    def ratio(self, label: str, num: dict[str, float], den: dict[str, float], canon: str | None = None):
        vals = {b: (num.get(b, 0) / den[b]) if den.get(b) else None for b in self.brands}
        tn, td = sum(num.values()), sum(den.values())
        self.rows.append({"label": label, "code": None, "kind": "ratio", "canon": canon, "group": None,
                          "values": vals, "periods": {"p0": {"value": tn / td if td else None, "ratio": None}}})

    def finish(self, net_key: str = "net") -> list[dict[str, Any]]:
        for r in self.rows:
            den = _ratio_base_value(self.rows, r, net_key)
            if r["kind"] not in ("ratio", "share") and r["canon"] != "qty" and den:
                r["periods"]["p0"]["ratio"] = (r["periods"]["p0"]["value"] or 0) / den
        return self.rows


def _ratio_base_value(rows: list[dict[str, Any]], row: dict[str, Any], default: str = "net") -> float | None:
    """مخرج «On sales» هر ردیف: پیش‌فرض فروش خالص؛ تخفیف و سربار تولید نسبت به فروش ناخالص."""
    canon = row.get("ratio_base") or default
    base = next((r for r in rows if r.get("canon") == canon), None)
    return base["periods"]["p0"]["value"] if base else None


def _sub(a: dict[str, float], *bs: dict[str, float]) -> dict[str, float]:
    out = defaultdict(float, a)
    for b in bs:
        for k, v in b.items():
            out[k] -= v
    return dict(out)


def _alloc(total: float, share: dict[str, float]) -> dict[str, float]:
    return {b: total * s for b, s in share.items()}


def _std_rows(rep: Report, std: dict[str, dict[str, float]] | None):
    """بلوک «بهای تمام شده استاندارد (جذبی)» کنار بهای تمام شده فعلی: مواد مستقیم + دستمزد مستقیم + سربار تولید."""
    if not std:
        return None
    dm, lab, oh = std.get("dm", {}), std.get("labour", {}), std.get("overhead", {})
    total = {b: dm.get(b, 0) + lab.get(b, 0) + oh.get(b, 0) for b in rep.brands}
    rep.add("بهای تمام شده استاندارد (جذبی)", total, kind="total", canon="cogs_std",
            source="استاندارد ۸ / IAS 2: مواد مستقیم + دستمزد مستقیم + سربار تولید جذب‌شده")
    rep.add("مواد مستقیم (روش ساخت × میانگین موزون خرید)", dm, group="cogs_std", source="میانگین موزون فاکتورهای خرید ۱۲ ماه منتهی به پایان دوره")
    rep.add("دستمزد مستقیم تولید", lab, group="cogs_std", source="دستمزد مراکز تولیدی طبق طبقه‌بندی راهکاران (7110)، جذب به نسبت مواد مستقیم تولید دوره")
    rep.add("سربار تولید", oh, group="cogs_std",
            source="طبقه‌بندی راهکاران: سربار مراکز تولیدی + کل مراکز خدماتی و دفاتر، بدون انتقال به کار در جریان ساخت و کارمزد بانکی؛ جذب به نسبت مواد مستقیم تولید دوره")
    return total


def _tail(rep: Report, net: dict[str, float], cogs: dict[str, float], qty: dict[str, float],
          opex_lines: list[tuple[str, dict[str, float], str | None, str]], after_op: list[tuple[str, dict[str, float], str]],
          std: dict[str, dict[str, float]] | None = None, cogs_groups: dict[str, dict[str, float]] | None = None):
    """بهای تمام شده ← سود ناخالص ← هزینه‌ها ← سود عملیاتی ← (کارمزد) ← مالیات ← سود خالص."""
    rep.add("cost of goods sold", cogs, canon="cogs", source="تعداد خالص × (روش ساخت × آخرین فاکتور خرید × ۱.۳) × ۱.۲")
    # سهم هر گروه کالا از بهای تمام شده (ستون On sales این ردیف‌ها = درصد از کل بهای تمام شده)
    for g, vals in sorted((cogs_groups or {}).items(), key=lambda kv: -sum(kv[1].values())):
        rep.add(g, vals, group="cogs_group", ratio_base="cogs", source="بهای تمام شده این گروه کالا؛ درصد = سهم از کل بهای تمام شده")
    std_total = _std_rows(rep, std)
    gp = rep.add("Gross Profit", _sub(net, cogs), kind="total", canon="gp")
    if std_total is not None:
        rep.add("Gross Profit (استاندارد)", _sub(net, std_total), kind="total", canon="gp_std",
                source="فروش خالص − بهای تمام شده استاندارد")
    tq = sum(qty.values())
    share = {b: (qty.get(b, 0) / tq if tq else 0) for b in rep.brands}
    rep.rows.append({"label": "سهم تخصیص هزینه (بر اساس تعداد)", "code": None, "kind": "share", "canon": None, "group": "opex",
                     "values": share, "periods": {"p0": {"value": 1.0 if tq else 0, "ratio": None}}})
    opex = defaultdict(float)
    for label, vals, group, source in opex_lines:
        v = rep.add(label, vals, group=group or "opex", source=source)
        for b, x in v.items():
            opex[b] += x
    rep.add("Total Expenses", dict(opex), kind="total", canon="opex")
    op = rep.add("OPERATION PROFIT", _sub(gp, opex), kind="total", canon="op")
    pre = op
    for label, vals, source in after_op:
        v = rep.add(label, vals, source=source)
        pre = _sub(pre, v)
    if after_op:
        pre = rep.add("سود قبل مالیات", pre, kind="total")
    tax = rep.add("TAX", {b: TAX_RATE * v for b, v in pre.items()}, canon="tax", source="۲۵٪ سود قبل مالیات")
    np_ = rep.add("NET PROFIT", _sub(pre, tax), kind="total", canon="np")
    rep.ratio("NET MARGIN", np_, net, canon="margin")
    return share


# ------------------------------------------------------------------ B2B / صادرات (راهکاران)
GL_SQL = """
SELECT sl.Code AS sl, LTRIM(RTRIM(vi.DLLevel4)) AS dl4, LTRIM(RTRIM(vi.DLLevel5)) AS dl5, d5.Title AS dl5_title,
       d4.Title AS dl4_title, SUM(ISNULL(vi.Debit, 0)) AS debit, SUM(ISNULL(vi.Credit, 0)) AS credit
FROM FIN3.VoucherItem vi
JOIN FIN3.Voucher v ON v.VoucherID = vi.VoucherRef
JOIN FIN3.SL sl ON sl.SLID = vi.SLRef
LEFT JOIN FIN3.DL d4 ON d4.Code = vi.DLLevel4
LEFT JOIN FIN3.DL d5 ON d5.Code = vi.DLLevel5
WHERE sl.Code IN :codes AND v.Date >= :a AND v.Date < DATEADD(day, 1, :b) AND v.VoucherTypeRef NOT IN (5, 6, 7, 11)
GROUP BY sl.Code, vi.DLLevel4, vi.DLLevel5, d5.Title, d4.Title
"""
EXPENSE_SQL = """
SELECT LEFT(sl.Code, 4) AS gl, LTRIM(RTRIM(vi.DLLevel4)) AS dl4, sl.Code AS sl,
       SUM(ISNULL(vi.Debit, 0)) - SUM(ISNULL(vi.Credit, 0)) AS amount
FROM FIN3.VoucherItem vi
JOIN FIN3.Voucher v ON v.VoucherID = vi.VoucherRef
JOIN FIN3.SL sl ON sl.SLID = vi.SLRef
WHERE (sl.Code LIKE '7110%' OR sl.Code LIKE '7130%' OR sl.Code = '712022') AND v.Date >= :a AND v.Date < DATEADD(day, 1, :b)
  AND v.VoucherTypeRef NOT IN (5, 6, 7, 11)   -- بستن حساب‌ها / افتتاحیه / اختتامیه
GROUP BY LEFT(sl.Code, 4), vi.DLLevel4, sl.Code
"""
QTY_SQL = """
SELECT d.Code AS dl, p.Code AS part, SUM(q.qty) AS qty
FROM (
  SELECT i.CustomerRef, ii.ProductRef, ii.Quantity AS qty FROM SLS3.Invoice i
  JOIN SLS3.InvoiceItem ii ON ii.InvoiceRef = i.InvoiceID
  WHERE i.Status IN (2, 11) AND i.Date >= :a AND i.Date < DATEADD(day, 1, :b)
  UNION ALL
  SELECT r.CustomerRef, ri.ProductRef, -ri.Quantity FROM SLS3.ReturnInvoice r
  JOIN SLS3.ReturnInvoiceItem ri ON ri.ReturnInvoiceRef = r.ReturnInvoiceID
  WHERE r.Status IN (2, 11) AND r.Date >= :a AND r.Date < DATEADD(day, 1, :b)   -- 1 = پیش‌نویس (تکراری)
) q
JOIN SLS3.Customer c ON c.CustomerID = q.CustomerRef
JOIN FIN3.DL d ON d.ReferenceID = c.PartyRef AND d.DLTypeRef IN (1, 2)   -- تفصیلی شخص (حقیقی/حقوقی)
JOIN SLS3.Product sp ON sp.ProductID = q.ProductRef
JOIN LGS3.Part p ON p.PartID = sp.PartRef
GROUP BY d.Code, p.Code
"""


def _rahkaran_rows(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    from sqlalchemy import bindparam
    stmt = text(sql)
    if ":codes" in sql:
        stmt = stmt.bindparams(bindparam("codes", expanding=True))
    with _rahkaran().connect() as c:
        return [dict(r) for r in c.execute(stmt, params).mappings().all()]


# ------------------------------------------------------------------ بهای تمام شده از SQL: روش ساخت × آخرین فاکتور خرید
# بهای مواد هر محصول = Σ (مصرف استاندارد + ضایعات هر جزء در روش ساخت اصلی) × بهای جزء ÷ مقدار تجزیه؛
# جزء نیمه‌ساخته روش ساخت خودش را دارد (بازگشتی)، جزء خریدنی = آخرین فاکتور خرید تا پایان دوره.
# مثل ستون «روش دوم» اکسل، بهای مواد × ۱.۳ و در گزارش × ۱.۲.
METHOD2_MARKUP = 1.3
PURCHASE_PRICE_SQL = """
SELECT p.Code AS part, x.unit_price FROM (
  SELECT pi.PartRef,
         ii.Price * CASE WHEN ISNULL(i.OperationalCurrencyExchangeRate, 0) > 0 THEN i.OperationalCurrencyExchangeRate ELSE 1 END
           / NULLIF(ii.MajorUnitQuantity, 0) AS unit_price,
         -- سطرهای تعدیلی (مقدار ۱ با مبلغ کل) فقط وقتی که خرید واقعی دیگری نباشد
         ROW_NUMBER() OVER (PARTITION BY pi.PartRef ORDER BY CASE WHEN ii.MajorUnitQuantity > 1 THEN 0 ELSE 1 END,
                            i.InvoiceDate DESC, ii.InvoiceItemID DESC) AS rn
  FROM PRC3.InvoiceItem ii
  JOIN PRC3.Invoice i ON i.InvoiceID = ii.InvoiceRef
  JOIN PRC3.PurchaseItem pi ON pi.PurchaseItemID = ii.PurchaseItemRef
  WHERE i.InvoiceDate < DATEADD(day, 1, :end) AND ii.MajorUnitQuantity > 0 AND ii.Price > 0
) x JOIN LGS3.Part p ON p.PartID = x.PartRef WHERE x.rn = 1
"""
BOM_SQL = """
SELECT b.BillOfMaterialID AS bom, bp.Code AS product, b.IsMajor AS major, b.Status AS status, b.DecompositionQuantity AS dq,
       n.BillOfMaterialNodeID AS node, n.ParentNodeRef AS parent, p.Code AS part, n.StandardConsumption AS std,
       n.WastageConsumption AS waste, n.WastageConsumptionPercent AS waste_pct, n.IsIneffective AS ineffective
FROM CAC3.BillOfMaterial b
JOIN LGS3.Part bp ON bp.PartID = b.PartRef
JOIN CAC3.BillOfMaterialNode n ON n.BillOfMaterialRef = b.BillOfMaterialID
JOIN LGS3.Part p ON p.PartID = n.PartRef
"""
_bom_cache: dict[str, tuple[float, Any]] = {}


def _bom_tree() -> dict[str, dict[int, dict[str, Any]]]:
    """همه روش‌های ساخت (CAC3.BillOfMaterial) گروه‌بندی‌شده به تفکیک محصول؛ ۳۰ دقیقه کش."""
    hit = _bom_cache.get("__tree")
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    with _rahkaran().connect() as c:
        rows = [dict(r) for r in c.execute(text(BOM_SQL)).mappings()]
    boms: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        b = boms[str(r["product"]).strip()].setdefault(r["bom"], {"major": bool(r["major"]), "active": r["status"] == 1,
                                                                    "dq": float(r["dq"] or 0) or 1.0, "nodes": []})
        b["nodes"].append(r)
    _bom_cache["__tree"] = (time.time(), boms)
    return boms


def _rollup(prices: dict[str, float]) -> tuple[dict[str, float], set[str]]:
    """بهای مواد هر کالا با روش ساخت اصلی (بازگشتی برای نیمه‌ساخته‌ها) و فهرست کالاهای تولیدی (دارای روش ساخت)."""
    boms = _bom_tree()
    cache: dict[str, float | None] = {}
    made: set[str] = set()

    def cost(part: str, stack: frozenset) -> float | None:
        if part in cache:
            return cache[part]
        cands = boms.get(part)
        if not cands or part in stack:
            cache[part] = prices.get(part)
            return cache[part]
        b = sorted(cands.items(), key=lambda kv: (kv[1]["major"], kv[1]["active"], kv[0]))[-1][1]
        root = next((n for n in b["nodes"] if n["parent"] is None), None)
        kids = [n for n in b["nodes"] if root and n["parent"] == root["node"] and not n["ineffective"]]
        if not kids:
            cache[part] = prices.get(part)
            return cache[part]
        made.add(part)
        total = 0.0
        for n in kids:
            std = float(n["std"] or 0)
            q = std + (float(n["waste"]) if n["waste"] is not None else std * float(n["waste_pct"] or 0) / 100)
            cc = cost(str(n["part"]).strip(), stack | {part})
            total += q * (cc or 0.0)
        cache[part] = total / b["dq"]
        return cache[part]

    out = {}
    for part in set(boms) | set(prices):
        v = cost(part, frozenset())
        if v:
            out[part] = v
    return out, made


def _prices(sql: str, end: str) -> dict[str, float]:
    with _rahkaran().connect() as c:
        return {str(r["part"]).strip(): float(r["unit_price"]) for r in c.execute(text(sql), {"end": end}).mappings() if r["unit_price"]}


def bom_costs(end: str) -> dict[str, float]:
    """بهای مواد هر کالا (ریال، بدون ضریب) با آخرین فاکتور خرید تا تاریخ end؛ ۳۰ دقیقه کش."""
    hit = _bom_cache.get(f"last:{end}")
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    out, _ = _rollup(_prices(PURCHASE_PRICE_SQL, end))
    _bom_cache[f"last:{end}"] = (time.time(), out)
    return out


# ------------------------------------------------------------------ بهای تمام شده استاندارد (هزینه‌یابی جذبی، استاندارد ۸ / IAS 2)
# بهای واحد = مواد مستقیم + دستمزد مستقیم + سربار تولید جذب‌شده
#   مواد مستقیم   = روش ساخت × میانگین موزون قیمت خرید ۱۲ ماه منتهی به پایان دوره (نه آخرین خرید)
#   دستمزد و سربار = هزینه‌های واقعی همان دوره با طبقه‌بندی خود راهکاران (CAC3.ConversionSL):
#                    دستمزد = معین‌های نوع دستمزد در مراکز تولیدی؛
#                    سربار  = معین‌های نوع سربار در مراکز تولیدی + همه هزینه مراکز خدماتی و دفاتر (که راهکاران روی تولید سرشکن می‌کند)؛
#                    به نسبت مواد مستقیمِ تولید همان دوره (رسید «دریافت از تولید») روی هر محصول جذب می‌شود.
#   کنار گذاشته می‌شود: سند «انتقال به کار در جریان ساخت» (بستن هزینه به موجودی، نه هزینه جدید)،
#                    کارمزد بانکی 712022 (ردیف جدا در P&L دارد) و سندهای EXCLUDED_CONVERSION_VOUCHERS.
#   کالای خریداری‌شده برای فروش (بدون روش ساخت) فقط بهای خرید دارد.
PRODUCTION_CENTERS = ("500001", "500002", "500003")   # مرکز تولیدی اکسیرکادوس / کادوس / فراز بهداشت
CONVERSION_LABOUR_TYPE = 2                            # CAC3.ConversionSL.Type: 1 = سربار، 2 = دستمزد
EXCLUDED_CONVERSION_VOUCHERS = (315794,)              # سند ۲۷۷۹۴ (۳۸۸٬۷۵۰ م.ر «سفر و اقامت»، ۲۵ بهمن ۱۴۰۴)؛ در انتظار تأیید مالی
WAVG_PRICE_SQL = """
SELECT p.Code AS part,
       SUM(ii.Price * CASE WHEN ISNULL(i.OperationalCurrencyExchangeRate, 0) > 0 THEN i.OperationalCurrencyExchangeRate ELSE 1 END)
         / NULLIF(SUM(ii.MajorUnitQuantity), 0) AS unit_price
FROM PRC3.InvoiceItem ii
JOIN PRC3.Invoice i ON i.InvoiceID = ii.InvoiceRef
JOIN PRC3.PurchaseItem pi ON pi.PurchaseItemID = ii.PurchaseItemRef
JOIN LGS3.Part p ON p.PartID = pi.PartRef
WHERE i.InvoiceDate >= DATEADD(year, -1, :end) AND i.InvoiceDate < DATEADD(day, 1, :end) AND ii.MajorUnitQuantity > 1 AND ii.Price > 0
GROUP BY p.Code
"""
PRODUCTION_SQL = """
SELECT p.Code AS part, SUM(i.Quantity) AS qty
FROM LGS3.InventoryVoucherItem i
JOIN LGS3.vwInventoryVoucherWithAllStates v ON v.InventoryVoucherID = i.InventoryVoucherRef
JOIN LGS3.Part p ON p.PartID = i.PartRef
WHERE v.InventoryVoucherSpecificationRef = 4 AND i.Date >= :a AND i.Date < DATEADD(day, 1, :b)   -- 4 = دریافت از تولید
GROUP BY p.Code
"""
CONVERSION_SQL = f"""
SELECT sl.Code AS sl, LEFT(sl.Code, 4) AS gl, LTRIM(RTRIM(vi.DLLevel4)) AS dl, m.kind,
       SUM(ISNULL(vi.Debit, 0) - ISNULL(vi.Credit, 0)) AS amount
FROM FIN3.VoucherItem vi
JOIN FIN3.Voucher v ON v.VoucherID = vi.VoucherRef
JOIN FIN3.SL sl ON sl.SLID = vi.SLRef
JOIN (SELECT s2.Code AS code, MAX(c.Type) AS kind FROM CAC3.ConversionSL c
      JOIN FIN3.SL s2 ON s2.SLID = c.SLRef
      WHERE c.FiscalYearRef = (SELECT MAX(FiscalYearRef) FROM CAC3.ConversionSL)
      GROUP BY s2.Code) m ON m.code = sl.Code
JOIN (SELECT DISTINCT LTRIM(RTRIM(Number)) AS dl FROM GNR3.CostCenter) cc ON cc.dl = LTRIM(RTRIM(vi.DLLevel4))
WHERE LEFT(sl.Code, 1) = '7' AND sl.Code <> '712022'
  AND v.Date >= :a AND v.Date < DATEADD(day, 1, :b) AND v.VoucherTypeRef NOT IN (5, 6, 7, 11)
  AND ISNULL(v.Description, '') NOT LIKE N'%انتقال به کار در جریان%'
  AND v.VoucherID NOT IN ({", ".join(map(str, EXCLUDED_CONVERSION_VOUCHERS))})
GROUP BY sl.Code, LEFT(sl.Code, 4), LTRIM(RTRIM(vi.DLLevel4)), m.kind
"""


def _conversion_pools(rows: list[dict[str, Any]]) -> tuple[float, float, dict[str, float]]:
    """(دستمزد، سربار، جمع به تفکیک کل): دستمزدِ مراکز تولیدی دستمزد است و هر هزینه دیگر سربار."""
    labour = overhead = 0.0
    by_gl: dict[str, float] = defaultdict(float)
    for r in rows:
        amount = float(r["amount"] or 0)
        by_gl[r["gl"]] += amount
        if r["dl"] in PRODUCTION_CENTERS and int(r["kind"]) == CONVERSION_LABOUR_TYPE:
            labour += amount
        else:
            overhead += amount
    return labour, overhead, dict(by_gl)


def standard_cost(p: dict[str, Any]) -> dict[str, Any]:
    """بهای واحد استاندارد هر کالا (مواد، دستمزد، سربار) برای دوره p؛ ۳۰ دقیقه کش."""
    key = f"std:{p['from']}:{p['to']}"
    hit = _bom_cache.get(key)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    last = _prices(PURCHASE_PRICE_SQL, p["to"])
    prices = {**last, **_prices(WAVG_PRICE_SQL, p["to"])}   # میانگین موزون؛ اگر خرید ۱۲ ماهه نبود آخرین خرید
    dm, made = _rollup(prices)
    produced = {str(r["part"]).strip(): float(r["qty"] or 0) for r in _rahkaran_rows(PRODUCTION_SQL, {"a": p["from"], "b": p["to"]})}
    labour, overhead, conv = _conversion_pools(_rahkaran_rows(CONVERSION_SQL, {"a": p["from"], "b": p["to"]}))
    dm_production = sum(q * dm.get(part, 0.0) for part, q in produced.items() if q > 0)
    out = {"dm": dm, "made": made,
           "labour_rate": labour / dm_production if dm_production else 0.0,
           "overhead_rate": overhead / dm_production if dm_production else 0.0,
           "summary": {"labour": labour, "overhead": overhead, "dm_production": dm_production,
                       "units_produced": sum(q for q in produced.values() if q > 0), "by_gl": conv}}
    _bom_cache[key] = (time.time(), out)
    return out


def _std_split(std: dict[str, Any], part: str, qty: float) -> tuple[float, float, float] | None:
    """(مواد، دستمزد، سربار) به ریال برای qty عدد از part؛ None اگر بهای مواد معلوم نیست."""
    unit = std["dm"].get(part)
    if not unit:
        return None
    dm = qty * unit
    if part not in std["made"]:
        return dm, 0.0, 0.0
    return dm, dm * std["labour_rate"], dm * std["overhead_rate"]


def _unit_cost(m: dict[str, Any], part: str, bom: dict[str, float] | None = None, used: dict[str, int] | None = None) -> float | None:
    """بهای واحد «روش دوم» (ریال): اول از روش ساخت × آخرین خرید (SQL)، وگرنه شیت Cost اکسل، وگرنه میانگین گروه کالا."""
    if bom and bom.get(part):
        if used is not None:
            used["sql"] = used.get("sql", 0) + 1
        return bom[part] * METHOD2_MARKUP
    if used is not None:
        used["excel"] = used.get("excel", 0) + 1
    if part in m["unit_cost"]:
        return m["unit_cost"][part]
    groups = m.setdefault("_groups", {})
    if not groups:
        acc: dict[str, list[float]] = defaultdict(list)
        for code, v in m["unit_cost"].items():
            acc[code[:7]].append(v); acc[code[:5]].append(v)
        groups.update({k: sum(v) / len(v) for k, v in acc.items()})
    return groups.get(part[:7]) or groups.get(part[:5])


# ------------------------------------------------------------------ گروه کالا (همان نگاشت داشبورد فروش: sales/category_map.json)
CATEGORY_MAP = Path(__file__).resolve().parents[3] / "sales" / "category_map.json"
NO_GROUP = "بدون گروه"
_group_cache: dict[str, Any] = {}


def _group_of(part: str) -> str:
    """گروه کالای هر کد کالا؛ کد ناشناخته = گروه غالب هم‌پیشوند (۷ و بعد ۵ رقم اول)، وگرنه «بدون گروه»."""
    try:
        mtime = CATEGORY_MAP.stat().st_mtime
    except OSError:
        return NO_GROUP
    if _group_cache.get("mtime") != mtime:
        try:
            prods = json.loads(CATEGORY_MAP.read_text(encoding="utf-8")).get("products") or {}
        except (OSError, ValueError):
            prods = {}
        exact = {str(k).strip(): (v[0] if isinstance(v, list) and v else v) or NO_GROUP for k, v in prods.items()}
        votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for k, g in exact.items():
            votes[k[:7]][g] += 1
            votes[k[:5]][g] += 1
        prefix = {p: max(c, key=c.get) for p, c in votes.items()}
        _group_cache.update(mtime=mtime, exact=exact, prefix=prefix)
    return _group_cache["exact"].get(part) or _group_cache["prefix"].get(part[:7]) or _group_cache["prefix"].get(part[:5]) or NO_GROUP


PART_NAME_SQL = "SELECT Code AS part, Name AS name FROM LGS3.Part"


def _part_names() -> dict[str, str]:
    hit = _bom_cache.get("__names")
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    try:
        names = {str(r["part"]).strip(): str(r["name"] or "").strip() for r in _rahkaran_rows(PART_NAME_SQL, {})}
    except Exception:  # noqa: BLE001 — نبود نام کالا نباید گزارش را خراب کند
        names = {}
    _bom_cache["__names"] = (time.time(), names)
    return names


def _cogs_group_detail(products: dict[str, dict[str, float]]) -> dict[str, Any]:
    """جزئیات «بهای تمام شده به تفکیک گروه کالا»: هر گروه با سهمش از بهای تمام شده و ریز کالاهایش (باز شدنی)."""
    names = _part_names()
    total = sum(v["cogs"] for v in products.values()) or 0.0
    groups: dict[str, list[tuple[str, dict[str, float]]]] = defaultdict(list)
    for part, v in products.items():
        groups[_group_of(part)].append((part, v))
    rows = []
    for g, items in sorted(groups.items(), key=lambda kv: -sum(v["cogs"] for _, v in kv[1])):
        gc = sum(v["cogs"] for _, v in items)
        rows.append({"cells": [g, len(items), round(sum(v["qty"] for _, v in items)), round(gc), (gc / total) if total else None],
                     "children": [[part, names.get(part, ""), round(v["qty"]), round(v["unit"]), round(v["cogs"]), (v["cogs"] / gc) if gc else None]
                                  for part, v in sorted(items, key=lambda kv: -kv[1]["cogs"])]})
    return {"key": "cogs_groups", "title": "بهای تمام شده به تفکیک گروه کالا", "source": "SQL",
            "tree": {"columns": ["گروه کالا", "تعداد کالا", "تعداد خالص", "بهای تمام شده (م.ر)", "سهم از بهای تمام شده"],
                     "pct_columns": [4],
                     "child_columns": ["کد کالا", "نام کالا", "تعداد خالص", "بهای واحد روش دوم (ریال)", "بهای تمام شده (م.ر)", "سهم از گروه"],
                     "child_pct_columns": [5], "rows": rows, "total": [None, None, None, round(total), 1.0 if total else None]}}


def _customer_brand(m: dict[str, Any], dl: str, title: Any) -> str:
    return m["brand"].get(dl) or _brand(title) or "Other"


def build_ledger(key: str, p: dict[str, Any]) -> dict[str, Any]:
    cfg, m = CHANNEL_GL[key], master()
    a, b = p["from"], p["to"]
    codes = [c for c in (cfg["gross"], cfg["discount"], cfg["return"]) if c]
    gl = _rahkaran_rows(GL_SQL, {"codes": codes, "a": a, "b": b})
    gross, ret, disc = defaultdict(float), defaultdict(float), defaultdict(float)
    disc_types: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    customers: dict[str, dict[str, Any]] = {}
    unmapped = defaultdict(float)
    in_channel: set[str] = set()
    for r in gl:
        dl = r["dl4"] or ""
        ch = m["channel"].get(dl)
        if ch != cfg["channel"] and not (key == "export" and r["sl"] in (cfg["gross"], cfg["discount"])):
            if ch is None and r["sl"] == cfg["gross"]:
                unmapped[f"{dl} {r['dl4_title'] or ''}".strip()] += (float(r["credit"]) - float(r["debit"])) / 1e6
            continue
        in_channel.add(dl)
        br = _customer_brand(m, dl, r["dl4_title"])
        amt = (float(r["credit"]) - float(r["debit"])) / 1e6
        cust = customers.setdefault(dl, {"name": r["dl4_title"] or dl, "brand": br, "gross": 0.0, "return": 0.0, "discount": 0.0})
        if r["sl"] == cfg["gross"]:
            gross[br] += amt; cust["gross"] += amt
        elif r["sl"] == cfg["return"]:
            ret[br] -= amt; cust["return"] -= amt
        else:
            disc[br] -= amt; cust["discount"] -= amt
            disc_types[(r["dl5_title"] or "سایر تخفیفات").strip()][br] -= amt

    qty, cogs = defaultdict(float), defaultdict(float)
    missing_cost = defaultdict(float)
    bom, cost_used = bom_costs(b), {}
    std_cost = standard_cost(p)
    std_vals: dict[str, dict[str, float]] = {"dm": defaultdict(float), "labour": defaultdict(float), "overhead": defaultdict(float)}
    products: dict[str, dict[str, float]] = defaultdict(lambda: {"qty": 0.0, "cogs": 0.0, "unit": 0.0})
    cogs_groups: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    brand_parts: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for r in _rahkaran_rows(QTY_SQL, {"a": a, "b": b}):
        dl = str(r["dl"]).strip()
        if dl not in in_channel and m["channel"].get(dl) != cfg["channel"]:
            continue
        br = customers.get(dl, {}).get("brand") or _customer_brand(m, dl, None)
        q = float(r["qty"] or 0)
        part = str(r["part"]).strip()
        qty[br] += q
        brand_parts[br][part][0] += q
        split = _std_split(std_cost, part, q)
        if split:
            std_vals["dm"][br] += split[0] / 1e6; std_vals["labour"][br] += split[1] / 1e6; std_vals["overhead"][br] += split[2] / 1e6
        unit = _unit_cost(m, part, bom, cost_used)
        if unit is None:
            missing_cost[part] += q
            continue
        c = q * unit * COGS_FACTOR / 1e6
        cogs[br] += c
        cogs_groups[_group_of(part)][br] += c
        brand_parts[br][part][1] += c
        products[part]["qty"] += q; products[part]["cogs"] += c; products[part]["unit"] = unit

    brands = BRANDS + (["Other"] if any(k == "Other" for k in list(gross) + list(qty)) else [])
    rep = Report(brands)
    rep.add("Net Sales(QqtY)", qty, canon="qty", source="SLS3 فاکتور فروش − برگشت")
    rep.add("Gross Sales (Mrials)", gross, canon="gross", source=f"معین {cfg['gross']}")
    rep.add("Return", ret, canon="return", source=f"معین {cfg['return']}" if cfg["return"] else None)
    rep.add("Discounts", disc, canon="discount", ratio_base="gross", source=f"معین {cfg['discount']}؛ درصد نسبت به فروش ناخالص")
    net = rep.add("Total Net Sales", _sub(gross, ret, disc), kind="total", canon="net")
    for title, vals in sorted(disc_types.items(), key=lambda kv: -sum(kv[1].values())):
        rep.add(title, vals, group="discount_detail", ratio_base="gross", source=f"تفصیلی سطح ۵ معین {cfg['discount']}")
    rep.ratio("%", {b: disc.get(b, 0) for b in brands}, {b: gross.get(b, 0) for b in brands})

    opex_lines, after_op, expenses = [], [], []
    if key == "b2b":
        tq = sum(qty.values())
        share = {b: (qty.get(b, 0) / tq if tq else 0) for b in brands}
        sal = sga = bank = 0.0
        for r in _rahkaran_rows(EXPENSE_SQL, {"a": a, "b": b}):
            amt = float(r["amount"] or 0) / 1e6
            dl = (r["dl4"] or "").strip()
            if r["gl"] == "7110" and dl in B2B_SALARY_DLS:
                sal += amt; expenses.append(["7110", dl, r["sl"], amt])
            elif r["gl"] == "7130" and dl in B2B_SGA_DLS:
                sga += amt; expenses.append(["7130", dl, r["sl"], amt])
            elif r["sl"] == "712022":
                bank += amt
        opex_lines = [("هزینه های حقوق و دستمزد", _alloc(sal, share), "opex", "7110 دفاتر تهران"),
                      ("هزینه های فروش ، اداری و عمومی", _alloc(sga, share), "opex", "7130 مراکز هزینه B2B")]
        after_op = [("هزینه کارمزدهای بانکی", _alloc(bank, share), "712022")]
    _tail(rep, net, dict(cogs), dict(qty), opex_lines, after_op, std_vals, cogs_groups)

    details = [
        _cogs_group_detail(products),
        _table_detail("customers", "مشتریان (لایو)", ["کد", "مشتری", "برند", "فروش ناخالص", "برگشت", "تخفیف", "فروش خالص"],
                      sorted(([dl, c["name"], c["brand"], round(c["gross"]), round(c["return"]), round(c["discount"]),
                               round(c["gross"] - c["return"] - c["discount"])] for dl, c in customers.items()), key=lambda x: -x[6])),
        _table_detail("products", "بهای تمام شده به تفکیک کالا", ["کد کالا", "بهای مواد (روش ساخت × آخرین خرید، ریال)",
                      "بهای روش دوم (× ۱.۳)", "تعداد خالص", "بهای تمام شده (م.ر، × ۱.۲)"],
                      sorted(([k, round(bom.get(k, 0)), round(v["unit"]), round(v["qty"]), round(v["cogs"])] for k, v in products.items()),
                             key=lambda x: -x[4])),
    ]
    if expenses:
        details.append(_table_detail("expenses", "هزینه‌ها (اسناد)", ["کل", "مرکز هزینه", "معین", "مبلغ"],
                                     sorted(([g, d, s, round(x)] for g, d, s, x in expenses), key=lambda x: -x[3])))
    warnings = []
    if missing_cost:
        warnings.append(f"{len(missing_cost)} کالا ({round(sum(missing_cost.values())):,} عدد) نه روش ساخت/فاکتور خرید دارد نه بهای اکسل؛ در بهای تمام شده نیامده.")
    if cost_used.get("excel"):
        warnings.append(f"بهای {cost_used['excel']:,} ردیف کالا از روش ساخت/فاکتور خرید درنیامد و از شیت Cost اکسل خوانده شد.")
    if unmapped:
        warnings.append(f"{len(unmapped)} مشتری با فروش {round(sum(unmapped.values())):,} م.ر در شیت Map کانال ندارد و کنار گذاشته شد.")
    return {"report": rep, "details": details, "warnings": warnings, "brand_parts": brand_parts}


def _table_detail(key: str, title: str, columns: list[str], rows: list[list[Any]], limit: int = 2000) -> dict[str, Any]:
    return {"key": key, "title": title, "source": "SQL", "table": {"columns": columns, "rows": rows[:limit]}}


# ------------------------------------------------------------------ هیبرید (کارآمد)
HYBRID_SQL = """
SELECT v.BrandName AS brand, v.GoodsCode AS goods, v.BranchName AS branch, v.FactorType AS kind,
       SUM(v.TotalT) AS qty, SUM(v.SumPrice) AS gross, SUM(v.Discount) AS vol_disc,
       SUM(v.CashDiscount) AS cash_disc, SUM(v.Vat) AS vat
FROM dbo.vwFactorFBLinesFull v
WHERE v.DateE >= :a AND v.DateE < DATEADD(day, 1, :b) AND v.BranchName LIKE N'%هیبرید%'
GROUP BY v.BrandName, v.GoodsCode, v.BranchName, v.FactorType
"""


# هزینه‌های هیبرید: اسناد حسابداری کارآمد (همان تراز شیت «هزینه ها» اکسل) — کل ۸۱/۸۳/۸۵/۸۷ شعبه‌های هیبرید
HYBRID_EXPENSE_SQL = """
SELECT g.Code AS gl, s.Code AS sl, s.Name AS sl_name, b.Name AS branch, SUM(l.Debtor - l.Creditor) AS amount
FROM dbo.tblVoucherLines l
JOIN dbo.tblVoucher v ON v.ID = l.VoucherRef
JOIN dbo.tblSL s ON s.ID = l.SLRef
JOIN dbo.tblGL g ON g.ID = s.GLRef
JOIN dbo.tblBranch b ON b.ID = v.BranchRef
WHERE v.DateE >= :a AND v.DateE < DATEADD(day, 1, :b) AND g.Code IN ('81', '83', '85', '87')
  AND ISNULL(l.isDeleted, 0) = 0 AND b.Name LIKE N'%هیبرید%' AND v.KindRef NOT IN (13, 14, 32)   -- اختتامیه/افتتاحیه
GROUP BY g.Code, s.Code, s.Name, b.Name
"""
# ترتیب و دسته‌بندی ردیف‌ها مثل اکسل: پورسانت (8138) و بهره‌وری (8137، 8704) جدا از حقوق و توزیع
HYBRID_EXPENSE_LINES = [
    ("هزینه های حقوق و دستمزد", "opex", "کل 81 (به‌جز 8137، 8138)"),
    ("هزینه های اداری وتشکیلاتی", "opex", "کل 83"),
    ("هزینه های مالی", "opex", "کل 85"),
    ("هزینه های توزیع و فروش", "opex", "کل 87 (به‌جز 8704)"),
    ("هزینه پورسانت هیبرید من", "پورسانت", "معین 8138"),
    ("بهره وری", "پورسانت", "معین 8137 و 8704"),
]


def _hybrid_expense_line(gl: str, sl: str) -> str:
    if sl == "8138":
        return "هزینه پورسانت هیبرید من"
    if sl in ("8137", "8704"):
        return "بهره وری"
    return {"81": "هزینه های حقوق و دستمزد", "83": "هزینه های اداری وتشکیلاتی",
            "85": "هزینه های مالی", "87": "هزینه های توزیع و فروش"}[gl]


def build_hybrid(p: dict[str, Any]) -> dict[str, Any]:
    m = master()
    with _karamad().connect() as c:
        rows = [dict(r) for r in c.execute(text(HYBRID_SQL), {"a": p["from"], "b": p["to"]}).mappings().all()]
    gross, ret, vol, cash, vat, qty, cogs = (defaultdict(float) for _ in range(7))
    branches: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    products: dict[str, dict[str, float]] = defaultdict(lambda: {"qty": 0.0, "cogs": 0.0, "unit": 0.0})
    cogs_groups: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    brand_parts: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    missing_cost = defaultdict(float)
    bom, cost_used = bom_costs(p["to"]), {}
    std_cost = standard_cost(p)
    std_vals: dict[str, dict[str, float]] = {"dm": defaultdict(float), "labour": defaultdict(float), "overhead": defaultdict(float)}
    for r in rows:
        br = _brand(r["brand"]) or "Other"
        sale = r["kind"] == "فروش"
        g = float(r["gross"] or 0) / 1e6
        q = float(r["qty"] or 0)
        (gross if sale else ret)[br] += g if sale else -g
        vol[br] += float(r["vol_disc"] or 0) / 1e6
        cash[br] += float(r["cash_disc"] or 0) / 1e6
        vat[br] += float(r["vat"] or 0) / 1e6
        qty[br] += q
        brand_parts[br][_code(r["goods"])][0] += q
        split = _std_split(std_cost, _code(r["goods"]), q)
        if split:
            std_vals["dm"][br] += split[0] / 1e6; std_vals["labour"][br] += split[1] / 1e6; std_vals["overhead"][br] += split[2] / 1e6
        unit = _unit_cost(m, _code(r["goods"]), bom, cost_used)
        if unit is None:
            missing_cost[_code(r["goods"])] += q
        else:
            cogs[br] += q * unit * COGS_FACTOR / 1e6
            cogs_groups[_group_of(_code(r["goods"]))][br] += q * unit * COGS_FACTOR / 1e6
            brand_parts[br][_code(r["goods"])][1] += q * unit * COGS_FACTOR / 1e6
            pr = products[_code(r["goods"])]
            pr["qty"] += q; pr["cogs"] += q * unit * COGS_FACTOR / 1e6; pr["unit"] = unit
        b = branches[str(r["branch"]).strip()]
        b["gross" if sale else "return"] += g if sale else -g
        b["discount"] += (float(r["vol_disc"] or 0) + float(r["cash_disc"] or 0)) / 1e6
        b["qty"] += q
    brands = HYBRID_BRANDS + (["Other"] if "Other" in gross or "Other" in qty else [])
    rep = Report(brands)
    disc = {b: vol.get(b, 0) + cash.get(b, 0) for b in brands}
    rep.add("Net Sales(QqtY)", qty, canon="qty", source="کارآمد، فروش − برگشت")
    rep.add("Gross Sales (Mrials)", gross, canon="gross", source="جمع قبل تخفیف فاکتورهای فروش")
    rep.add("Return", ret, canon="return", source="برگشت از فروش (به تاریخ برگشت)")
    rep.ratio("Discount %", disc, gross)
    rep.add("Discount", disc, canon="discount", ratio_base="gross")
    net = rep.add("Total Net Sales", _sub(gross, ret, disc), kind="total", canon="net")
    rep.add("Value added", vat, canon="vat")
    rep.add("تخفیف حجمی", vol, group="discount_detail", ratio_base="gross")
    rep.add("تخفیف نقدی", cash, group="discount_detail", ratio_base="gross")
    rep.add("جمع تخفیفات", disc, kind="total", ratio_base="gross")
    with _karamad().connect() as c:
        exp_rows = [dict(r) for r in c.execute(text(HYBRID_EXPENSE_SQL), {"a": p["from"], "b": p["to"]}).mappings().all()]
    totals: dict[str, float] = defaultdict(float)
    for r in exp_rows:
        totals[_hybrid_expense_line(str(r["gl"]).strip(), str(r["sl"]).strip())] += float(r["amount"] or 0) / 1e6
    tq = sum(qty.values())
    share = {b: (qty.get(b, 0) / tq if tq else 0) for b in brands}
    opex_lines = [(label, _alloc(totals.get(label, 0.0), share), group, f"اسناد حسابداری کارآمد، {src}، تخصیص به نسبت تعداد")
                  for label, group, src in HYBRID_EXPENSE_LINES]
    _tail(rep, net, dict(cogs), dict(qty), opex_lines, [], std_vals, cogs_groups)
    details = [_cogs_group_detail(products),
               _table_detail("branches", "شعبه‌های هیبرید (لایو)", ["شعبه", "تعداد خالص", "فروش ناخالص", "برگشت", "تخفیف", "فروش خالص"],
                             sorted(([k, round(v["qty"]), round(v["gross"]), round(v["return"]), round(v["discount"]),
                                      round(v["gross"] - v["return"] - v["discount"])] for k, v in branches.items()), key=lambda x: -x[5])),
               _table_detail("products", "بهای تمام شده به تفکیک کالا", ["کد کالا", "بهای مواد (روش ساخت × آخرین خرید، ریال)",
                             "بهای روش دوم (× ۱.۳)", "تعداد خالص", "بهای تمام شده (م.ر، × ۱.۲)"],
                             sorted(([k, round(bom.get(k, 0)), round(v["unit"]), round(v["qty"]), round(v["cogs"])] for k, v in products.items()),
                                    key=lambda x: -x[4])),
               _table_detail("expenses", "هزینه‌ها (اسناد کارآمد)", ["کل", "معین", "عنوان", "شعبه", "ردیف P&L", "مبلغ"],
                             sorted(([str(r["gl"]).strip(), str(r["sl"]).strip(), r["sl_name"], str(r["branch"]).strip(),
                                      _hybrid_expense_line(str(r["gl"]).strip(), str(r["sl"]).strip()), round(float(r["amount"] or 0) / 1e6)]
                                     for r in exp_rows), key=lambda x: -x[5]))]
    warnings = []
    if missing_cost:
        warnings.append(f"{len(missing_cost)} کالا ({round(sum(missing_cost.values())):,} عدد) نه روش ساخت/فاکتور خرید دارد نه بهای اکسل؛ در بهای تمام شده نیامده.")
    if cost_used.get("excel"):
        warnings.append(f"بهای {cost_used['excel']:,} ردیف کالا از روش ساخت/فاکتور خرید درنیامد و از شیت Cost اکسل خوانده شد.")
    return {"report": rep, "details": details, "warnings": warnings, "brand_parts": brand_parts}


# ------------------------------------------------------------------ مقایسه با اکسل و خروجی
def _excel_compare(key: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        cached = json.loads((pnl_service.CACHE_DIR / f"{key}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rep = cached.get("report") or {}
    ex = {(r.get("canon") or r["label"]): r for r in rep.get("rows", [])}
    p0 = (rep.get("periods") or [{}])[0]
    for r in rows:
        e = ex.get(r.get("canon") or r["label"])
        if e:
            r["periods"]["excel"] = {"value": (e["periods"].get(p0.get("key"), {}) or {}).get("value"), "ratio": None}
    return {"label": f"اکسل ({p0.get('label', '')})", "modified": cached.get("modified")}


def _comparison_periods(p: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """ستون‌های مقایسه: همه فصل‌های قبلیِ همان سال (جدیدترین اول؛ برای Q1 فصل آخر سال قبل)،
    همان فصل سال قبل و کل سال قبل (برای کل سال: فقط سال قبل)."""
    m = re.match(r"(\d{4})(?:-Q(\d))?$", p["key"])
    if not m:
        return []
    year, q = int(m.group(1)), int(m.group(2) or 0)
    if q:
        wanted = [f"{year}-Q{i}" for i in range(q - 1, 0, -1)] or [f"{year - 1}-Q4"]
        wanted.append(f"{year - 1}-Q{q}")
    else:
        # «کل سال»: ریز هر فصل بسته‌شده همان سال (به ترتیب) و بعد کل سال قبل
        wanted = [f"{year}-Q{i}" for i in p.get("quarters") or []] if len(p.get("quarters") or []) > 1 else []
    wanted.append(f"{year - 1}")
    out = []
    for k in wanted:
        try:
            out.append((k, _period(k)))
        except (KeyError, AttributeError):
            continue
    return out


def _attach_period(rows: list[dict[str, Any]], key: str, other: list[dict[str, Any]]):
    """جمع هر ردیف دوره دیگر را با کلید canon/عنوان کنار ردیف دوره جاری می‌گذارد (+ «On sales» با همان مخرج ردیف)."""
    by_key = {(r.get("canon") or r["label"]): r for r in other}
    seen = set()
    for r in rows:
        k = r.get("canon") or r["label"]
        o = by_key.get(k)
        seen.add(k)
        v = o["periods"]["p0"]["value"] if o else None
        den = _ratio_base_value(other, r)
        r["periods"][key] = {"value": v, "ratio": (v / den) if (v is not None and den and r["kind"] not in ("ratio", "share")
                                                                  and r.get("canon") != "qty") else None,
                             "brands": dict(o["values"]) if o else None}
    # نوع تخفیف یا گروه کالایی که فقط در دوره مقایسه بوده (مثل «فروش ویژه زمستان ۱۴۰۴» اکسل): ردیف صفر برای دوره جاری
    for group in ("discount_detail", "cogs_group"):
        _insert_missing(rows, key, other, seen, group)


def _insert_missing(rows: list[dict[str, Any]], key: str, other: list[dict[str, Any]], seen: set, group: str):
    last_detail = max((i for i, r in enumerate(rows) if r.get("group") == group), default=None)
    if last_detail is None:
        return
    for o in other:
        k = o.get("canon") or o["label"]
        if o.get("group") == group and k not in seen:
            v = o["periods"]["p0"]["value"]
            den = _ratio_base_value(other, o)
            new = {**o, "values": {b: 0.0 for b in rows[0]["values"]}, "periods": {"p0": {"value": 0.0, "ratio": 0.0},
                   key: {"value": v, "ratio": (v / den) if den and v is not None else None, "brands": dict(o["values"])}}}
            last_detail += 1
            rows.insert(last_detail, new)
            seen.add(k)


def _build(key: str, p: dict[str, Any]) -> dict[str, Any]:
    t0 = time.time()
    res = build_hybrid(p) if key == "hybrid" else build_ledger(key, p)
    rows = res["report"].finish()
    sc = standard_cost(p)["summary"]
    res["details"].append(_table_detail("standard_cost", "بهای تمام شده استاندارد — مبنای محاسبه", ["شرح", "مبلغ (م.ر) / مقدار"], [
        ["دستمزد مستقیم تولید (دستمزد مراکز تولیدی طبق راهکاران)", round(sc["labour"] / 1e6)],
        ["سربار تولید (طبق راهکاران، با مراکز خدماتی و دفاتر)", round(sc["overhead"] / 1e6)],
        ["مواد مستقیمِ تولید دوره (رسید دریافت از تولید × بهای مواد)", round(sc["dm_production"] / 1e6)],
        ["نرخ جذب دستمزد (٪ از مواد مستقیم)", round(100 * sc["labour"] / sc["dm_production"], 1) if sc["dm_production"] else 0],
        ["نرخ جذب سربار (٪ از مواد مستقیم)", round(100 * sc["overhead"] / sc["dm_production"], 1) if sc["dm_production"] else 0],
        ["تعداد تولید دوره (عدد)", round(sc["units_produced"])],
    ]))
    periods_meta = [{"key": "p0", "label": p["label"], "has_ratio": True}]
    # ریز کالا و مشتری هر دوره برای پنجره جزئیات ستون‌های دوره
    period_parts = {"p0": _period_parts_payload(res.get("brand_parts") or {}, res["report"].brands)}
    period_customers = {"p0": _customers_rows(res["details"])}
    for i, (_, cp) in enumerate(_comparison_periods(p), start=1):
        try:
            ores = build_hybrid(cp) if key == "hybrid" else build_ledger(key, cp)
            other = ores["report"].finish()
        except Exception:  # noqa: BLE001 — نبودِ یک دوره مقایسه نباید گزارش اصلی را خراب کند
            continue
        _attach_period(rows, f"p{i}", other)
        period_parts[f"p{i}"] = _period_parts_payload(ores.get("brand_parts") or {}, ores["report"].brands)
        period_customers[f"p{i}"] = _customers_rows(ores["details"])
        # هم‌طول با دوره جاری (فصل با فصل، کل سال با کل سال هم‌تعداد فصل)؟ کارت «رشد» فقط با دوره هم‌طول مقایسه می‌کند
        same = len(cp.get("quarters") or []) == len(p.get("quarters") or []) and ("Q" in cp["key"]) == ("Q" in p["key"])
        periods_meta.append({"key": f"p{i}", "label": cp["label"], "has_ratio": True, "comparable": same})
    # اکسل‌ها گزارش آخرین فصل کامل‌شده‌اند؛ برای دوره‌های دیگر ستون مقایسه گمراه‌کننده است
    cy, cq = last_closed_quarter()
    excel = _excel_compare(key, rows) if p["key"] == f"{cy}-Q{cq}" else None
    if excel:
        periods_meta.append({"key": "excel", "label": excel["label"], "has_ratio": False})
    report = {"brands": res["report"].brands, "periods": periods_meta, "rows": rows,
              "settings": {"method": "Method2", "return_mode": "WithReturn", "cost_multiplier": COGS_FACTOR}, "unit": "میلیون ریال"}
    return {"key": key, "title": pnl_service.SOURCES[key]["title"], "status": "ready", "live": True,
            "period": p, "modified": datetime.now().isoformat(timespec="seconds"), "built_seconds": round(time.time() - t0, 1),
            "warnings": res["warnings"], "excel": excel, "report": report, "details": res["details"],
            "brand_parts": _brand_parts_payload(res.get("brand_parts") or {}),
            "period_parts": period_parts, "period_customers": {k: v for k, v in period_customers.items() if v}}


def _period_parts_payload(bp: dict[str, dict[str, list[float]]], brands: list[str]) -> list[list[Any]]:
    """ریز کالاهای یک دوره (جمع همه برندها): [کد، نام، گروه کالا، تعداد خالص، بهای تمام شده (م.ر)، برندها]."""
    names = _part_names()
    tot: dict[str, list[Any]] = {}
    for br, parts in bp.items():
        if br not in brands:  # همان برندهای ستون‌های گزارش، تا جمع کالاها با ردیف بهای تمام شده یکی باشد
            continue
        for part, v in parts.items():
            if not (v[0] or v[1]):
                continue
            t = tot.setdefault(part, [0.0, 0.0, set()])
            t[0] += v[0]; t[1] += v[1]; t[2].add(br)
    return sorted(([part, names.get(part, ""), _group_of(part), round(t[0]), round(t[1], 2), "، ".join(sorted(t[2]))]
                   for part, t in tot.items()), key=lambda x: -x[4])


def _customers_rows(details: list[dict[str, Any]]) -> list[list[Any]] | None:
    """جدول مشتریان (B2B/صادرات): [کد، مشتری، برند، فروش ناخالص، برگشت، تخفیف، فروش خالص]."""
    d = next((x for x in details if x.get("key") == "customers"), None)
    return d["table"]["rows"] if d and d.get("table") else None


def _brand_parts_payload(bp: dict[str, dict[str, list[float]]]) -> dict[str, list[list[Any]]]:
    """ریز کالاهای هر برند برای پنجره جزئیات سلول‌های جدول: [کد، نام، گروه کالا، تعداد خالص، بهای تمام شده (م.ر)]."""
    names = _part_names()
    return {br: sorted(([part, names.get(part, ""), _group_of(part), round(v[0]), round(v[1], 2)]
                        for part, v in parts.items() if v[0] or v[1]), key=lambda x: -x[4])
            for br, parts in bp.items()}


def _run(job_key: str, key: str, p: dict[str, Any]):
    job = _jobs[job_key]
    try:
        _results[job_key] = (time.time(), _build(key, p))
        job.update(state="done", message="")
    except Exception as exc:  # noqa: BLE001
        job.update(state="error", message=f"{type(exc).__name__}: {str(exc)[:300]}")


def load(key: str, period: str | None = None, refresh: bool = False) -> dict[str, Any]:
    """P&L لایو یک کانال؛ اولین بار (یا پس از ۱۰ دقیقه) در پس‌زمینه از SQL خوانده می‌شود."""
    if key not in pnl_service.SOURCES:
        raise KeyError(key)
    p = _period(period)
    job_key = f"{key}:{p['key']}"
    hit = _results.get(job_key)
    if hit and not refresh and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    with _lock:
        job = _jobs.get(job_key)
        if not job or job.get("state") != "running":
            job = _jobs[job_key] = {"state": "running", "message": "خواندن از SQL", "started": time.time()}
            threading.Thread(target=_run, args=(job_key, key, p), daemon=True).start()
    if job.get("state") == "error" and not hit:
        return {"key": key, "status": "error", "message": job["message"], "live": True, "period": p}
    if hit:   # نسخه قبلی تا ساخت نسخه تازه
        return {**hit[1], "status": "ready", "refreshing": True}
    return {"key": key, "status": "building", "live": True, "period": p, "message": job.get("message"),
            "elapsed": round(time.time() - job.get("started", time.time()))}
