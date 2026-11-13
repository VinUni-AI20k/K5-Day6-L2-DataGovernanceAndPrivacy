"""Unit tests for the shared metric library (success + edge paths)."""
import math

import numpy as np
import pandas as pd
import pytest

from src.metrics import (auroc, budget_b, ci_coverage, detection_prf, iou_xywh, pair_accuracy_at_tol, pair_prf, pairs_from_groups,
                         pii_miss_rate, precision_at_k, prf, recall_at_k, region_coverage, residual_cross_split_leak, spearman,
                         weighted_coverage, wilson_ci)


def test_prf_basic_and_zero_division():
    r = prf([1, 1, 0, 0], [1, 0, 1, 0])
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (1, 1, 1, 1)
    assert r["precision"] == 0.5 and r["recall"] == 0.5 and r["f1"] == 0.5
    r0 = prf([0, 0], [0, 0])          # no positives at all -> undefined, not a crash
    assert r0["precision"] is None and r0["recall"] is None


def test_recall_precision_at_k():
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(ranked, ["b", "d", "z"], 2)["value"] == pytest.approx(1 / 3)
    assert precision_at_k(ranked, ["b", "d"], 2)["value"] == 0.5
    assert recall_at_k(ranked, [], 2)["value"] is None
    assert budget_b(50) == 10 and budget_b(250) == 25


def test_weighted_coverage_ignores_non_targets():
    r = weighted_coverage(["A", "X"], {"A": 3, "B": 1})
    assert r["value"] == 0.75 and r["missing"] == ["B"]


def test_iou_and_detection_matching():
    assert iou_xywh((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou_xywh((0, 0, 10, 10), (20, 20, 5, 5)) == 0.0
    gt = pd.DataFrame([{"image_id": "i", "class": "car", "x": 0, "y": 0, "w": 10, "h": 10}])
    pred = pd.DataFrame([{"image_id": "i", "class": "car", "x": 1, "y": 0, "w": 10, "h": 10, "conf": 0.9},
                         {"image_id": "i", "class": "car", "x": 0, "y": 0, "w": 10, "h": 10, "conf": 0.5}])
    r = detection_prf(gt, pred)
    assert (r["tp"], r["fp"], r["fn"]) == (1, 1, 0)   # duplicate box is a false positive
    wrong_cls = pred.assign(**{"class": "pedestrian"})
    assert detection_prf(gt, wrong_cls)["tp"] == 0


def test_region_coverage_and_pii_miss():
    assert region_coverage((0, 0, 10, 10), [(0, 0, 5, 10)], (20, 20)) == 0.5
    gt = pd.DataFrame([{"image_id": "a", "region_id": "r1", "x": 0, "y": 0, "w": 10, "h": 10, "must_redact": 1},
                       {"image_id": "a", "region_id": "r2", "x": 15, "y": 15, "w": 4, "h": 4, "must_redact": 1}])
    red = pd.DataFrame([{"image_id": "a", "x": 0, "y": 0, "w": 10, "h": 10}])
    r = pii_miss_rate(gt, red, {"a": (20, 20)})
    assert r["value"] == 0.5 and r["numerator"] == 1


def test_pairs_and_leak():
    g = pairs_from_groups({"a": 1, "b": 1, "c": 1, "d": 2})
    assert g == {("a", "b"), ("a", "c"), ("b", "c")}
    r = pair_prf([("b", "a"), ("a", "d")], g)
    assert r["tp"] == 1 and r["fp"] == 1 and r["fn"] == 2
    leak = residual_cross_split_leak({"a": "train", "b": "test", "c": "drop"}, g)
    assert leak["numerator"] == 1 and leak["denominator"] == 1


def test_timing_hold_counts_as_wrong():
    r = pair_accuracy_at_tol([100, np.nan, 300], [110, 200, 400], tol_ms=50)
    assert r["numerator"] == 1 and r["denominator"] == 3


def test_estimation_and_correlation():
    lo, hi = wilson_ci(0, 20)
    assert lo == 0.0 and 0.1 < hi < 0.2          # 0/20 does NOT prove a 0% error rate
    assert ci_coverage([0, 0], [1, 0.1], [0.5, 0.5]) == 0.5
    assert spearman([1, 2, 3], [10, 20, 30])["value"] == pytest.approx(1.0)
    assert auroc([0, 1, 1], [0.1, 0.9, 0.8]) == 1.0
    assert auroc([1, 1], [0.1, 0.2]) is None
