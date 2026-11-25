"""Promotion data from KDB (read-only) and the free-market dollar rate.

  kdb_formulas.csv            promotion definitions (tblFormulaF): id, name, start/end date, type fields
  kdb_formula_goods.csv       products named in each promotion with its rule (min amount, discount %, bonus)
  kdb_promo_lines_monthly.csv per Persian month x product x promotion: discounted invoice lines, units, gross,
                              discount amount, units on 100%-discount lines (free goods), average discount %
                              (tblFactorfDiscount joined to the invoice line it belongs to)
  usd_daily.csv               free-market USD price per day (tgju.org public API), rial
Run: py -3 pull_promos.py [kdb] [usd]
"""
import json
import re
import sys
import urllib.request

import pandas as pd

import pull_data as PD

OUT = PD.OUT

FORMULAS = """
SELECT f.ID AS formula, f.Code, f.Name, f.Status, f.DateStart, f.DateEnd, f.Type, f.CalcMethod, f.Kind, f.Unit,
       f.MaxBonus, f.FormulaTypeRef, f.DiscountRef, f.Multiply, f.Description
FROM dbo.tblFormulaF f
"""
FORMULA_GOODS = """
SELECT l.FormulaRef AS formula, CAST(g.Code AS nvarchar(50)) AS code, l.Amount, l.Discount, l.Bonus, l.BonusNew,
       l.NewPrice, l.MinAmount, l.ConstDiscount
FROM dbo.tblFormulaFLinesGoods l JOIN dbo.tblGoods g ON g.ID = l.GoodsRef
"""
PROMO_LINES = """
SELECT LEFT(c.PersianDate, 7) AS pm, CAST(v.GoodsCode AS nvarchar(50)) AS code, d.FormulaRef AS formula, d.DiscountRef AS dtype,
       COUNT(*) AS lines, COUNT(DISTINCT d.FactorRef) AS invoices, SUM(v.TotalT) AS units, SUM(v.SumPrice) AS gross,
       SUM(d.Price) AS discount, SUM(CASE WHEN d.Per >= 99.9 THEN v.TotalT ELSE 0 END) AS free_units,
       SUM(d.Per * v.TotalT) / NULLIF(SUM(v.TotalT), 0) AS avg_per
FROM dbo.tblFactorfDiscount d
JOIN dbo.vwFactorFLinesFull v ON v.FactorRef = d.FactorRef AND v.Row = d.RowRef
JOIN dbo.tblCalendar c ON c.GregorianDate = v.DateE
WHERE v.DateE >= '2022-03-21'
GROUP BY LEFT(c.PersianDate, 7), CAST(v.GoodsCode AS nvarchar(50)), d.FormulaRef, d.DiscountRef
"""


def kdb():
    with PD.kdb() as cn:
        f = PD.df(cn, FORMULAS)
        g = PD.df(cn, FORMULA_GOODS)
        f.to_csv(OUT / "kdb_formulas.csv", index=False, encoding="utf-8-sig")
        g.to_csv(OUT / "kdb_formula_goods.csv", index=False, encoding="utf-8-sig")
        print("formulas", len(f), "| formula goods", len(g), flush=True)
        for t in ("tblAccDiscount", "tblFormulaType", "tblFormulaKind"):
            x = PD.df(cn, f"SELECT * FROM dbo.{t}").drop(columns=["RowVer"], errors="ignore")
            x.to_csv(OUT / f"kdb_{t}.csv", index=False, encoding="utf-8-sig")
        p = PD.df(cn, PROMO_LINES)
    p.to_csv(OUT / "kdb_promo_lines_monthly.csv", index=False, encoding="utf-8-sig")
    print("promo line rows", len(p), "| months", p.pm.min(), p.pm.max(), "| with formula", int((p.formula.fillna(0) > 0).sum()))


def usd():
    rows, start = [], 0
    while True:
        url = ("https://api.tgju.org/v1/market/indicator/summary-table-data/price_dollar_rl"
               f"?lang=fa&order_dir=asc&start={start}&length=1000")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
        for r in d["data"]:
            rows.append({"date": r[6].replace("/", "-"), "pdate": r[7], "close": float(re.sub(r"[^\d.]", "", r[3]))})
        start += 1000
        if start >= int(d["recordsTotal"]) or not d["data"]:
            break
    u = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
    u.to_csv(OUT / "usd_daily.csv", index=False, encoding="utf-8-sig")
    print("usd rows", len(u), u.date.min(), u.date.max(), "last", u.close.iloc[-1])


if __name__ == "__main__":
    what = sys.argv[1:] or ["kdb", "usd"]
    if "usd" in what:
        usd()
    if "kdb" in what:
        kdb()
