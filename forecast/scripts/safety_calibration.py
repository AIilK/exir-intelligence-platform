"""Empirical cumulative-error buffers; coverage is measured, never guaranteed.

Pool normalized, joint Hybrid+B2B errors within ABC classes. This preserves
observed dependence across channels and months without a square-root assumption.
Calibration outcomes must precede the validation period. Sparse SKU history uses
the class pool rather than silently contributing a zero error estimate.
"""
import math

import numpy as np
import pandas as pd

TARGETS = {"A": 0.95, "B": 0.90}


def empirical_upper(values, target):
    values = np.asarray(values, float)
    values = np.sort(values[np.isfinite(values)])
    if len(values) < math.ceil(1 / (1 - target)):
        raise ValueError("Insufficient calibration observations for service target")
    rank = min(len(values), math.ceil((len(values) + 1) * target))
    return max(0.0, float(values[rank - 1]))


def fit(errors, predictions, classes):
    """Arrays are origin x SKU, with errors = actual 3m - predicted 3m."""
    scale = np.maximum(np.asarray(predictions) / 3, 1)
    scores = np.asarray(errors) / scale
    result = {"method": "joint_empirical_3m", "horizons": [2, 3, 4], "classes": {}}
    for label, target in TARGETS.items():
        mask = (classes == label) & np.isfinite(scores)
        values = scores[mask]
        result["classes"][label] = {
            "target": target, "multiplier": empirical_upper(values, target),
            "samples": int(mask.sum()), "origins": int(mask.any(axis=1).sum()),
        }
    return result


def apply(plan, calibration, channels=("hybrid", "b2b")):
    classes = plan[[f"{ch}_class" for ch in channels]]
    label = np.select([classes.eq("A").any(axis=1), classes.eq("B").any(axis=1)], ["A", "B"], default="C")
    scale = np.maximum(plan[[f"{ch}_3m" for ch in channels]].fillna(0).sum(axis=1) / 3, 1)
    buffer = np.zeros(len(plan))
    samples = np.zeros(len(plan), dtype=int)
    for cls in TARGETS:
        entry = calibration["classes"][cls]
        if not np.isfinite(entry["multiplier"]) or entry["multiplier"] < 0 or entry["samples"] < 1:
            raise ValueError("Invalid safety calibration")
        mask = label == cls
        buffer[mask] = scale[mask] * entry["multiplier"]
        samples[mask] = entry["samples"]
    plan = plan.copy()
    plan["safety_calibrated_3m"] = buffer
    plan["safety_calibration_samples"] = samples
    plan["safety_method"] = calibration["method"]
    return plan
