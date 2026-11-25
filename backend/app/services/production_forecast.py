"""Run the isolated forecast process and serve its last published snapshots."""
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock, Thread

from app.core.config import BACKEND_DIR, settings

PROJECT = BACKEND_DIR.parent
LOG = logging.getLogger(__name__)
LOCKS = {"refresh": Lock(), "market": Lock()}
DEFAULT_DATA = BACKEND_DIR / "data" / "production_forecast"


def data_root():
    return Path(settings.forecast_data_dir).resolve() if settings.forecast_data_dir else DEFAULT_DATA


@lru_cache(maxsize=8)
def _read(path, timestamp):
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot(name, default=None):
    path = data_root() / f"{name}.json"
    try:
        return _read(path, path.stat().st_mtime_ns)
    except FileNotFoundError:
        return default


def stamp(mode, state, message=None):
    path = data_root() / f"{mode}_status.json"
    record = {"state": state, "at": datetime.now(timezone.utc).isoformat()}
    if message:
        record["message"] = message
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(record, stream, ensure_ascii=False)
    try:
        os.replace(stream.name, path)
    finally:
        Path(stream.name).unlink(missing_ok=True)


def execute(mode):
    try:
        root = data_root()
        root.mkdir(parents=True, exist_ok=True)
        stamp(mode, "running")
        package = PROJECT / "forecast"
        venv = PROJECT / ".venv-runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        python = settings.forecast_python or (str(venv) if venv.is_file() else sys.executable)
        runner = package / "scripts" / "refresh_production_dashboard.py"
        env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "2"}
        result = subprocess.run([python, "-X", "utf8", "-B", str(runner), mode, "--data-root", str(root)],
                                cwd=PROJECT, env=env, capture_output=True, timeout=900,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError(f"forecast process returned {result.returncode}")
        stamp(mode, "ok")
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        LOG.warning("Production forecast %s failed: %s", mode, type(error).__name__)
        try:
            stamp(mode, "failed", "به‌روزرسانی کامل نشد. آخرین دادهٔ معتبر نمایش داده می‌شود.")
        except OSError:
            LOG.exception("Could not publish production forecast status")
    finally:
        LOCKS[mode].release()


def launch(mode, *, background):
    if not LOCKS[mode].acquire(blocking=False):
        return False
    if background:
        Thread(target=execute, args=(mode,), name=f"forecast-{mode}", daemon=True).start()
    else:
        execute(mode)
    return True


def run_scheduled_plan():
    launch("refresh", background=False)


def run_scheduled_market():
    launch("market", background=False)


def status(mode):
    if LOCKS[mode].locked():
        return {"state": "running"}
    saved = snapshot(f"{mode}_status", {"state": "waiting"})
    if saved.get("state") == "running":
        return {**saved, "state": "failed", "message": "اجرای قبلی متوقف شده است. به‌روزرسانی را دوباره اجرا کنید."}
    return saved


def category_production(plan, period, selected):
    """Allocate each SKU's production over published months, then aggregate categories."""
    months = sorted(plan["overview"]["months"])

    def bucket(month):
        year, number = month.split("/")
        if period == "monthly":
            return month
        if period == "quarterly":
            return f"{year}-Q{(int(number) - 1) // 3 + 1}"
        return year

    periods = list(dict.fromkeys(bucket(month) for month in months))
    selected = selected or periods[0]
    if selected not in periods:
        raise ValueError("Unknown production period")
    covered = [month for month in months if bucket(month) == selected]
    categories = {}
    for product in plan["products"]:
        if not product.get("has_forecast"):
            continue
        name = product.get("category") or "دسته‌بندی نشده"
        row = categories.setdefault(name, {"category": name, "products": 0, "production_skus": 0,
                                          "production_need": 0, "demand": 0.0})
        cumulative = 0.0
        produced = 0
        needed = 0
        demand = 0.0
        inventory = product["factory_stock_1_4"] + product["branch_stock"]
        for index, month in enumerate(months, start=1):
            monthly = product.get(f"hybrid_{month}", 0) + product.get(f"b2b_{month}", 0)
            cumulative += monthly
            safety = product["safety_3"] * (index / 3) ** 0.5
            target = 0 if product.get("inactive") else round(max(0, cumulative + safety - inventory))
            addition = max(0, target - produced)
            produced += addition
            if month in covered:
                needed += addition
                demand += monthly
        row["products"] += 1
        row["production_skus"] += int(needed > 0)
        row["production_need"] += needed
        row["demand"] += demand
    rows = sorted(categories.values(), key=lambda row: row["production_need"], reverse=True)
    expected = {"monthly": 1, "quarterly": 3, "annual": 12}[period]
    return {"period": period, "selected": selected, "periods": periods, "months": covered,
            "covered_months": len(covered), "expected_months": expected,
            "complete": len(covered) == expected, "rows": rows,
            "total_production": sum(row["production_need"] for row in rows)}
