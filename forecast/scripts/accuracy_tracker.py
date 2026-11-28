"""Score archived monthly models against closed sales and summarize held-out accuracy."""
import json
from pathlib import Path

import jdatetime
import numpy as np
import pandas as pd

from channel_rules import channel_of, normalize
from production_dashboard_data import load_goods, read


def _mon(label: str) -> int:
    return int(label[:4]) * 12 + int(label[5:]) - 1


def _plabel(idx: int) -> str:
    y, m = divmod(int(idx), 12)
    return f"{y:04d}/{m + 1:02d}"


def _finite(val, default=None):
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    return f if np.isfinite(f) else default


def _metrics(pred: np.ndarray, act: np.ndarray) -> dict:
    p = np.clip(np.asarray(pred, dtype=np.float64), 0.0, None)
    a = np.clip(np.asarray(act, dtype=np.float64), 0.0, None)
    tot_a = float(a.sum())
    tot_p = float(p.sum())
    if tot_a <= 0:
        return {"forecast": round(tot_p, 1), "actual": 0.0, "wape": None, "tol_wape": None, "bias": None}
    err = np.abs(p - a)
    ok = np.where(a > 0, (p >= 0.95 * a) & (p <= 1.10 * a), p < 0.5)
    return {
        "forecast": round(tot_p, 1),
        "actual": round(tot_a, 1),
        "wape": round(float(err.sum() / tot_a), 4),
        "tol_wape": round(float((err * ~ok).sum() / tot_a), 4),
        "bias": round(float((tot_p - tot_a) / tot_a), 4),
    }


def _load_actuals(source: Path, closed_month: str, goods_source: Path | None = None):
    g_dir = goods_source or source
    kdb_goods = read(g_dir, "kdb_goods.csv", dtype={"code": str}).drop_duplicates("code").set_index("code")
    goods = load_goods(g_dir)
    prod_path = source / "rk_production_daily.csv"
    prod_codes = set(pd.read_csv(prod_path, dtype={"code": str})["code"]) if prod_path.is_file() else set()
    finished = set(kdb_goods.index) | prod_codes

    kdb = pd.read_csv(source / "kdb_sales_monthly.csv", dtype={"code": str})
    kdb = kdb.loc[kdb["pm"] <= closed_month]
    hyb_actuals = {}
    for pm, grp in kdb.groupby("pm"):
        hyb_actuals[str(pm)] = grp.groupby("code")["net_qty"].sum().clip(lower=0).to_dict()

    inv = pd.read_csv(source / "rk_invoices_daily.csv", dtype={"code": str})
    ret_path = source / "rk_returns_daily.csv"
    if ret_path.is_file():
        ret = pd.read_csv(ret_path, dtype={"code": str})
        ret = ret[ret["status"] == 11].copy()
        ret["qty"] = -ret["qty"]
        df = pd.concat([inv, ret], ignore_index=True)
    else:
        df = inv.copy()
    df = df.loc[df["code"].isin(finished)].copy()
    df = df.loc[df["cust"].map(normalize).map(channel_of) == "b2b"].copy()
    uniq_dates = {d: jdatetime.date.fromgregorian(date=pd.Timestamp(d).date()) for d in pd.unique(df["d"])}
    df["pm"] = df["d"].map(lambda d: f"{uniq_dates[d].year:04d}/{uniq_dates[d].month:02d}")
    df = df.loc[df["pm"] <= closed_month]
    b2b_actuals = {}
    for pm, grp in df.groupby("pm"):
        b2b_actuals[str(pm)] = grp.groupby("code")["qty"].sum().clip(lower=0).to_dict()

    names = goods["name"].fillna("").astype(str).to_dict()
    return hyb_actuals, b2b_actuals, names


def _backtest_summary(lab_dir: Path | None) -> tuple[dict, list[dict]]:
    if not lab_dir or not lab_dir.is_dir():
        return {}, []
    summary = {}
    monthly_rows = {}
    for ch in ("hybrid", "b2b"):
        npz_path = lab_dir / f"backtest_{ch}.npz"
        choice_path = lab_dir / f"choice_{ch}.json"
        if not npz_path.is_file() or not choice_path.is_file():
            continue
        choice = json.loads(choice_path.read_text(encoding="utf-8"))["chosen"]
        with np.load(npz_path, allow_pickle=True) as data:
            act = data["ACT"]
            cls_p = data["CLS_P"]
            late = data["LATE"].astype(bool)
            orig = data["ORIG"]
            targ = data["TARG"]
            chosen_pred = np.zeros_like(act, dtype=np.float64)
            classes = ("A", "B", "C", "N")
            for ci, cl in enumerate(classes):
                m = choice[cl]
                if m in data:
                    chosen_pred = np.where(cls_p == ci, data[m], chosen_pred)

            # Held-out late 3m totals by origin
            p3, a3 = [], []
            for o in sorted(set(orig)):
                idx = np.where(orig == o)[0]
                if len(idx) == 3 and late[idx[0]]:
                    p3.append(chosen_pred[idx].sum(axis=0))
                    a3.append(act[idx].sum(axis=0))
            if p3:
                m3 = _metrics(np.vstack(p3), np.vstack(a3))
                summary[f"{ch}_3m_wape"] = m3["wape"]
                summary[f"{ch}_3m_tol_wape"] = m3["tol_wape"]
                summary[f"{ch}_3m_bias"] = m3["bias"]
            summary[f"{ch}_chosen"] = choice

            # Held-out monthly WAPE/bias aggregated by target month
            for tm in sorted(set(targ[late])):
                rows = np.where(late & (targ == tm))[0]
                if not len(rows):
                    continue
                mm = _metrics(chosen_pred[rows], act[rows])
                key = _plabel(int(tm))
                monthly_rows.setdefault(key, {"month": key, "source": "held_out_backtest"})[ch] = mm

    ordered = [monthly_rows[k] for k in sorted(monthly_rows)]
    return summary, ordered


