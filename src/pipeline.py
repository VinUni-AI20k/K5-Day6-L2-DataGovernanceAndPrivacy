"""YOUR PoC PIPELINE — this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   your algorithm / model (the research part)
    03 rank      prioritise for a fixed review budget B
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

Required output: out/<pred_file> with the columns listed for your track in
docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
    python -m src.evaluate --track tXX --pred out/<pred_file>

Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
no network calls; fail loudly on missing models instead of downloading.
See src/examples/random_baseline.py for a minimal end-to-end wiring example.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import brightness_stats, laplacian_variance, load_rgb, to_gray
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


def _robust_upper(values: pd.Series, groups: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"value": values.astype(float), "group": groups.astype(str)})
    median = frame.groupby("group")["value"].transform("median")
    deviation = (frame["value"] - median).abs()
    mad = deviation.groupby(frame["group"]).transform("median").clip(lower=1e-6)
    return ((frame["value"] - median) / (1.4826 * mad)).clip(lower=0.0, upper=8.0)


def _jpeg_blockiness(gray: np.ndarray) -> float:
    vertical = np.abs(np.diff(gray, axis=1))
    horizontal = np.abs(np.diff(gray, axis=0))
    boundary = np.concatenate((vertical[:, 7::8].ravel(), horizontal[7::8, :].ravel()))
    interior = np.concatenate((vertical[:, 6::8].ravel(), horizontal[6::8, :].ravel()))
    return float(max(boundary.mean() - interior.mean(), 0.0))


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    data = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}
    if ctx.track == "t02":
        data["images"] = pd.read_csv(ctx.input_dir / "images.csv")
    # TODO: load the tables/images your track needs, e.g.
    # data["images"] = pd.read_csv(ctx.input_dir / "images.csv")
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    spec = get_track(ctx.track)
    if ctx.track != "t02":
        raise NotImplementedError(
            f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
            f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
        )
    rows = []
    for item in data["images"].itertuples(index=False):
        image = load_rgb(ctx.input_dir / item.path)
        brightness = brightness_stats(image)
        rows.append(
            {
                "image_id": item.image_id,
                "path": item.path,
                "camera_id": item.camera_id,
                "light": item.light,
                "split": item.split,
                "sharpness": laplacian_variance(image),
                "mean_brightness": brightness["mean"],
                "frac_dark": brightness["frac_dark"],
                "frac_saturated": brightness["frac_saturated"],
                "blockiness": _jpeg_blockiness(to_gray(image)),
            }
        )
    scored = pd.DataFrame(rows)
    camera_light = scored["camera_id"].astype(str) + ":" + scored["light"].astype(str)
    scored["blur_score"] = _robust_upper(-np.log1p(scored["sharpness"]), scored["camera_id"])
    scored["dark_score"] = _robust_upper(scored["frac_dark"], camera_light)
    scored["glare_score"] = _robust_upper(scored["frac_saturated"], camera_light)
    scored["compression_score"] = _robust_upper(scored["blockiness"], scored["camera_id"])
    feature_scores = scored[["blur_score", "dark_score", "glare_score", "compression_score"]]
    scored["score"] = feature_scores.max(axis=1) + 0.15 * feature_scores.mean(axis=1)
    labels = feature_scores.idxmax(axis=1).str.replace("_score", "", regex=False)
    scored["pred_defect_type"] = labels.where(scored["score"] >= 1.5, "none")
    scored["pred_action"] = np.where(scored["score"] >= 2.5, "RECAPTURE", "KEEP")
    scored["reason"] = "qc:" + labels
    return scored


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Default: top-B by `score`. Adapt id/score/reason columns to your track."""
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first), "
                         "or adapt rank() to your track")
    q = make_review_queue(scored, id_col=scored.columns[0], score_col="score", budget=budget,
                          reason_col="reason" if "reason" in scored.columns else None,
                          action_col="pred_action" if "pred_action" in scored.columns else None,
                          slice_col="light" if "light" in scored.columns else None,
                          evidence_col="path" if "path" in scored.columns else None)
    write_review_queue(q, ctx.out("review_queue.csv"))
    if "path" in scored.columns:
        render_contact_sheet(q, ctx.out("contact_sheet.html"), image_root=ctx.input_dir, title=f"{ctx.track} QC review queue")
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """If a reviewed queue exists (out/review_queue_reviewed.csv), apply it. Otherwise pass through.

    TODO: decide what an `edit` / `reject` means for your track and apply it
    (e.g. via common.review.apply_overrides), logging every change to ctx.audit.
    """
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        # TODO: apply overrides
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    # TODO: replace with your policy (thresholds frozen BEFORE looking at eval results)
    recapture_count = int((final["pred_action"] == "RECAPTURE").sum())
    status = "RECAPTURE" if recapture_count else "KEEP"
    reason_code = "QC_ANOMALIES_FOUND" if recapture_count else "QC_WITHIN_LIMITS"
    reason = f"{recapture_count} images exceeded the frozen QC anomaly threshold"
    return Decision(status=status, reason_code=reason_code, reason=reason,
                    owner=ctx.config.get("owner", "TODO-owner"), scope=ctx.track,
                    evidence=[str(ctx.out("ranked_review.csv")), str(ctx.out("review_queue.csv"))],
                    metrics={"n_images": len(final), "n_recapture": recapture_count})


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
