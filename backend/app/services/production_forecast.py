"""Run the isolated forecast process and serve its last published snapshots."""
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock, Thread
from zoneinfo import ZoneInfo

from app.core.config import BACKEND_DIR, settings

PROJECT = BACKEND_DIR.parent
LOG = logging.getLogger(__name__)
LOCKS = {"refresh": Lock(), "market": Lock()}
_CACHE = {}
_EFFECTIVE_CACHE = {}
_CACHE_LOCK = Lock()
_USD_CACHE = {"fetched_at": 0.0, "data": None}
_USD_LOCK = Lock()
TEHRAN = ZoneInfo("Asia/Tehran")
TGJU_LIVE_URL = "https://call.tgju.org/ajax.json"
DEFAULT_DATA = BACKEND_DIR / "data" / "production_forecast"


def data_root():
    return Path(settings.forecast_data_dir).resolve() if settings.forecast_data_dir else DEFAULT_DATA


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return 0


def _read(path, timestamp):
    with _CACHE_LOCK:
        cached = _CACHE.get(path)
        if cached and cached[0] == timestamp:
            return cached[1]
    loaded = json.loads(path.read_text(encoding="utf-8"))
    with _CACHE_LOCK:
        _CACHE[path] = (timestamp, loaded)
    return loaded


def write_snapshot(name: str, payload: dict):
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.json"
    tmp_name = None
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as stream:
        tmp_name = stream.name
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    try:
        os.replace(tmp_name, path)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)


def get_overrides() -> dict:
    return snapshot("distributor_overrides", {"overrides": {}})


def set_override(key: str, distributor: str, brand: str, months_map: dict[str, float], note: str = "", user: str = "") -> dict:
    data = get_overrides()
    overrides = dict(data.get("overrides", {}))
    clean_months = {str(m): max(0.0, float(v)) for m, v in months_map.items()}
    entry = {
        "key": key,
        "distributor": distributor,
        "brand": brand,
        "months": clean_months,
        "note": note.strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user,
    }
    overrides[key] = entry
    write_snapshot("distributor_overrides", {"overrides": overrides})
    return entry


def delete_override(key: str) -> bool:
    data = get_overrides()
    overrides = dict(data.get("overrides", {}))
    if key not in overrides:
        return False
    overrides.pop(key)
    write_snapshot("distributor_overrides", {"overrides": overrides})
    return True


def get_events() -> dict:
    data = snapshot("planned_events", {"events": []})
    events = sorted(data.get("events", []), key=lambda item: (item.get("month") or "", item.get("created_at") or ""))
    return {"events": events}


def add_event(event: dict) -> dict:
    data = get_events()
    events = list(data.get("events", []))
    events.append(event)
    events.sort(key=lambda item: (item.get("month") or "", item.get("created_at") or ""))
    write_snapshot("planned_events", {"events": events})
    return event


def delete_event(event_id: str) -> bool:
    data = get_events()
    events = list(data.get("events", []))
    kept = [item for item in events if item.get("id") != event_id]
    if len(kept) == len(events):
        return False
    write_snapshot("planned_events", {"events": kept})
    return True


