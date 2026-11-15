"""T07 self-check on the group's own mini gold set (dev split only).

Adds what `src.evaluate` does not print: miss rate by region size and a Wilson 95% interval.
It uses the same metric functions as the official evaluator (src/metrics/detection.py).

    python -m tools.t07_selfcheck --gt reports/mini_gt/gt_regions.csv \
        --run baseline=out/baseline/redactions.csv --run poc=out/poc/redactions.csv \
        --out reports/t07_selfcheck_slices.csv
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from src.metrics import detection as DE


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--run", action="append", required=True, help="name=path/to/redactions.csv (repeatable)")
    ap.add_argument("--min-coverage", type=float, default=0.9)
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    gt_path = Path(a.gt)
    gt = pd.read_csv(gt_path)
    imgs = pd.read_csv(gt_path.parent / "images.csv")
    sizes = {r.image_id: (int(r.height), int(r.width)) for r in imgs.itertuples()}
    pool = set(imgs.image_id)
    if "size" not in gt.columns:
        area = gt.w * gt.h
        gt["size"] = ["small" if v < 200 else ("medium" if v < 700 else "large") for v in area]
    rows = []
    for spec in a.run:
        name, path = spec.split("=", 1)
        red = pd.read_csv(path)
        red = red[red.image_id.isin(pool)]
        reg = DE.pii_miss_rate(gt, red, sizes, a.min_coverage)["regions"]
        over = DE.over_redaction_rate(gt, red, sizes)["value"]
        groups = [("all", "all", reg)]
        for col in ("type", "condition", "size"):
            groups += [(col, str(v), sub) for v, sub in reg.groupby(col)]
        for col, val, sub in groups:
            k, n = int(sub.missed.sum()), int(len(sub))
            lo, hi = wilson(k, n)
            rows.append({"run": name, "slice": f"{col}={val}", "n": n, "missed": k,
                         "miss_rate": round(k / n, 4) if n else None,
                         "wilson95_low": round(lo, 4), "wilson95_high": round(hi, 4),
                         "over_redaction_rate": round(over, 4) if col == "all" else None})
    out = pd.DataFrame(rows)
    with pd.option_context("display.width", 200):
        print(out.to_string(index=False))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(a.out, index=False)
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
