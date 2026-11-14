"""Failure-mode evidence for T14 (no GT needed): where does 'valid-looking' export hide problems?

    python -m tools.t14_failure_evidence [--input fixtures/t14_auto_annotation] [--thr 0.25]

Prints: (1) boxes the baseline exports that are invalid, (2) naive id->taxonomy mapping vs label-map mapping,
(3) class-confusion pairs, (4) small / mid-conf share of boxes above the threshold.
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.t14_tools import (add_box_ids, add_suspicion, build_class_map, load_inputs, map_classes, normalise_boxes,
                           validate_predictions)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="fixtures/t14_auto_annotation")
    ap.add_argument("--thr", type=float, default=0.25)
    a = ap.parse_args()
    d = load_inputs(a.input)
    cmap = build_class_map(d["label_map"], d["taxonomy"], None)
    boxes = map_classes(d["preds"], cmap)
    kept = boxes[boxes["conf"] >= a.thr]

    bad = validate_predictions(kept[["image_id", "class", "x", "y", "w", "h"]], d["taxonomy"], d["images"])
    print(f"[1] baseline exports {len(kept)} boxes, {len(bad)} invalid (out of bounds etc.)")
    print(bad[["image_id", "class", "x", "y", "w", "h", "problem"]].to_string(index=False))

    naive = d["preds"]["class_id"].map(d["taxonomy"])
    right = d["preds"]["class_id"].map(cmap)
    print(f"\n[2] naive class_id->taxonomy would mislabel {(naive != right).sum()}/{len(naive)} boxes "
          f"({int(naive.isna().sum())} have no taxonomy entry at all -> silently dropped or invalid)")
    print(pd.crosstab(d["preds"]["class_id"].map(d["label_map"]), right.rename("mapped_to")).to_string())

    norm, _ = normalise_boxes(add_box_ids(boxes), d["images"])
    s = add_suspicion(norm, a.thr)
    conf = s[s["confusion"]]
    print(f"\n[3] {len(conf)} boxes overlap a different-class box (IoU>=0.5); classes: {sorted(conf['class'].unique())}")

    k = s[s["conf"] >= a.thr]
    print(f"\n[4] above thr: small={int(k['small'].sum())}/{len(k)}, mid_conf(0.35-0.65)={int(k['conf'].between(.35,.65).sum())}/{len(k)}")
    print("    small boxes' conf: median=%.2f; high-conf(>=0.8) small boxes=%d" % (k[k['small']]['conf'].median(), int((k['small'] & (k['conf'] >= .8)).sum())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