def build_accuracy_history(
    source: Path, root: Path, closed_month: str, lab_dir: Path | None = None, *, goods_source: Path | None = None
) -> dict:
    """Compare all archived model_YYYY-MM.csv files against closed sales and summarize held-out performance."""
    hyb_act, b2b_act, names = _load_actuals(source, closed_month, goods_source=goods_source)

    model_files = {}
    for folder in (root / "archive", root):
        if folder.is_dir():
            for path in sorted(folder.glob("model_*.csv")):
                model_files[path.name] = path

    live_monthly = []
    pending = []
    for fname in sorted(model_files):
        path = model_files[fname]
        df = pd.read_csv(path, dtype={"code": str}).drop_duplicates("code").set_index("code")
        model_closed = fname.removeprefix("model_").removesuffix(".csv").replace("-", "/")
        months = sorted(k.removeprefix("hybrid_") for k in df.columns if k.startswith("hybrid_") and "/" in k)
        for m_str in months:
            if m_str <= closed_month and m_str in hyb_act and m_str in b2b_act:
                codes = list(df.index)
                p_h = np.nan_to_num(df[f"hybrid_{m_str}"].to_numpy(dtype=np.float64), nan=0.0)
                p_b = np.nan_to_num(df[f"b2b_{m_str}"].to_numpy(dtype=np.float64), nan=0.0)
                a_h = np.array([hyb_act[m_str].get(c, 0.0) for c in codes], dtype=np.float64)
                a_b = np.array([b2b_act[m_str].get(c, 0.0) for c in codes], dtype=np.float64)

                mh = _metrics(p_h, a_h)
                mb = _metrics(p_b, a_b)
                mt = _metrics(p_h + p_b, a_h + a_b)

                errs = []
                for idx_c, code in enumerate(codes):
                    for ch_name, pv, av in (("hybrid", p_h[idx_c], a_h[idx_c]), ("b2b", p_b[idx_c], a_b[idx_c])):
                        diff = abs(pv - av)
                        if diff >= 1.0:
                            errs.append({
                                "code": code,
                                "name": str(df.at[code, "name"] if "name" in df.columns and pd.notna(df.at[code, "name"]) else names.get(code, "")),
                                "channel": ch_name,
                                "forecast": round(float(pv), 1),
                                "actual": round(float(av), 1),
                                "abs_error": round(float(diff), 1),
                            })
                errs.sort(key=lambda r: r["abs_error"], reverse=True)
                live_monthly.append({
                    "model_file": fname,
                    "model_closed_month": model_closed,
                    "target_month": m_str,
                    "horizon": _mon(m_str) - _mon(model_closed),
                    "sku_count": len(codes),
                    "hybrid": mh,
                    "b2b": mb,
                    "total": mt,
                    "top_errors": errs[:8],
                })
            elif m_str > closed_month:
                p_h = float(np.nansum(df[f"hybrid_{m_str}"].to_numpy(dtype=np.float64)))
                p_b = float(np.nansum(df[f"b2b_{m_str}"].to_numpy(dtype=np.float64)))
                pending.append({
                    "model_file": fname,
                    "model_closed_month": model_closed,
                    "target_month": m_str,
                    "horizon": _mon(m_str) - _mon(model_closed),
                    "hybrid_forecast": round(_finite(p_h, 0.0), 1),
                    "b2b_forecast": round(_finite(p_b, 0.0), 1),
                    "total_forecast": round(_finite(p_h + p_b, 0.0), 1),
                })

    bt_summary, bt_monthly = _backtest_summary(lab_dir)
    return {
        "closed_month": closed_month,
        "archived_models": sorted(model_files),
        "live_evaluated_count": len(live_monthly),
        "live_monthly": live_monthly,
        "pending_forecasts": pending,
        "backtest_summary": bt_summary,
        "backtest_monthly": bt_monthly,
    }
