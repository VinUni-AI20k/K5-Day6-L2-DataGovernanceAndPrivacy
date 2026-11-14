"""Box metrics. Boxes are (x, y, w, h) in pixels, top-left origin."""
from __future__ import annotations

import numpy as np
import pandas as pd


def iou_xywh(a, b) -> float:
    ax, ay, aw, ah = map(float, a)
    bx, by, bw, bh = map(float, b)
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def match_detections(gt: pd.DataFrame, pred: pd.DataFrame, iou_thr: float = 0.5, class_aware: bool = True) -> dict:
    """Greedy matching per image, predictions sorted by `conf` desc (if present).

    gt  : columns image_id, x, y, w, h [, class]
    pred: columns image_id, x, y, w, h [, class] [, conf]
    A prediction is TP if IoU >= thr with an unmatched GT (same class if class_aware).
    Returns tp/fp/fn and list of matched (gt_index, pred_index, iou).
    """
    tp = fp = 0
    matches = []
    matched_gt: set = set()
    pred = pred.copy()
    if "conf" in pred.columns:
        pred = pred.sort_values("conf", ascending=False, kind="mergesort")
    gt_by_img = {k: v for k, v in gt.groupby("image_id")}
    for pi, p in pred.iterrows():
        cands = gt_by_img.get(p["image_id"])
        best, best_iou = None, iou_thr
        if cands is not None:
            for gi, g in cands.iterrows():
                if gi in matched_gt:
                    continue
                if class_aware and "class" in gt.columns and str(g["class"]) != str(p.get("class")):
                    continue
                iou = iou_xywh((g.x, g.y, g.w, g.h), (p.x, p.y, p.w, p.h))
                if iou >= best_iou:
                    best, best_iou = gi, iou
        if best is None:
            fp += 1
        else:
            tp += 1
            matched_gt.add(best)
            matches.append((best, pi, best_iou))
    fn = len(gt) - len(matched_gt)
    return {"tp": tp, "fp": fp, "fn": fn, "matches": matches, "unmatched_gt": sorted(set(gt.index) - matched_gt)}


def detection_prf(gt: pd.DataFrame, pred: pd.DataFrame, iou_thr: float = 0.5, class_aware: bool = True) -> dict:
    m = match_detections(gt, pred, iou_thr, class_aware)
    tp, fp, fn = m["tp"], m["fp"], m["fn"]
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1, "n_gt": len(gt), "n_pred": len(pred)}


def _mask(boxes, shape) -> np.ndarray:
    H, W = shape
    m = np.zeros((H, W), dtype=bool)
    for x, y, w, h in boxes:
        x0, y0 = max(0, int(np.floor(x))), max(0, int(np.floor(y)))
        x1, y1 = min(W, int(np.ceil(x + w))), min(H, int(np.ceil(y + h)))
        if x1 > x0 and y1 > y0:
            m[y0:y1, x0:x1] = True
    return m


def region_coverage(gt_box, redaction_boxes, shape) -> float:
    """Fraction of GT region pixels covered by the union of redaction boxes."""
    g = _mask([gt_box], shape)
    r = _mask(redaction_boxes, shape)
    area = g.sum()
    return float((g & r).sum() / area) if area else 1.0


def pii_miss_rate(gt: pd.DataFrame, red: pd.DataFrame, image_sizes: dict, min_coverage: float = 0.9) -> dict:
    """PII Miss Rate = #GT regions with coverage < min_coverage / #GT regions (must_redact only).

    gt : image_id, region_id, x, y, w, h [, must_redact]
    red: image_id, x, y, w, h  (final redaction boxes)
    image_sizes: {image_id: (H, W)}
    Returns value + per-region coverage DataFrame for slicing.
    """
    gt = gt.copy()
    # Regions explicitly marked as exempt from redaction do not count as PII misses.
    if "must_redact" in gt.columns:
        gt = gt[gt["must_redact"].astype(int) == 1]
    red_by_img = {k: v[["x", "y", "w", "h"]].values.tolist() for k, v in red.groupby("image_id")}
    cov = []
    for r in gt.itertuples(index=False):
        cov.append(region_coverage((r.x, r.y, r.w, r.h), red_by_img.get(r.image_id, []), image_sizes[r.image_id]))
    gt["coverage"] = cov
    gt["missed"] = (gt["coverage"] < min_coverage).astype(int)
    n = len(gt)
    return {"value": gt["missed"].mean() if n else None, "numerator": int(gt["missed"].sum()), "denominator": n, "regions": gt}


def over_redaction_rate(gt: pd.DataFrame, red: pd.DataFrame, image_sizes: dict) -> dict:
    """Redacted pixels outside any GT region / total redacted pixels (lower = less utility loss)."""
    outside = total = 0
    gt_by = {k: v[["x", "y", "w", "h"]].values.tolist() for k, v in gt.groupby("image_id")}
    for img, sub in red.groupby("image_id"):
        shape = image_sizes[img]
        # Compare pixel unions so overlapping boxes are not counted multiple times.
        rm = _mask(sub[["x", "y", "w", "h"]].values.tolist(), shape)
        gm = _mask(gt_by.get(img, []), shape)
        total += int(rm.sum())
        outside += int((rm & ~gm).sum())
    return {"value": outside / total if total else 0.0, "numerator": outside, "denominator": total}
