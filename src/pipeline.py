"""Track T02 PoC Pipeline: Raw QC Triage (blur, glare, dark, compression).

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   camera- and lighting-aware QC multi-defect triage
    03 rank      prioritise top-B review budget with contact sheet
    04 review    human-in-the-loop: review queue -> overrides + audit log
    05 decide    GO / REWORK with reason_code + owner, write outputs
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import brightness_stats, laplacian_variance, to_gray
from .common.manifest import verify_manifest
from .common.review import (
    apply_overrides,
    load_review_decisions,
    make_review_queue,
    write_review_queue,
)
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    if ctx.track != "t02":
        spec = get_track(ctx.track)
        raise NotImplementedError(
            f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
            f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
        )
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    images_csv = ctx.input_dir / "images.csv"
    if not images_csv.exists():
        raise FileNotFoundError(f"Missing images.csv in {ctx.input_dir}")
    images = pd.read_csv(images_csv)
    return {
        "manifest": pd.read_csv(manifest) if manifest.exists() else None,
        "images": images,
    }


# ---------------------------------------------------------------- 02 process
def _score_image(img_path: Path, camera_id: str, light: str) -> dict:
    """Extract camera- and lighting-calibrated defect scores for T02."""
    img = np.asarray(Image.open(img_path))
    g = to_gray(img)
    lap = laplacian_variance(img)
    bs = brightness_stats(img)

    # 1. Blur score:
    # cam_A baseline lap ~1000-2200; cam_B soft-lens optical baseline ~180-360.
    # Blurry images have lap < 15. Normalize by optical baseline.
    lap_baseline = 250.0 if camera_id == "cam_B" else 1000.0
    lap_norm = lap / lap_baseline
    s_blur = max(0.0, float(1.0 - lap_norm / 0.15)) if lap_norm < 0.15 else 0.0

    # 2. Dark score:
    # Day normal mean is ~120, dusk ~90, night ~32.
    # If day/dusk, defect dark has mean < 40 and dark > 0.50.
    # If night, normal has dark ~0.50-0.65; defect dark has mean < 15 and dark > 0.85.
    if light == "night":
        if bs["mean"] < 15.0 and bs["frac_dark"] > 0.85:
            s_dark = float(min(1.0, 0.98 - bs["mean"] / 15.0))
        else:
            s_dark = 0.0
    else:
        if bs["mean"] < 40.0 and bs["frac_dark"] > 0.50:
            s_dark = float(min(1.0, 1.0 - bs["mean"] / 40.0))
        else:
            s_dark = 0.0

    # 3. Glare score:
    # Localized overexposure/specular reflection. Normal images have sat < 0.002.
    sat = bs["frac_saturated"]
    if sat > 0.003 or (bs["p95"] > 240.0 and bs["mean"] > 140.0):
        s_glare = float(min(1.0, sat * 50.0 + (1.0 if sat > 0.02 else 0.5)))
    else:
        s_glare = 0.0

    # 4. Compression (JPEG blockiness) score:
    # Contrast across 8x8 block boundaries vs intra-block step.
    diff_h = np.abs(g[:, 7:-1:8] - g[:, 8::8]).mean()
    diff_in_h = np.abs(g[:, 3:-1:8] - g[:, 4::8]).mean()
    diff_v = np.abs(g[7:-1:8, :] - g[8::8, :]).mean()
    diff_in_v = np.abs(g[3:-1:8, :] - g[4::8, :]).mean()
    blocky = ((diff_h / (diff_in_h + 1e-4)) + (diff_v / (diff_in_v + 1e-4))) / 2.0
    if blocky > 2.2:
        s_comp = float(min(1.0, (blocky - 2.0) / 1.5))
    else:
        s_comp = 0.0

    # If an image is severely dark / underexposed, low laplacian variance is a symptom
    # of darkness rather than optical defocus blur. Suppress blur score when dark.
    if s_dark > 0.4:
        s_blur = 0.0

    scores = {
        "blur": s_blur,
        "dark": s_dark,
        "glare": s_glare,
        "compression": s_comp,
    }
    top_defect = max(scores, key=scores.get)
    max_score = float(scores[top_defect])

    if max_score > 0.3:
        defect_type = top_defect
        action = "RECAPTURE"
        reason = f"{top_defect.capitalize()} defect detected (subscore={max_score:.3f})"
    else:
        defect_type = "none"
        action = "KEEP"
        reason = f"Normal image (max defect subscore: {top_defect}={max_score:.3f})"

    return {
        "score": max_score,
        "pred_defect_type": defect_type,
        "pred_action": action,
        "reason": reason,
    }


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    if ctx.track != "t02":
        spec = get_track(ctx.track)
        raise NotImplementedError(
            f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
            f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
        )

    images = data["images"].copy()
    results = []
    for _, row in images.iterrows():
        img_path = ctx.input_dir / row["path"]
        sc = _score_image(img_path, row.get("camera_id", "cam_A"), row.get("light", "day"))
        results.append({
            "image_id": row["image_id"],
            "score": sc["score"],
            "pred_defect_type": sc["pred_defect_type"],
            "pred_action": sc["pred_action"],
            "reason": sc["reason"],
            "path": row["path"],
            "camera_id": row.get("camera_id", ""),
            "light": row.get("light", ""),
            "split": row.get("split", ""),
        })

    return pd.DataFrame(results)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Prioritise top-B review budget by score descending and render offline contact sheet."""
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column")

    q = make_review_queue(
        df=scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        action_col="pred_action",
        slice_col="light",
        evidence_col="path",
        ascending=False,
    )
    write_review_queue(q, ctx.out("review_queue.csv"))

    # Render offline HTML contact sheet for human inspection
    render_contact_sheet(
        queue=q,
        out_html=ctx.out("contact_sheet.html"),
        image_root=ctx.input_dir,
        title=f"T02 Raw QC Triage Review Queue (Top {budget})",
    )
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Apply human review decisions from review_queue_reviewed.csv if available."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        for _, row in reviewed.iterrows():
            ctx.audit.log(
                actor=row["reviewer"],
                action="human_review",
                item_id=row["item_id"],
                before=row.get("suggested_action", ""),
                after=row["reviewer_decision"],
                reason=row.get("review_note", ""),
            )
        # Apply overrides to final output
        scored = apply_overrides(scored, reviewed, id_col="image_id", value_col="pred_action", audit=ctx.audit)
    else:
        ctx.stats["n_reviewed"] = 0
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Policy: if high defect rate in batch or review queue, trigger REWORK, else GO."""
    n_defects = int((final["score"] > 0.3).sum())
    defect_rate = n_defects / max(len(final), 1)
    owner = ctx.config.get("owner", "Hoang Sy Khiem (Data Lead)")

    if defect_rate > 0.20:
        return Decision(
            status="REWORK",
            reason_code="EXCESSIVE_DEFECTS",
            reason=f"Batch has {n_defects}/{len(final)} ({defect_rate:.1%}) flagged defects. Recapture required.",
            owner=owner,
            scope=ctx.track,
            evidence=[str(ctx.out("review_queue.csv")), str(ctx.out("ranked_review.csv"))],
        )

    return Decision(
        status="GO",
        reason_code="QC_TRIAGE_PASSED",
        reason=f"Batch defect rate {defect_rate:.1%} is within allowable threshold.",
        owner=owner,
        scope=ctx.track,
        evidence=[str(ctx.out("review_queue.csv"))],
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)

    # Save out/<pred_file> with required columns
    export_cols = spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]
    final[export_cols].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
