"""Pull all forecasting inputs from KDB (Karamad) and Rahkaran (factory). Read-only.

Credentials from backend/.env, backend/env, or the environment:
  KDB       -> backend/.env  (KARAMAD_SQLSERVER_*)
  Rahkaran  -> backend/.env  (RAHKARAN_SQLSERVER_*), or environment variables RK_SERVER / RK_DB / RK_USER / RK_PWD
Outputs go to forecast/data/*.csv. Nothing is written to either database.
"""
import os
import sys
from pathlib import Path

import pandas as pd
import pyodbc

ROOT = Path(__file__).resolve().parents[2]          # project root
BACKEND_DIR = next(
    (path / "backend" for path in (ROOT, ROOT.parent) if (path / "backend" / "app").is_dir()),
    ROOT / "backend",
)
OUT = ROOT / "forecast" / "data"
sys.path.insert(0, str(BACKEND_DIR.parent / "sales" / "backend"))  # reuse the SQL text the app already uses
import rahkaran as RK  # noqa: E402  (only its SQL constants are used)

def read_env(prefix):
    env = {}
    for filename in ("env", ".env"):
        path = BACKEND_DIR / filename
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                env[key.strip()] = value.strip().strip('"').strip("'")
    env.update(os.environ)
    return {k[len(prefix):]: v for k, v in env.items() if k.startswith(prefix)}


def conn_string(d, driver="ODBC Driver 18 for SQL Server"):
    return (f"DRIVER={{{d.get('DRIVER', driver)}}};SERVER={d['SERVER']};DATABASE={d['DATABASE']};"
            f"UID={d['USERNAME']};PWD={{{d['PASSWORD']}}};Encrypt=yes;TrustServerCertificate=yes;"
            "ApplicationIntent=ReadOnly;")


def kdb():
    d = read_env("KARAMAD_SQLSERVER_")
    if not all(d.get(k) for k in ("SERVER", "DATABASE", "USERNAME", "PASSWORD")):
        raise SystemExit("Karamad settings missing (backend/.env, backend/env, or KARAMAD_SQLSERVER_* variables)")
    return pyodbc.connect(conn_string(d), timeout=30, readonly=True)


def rahkaran():
    d = read_env("RAHKARAN_SQLSERVER_") or read_env("SQLSERVER_")
    if not d.get("SERVER"):
        d = {"SERVER": os.environ.get("RK_SERVER", ""), "DATABASE": os.environ.get("RK_DB", ""),
             "USERNAME": os.environ.get("RK_USER", ""), "PASSWORD": os.environ.get("RK_PWD", "")}
    if not all(d.get(k) for k in ("SERVER", "DATABASE", "USERNAME", "PASSWORD")):
        raise SystemExit("Rahkaran settings missing (backend/.env RAHKARAN_SQLSERVER_*, SQLSERVER_*, or RK_* env vars)")
    return pyodbc.connect(conn_string(d), timeout=30, readonly=True)


def df(cn, sql, params=()):
    cur = cn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return pd.DataFrame.from_records(cur.fetchall(), columns=cols)


SALES_MONTHLY = """
SELECT LEFT(c.PersianDate, 7) AS pm, CAST(v.GoodsCode AS nvarchar(50)) AS code,
       SUM(v.TotalT) AS net_qty,
       SUM(CASE WHEN v.FactorType = N'فروش' THEN v.TotalT ELSE 0 END) AS sales_qty,
       SUM(CASE WHEN v.FactorType <> N'فروش' THEN -v.TotalT ELSE 0 END) AS return_qty,
       SUM(v.PriceP) AS revenue,
       COUNT(DISTINCT v.BranchRef) AS branches,
       COUNT(DISTINCT v.CustomerRef) AS customers
FROM dbo.vwFactorFBLinesFull v
JOIN dbo.tblCalendar c ON c.GregorianDate = v.DateE
GROUP BY LEFT(c.PersianDate, 7), CAST(v.GoodsCode AS nvarchar(50))
"""

