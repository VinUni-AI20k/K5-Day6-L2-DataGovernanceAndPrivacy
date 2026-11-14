"""T02 baseline: rank by whole-image Laplacian variance."""

from __future__ import annotations

import pandas as pd

from ..common.contact_sheet import render_contact_sheet
from ..common.context import RunContext
from ..common.decision import Decision, write_decision
from ..common.image_ops import laplacian_variance, load_rgb
from ..common.manifest import verify_manifest
from ..common.review import make_review_queue, write_review_queue


# Fix the cutoff rule before evaluating. With unlabeled dev images, use the
# lower quintile as a simple provisional decision threshold.
DEV_QUANTILE = 0.20


def run(ctx: RunContext) -> None:
    if ctx.track != "t02":
        raise ValueError("The Laplacian baseline supports T02 only.")

    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.is_file() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="baseline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"Provenance check failed: {problems[:3]}")

    images = pd.read_csv(ctx.input_dir / "images.csv")
    required = {"image_id", "path", "light", "split"}
    missing = required - set(images.columns)
    if missing:
        raise ValueError(f"images.csv is missing columns: {sorted(missing)}")
    dev = images["split"].eq(ctx.param("dev_split", "dev"))
    if not dev.any():
        raise ValueError("images.csv needs dev images to set the sharpness threshold.")

    sharpness = []
    for path in images["path"]:
        try:
            sharpness.append(laplacian_variance(load_rgb(ctx.input_dir / path)))
        except (OSError, TypeError) as exc:
            raise ValueError(f"Cannot read image {path!r}: {exc}") from exc

    images["laplacian_variance"] = sharpness
    threshold = float(images.loc[dev, "laplacian_variance"].quantile(DEV_QUANTILE))
    images["score"] = 1.0 / (1.0 + images["laplacian_variance"])
    images["pred_action"] = "KEEP"
    images.loc[images["laplacian_variance"] <= threshold, "pred_action"] = "RECAPTURE"
    images["reason"] = "whole_image_sharpness"

    ranked = images.sort_values("score", ascending=False, kind="stable")
    pred_path = ctx.out("ranked_review.csv")
    ranked[["image_id", "score", "laplacian_variance", "pred_action"]].to_csv(pred_path, index=False)

    queue = make_review_queue(
        ranked, id_col="image_id", score_col="score", budget=int(ctx.param("budget", 20)),
        reason_col="reason", action_col="pred_action", slice_col="light", evidence_col="path",
    )
    queue_path = write_review_queue(queue, ctx.out("review_queue.csv"))
    render_contact_sheet(
        queue, ctx.out("contact_sheet.html"), image_root=ctx.input_dir, title="T02 Laplacian baseline",
    )

    ctx.stats.update(n_items=len(images), n_dev=int(dev.sum()), laplacian_threshold=threshold)
    write_decision(
        Decision(
            status="HOLD", reason_code="BASELINE_ONLY",
            reason="Sharpness-only baseline. The suggested actions are for manual review.",
            owner=ctx.config.get("owner", "baseline"), scope=ctx.track,
            evidence=[str(pred_path), str(queue_path)],
        ),
        ctx.out("decision.json"), ctx.out("decision_log.csv"),
    )
