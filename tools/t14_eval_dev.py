"""T14: internal evaluation against the TEAM's hand-drawn gold set on DEV images (not the hidden eval GT).

    # F1 of an export vs the team gold
    python -m tools.t14_eval_dev --gold gold/gold_dev.csv --pred out/poc/predictions.csv
    # sweep conf thresholds on dev using the scored table written by the PoC (pick the threshold HERE, never on eval)
    python -m tools.t14_eval_dev --gold gold/gold_dev.csv --boxes out/poc/boxes_all.csv --sweep 0.1,0.2,0.25,0.3,0.4,0.5,0.6

gold csv columns: image_id,class,x,y,w,h  (class = taxonomy name). Every image_id must be a `dev` image.
Numbers are labelled 'internal gold, N images': they are not the official F1 of the lab.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

from src.metrics.detection import detection_prf

FIXTURE = Path("fixtures/t14_auto_annotation")


def _prf(gold: pd.DataFrame, pred: pd.DataFrame, iou: float) -> dict:
    pred = pred[pred["image_id"].isin(set(gold["image_id"]))]      # score only the images that were hand-labelled
    return detection_prf(gold.reset_index(drop=True), pred.reset_index(drop=True), iou, True)


def load_gold(path: str, images: pd.DataFrame, taxonomy: set[str]) -> pd.DataFrame:
    gold = pd.read_csv(path)
    need = ["image_id", "class", "x", "y", "w", "h"]
    miss = [c for c in need if c not in gold.columns]
    if miss:
        raise SystemExit(f"gold file missing columns {miss}")
    dev = set(images.loc[images["split"] == "dev", "image_id"])
    bad = sorted(set(gold["image_id"]) - dev)
    if bad:
        raise SystemExit(f"gold contains non-dev images (eval is off limits): {bad[:5]}")
    wrong = sorted(set(gold["class"]) - taxonomy)
    if wrong:
        raise SystemExit(f"gold has classes outside the taxonomy: {wrong}")
    return gold[need]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--pred")
    ap.add_argument("--boxes", help="out/poc/boxes_all.csv (for --sweep)")
    ap.add_argument("--sweep", help="comma separated conf thresholds")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--fixture", default=str(FIXTURE))
    a = ap.parse_args(argv)
    fx = Path(a.fixture)
    images = pd.read_csv(fx / "images.csv")
    tax = set(yaml.safe_load((fx / "taxonomy.yaml").read_text(encoding="utf-8"))["classes"].values())
    gold = load_gold(a.gold, images, tax)
    n_img = gold["image_id"].nunique()
    print(f"internal gold: {n_img} dev images, {len(gold)} boxes, IoU>={a.iou}")
    if a.pred:
        r = _prf(gold, pd.read_csv(a.pred), a.iou)
        print(f"{a.pred}: P={r['precision']} R={r['recall']} F1={r['f1']:.3f} (tp={r['tp']} fp={r['fp']} fn={r['fn']})")
    if a.sweep:
        if not a.boxes:
            raise SystemExit("--sweep needs --boxes out/poc/boxes_all.csv")
        boxes = pd.read_csv(a.boxes)
        print("thr    P      R      F1     n_pred")
        for t in (float(s) for s in a.sweep.split(",")):
            p = boxes[boxes["conf"] >= t]
            r = _prf(gold, p, a.iou)
            f = lambda v: "  -  " if v is None else f"{v:.3f}"
            print(f"{t:<5}  {f(r['precision'])}  {f(r['recall'])}  {r['f1']:.3f}  {r['n_pred']}")
    if not a.pred and not a.sweep:
        print("nothing to evaluate: pass --pred and/or --sweep")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