def effective_plan(plan: dict) -> dict:
    """Apply active BI distributor overrides and planned events cleanly onto a copy of plan."""
    root = data_root()
    months = sorted(plan["overview"]["months"])
    cache_key = (
        str(root),
        _mtime(root / "plan.json"),
        _mtime(root / "distributors.json"),
        _mtime(root / "distributor_overrides.json"),
        _mtime(root / "planned_events.json"),
    )
    with _CACHE_LOCK:
        cached = _EFFECTIVE_CACHE.get(cache_key)
        if cached is not None:
            return cached

    overrides = get_overrides().get("overrides", {})
    events = get_events().get("events", [])
    active_events = [
        ev for ev in events
        if ev.get("apply_to_forecast") and float(ev.get("expected_lift_pct") or 0.0) != 0.0 and ev.get("month") in months
    ]
    if not overrides and not active_events:
        return plan

    dist_doc = snapshot("distributors", {"rows": []})
    dist_by_key = {row["key"]: row for row in dist_doc.get("rows", [])}
    sku_b2b_delta = {}
    override_delta_units = 0.0
    matched_overrides = 0
    for key, ov in overrides.items():
        dist_row = dist_by_key.get(key)
        if not dist_row or not dist_row.get("sku_basket"):
            continue
        basket = dist_row["sku_basket"]
        base_fc = dist_row.get("forecast", {})
        row_has_delta = False
        for m, target_val in ov.get("months", {}).items():
            if m not in months:
                continue
            delta = float(target_val) - float(base_fc.get(m, 0.0) or 0.0)
            if abs(delta) > 1e-6:
                row_has_delta = True
            override_delta_units += delta
            for item in basket:
                code = item["code"]
                sku_b2b_delta[(code, m)] = sku_b2b_delta.get((code, m), 0.0) + delta * float(item["share"])
        if row_has_delta:
            matched_overrides += 1

    new_products = []
    tot_h = 0.0
    tot_b = 0.0
    tot_need = 0.0
    prod_skus = 0
    rev_skus = 0
    monthly_h = {m: 0.0 for m in months}
    monthly_b = {m: 0.0 for m in months}

    for product in plan["products"]:
        row = dict(product)
        if row.get("has_forecast"):
            brand = str(row.get("brand") or "").strip().lower()
            category = str(row.get("category") or "").strip().lower()
            code = row["code"]
            h_sum = 0.0
            b_sum = 0.0
            for m in months:
                hv = float(row.get(f"hybrid_{m}", 0.0) or 0.0)
                bv = max(0.0, float(row.get(f"b2b_{m}", 0.0) or 0.0) + sku_b2b_delta.get((code, m), 0.0))
                for ev in active_events:
                    if ev["month"] != m:
                        continue
                    scope = str(ev.get("scope") or "").strip().lower()
                    if scope not in ("", "همه", "all", "*") and scope not in (brand, category):
                        continue
                    mult = max(0.0, 1.0 + float(ev["expected_lift_pct"]) / 100.0)
                    ch = ev.get("channel", "all")
                    if ch in ("all", "hybrid"):
                        hv *= mult
                    if ch in ("all", "b2b"):
                        bv *= mult
                row[f"hybrid_{m}"] = hv
                row[f"b2b_{m}"] = bv
                h_sum += hv
                b_sum += bv
                monthly_h[m] += hv
                monthly_b[m] += bv
            row["hybrid_3m"] = h_sum
            row["b2b_3m"] = b_sum
            row["demand_3m"] = h_sum + b_sum
            inv_tot = float(row.get("factory_stock_1_4") or 0.0) + float(row.get("branch_stock") or 0.0)
            need = 0.0 if row.get("inactive") else float(round(max(0.0, row["demand_3m"] + float(row.get("safety") or 0.0) - inv_tot)))
            row["production_need"] = need
        tot_h += float(row.get("hybrid_3m") or 0.0)
        tot_b += float(row.get("b2b_3m") or 0.0)
        tot_need += float(row.get("production_need") or 0.0)
        if (row.get("production_need") or 0.0) > 0:
            prod_skus += 1
            if row.get("review"):
                rev_skus += 1
        new_products.append(row)

    new_overview = {
        **plan["overview"],
        "totals": {
            **plan["overview"]["totals"],
            "hybrid_3m": tot_h,
            "b2b_3m": tot_b,
            "demand_3m": tot_h + tot_b,
            "production_need": tot_need,
        },
        "production_skus": prod_skus,
        "review_skus": rev_skus,
        "monthly": [{"month": m, "hybrid": monthly_h[m], "b2b": monthly_b[m]} for m in months],
        "adjustments": {
            "override_count": len(overrides),
            "matched_overrides": matched_overrides,
            "override_delta_units": round(override_delta_units, 1),
            "applied_events_count": len(active_events),
        },
    }
    adjusted = {**plan, "overview": new_overview, "products": new_products}
    with _CACHE_LOCK:
        _EFFECTIVE_CACHE.clear()
        _EFFECTIVE_CACHE[cache_key] = adjusted
    return adjusted


def snapshot(name, default=None):
    path = data_root() / f"{name}.json"
    try:
        return _read(path, path.stat().st_mtime_ns)
    except FileNotFoundError:
        return default


def _parse_usd_number(value) -> float | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(value))
    if not cleaned:
        return None
    try:
        num = float(cleaned)
    except ValueError:
        return None
    return num if num == num else None


