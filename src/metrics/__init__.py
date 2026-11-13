"""Metric library. Every function documents unit, numerator and denominator.

Use these instead of re-implementing so all groups share one definition.
`src/metrics/tracks.py` wires them into one evaluator per track.
"""
from .classification import confusion_counts, false_alarm_rate, miss_rate, prf, per_slice
from .ranking import budget_b, precision_at_k, recall_at_k, weighted_coverage
from .detection import iou_xywh, match_detections, detection_prf, region_coverage, pii_miss_rate, over_redaction_rate
from .pairs import pairs_from_groups, pair_prf, residual_cross_split_leak
from .timing import pair_accuracy_at_tol, median_abs_residual
from .estimation import mae, wilson_ci, ci_coverage
from .correlation import spearman, auroc, bootstrap_ci

__all__ = [
    "confusion_counts", "false_alarm_rate", "miss_rate", "prf", "per_slice",
    "budget_b", "precision_at_k", "recall_at_k", "weighted_coverage",
    "iou_xywh", "match_detections", "detection_prf", "region_coverage", "pii_miss_rate", "over_redaction_rate",
    "pairs_from_groups", "pair_prf", "residual_cross_split_leak",
    "pair_accuracy_at_tol", "median_abs_residual",
    "mae", "wilson_ci", "ci_coverage",
    "spearman", "auroc", "bootstrap_ci",
]
