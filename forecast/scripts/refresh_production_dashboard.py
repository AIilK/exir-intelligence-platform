"""Build and refresh the production dashboard from read-only company and public market data."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import jdatetime
import pandas as pd
import pyodbc

import pull_data as PD
import pull_extra as PE
from accuracy_tracker import build_accuracy_history
from distributor_forecast import build_distributor_forecast
from production_dashboard_data import (
    TEHRAN, external, historical_prices, live_listings, model_file_name, publish_plan, write_json,
)

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
RETURNS = """
SELECT p.FullName AS cust, pr.Number AS code, CONVERT(char(10), r.Date, 23) AS d,
       r.Status AS status, SUM(ri.MajorUnitQuantity) AS qty
FROM SLS3.ReturnInvoiceItem ri JOIN SLS3.ReturnInvoice r ON r.ReturnInvoiceID = ri.ReturnInvoiceRef
JOIN SLS3.Customer c ON c.CustomerID = r.CustomerRef
JOIN GNR3.Party p ON p.PartyID = c.PartyRef
JOIN SLS3.Product pr ON pr.ProductID = ri.ProductRef
WHERE r.Status = 11
GROUP BY p.FullName, pr.Number, CONVERT(char(10), r.Date, 23), r.Status
"""


def now():
    return datetime.now(TEHRAN).isoformat(timespec="seconds")


def closed_month(today):
    """Close the last month on the third day of the following Persian month."""
    persian = jdatetime.date.fromgregorian(date=today)
    index = persian.year * 12 + persian.month - 1 - (1 if persian.day >= 3 else 2)
    year, month = divmod(index, 12)
    return f"{year:04d}/{month + 1:02d}"


def rahkaran():
    cfg = PD.read_env("RAHKARAN_SQLSERVER_") or PD.read_env("SQLSERVER_")
    if not all(cfg.get(key) for key in ("SERVER", "DATABASE", "USERNAME", "PASSWORD")):
        raise RuntimeError("Rahkaran settings are missing")
    return pyodbc.connect(PD.conn_string(cfg), timeout=15, readonly=True)


def pull(source, full):
    kdb = {"kdb_goods.csv": PD.GOODS, "kdb_branch_stock.csv": PD.BRANCH_STOCK}
    rk = {"rk_factory_stock.csv": PD.RK.STOCK_SQL, "rk_goods.csv": PD.RK_GOODS}
    if full:
        kdb.update({"kdb_sales_monthly.csv": PD.SALES_MONTHLY, "kdb_stock_moves_monthly.csv": PE.STOCK_MOVES,
                    "kdb_discount_monthly.csv": PE.DISCOUNTS})
        rk.update({"rk_production_daily.csv": PD.RK_PRODUCTION_DAILY, "rk_invoices_daily.csv": PE.RK_INVOICES,
                   "rk_returns_daily.csv": RETURNS})
    for connect, queries in ((PD.kdb, kdb), (rahkaran, rk)):
        with closing(connect()) as conn:
            conn.timeout = 150
            for filename, sql in queries.items():
                rows = PD.df(conn, sql)
                if rows.empty and filename != "rk_returns_daily.csv":
                    raise RuntimeError(f"Empty source: {filename}")
                rows.to_csv(source / filename, index=False, encoding="utf-8-sig")
                print(f"{filename}: {len(rows):,} rows", flush=True)


def put_model(root, closed, source):
    name = model_file_name(closed)
    target = root / name
    pending = target.with_suffix(".tmp")
    shutil.copyfile(source, pending)
    os.replace(pending, target)
    archive_dir = root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    arch_target = archive_dir / name
    arch_pending = arch_target.with_suffix(".tmp")
    shutil.copyfile(target, arch_pending)
    os.replace(arch_pending, arch_target)
    return target


def _publish_insights(sales_source, root, active_closed, *, goods_source=None):
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    months = sorted(plan["overview"]["months"])
    src = sales_source if (sales_source / "rk_invoices_daily.csv").is_file() else DATA
    gsrc = goods_source or sales_source
    lab_dir = HERE.parent / "lab"
    write_json(
        root / "distributors.json",
        build_distributor_forecast(src, months, active_closed, top_n=30, goods_source=gsrc),
    )
    write_json(
        root / "accuracy_history.json",
        build_accuracy_history(src, root, active_closed, lab_dir=lab_dir, goods_source=gsrc),
    )


def seed(args):
    if not all((args.source, args.model, args.closed_month, args.rivals)):
        raise ValueError("Seed requires --source, --model, --closed-month and --rivals")
    model = put_model(args.data_root, args.closed_month, args.model)
    for key, location in (("usd_daily.csv", DATA / "usd_daily.csv"),
                          ("promotion_calendar.csv", args.promotions)):
        if location and location.is_file():
            shutil.copyfile(location, args.data_root / key)
    market = historical_prices(args.rivals)
    cache = DATA / "rival_price_listings.csv"
    if cache.is_file():
        market["live_products"] = live_listings(cache, DATA / "price_sources.csv")
    write_json(args.data_root / "market.json", market)
    inventory_at = min(datetime.fromtimestamp((args.source / name).stat().st_mtime, TEHRAN)
                       for name in ("rk_factory_stock.csv", "kdb_branch_stock.csv")).isoformat(timespec="seconds")
    model_at = datetime.fromtimestamp(args.model.stat().st_mtime, TEHRAN).isoformat(timespec="seconds")
    publish_plan(model, args.source, args.data_root, args.closed_month, inventory_at, model_at=model_at)
    _publish_insights(args.source, args.data_root, args.closed_month)


def refresh(root):
    previous = root / "plan.json"
    overview = json.loads(previous.read_text(encoding="utf-8"))["overview"] if previous.is_file() else {}
    current = closed_month(datetime.now(TEHRAN).date())
    refit = current > overview.get("closed_month", "")
    active = current if refit else overview["closed_month"]
    with TemporaryDirectory(dir=root) as work:
        stage = Path(work)
        pull(stage, refit)
        model = root / model_file_name(active)
        model_at = overview.get("model_at")
        if refit:
            kdb_months = pd.read_csv(stage / "kdb_sales_monthly.csv", usecols=["pm"]).pm
            invoices = pd.read_csv(stage / "rk_invoices_daily.csv", usecols=["d"]).d
            last_invoice = jdatetime.date.fromgregorian(date=datetime.fromisoformat(str(invoices.max())).date())
            if active not in set(kdb_months) or f"{last_invoice.year:04d}/{last_invoice.month:02d}" < active:
                raise RuntimeError("The selected closed month is missing in a sales source")
            env = {**os.environ, "EXIR_FORECAST_SNAPSHOT": str(stage), "EXIR_FORECAST_LAST_CLOSED_MONTH": active}
            subprocess.run([sys.executable, "-X", "utf8", "-B", str(HERE / "run_hybrid_b2b_plan.py"),
                            "--output-dir", str(stage)], env=env, check=True, timeout=480)
            model = put_model(root, active, stage / "production_plan_hybrid_b2b.csv")
            model_at = now()
        publish_plan(model, stage, root, active, now(), model_at=model_at)
        _publish_insights(stage, root, active, goods_source=stage)


def markets(root):
    import pull_promos as macro
    import rival_prices as market

    done = []
    with TemporaryDirectory(dir=root) as work:
        stage = Path(work)
        market.LISTINGS = stage / "rival_price_listings.csv"
        macro.OUT = stage
        try:
            macro.usd()
            probe = stage / "usd_daily.csv"
            if not external(probe)["usd"]["date"]:
                raise ValueError("Empty USD data")
            previous = root / "usd_daily.csv"
            if not previous.exists() or external(probe)["usd"]["date"] >= external(previous)["usd"]["date"]:
                os.replace(probe, previous)
            done.append("usd")
        except (OSError, ValueError) as error:
            print(f"USD updates unavailable ({type(error).__name__})", flush=True)
        try:
            market.collect()
            product_rows = live_listings(market.LISTINGS, market.SOURCES)
            path = root / "market.json"
            saved = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            saved["live_products"] = product_rows
            saved["live_updated_at"] = now()
            write_json(path, saved)
            done.append("market")
        except (OSError, ValueError) as error:
            print(f"Market updates unavailable ({type(error).__name__})", flush=True)
    if not done:
        raise RuntimeError("All market sources failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seed", "refresh", "market"))
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--closed-month")
    parser.add_argument("--rivals", type=Path)
    parser.add_argument("--promotions", type=Path)
    args = parser.parse_args()
    args.data_root = args.data_root.resolve()
    args.data_root.mkdir(parents=True, exist_ok=True)
    if args.mode == "seed":
        seed(args)
    elif args.mode == "refresh":
        refresh(args.data_root)
    else:
        markets(args.data_root)
    if (args.data_root / "usd_daily.csv").is_file():
        write_json(args.data_root / "external.json", external(args.data_root / "usd_daily.csv",
                                                               args.data_root / "promotion_calendar.csv"))


if __name__ == "__main__":
    main()
