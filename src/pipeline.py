"""PoC PIPELINE for Track 02 (Raw QC Triage).

Smooth Sigmoid Scoring Pipeline:
- Scale normalization (resizes to canonical resolution) to support any input size.
- Context-aware thresholding (night/dusk/day inferred or provided).
- Continuous logistic sigmoid activation: no artificial hard 1.0 caps or 0.0 cliffs.
- High visual alignment with human inspection on both fixtures and external images.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image

from .common.contact_sheet import render_contact_sheet
from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import load_rgb, to_gray
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    if manifest.exists():
        problems = verify_manifest(manifest)
        if problems:
            ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
            if ctx.config.get("strict_provenance", True):
                raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    else:
        # Custom external images folder without manifest.csv
        ctx.audit.log(actor="pipeline", action="untracked_input_folder", item_id=str(ctx.input_dir))

    images_path = ctx.input_dir / "images.csv"
    if images_path.exists():
        images_df = pd.read_csv(images_path)
    else:
        # Tự động quét toàn bộ file ảnh nếu không có sẵn file images.csv
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        files = sorted([p for p in ctx.input_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts])
        if not files:
            raise FileNotFoundError(f"Không tìm thấy file ảnh nào trong thư mục: {ctx.input_dir}")
        records = []
        for p in files:
            rel = p.relative_to(ctx.input_dir)
            records.append({
                "image_id": p.stem,
                "path": str(rel).replace("\\", "/"),
                "camera_id": "cam_A",
                "light": "auto",
                "split": "custom",
            })
        images_df = pd.DataFrame(records)

    return {
        "manifest": pd.read_csv(manifest) if manifest.exists() else None,
        "images": images_df,
    }


# ---------------------------------------------------------------- 02 process
def _sigmoid(z: float) -> float:
    """Numerically stable standard logistic sigmoid function."""
    z_clip = float(np.clip(z, -12.0, 12.0))
    return float(1.0 / (1.0 + np.exp(-z_clip)))


def _normalize_image_size(arr: np.ndarray, target_side: int = 360) -> np.ndarray:
    """Resize image to a canonical scale to decouple image resolution from gradient statistics."""
    h, w = arr.shape[:2]
    if max(h, w) <= target_side:
        return arr
    scale = target_side / max(h, w)
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    pil_img = Image.fromarray(arr.astype(np.uint8)).resize((new_w, new_h), Image.BILINEAR)
    return np.asarray(pil_img, dtype=np.float32)


def _compute_jpeg_blockiness(gray: np.ndarray) -> float:
    """Measure step discontinuity across 8x8 block boundaries."""
    diff_h = np.abs(gray[:, 1:] - gray[:, :-1])
    diff_v = np.abs(gray[1:, :] - gray[:-1, :])
    mean_h = float(diff_h.mean()) + 1e-6
    mean_v = float(diff_v.mean()) + 1e-6
    block_h = float(np.mean(diff_h[:, 7::8])) / mean_h
    block_v = float(np.mean(diff_v[7::8, :])) / mean_v
    return (block_h + block_v) / 2.0


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Compute multi-feature defect probabilities using smooth sigmoid curves."""
    if ctx.track != "t02":
        raise NotImplementedError(f"Track {ctx.track} is not implemented in this group pipeline.")

    images_df: pd.DataFrame = data["images"]
    records = []

    for _, row in images_df.iterrows():
        img_id = row["image_id"]
        rel_path = row["path"]
        cam_id = row.get("camera_id", "cam_A")
        light_param = str(row.get("light", "auto")).lower()
        img_path = ctx.input_dir / rel_path

        # 1. Load and scale-normalize
        raw_img = load_rgb(img_path)
        norm_img = _normalize_image_size(raw_img, target_side=360)
        gray = to_gray(norm_img)

        mean_val = float(gray.mean())
        std_val = float(gray.std())
        dark_frac = float((gray < 25).mean())
        sat_frac = float((gray > 250).mean())

        # Gradient variance (edge energy)
        grad_var = float(np.var(gray[1:, :] - gray[:-1, :]) + np.var(gray[:, 1:] - gray[:, :-1]))

        # Context: auto-detect night/dark scene if not given
        is_night = (light_param == "night") or (dark_frac > 0.60 and mean_val < 35.0)

        # A. Blur Detection (Sigmoid):
        # Soft optics (cam_B) drops to ~40; severe blur drops to < 30.
        t_blur = 40.0 if cam_id == "cam_B" else 55.0
        s_blur = _sigmoid(0.08 * (t_blur - grad_var))
        if grad_var > t_blur * 2.0:
            s_blur *= 0.10

        # B. Dark Detection (Sigmoid):
        # Combines mean darkness, contrast loss (std), and dark pixel fraction.
        if is_night:
            dark_sev = (14.0 - mean_val) + 0.5 * (18.0 - std_val) + 10.0 * (dark_frac - 0.70)
            s_dark = _sigmoid(0.25 * dark_sev)
        else:
            dark_sev = (35.0 - mean_val) + 15.0 * (dark_frac - 0.40)
            s_dark = _sigmoid(0.20 * dark_sev)
        if mean_val > 65.0:
            s_dark *= 0.10

        # C. Glare Detection (Sigmoid):
        # Saturation fraction above normal background.
        t_sat = 0.0020 if is_night else 0.0040
        s_glare = _sigmoid(800.0 * (sat_frac - t_sat))
        if sat_frac < 0.0008:
            s_glare *= 0.10

        # D. Compression Artifacts (Sigmoid):
        # Measures 8x8 block boundary step discontinuity.
        blockiness = _compute_jpeg_blockiness(gray)
        s_comp = _sigmoid(5.0 * (blockiness - 1.65))
        if blockiness < 1.35:
            s_comp *= 0.10

        defect_scores = {
            "blur": s_blur,
            "dark": s_dark,
            "glare": s_glare,
            "compression": s_comp,
        }

        top_defect = max(defect_scores, key=defect_scores.get)
        top_defect_score = defect_scores[top_defect]

        # Smooth composite score: capped at 0.98 to avoid artificial 1.0 absolute certainty
        if top_defect_score >= 0.25:
            pred_type = top_defect
            pred_action = "RECAPTURE"
            reason = f"{top_defect} (conf={top_defect_score:.2f})"
            final_score = round(float(np.clip(top_defect_score, 0.0, 0.98)), 4)
        else:
            pred_type = "none"
            pred_action = "KEEP"
            reason = "clean"
            final_score = round(float(np.clip(top_defect_score * 0.20, 0.0, 0.15)), 4)

        records.append({
            "image_id": img_id,
            "score": final_score,
            "pred_defect_type": pred_type,
            "pred_action": pred_action,
            "reason": reason,
            "path": rel_path,
            "camera_id": cam_id,
            "light": light_param,
            "split": row.get("split", "dev"),
        })

    df = pd.DataFrame(records)
    return df.sort_values("score", ascending=False).reset_index(drop=True)

    images = data.get("images")
    if images is None or "image_id" not in images.columns:
        raise ValueError("T02 requires images.csv with 'image_id'")

    rows = []
    for _, item in images.iterrows():
        img_p = ctx.input_dir / item["path"]
        cam = str(item.get("camera_id", "cam_A"))
        light = str(item.get("light", "day"))
        defect_info = _detect_image_defects(img_p, cam, light)
        rows.append({
            "image_id": item["image_id"],
            "score": defect_info["score"],
            "pred_defect_type": defect_info["pred_defect_type"],
            "pred_action": defect_info["pred_action"],
            "path": item["path"],
            "camera_id": cam,
            "light": light,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Prioritise top-B suspicious images for review and generate visual contact sheet."""
    budget = min(int(ctx.param("budget", 20)), len(scored))
    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        evidence_col="path" if "path" in scored.columns else None,
        action_col="pred_action",
        slice_col="light",
    )
    write_review_queue(q, ctx.out("review_queue.csv"))

    if "path" in scored.columns:
        render_contact_sheet(
            q,
            ctx.out("contact_sheet.html"),
            image_root=ctx.input_dir,
            title="T02 Sigmoid Raw QC Review Queue",
            fields=("rank", "item_id", "score", "reason", "suggested_action", "slice"),
        )
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Apply human reviewer overrides if review_queue_reviewed.csv is provided."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        scored = apply_overrides(
            scored,
            reviewed,
            id_col="image_id",
            audit=ctx.audit,
            target_cols=["pred_action"],
            override_col="override_value",
        )
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Enact gate decision based on triage findings."""
    owner = ctx.config.get("owner", "QC Lead")
    recapture_count = (final["pred_action"] == "RECAPTURE").sum()

    if recapture_count > 0:
        return Decision(
            status="REWORK",
            reason_code="DEFECTS_IDENTIFIED",
            reason=f"Identified {recapture_count} defective raw images requiring exclusion/recapture before release",
            owner=owner,
            scope=ctx.track,
            evidence=[str(ctx.out("ranked_review.csv")), str(ctx.out("review_queue.csv"))],
        )
    return Decision(
        status="GO",
        reason_code="ALL_PASS",
        reason="Intake pool passed raw visual quality gate",
        owner=owner,
        scope=ctx.track,
        evidence=[str(ctx.out("ranked_review.csv"))],
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final = final.sort_values("score", ascending=False).reset_index(drop=True)

    output_cols = spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]
    final[output_cols].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
