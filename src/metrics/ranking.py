"""Ranking / budgeted-selection metrics."""
from __future__ import annotations

import math
from typing import Iterable, Mapping


def budget_b(n: int, frac: float = 0.10, minimum: int = 10) -> int:
    """B = max(minimum, ceil(frac * N)) — e.g. T11 uses max(10, 10% N)."""
    return max(minimum, math.ceil(frac * n))


def recall_at_k(ranked_ids: Iterable, positive_ids: Iterable, k: int) -> dict:
    """#positives in top-k / #positives total. Denominator = all positives in the eval pool."""
    top = list(ranked_ids)[:k]
    pos = set(map(str, positive_ids))
    hits = sum(1 for x in top if str(x) in pos)
    return {"value": (hits / len(pos)) if pos else None, "numerator": hits, "denominator": len(pos), "k": k}


def precision_at_k(ranked_ids: Iterable, positive_ids: Iterable, k: int) -> dict:
    """#positives in top-k / k (uses len(top) if fewer than k items)."""
    top = list(ranked_ids)[:k]
    pos = set(map(str, positive_ids))
    hits = sum(1 for x in top if str(x) in pos)
    return {"value": (hits / len(top)) if top else None, "numerator": hits, "denominator": len(top), "k": k}


def weighted_coverage(covered_cells: Iterable, target_weights: Mapping[str, float]) -> dict:
    """Σ weight(target cells covered) / Σ weight(all target cells). Non-target cells ignored."""
    covered = set(map(str, covered_cells)) & set(target_weights)
    num = float(sum(target_weights[c] for c in covered))
    den = float(sum(target_weights.values()))
    return {
        "value": num / den if den else None,
        "numerator": num,
        "denominator": den,
        "covered": sorted(covered),
        "missing": sorted(set(target_weights) - covered),
    }