BRANCH_REQUESTS_OPEN = """
SELECT CAST(v.GoodsCode AS nvarchar(50)) AS code, SUM(v.TotalT) AS open_req_qty
FROM dbo.vwFactorDLinesFull v
WHERE v.FactorStatus = 0
GROUP BY CAST(v.GoodsCode AS nvarchar(50))
"""

BRANCH_STOCK = """
SELECT CAST(s.GoodsCode AS nvarchar(50)) AS code, s.BranchName AS branch, SUM(s.TotalT) AS qty
FROM dbo.vwStockFull s
WHERE s.FiscalYear = (SELECT MAX(FiscalYear) FROM dbo.vwStockFull)
GROUP BY CAST(s.GoodsCode AS nvarchar(50)), s.BranchName
"""

GOODS = """
SELECT CAST(g.Code AS nvarchar(50)) AS code, g.Name AS name, g.Status AS active,
       b.Name AS brand, c.Name AS category, g.Unity AS unit
FROM dbo.tblGoods g
LEFT JOIN dbo.tblGoodsBrand b ON b.ID = g.BrandRef
LEFT JOIN dbo.tblGoodsCategory c ON c.ID = g.CategoryRef
"""

RK_PRODUCTION_DAILY = """
SELECT pt.Code AS code, CONVERT(char(10), iv.Date, 23) AS d, SUM(vi.MajorUnitQuantity) AS qty
FROM LGS3.InventoryVoucherItem vi
JOIN LGS3.InventoryVoucher iv ON iv.InventoryVoucherID = vi.InventoryVoucherRef
JOIN LGS3.InventoryVoucherSpecification sp ON sp.InventoryVoucherSpecificationID = iv.InventoryVoucherSpecificationRef
JOIN LGS3.Part pt ON pt.PartID = vi.PartRef
WHERE sp.Name = N'دریافت از تولید'
GROUP BY pt.Code, CONVERT(char(10), iv.Date, 23)
"""

RK_GOODS = """
SELECT CAST(pt.Code AS nvarchar(50)) AS code,
       LTRIM(RTRIM(ISNULL(pt.Name, N''))) AS name,
       CASE WHEN pt.State = 1 THEN 1 ELSE 0 END AS active,
       N'' AS brand,
       LTRIM(RTRIM(ISNULL(c.Name, N''))) AS category,
       N'' AS unit
FROM LGS3.Part pt
LEFT JOIN LGS3.Category c ON c.CategoryID = pt.CategoryRef
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with kdb() as cn:
        sales = df(cn, SALES_MONTHLY)
        req = df(cn, BRANCH_REQUESTS_OPEN)
        bstock = df(cn, BRANCH_STOCK)
        goods = df(cn, GOODS)
    sales.to_csv(OUT / "kdb_sales_monthly.csv", index=False, encoding="utf-8-sig")
    req.to_csv(OUT / "kdb_open_requests.csv", index=False, encoding="utf-8-sig")
    bstock.to_csv(OUT / "kdb_branch_stock.csv", index=False, encoding="utf-8-sig")
    goods.to_csv(OUT / "kdb_goods.csv", index=False, encoding="utf-8-sig")
    print("KDB: sales rows", len(sales), "| open requests", len(req), "| branch stock rows", len(bstock), "| goods", len(goods))

    with rahkaran() as cn:
        prod = df(cn, RK_PRODUCTION_DAILY)
        stock = df(cn, RK.STOCK_SQL)
        rk_goods = df(cn, RK_GOODS)
    prod.to_csv(OUT / "rk_production_daily.csv", index=False, encoding="utf-8-sig")
    stock.to_csv(OUT / "rk_factory_stock.csv", index=False, encoding="utf-8-sig")
    rk_goods.to_csv(OUT / "rk_goods.csv", index=False, encoding="utf-8-sig")
    print("Rahkaran: production rows", len(prod), "| factory stock rows", len(stock), "| goods", len(rk_goods))


if __name__ == "__main__":
    main()
