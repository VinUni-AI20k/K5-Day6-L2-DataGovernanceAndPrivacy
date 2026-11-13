"""Estimation metrics with uncertainty (T12 and any small-N evaluation)."""
from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm


def mae(est, truth) -> float:
    return float(np.mean(np.abs(np.asarray(est, float) - np.asarray(truth, float))))


def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a proportion k/n. Use it whenever N is small."""
    if n == 0:
        return (0.0, 1.0)
    z = norm.ppf(1 - alpha / 2)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def ci_coverage(lows, highs, truths) -> float:
    """Share of intervals that contain the true value (target ≈ nominal level, e.g. 0.95)."""
    lo, hi, t = (np.asarray(x, float) for x in (lows, highs, truths))
    return float(np.mean((lo <= t) & (t <= hi)))
