"""Score predictions against ground truth with the shared metric contract.

    python -m src.evaluate --track t02 --pred out/ranked_review.csv
    python -m src.evaluate --track t02 --gt fixtures/t02_raw_qc/gt/labels.csv --pred out/ranked_review.csv \
        --run-name poc --out reports/metrics_poc.json
    python -m src.evaluate --gt fixtures/eval_gt.csv --pred out/predictions.csv   # track from configs/lab.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .common.io import read_json, resolve_config
from .common.report import write_metrics
from .metrics.tracks import default_gt_path, get_track


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--track")
    ap.add_argument("--gt", help="ground-truth file (default: track's fixtures/<track>/gt/...)")
    ap.add_argument("--pred", required=True)
    ap.add_argument("--config", default="configs/lab.yaml")
    ap.add_argument("--split", help="eval split filter (eval/dev/heldout/all) where applicable")
    ap.add_argument("--budget", type=int, help="review budget B (ranking tracks)")
    ap.add_argument("--k", type=int, help="selection size K (T01/T13)")
    ap.add_argument("--run-name", default="poc")
    ap.add_argument("--out", help="write metrics JSON here (e.g. reports/metrics_poc.json)")
    ap.add_argument("--slices-out", help="write slice table CSV here")
    a = ap.parse_args(argv)

    cfg = resolve_config(a.config, a.track)
    track = a.track or cfg.get("track")
    if not track:
        print("--track is required (or set `track:` in configs/lab.yaml)", file=sys.stderr)
        return 2
    spec = get_track(track)
    gt = Path(a.gt) if a.gt else default_gt_path(spec.track)
    pred = Path(a.pred)
    for p, what in ((gt, "ground truth"), (pred, "predictions")):
        if not p.exists():
            print(f"{what} file not found: {p}", file=sys.stderr)
            return 2
    same_track = str(cfg.get("track", "")).lower()[:3] == spec.track
    params = {**spec.params, **((cfg.get("eval_params") or {}) if same_track else {})}
    for k in ("split", "budget", "k"):
        v = getattr(a, k)
        if v is not None:
            params[k] = v
    res = spec.evaluator(gt, pred, params)

    print(f"\n== {spec.track.upper()} · {spec.title} · run={a.run_name}")
    print(f"   gt={gt}\n   pred={pred}\n   params={params}")
    rows = [{"metric": m.name + (" [PRIMARY]" if m.primary else ""), "slice": m.slice, "value": m.value, "direction": m.direction,
             "num": m.numerator, "den": m.denominator, "N": m.n, "unit": m.unit} for m in res.metrics]
    with pd.option_context("display.max_colwidth", 70, "display.width", 200):
        print(pd.DataFrame(rows).to_string(index=False))
        if len(res.slices):
            print("\n-- slices")
            print(res.slices.to_string(index=False))
    for n in res.notes:
        print(f"note: {n}")

    if a.out:
        run_info = pred.parent / "run_info.json"
        info = read_json(run_info) if run_info.exists() else {}
        write_metrics(a.out, a.run_name, spec.track, res.metrics, seed=info.get("seed"), config=params,
                      runtime_seconds=info.get("runtime_seconds"), n_items=(info.get("stats") or {}).get("n_items"),
                      extra={"gt": str(gt), "pred": str(pred), "notes": res.notes, "slices": res.slices.to_dict(orient="records")})
        print(f"\nwrote {a.out}")
    if a.slices_out:
        Path(a.slices_out).parent.mkdir(parents=True, exist_ok=True)
        res.slices.to_csv(a.slices_out, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
