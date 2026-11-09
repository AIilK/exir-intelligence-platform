"""Extra inputs for the improvement round (read-only):
  kdb_stock_moves_monthly.csv  per branch x product x Persian month: signed stock movement, opening entries, sales out
  kdb_discount_monthly.csv     per product x Persian month: gross amount and discounts (promotion signal)
  rk_invoices_daily.csv        Rahkaran factory invoices per customer x product x day (external customers)
"""
from pathlib import Path

import pull_data as PD

OUT = PD.OUT

STOCK_MOVES = """
SELECT l.BranchRef AS bid, CAST(g.Code AS nvarchar(50)) AS code, LEFT(c.PersianDate, 7) AS pm, l.FiscalYear AS fy,
       SUM(CASE WHEN l.Kind IN ('K', 'B', 'I', 'M') THEN l.TotalT ELSE -l.TotalT END) AS net_move,
       SUM(CASE WHEN l.Kind = 'M' THEN l.TotalT ELSE 0 END) AS opening,
       SUM(CASE WHEN l.Kind = 'F' THEN l.TotalT ELSE 0 END) AS sales_out
FROM dbo.vwStockLines l
JOIN dbo.tblGoods g ON g.ID = l.GoodsRef
JOIN dbo.tblCalendar c ON c.GregorianDate = l.DateE
GROUP BY l.BranchRef, CAST(g.Code AS nvarchar(50)), LEFT(c.PersianDate, 7), l.FiscalYear
"""

DISCOUNTS = """
SELECT LEFT(c.PersianDate, 7) AS pm, CAST(v.GoodsCode AS nvarchar(50)) AS code,
       SUM(CASE WHEN v.FactorType = N'فروش' THEN v.SumPrice ELSE 0 END) AS gross,
       SUM(CASE WHEN v.FactorType = N'فروش' THEN v.Discount + v.CashDiscount ELSE 0 END) AS discount,
       SUM(CASE WHEN v.FactorType = N'فروش' THEN v.TotalT ELSE 0 END) AS qty
FROM dbo.vwFactorFBLinesFull v
JOIN dbo.tblCalendar c ON c.GregorianDate = v.DateE
GROUP BY LEFT(c.PersianDate, 7), CAST(v.GoodsCode AS nvarchar(50))
"""

RK_INVOICES = """
SELECT p.FullName AS cust, pr.Number AS code, CONVERT(char(10), i.Date, 23) AS d, SUM(ii.MajorUnitQuantity) AS qty
FROM SLS3.InvoiceItem ii
JOIN SLS3.Invoice i ON i.InvoiceID = ii.InvoiceRef
JOIN SLS3.Customer cu ON cu.CustomerID = i.CustomerRef
JOIN GNR3.Party p ON p.PartyID = cu.PartyRef
JOIN SLS3.Product pr ON pr.ProductID = ii.ProductRef
GROUP BY p.FullName, pr.Number, CONVERT(char(10), i.Date, 23)
"""


def main():
    with PD.kdb() as cn:
        moves = PD.df(cn, STOCK_MOVES)
        disc = PD.df(cn, DISCOUNTS)
    moves.to_csv(OUT / "kdb_stock_moves_monthly.csv", index=False, encoding="utf-8-sig")
    disc.to_csv(OUT / "kdb_discount_monthly.csv", index=False, encoding="utf-8-sig")
    print("KDB: stock move rows", len(moves), "| discount rows", len(disc), flush=True)
    with PD.rahkaran() as cn:
        inv = PD.df(cn, RK_INVOICES)
    inv.to_csv(OUT / "rk_invoices_daily.csv", index=False, encoding="utf-8-sig")
    print("Rahkaran: invoice rows", len(inv), "| customers", inv["cust"].nunique())


if __name__ == "__main__":
    main()
