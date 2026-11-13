"""Time-sync metrics (T04). All times in MILLISECONDS — convert before calling."""
from __future__ import annotations

import numpy as np


def pair_accuracy_at_tol(pred_ms, gt_ms, tol_ms: float = 50.0) -> dict:
    """Share of GT-pairable frames whose predicted partner time is within tol of GT.

    pred_ms / gt_ms: aligned arrays, NaN in pred = frame put on HOLD (counts as wrong).
    Denominator = frames that have a GT partner (gt not NaN).
    """
    pred = np.asarray(pred_ms, dtype=float)
    gt = np.asarray(gt_ms, dtype=float)
    valid = ~np.isnan(gt)
    ok = valid & ~np.isnan(pred) & (np.abs(pred - gt) <= tol_ms)
    den = int(valid.sum())
    return {"value": ok.sum() / den if den else None, "numerator": int(ok.sum()), "denominator": den, "tol_ms": tol_ms}


def median_abs_residual(pred_ms, gt_ms) -> float | None:
    pred = np.asarray(pred_ms, dtype=float)
    gt = np.asarray(gt_ms, dtype=float)
    m = ~np.isnan(pred) & ~np.isnan(gt)
    return float(np.median(np.abs(pred[m] - gt[m]))) if m.any() else None
