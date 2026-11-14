"""Box metrics. Boxes are (x, y, w, h) in pixels, top-left origin."""
from __future__ import annotations

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
