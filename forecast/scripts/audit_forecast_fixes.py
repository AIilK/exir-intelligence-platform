"""Reproducible before/after audit using saved company exports, with checkpoints.

Does not publish or overwrite the active production plan. Calibration uses early
outcomes only; late scores and achieved coverage are held out from all choices.
"""
import argparse
from copy import copy
import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

import forecast_lab2 as L
from safety_calibration import fit

F = L.F


def view(ch, horizons):
    result = copy(ch)
    result.PAIRS = [(o, o + h) for o in ch.ROLL for h in horizons
                    if o + h <= F.i_last and ch.valid[F.R(o + h)]]
    result.ACT = np.stack([np.clip(np.nan_to_num(ch.Y[F.R(t)]), 0, None) for o, t in result.PAIRS])
    result.CLS_P = np.stack([ch.CLS[F.R(o)] for o, t in result.PAIRS])
    result.ORIG = np.array([o for o, t in result.PAIRS])
    result.LATE = np.array([F.plabel(o) > F.SPLIT for o, t in result.PAIRS])
    return result


def take(preds, source, target):
    indices = {pair: i for i, pair in enumerate(source.PAIRS)}
    return {key: value[[indices[pair] for pair in target.PAIRS]] for key, value in preds.items()}


def selected(ch, preds, choices):
    out = np.zeros_like(ch.ACT)
    for i, label in enumerate(F.CLASSES):
        out = np.where(ch.CLS_P == i, preds[choices[label]], out)
    return out


def cumulative(ch, predictions):
    values = {}
    for o in sorted(set(ch.ORIG)):
        rows = np.flatnonzero(ch.ORIG == o)
        if len(rows) != 3:
            continue
        # Do not calibrate with outcomes on the validation side of the split.
        early = max(ch.PAIRS[i][1] for i in rows) <= F.mon(F.SPLIT)
        late = o > F.mon(F.SPLIT)
        if early or late:
            values[o] = (predictions[rows].sum(0), ch.ACT[rows].sum(0), ch.CLS_P[rows[0]], early)
    return values


