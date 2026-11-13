"""Binary classification metrics. Positive class = 1 = "defect / risky / must act"."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd


def confusion_counts(y_true, y_pred) -> dict:
    t = np.asarray(y_true).astype(int)
    p = np.asarray(y_pred).astype(int)
    return {
        "tp": int(((t == 1) & (p == 1)).sum()),
        "fp": int(((t == 0) & (p == 1)).sum()),
        "fn": int(((t == 1) & (p == 0)).sum()),
        "tn": int(((t == 0) & (p == 0)).sum()),
    }


def prf(y_true, y_pred) -> dict:
    """precision = TP/(TP+FP); recall = TP/(TP+FN); F1 = harmonic mean. None if denominator 0."""
    c = confusion_counts(y_true, y_pred)
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    p = tp / (tp + fp) if (tp + fp) else None
    r = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * p * r / (p + r)) if (p is not None and r is not None and (p + r) > 0) else (0.0 if (p == 0 or r == 0) else None)
    return {**c, "precision": p, "recall": r, "f1": f1, "n": len(np.asarray(y_true))}


def miss_rate(y_true, y_pred) -> float | None:
    """FN / (TP+FN): share of real positives that were missed."""
    c = confusion_counts(y_true, y_pred)
    den = c["tp"] + c["fn"]
    return c["fn"] / den if den else None


def false_alarm_rate(y_true, y_pred) -> float | None:
    """FP / (FP+TN): share of real negatives that were flagged."""
    c = confusion_counts(y_true, y_pred)
    den = c["fp"] + c["tn"]
    return c["fp"] / den if den else None


def per_slice(df: pd.DataFrame, slice_col: str, fn: Callable[[pd.DataFrame], dict]) -> pd.DataFrame:
    """Apply `fn(sub_df) -> dict` per slice value; returns one row per slice (+ n)."""
    rows = []
    for s, sub in df.groupby(slice_col, dropna=False):
        rows.append({"slice": s, "n": len(sub), **fn(sub)})
    return pd.DataFrame(rows)