def live_usd(force: bool = False, ttl: float = 60.0) -> dict | None:
    """Fetch the real-time free-market USD rate from TGJU with a short TTL cache."""
    now_mono = time.monotonic()
    with _USD_LOCK:
        cached_data = _USD_CACHE["data"]
        cached_at = _USD_CACHE["fetched_at"]
    if not force and cached_data is not None and (now_mono - cached_at) < ttl:
        return cached_data

    try:
        req = urllib.request.Request(
            TGJU_LIVE_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        item = (payload.get("current") or {}).get("price_dollar_rl") or {}
        rial = _parse_usd_number(item.get("p"))
        if not rial or rial <= 0:
            raise ValueError("Missing or non-positive USD quote")
        high_rial = _parse_usd_number(item.get("h"))
        low_rial = _parse_usd_number(item.get("l"))
        raw_diff = _parse_usd_number(item.get("d")) or 0.0
        raw_pct = _parse_usd_number(item.get("dp")) or 0.0
        dt = str(item.get("dt") or "").strip().lower()
        sign = -1.0 if dt == "low" else 1.0
        ts = str(item.get("ts") or "").strip()
        if ts:
            updated_at = ts.replace(" ", "T") + "+03:30"
            date_str = ts[:10]
        else:
            now_ir = datetime.now(TEHRAN)
            updated_at = now_ir.isoformat(timespec="seconds")
            date_str = now_ir.date().isoformat()
        quote = {
            "rial": rial,
            "high_rial": high_rial,
            "low_rial": low_rial,
            "change_rial": sign * abs(raw_diff),
            "change_pct": round(sign * abs(raw_pct), 2),
            "direction": dt or "flat",
            "date": date_str,
            "updated_at": updated_at,
            "time_fa": str(item.get("t") or ""),
            "live": True,
            "source": "https://www.tgju.org/profile/price_dollar_rl",
        }
        with _USD_LOCK:
            _USD_CACHE["data"] = quote
            _USD_CACHE["fetched_at"] = time.monotonic()
        return quote
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        LOG.warning("Live USD fetch failed: %s: %s", type(error).__name__, error)
        if cached_data is not None:
            is_fresh = (time.monotonic() - cached_at) < 600.0
            return {**cached_data, "live": is_fresh}
        return None


def external_with_live_usd(force: bool = False) -> dict:
    """Merge the cached 12-month external snapshot with the live intraday TGJU USD rate."""
    base = snapshot("external", {}) or {}
    saved_usd = base.get("usd") if isinstance(base.get("usd"), dict) else {}
    quote = live_usd(force=force)
    if quote is None:
        return base
    merged_usd = {
        **saved_usd,
        **quote,
        "trend": saved_usd.get("trend", []),
    }
    return {**base, "usd": merged_usd}


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


def _decode_output(data):
    if not data:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _format_process_error(header, stdout, stderr):
    err = _decode_output(stderr).strip()
    out = _decode_output(stdout).strip()
    detail = f"{header}\n--- stderr ---\n{err[-6000:]}\n--- stdout ---\n{out[-2000:]}"
    excerpt = (err or out)[-500:].replace("\n", " | ")
    return detail, excerpt


def _write_error_log(root, mode, detail):
    path = root / f"{mode}_last_error.log"
    stamp_utc = datetime.now(timezone.utc).isoformat()
    tmp_name = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            tmp_name = stream.name
            stream.write(f"[{stamp_utc}] {detail.strip()}\n")
        os.replace(tmp_name, path)
    except OSError:
        LOG.exception("Could not write production forecast error log")
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)


def _stamp_failed(mode):
    try:
        stamp(mode, "failed", "به‌روزرسانی کامل نشد. آخرین دادهٔ معتبر نمایش داده می‌شود.")
    except OSError:
        LOG.exception("Could not publish production forecast status")


