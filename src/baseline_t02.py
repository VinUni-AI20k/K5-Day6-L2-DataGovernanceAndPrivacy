"""T02 Baseline: single global Laplacian variance threshold (no per-camera/light normalisation).

Follows the 5-step lab contract (load -> process -> rank -> review -> decide)
and writes out/baseline/ranked_review.csv, review_queue.csv, contact_sheet.html,
decision.json, and decision_log.csv.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import laplacian_variance, load_rgb
from .common.manifest import verify_manifest
from .common.review import make_review_queue, write_review_queue
from .metrics.tracks import get_track


def load(ctx: RunContext) -> dict:
    """Load images.csv after verifying manifest provenance."""
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    return {"images": pd.read_csv(ctx.input_dir / "images.csv")}


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Score each image by global Laplacian variance (lower variance -> higher defect score)."""
    df = data["images"].copy()
    df["lap_var"] = [laplacian_variance(load_rgb(ctx.input_dir / p)) for p in df["path"]]

    dev_split = str(ctx.param("dev_split", "dev"))
    dev_vals = df.loc[df["split"] == dev_split, "lap_var"] if "split" in df.columns else df["lap_var"]
    thr_q = float(ctx.param("baseline_quantile", 0.25))
    thr = float(np.quantile(dev_vals, thr_q)) if len(dev_vals) else float(np.median(df["lap_var"]))
    ctx.stats["lap_var_threshold_dev"] = round(thr, 4)

    df["score"] = 1.0 / (1.0 + df["lap_var"])
    is_flag = df["lap_var"] < thr
    df["pred_defect_type"] = np.where(is_flag, "blur", "none")
    df["pred_action"] = np.where(is_flag, "RECAPTURE", "KEEP")
    df["reason"] = [f"lap_var={v:.1f} (thr={thr:.1f})" for v in df["lap_var"]]
    return df


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)

    budget = int(ctx.param("budget", 20))
    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        action_col="pred_action",
        slice_col="light",
        evidence_col="path",
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(
        q,
        ctx.out("contact_sheet.html"),
        image_root=ctx.input_dir,
        title=f"{spec.track} Laplacian Baseline (top-{budget})",
    )

    ranked = scored.sort_values("score", ascending=False, kind="mergesort")
    cols = ["image_id", "score", "pred_defect_type", "pred_action", "lap_var", "camera_id", "light", "split"]
    ranked[[c for c in cols if c in ranked.columns]].to_csv(ctx.out(spec.pred_file), index=False)

    write_decision(
        Decision(
            status="HOLD",
            reason_code="BASELINE_LAPLACIAN",
            reason="Global Laplacian baseline for comparison only; do not release without PoC.",
            owner=ctx.config.get("owner", "baseline"),
            scope=ctx.track,
            evidence=[str(ctx.out(spec.pred_file)), str(ctx.out("review_queue.csv"))],
            metrics={"lap_var_threshold_dev": ctx.stats["lap_var_threshold_dev"]},
        ),
        ctx.out("decision.json"),
        ctx.out("decision_log.csv"),
    )
