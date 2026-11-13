"""Pair / group metrics for near-duplicate & leakage detection."""
from __future__ import annotations

from itertools import combinations
from typing import Iterable, Mapping


def _norm(a, b) -> tuple[str, str]:
    a, b = str(a), str(b)
    return (a, b) if a <= b else (b, a)


def pairs_from_groups(item_to_group: Mapping) -> set[tuple[str, str]]:
    """All unordered pairs of items that share a group id (singletons contribute nothing)."""
    groups: dict = {}
    for item, g in item_to_group.items():
        groups.setdefault(g, []).append(str(item))
    out = set()
    for members in groups.values():
        for a, b in combinations(sorted(members), 2):
            out.add((a, b))
    return out


def pair_prf(pred_pairs: Iterable, gt_pairs: Iterable) -> dict:
    """Evaluation unit = unordered pair. TP = predicted pair in GT pairs."""
    P = {_norm(a, b) for a, b in pred_pairs if str(a) != str(b)}
    G = {_norm(a, b) for a, b in gt_pairs}
    tp = len(P & G)
    fp = len(P - G)
    fn = len(G - P)
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def residual_cross_split_leak(split_of: Mapping, gt_pairs: Iterable) -> dict:
    """#GT duplicate pairs whose members land in different splits / #GT pairs with both members kept."""
    leak = kept = 0
    for a, b in gt_pairs:
        sa, sb = split_of.get(str(a)), split_of.get(str(b))
        if sa in (None, "drop", "") or sb in (None, "drop", ""):
            continue
        kept += 1
        leak += int(sa != sb)
    return {"value": leak / kept if kept else 0.0, "numerator": leak, "denominator": kept}