def safety_audit(channels, predictions, out):
    codes = sorted(set().union(*(set(ch.codes) for ch in channels.values())))
    sums = {name: cumulative(ch, predictions[name]) for name, ch in channels.items()}
    origins = sorted(set.intersection(*(set(rows) for rows in sums.values())))
    joint_p, joint_a, joint_class, legacy, early = [], [], [], [], []
    for origin in origins:
        p, a = np.zeros(len(codes)), np.zeros(len(codes))
        cls, variance = np.full(len(codes), 3), np.zeros(len(codes))
        for name, ch in channels.items():
            cp, ca, cc, is_early = sums[name][origin]
            ix = pd.Index(codes).get_indexer(ch.codes)
            p[ix] += cp; a[ix] += ca
            cls[ix] = np.minimum(cls[ix], cc)
            # Legacy RMSE also uses early errors only for a fair held-out comparison.
            rows = np.array([t <= F.mon(F.SPLIT) for o, t in ch.PAIRS])
            rmse = np.sqrt(np.mean((predictions[name][rows] - ch.ACT[rows]) ** 2, axis=0))
            variance[ix] += rmse ** 2
        z = np.select([cls == 0, cls == 1], [1.645, 1.282], default=0)
        legacy.append(z * np.sqrt(variance * 3))
        joint_p.append(p); joint_a.append(a); joint_class.append(cls); early.append(is_early)
    p, a, cls, legacy = map(np.asarray, (joint_p, joint_a, joint_class, legacy))
    early = np.asarray(early)
    labels = np.array(F.CLASSES)[cls]
    calibration = fit((a - p)[early], p[early], labels[early])
    calibration.update({"split": F.SPLIT, "last_closed_month": F.LAST_FULL,
                        "calibration_origins": [F.plabel(o) for o, yes in zip(origins, early) if yes],
                        "validation_origins": [F.plabel(o) for o, yes in zip(origins, early) if not yes]})
    empirical = np.zeros_like(p)
    for label, entry in calibration["classes"].items():
        mask = labels == label
        empirical[mask] = np.maximum(p[mask] / 3, 1) * entry["multiplier"]
    report = []
    for label in ("A", "B"):
        mask = (labels == label) & ~early[:, None]
        for name, buffer in (("legacy_rmse", legacy), ("joint_empirical", empirical)):
            report.append({"class": label, "method": name, "target": calibration["classes"][label]["target"],
                           "validation_observations": int(mask.sum()),
                           "coverage": float((a <= p + buffer + 1e-9)[mask].mean()),
                           "mean_buffer": float(buffer[mask].mean()),
                           "mean_shortfall": float(np.maximum(a - p - buffer, 0)[mask].mean())})
    calibration["validation"] = report
    (out / "safety_calibration.json").write_text(json.dumps(calibration, indent=2), encoding="utf-8")
    pd.DataFrame(report).to_csv(out / "safety_coverage.csv", index=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    F.LGB_PARAMS.update(n_jobs=args.threads, n_estimators=160)
    valid = ~np.isin(F.idx, [F.mon(m) for m in F.MANUAL_EXCLUDE])
    hybrid = F.net.reindex(columns=F.codes).to_numpy(copy=True)
    rk = L.C.rahkaran_channels(valid)[0]
    channels = {"hybrid": L.Channel("hybrid", hybrid, F.codes, valid_months=valid)}
    channels["b2b"] = L.Channel("b2b", *rk["b2b"], valid_months=valid)
    scores, chosen_predictions, safety_channels = [], {}, {}
    inputs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (F.SNAPSHOT or F.DATA).glob("*.csv")}
    provenance = {"inputs": inputs, "last_closed_month": F.LAST_FULL, "split": F.SPLIT,
                  "trees": F.LGB_PARAMS["n_estimators"], "source": str(F.SNAPSHOT or F.DATA)}
    manifest = out / "provenance.json"
    if manifest.is_file() and json.loads(manifest.read_text()) != provenance:
        raise ValueError("Checkpoint inputs changed; choose a new output directory")
    manifest.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    for name, ch in channels.items():
        all_h = view(ch, (1, 2, 3, 4)); standard = view(ch, (1, 2, 3))
        configs = {}
        for label, cfg in L.CFGS.items():
            checkpoint = out / f"corrected_{name}_{label.replace('+', '')}.npz"
            if checkpoint.is_file():
                with np.load(checkpoint) as data:
                    full = {k: data[k] for k in data.files}
            else:
                F.log("causal backtest", name, label)
                full, _, _ = L.backtest(ch, cfg, horizons=(1, 2, 3, 4))
                np.savez_compressed(checkpoint, **full)
            preds = take(full, all_h, standard)
            rows, choices, combined = L.evaluate(standard, preds, label)
            configs[label] = (rows, choices, full)
        keep = L.choose_configuration({label: value[0] for label, value in configs.items()})
        rows, choices, full = configs[keep]
        for row in rows:
            scores.append({"channel": name, "version": "corrected", **row})
        (out / f"choice_{name}.json").write_text(json.dumps({"config": keep, "chosen": choices}), encoding="utf-8")
        np.savez_compressed(out / f"backtest_{name}.npz", **take(full, all_h, standard),
                            ACT=standard.ACT, CLS_P=standard.CLS_P, ORIG=standard.ORIG,
                            TARG=np.array([t for o, t in standard.PAIRS]), codes=np.array(ch.codes))
        safety_ch = view(ch, (2, 3, 4))
        safety_channels[name] = safety_ch
        chosen_predictions[name] = selected(safety_ch, take(full, all_h, safety_ch), choices)
        baseline = {}
        for label, cfg in L.CFGS.items():
            checkpoint = out / f"legacy_{name}_{label.replace('+', '')}.npz"
            if checkpoint.is_file():
                with np.load(checkpoint) as data:
                    old = {key: data[key] for key in data.files}
            else:
                F.log("full-history baseline", name, label)
                old, _, _ = L.backtest(ch, cfg, causal=False)
                np.savez_compressed(checkpoint, **old)
            baseline[label] = L.evaluate(standard, old, label, independent=False)
        score = lambda label, half: next(r["tolWAPE"] for r in baseline[label][0] if r["half"] == half and r["class"] == "ALL")
        old_keep = "+inflation" if score("+inflation", "early") < score("prev", "early") and score("+inflation", "late") <= score("prev", "late") else "prev"
        for row in baseline[old_keep][0]:
            scores.append({"channel": name, "version": "legacy_full_history", **row})
        pd.DataFrame(scores).to_csv(out / "accuracy_comparison.csv", index=False)
        F.log(name, "selected", keep, choices)
    coverage = safety_audit(safety_channels, chosen_predictions, out)
    F.log("coverage", coverage)


if __name__ == "__main__":
    main()
