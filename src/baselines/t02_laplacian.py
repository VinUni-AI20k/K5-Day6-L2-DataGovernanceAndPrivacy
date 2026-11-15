"""T02 baseline — single global Laplacian threshold (docs/tracks/T02.md §4).

Score = 1000 / (lap + 1e-5)  (higher = more suspicious)
Rule  = lap < LAP_THRESHOLD -> pred_defect_type "blur"

The baseline deliberately has no defect typing, no group normalisation and no
compression/glare feature: it is the bar the PoC must beat on the same pool,
budget and seed.

Threshold provenance: re-frozen on all 56 dev labels (reports/dev_labels.csv).
Any T in (745.0, 772.7] gives the same threshold decisions; 760 is the round
value inside the interval. The ranking score is monotonic in `lap`, so this
re-freeze does not change Recall@B / Precision@B, only the flagged set.
Never tune on eval.

    python -m src.main --track t02 --input fixtures/t02_raw_qc \
        --output out/baseline --run-name baseline \
        --pipeline src.baselines.t02_laplacian --offline
"""
from __future__ import annotations

import pandas as pd

from ..common.context import RunContext
from ..common.image_ops import laplacian_variance, load_rgb

LAP_THRESHOLD = 760.0  # frozen on 56 dev labels; do not tune on eval


def run(ctx: RunContext) -> None:
    images = pd.read_csv(ctx.input_dir / "images.csv")
    rows = []
    for r in images.itertuples():
        lap = laplacian_variance(load_rgb(ctx.input_dir / r.path))
        rows.append(
            {
                "image_id": r.image_id,
                "lap": round(lap, 1),
                "score": round(1000.0 / (lap + 1e-5), 6),
                "pred_defect_type": "blur" if lap < LAP_THRESHOLD else "none",
            }
        )
    out = pd.DataFrame(rows).sort_values("score", ascending=False, kind="mergesort")
    pred_path = ctx.out("ranked_review.csv")
    out[["image_id", "lap", "score", "pred_defect_type"]].to_csv(pred_path, index=False)

    ctx.stats["n_items"] = int(len(out))
    ctx.stats["n_flagged"] = int((out["pred_defect_type"] != "none").sum())
    print(
        f"[t02_laplacian] {pred_path} | {len(out)} images | "
        f"flagged={ctx.stats['n_flagged']} (lap < {LAP_THRESHOLD})"
    )
