"""Correlation / ranking-quality metrics with bootstrap uncertainty."""
from __future__ import annotations

from typing import Callable

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score


def spearman(x, y) -> dict:
    r = spearmanr(np.asarray(x, float), np.asarray(y, float))
    return {"value": float(r.statistic), "p_value": float(r.pvalue), "n": len(np.asarray(x))}


def auroc(y_true, score) -> float | None:
    y = np.asarray(y_true).astype(int)
    if len(set(y)) < 2:
        return None
    return float(roc_auc_score(y, np.asarray(score, float)))


def bootstrap_ci(fn: Callable[..., float], *arrays, n_boot: int = 1000, alpha: float = 0.05, seed: int = 42) -> tuple[float, float]:
    """Percentile bootstrap CI of fn(*arrays) resampling rows jointly."""
    rng = np.random.default_rng(seed)
    arrs = [np.asarray(a) for a in arrays]
    n = len(arrs[0])
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        try:
            v = fn(*[a[idx] for a in arrs])
        except Exception:
            continue
        if v is not None and not np.isnan(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 100 * alpha / 2)), float(np.percentile(vals, 100 * (1 - alpha / 2))))