def execute(mode):
    root = data_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        stamp(mode, "running")
        package = PROJECT / "forecast"
        venv = PROJECT / ".venv-runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        python = settings.forecast_python or (str(venv) if venv.is_file() else sys.executable)
        runner = package / "scripts" / "refresh_production_dashboard.py"
        env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "2"}
        result = subprocess.run(
            [python, "-X", "utf8", "-B", str(runner), mode, "--data-root", str(root)],
            cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=1800 if mode == "market" else 900,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            detail, excerpt = _format_process_error(f"returncode={result.returncode}", result.stdout, result.stderr)
            _write_error_log(root, mode, detail)
            LOG.warning("Production forecast %s failed (rc=%s): %s", mode, result.returncode, excerpt)
            _stamp_failed(mode)
            return
        stamp(mode, "ok")
    except subprocess.TimeoutExpired as error:
        detail, excerpt = _format_process_error(f"timeout={error.timeout}s", error.stdout, error.stderr)
        _write_error_log(root, mode, detail)
        LOG.warning("Production forecast %s timed out after %ss: %s", mode, error.timeout, excerpt)
        _stamp_failed(mode)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        _write_error_log(root, mode, f"{type(error).__name__}: {error}")
        LOG.warning("Production forecast %s failed: %s: %s", mode, type(error).__name__, error)
        _stamp_failed(mode)
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


HORIZONS = (1, 2, 3, 4, 6, 12)


def _monthly_schedule(product, months):
    """Allocate a single SKU's production across published months."""
    inventory = product["factory_stock_1_4"] + product["branch_stock"]
    inactive = bool(product.get("inactive")) or not product.get("has_forecast")
    cumulative = 0.0
    produced = 0
    rows = []
    for index, month in enumerate(months, start=1):
        hybrid = float(product.get(f"hybrid_{month}", 0) or 0)
        b2b = float(product.get(f"b2b_{month}", 0) or 0)
        monthly = hybrid + b2b
        cumulative += monthly
        safety = product["safety_3"] * (index / 3) ** 0.5 if product.get("has_forecast") else 0.0
        target = 0 if inactive else round(max(0.0, cumulative + safety - inventory))
        addition = max(0, target - produced)
        produced += addition
        rows.append({
            "month": month, "hybrid": hybrid, "b2b": b2b, "total": monthly,
            "cumulative_demand": cumulative, "safety": safety,
            "cumulative_need": produced, "monthly_need": addition,
        })
    return rows


def product_horizons(product, months):
    """Compute demand, safety stock, and production need for 1, 2, 3, 4, 6, and 12 months."""
    schedule = _monthly_schedule(product, months)
    inventory = product["factory_stock_1_4"] + product["branch_stock"]
    inactive = bool(product.get("inactive")) or not product.get("has_forecast")
    published_months = len(months)
    published_demand = schedule[-1]["cumulative_demand"] if schedule else 0.0
    out = {"monthly_breakdown": schedule}
    for h in HORIZONS:
        if not product.get("has_forecast"):
            demand = 0.0
            safety = 0.0
        elif h <= published_months:
            demand = schedule[h - 1]["cumulative_demand"]
            safety = schedule[h - 1]["safety"]
        else:
            demand = published_demand * (h / published_months) if published_months else 0.0
            safety = product["safety_3"] * (h / 3) ** 0.5
        need = 0 if inactive else round(max(0.0, demand + safety - inventory))
        out[f"demand_{h}"] = demand
        out[f"safety_{h}"] = safety
        out[f"production_need_{h}"] = need
    return out


def overview_horizons(plan):
    """Aggregate demand, safety stock, and production need across 1, 2, 3, 4, 6, and 12 months."""
    months = sorted(plan["overview"]["months"])
    by_h = {
        str(h): {"horizon": h, "need": 0, "skus": 0, "demand": 0.0, "safety": 0.0, "estimated": h > len(months)}
        for h in HORIZONS
    }
    for product in plan["products"]:
        hz = product_horizons(product, months)
        for h in HORIZONS:
            bucket = by_h[str(h)]
            need = hz[f"production_need_{h}"]
            bucket["need"] += need
            bucket["skus"] += int(need > 0)
            bucket["demand"] += hz[f"demand_{h}"]
            bucket["safety"] += hz[f"safety_{h}"]
    return {
        "horizons": list(HORIZONS),
        "production_by_horizon": by_h,
        "safety_totals": {f"safety_{h}": by_h[str(h)]["safety"] for h in HORIZONS},
    }


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
    covered = set(month for month in months if bucket(month) == selected)
    categories = {}
    for product in plan["products"]:
        if not product.get("has_forecast"):
            continue
        name = product.get("category") or "دسته‌بندی نشده"
        row = categories.setdefault(name, {"category": name, "products": 0, "production_skus": 0,
                                          "production_need": 0, "demand": 0.0})
        needed = 0
        demand = 0.0
        for item in _monthly_schedule(product, months):
            if item["month"] in covered:
                needed += item["monthly_need"]
                demand += item["total"]
        row["products"] += 1
        row["production_skus"] += int(needed > 0)
        row["production_need"] += needed
        row["demand"] += demand
    rows = sorted(categories.values(), key=lambda row: row["production_need"], reverse=True)
    expected = {"monthly": 1, "quarterly": 3, "annual": 12}[period]
    return {"period": period, "selected": selected, "periods": periods, "months": [m for m in months if m in covered],
            "covered_months": len(covered), "expected_months": expected,
            "complete": len(covered) == expected, "rows": rows,
            "total_production": sum(row["production_need"] for row in rows)}
