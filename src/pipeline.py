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
from scipy.ndimage import label

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import laplacian_variance, load_rgb, to_gray
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track

# ===============================================================
# FROZEN PARAMETERS — live in configs/tracks/t02.yaml under `params:`
# (merged into ctx.config by the `track_config` link in configs/lab.yaml).
# They were hard-coded here until 2026-11-15; the values are unchanged.
# Calibrated GT-free on the dev split (n=40), seed 42 — see
# reports/metric_contract.md. Never tune them on eval.
# ===============================================================
PARAM_KEYS = (
    "camera_medians", "global_median",
    "blur_threshold", "blur_range",
    "dark_threshold",
    "glare_threshold", "glare_range",
    "jpeg_threshold", "jpeg_range",
    "weights",
    "pred_action_threshold", "pred_defect_epsilon",
)
WEIGHT_KEYS = ("blur", "dark", "glare", "jpeg")


def load_params(config: dict) -> dict:
    """Pull the frozen T02 parameters out of the merged run config.

    The runner merges `configs/lab.yaml` over `configs/tracks/t02.yaml` (via the
    `track_config:` key), so `config["params"]` already holds every frozen value.
    Fails loudly rather than silently scoring with a partial parameter set.
    """
    params = dict((config or {}).get("params") or {})
    missing = [k for k in PARAM_KEYS if k not in params]
    if missing:
        raise ValueError(
            f"T02 config is missing frozen params {missing}; they belong under `params:` in "
            "configs/tracks/t02.yaml (linked from configs/lab.yaml via `track_config:`)"
        )
    weights = params["weights"] or {}
    missing_w = [k for k in WEIGHT_KEYS if k not in weights]
    if missing_w:
        raise ValueError(f"T02 config param `weights` is missing {missing_w}; expected all of {WEIGHT_KEYS}")
    total = sum(float(weights[k]) for k in WEIGHT_KEYS)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"T02 weights must sum to 1.0, got {total!r} (weights={weights})")
    return params



# ===============================================================
# HELPER FUNCTIONS — PoC multi-defect feature extraction
# ===============================================================

def blockiness_ratio(gray: np.ndarray) -> float:
    """JPEG compression artifact detection via 8×8 block boundary discontinuity.

    Returns ratio of boundary gradients to interior gradients. Higher = more blocking.
    Calibrated threshold: 2.20 (catches 48% sev1, 98% sev2; 16% dev flagged).
    """
    g = gray.astype(np.float32)
    dh = np.abs(np.diff(g, axis=1))  # horizontal gradients
    dv = np.abs(np.diff(g, axis=0))  # vertical gradients

    cols = np.arange(dh.shape[1])
    rows = np.arange(dv.shape[0])

    # 8×8 block boundaries (columns/rows where (idx+1) % 8 == 0)
    boundary_h = dh[:, (cols + 1) % 8 == 0].mean()
    interior_h = dh[:, (cols + 1) % 8 != 0].mean()
    boundary_v = dv[(rows + 1) % 8 == 0, :].mean()
    interior_v = dv[(rows + 1) % 8 != 0, :].mean()

    eps = 1e-6
    ratio = 0.5 * ((boundary_h / (interior_h + eps)) + (boundary_v / (interior_v + eps)))
    return float(ratio)


def glare_blob_fraction(gray: np.ndarray, threshold: int = 250) -> float:
    """Local glare detection via largest connected saturated region (8-connected).

    Returns fraction of image covered by largest blob of pixels >= threshold.
    Calibrated threshold: 0.010 (catches 82% sev1/100% sev2; 0% dev flagged).
    """
    mask = gray >= threshold
    labeled, n_components = label(mask, structure=np.ones((3, 3), dtype=int))

    if n_components == 0:
        return 0.0

    # Find largest component (exclude background label 0)
    component_sizes = np.bincount(labeled.ravel())[1:]  # skip label 0
    largest = component_sizes.max()
    return float(largest / gray.size)


def compute_badness(lap_var: float, lum_p95: float, glare_blob: float, blockiness: float,
                    camera_id: str, params: dict) -> tuple[float, float, float, float]:
    """Convert raw features to normalized badness scores ∈ [0,1].

    Returns (b_blur, b_dark, b_glare, b_jpeg) where 1.0 = severe defect, 0.0 = clean.
    Uses camera-specific normalization for blur; absolute thresholds for others.
    """
    cam_med = params["camera_medians"].get(camera_id, params["global_median"])
    ratio = lap_var / cam_med

    # Blur: lower ratio = blurrier (inverse relationship)
    b_blur = np.clip((params["blur_threshold"] - ratio) / params["blur_range"], 0.0, 1.0)

    # Dark: lower p95 = darker (inverse relationship)
    b_dark = np.clip((params["dark_threshold"] - lum_p95) / params["dark_threshold"], 0.0, 1.0)

    # Glare: higher blob fraction = more glare (direct relationship)
    b_glare = np.clip((glare_blob - params["glare_threshold"]) / params["glare_range"], 0.0, 1.0)

    # JPEG: higher blockiness = more compression (direct relationship)
    b_jpeg = np.clip((blockiness - params["jpeg_threshold"]) / params["jpeg_range"], 0.0, 1.0)

    return (float(b_blur), float(b_dark), float(b_glare), float(b_jpeg))


def aggregate_score(badness: tuple[float, float, float, float], params: dict) -> float:
    """Weighted-sum aggregation of badness components → score ∈ [0, 100].

    Weighted sum outperformed max-risk on synthetic validation pool:
    - weighted_sum: R@20=0.286, P@20=0.800
    - max_risk: R@20=0.250, P@20=0.700

    Naturally accumulates multiple defects (blur+glare sev1 → score 54.5).
    """
    w = params["weights"]
    return 100.0 * (badness[0] * w["blur"] + badness[1] * w["dark"] +
                    badness[2] * w["glare"] + badness[3] * w["jpeg"])


def infer_defect_type(badness: tuple[float, float, float, float], params: dict) -> str:
    """Infer dominant defect type from badness components.

    Returns "none" if all components below epsilon (noise filter), else argmax.
    """
    if max(badness) < params["pred_defect_epsilon"]:
        return "none"
    return ["blur", "dark", "glare", "compression"][int(np.argmax(badness))]


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    data = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}

    # T02: image metadata table (image_id, path, camera_id, light, split)
    images_path = ctx.input_dir / "images.csv"
    if not images_path.exists():
        raise FileNotFoundError(f"required input missing: {images_path}")
    data["images"] = pd.read_csv(images_path)
    ctx.audit.log(actor="pipeline", action="load", item_id="images.csv",
                  after={"n_rows": int(len(data["images"]))})
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """T02 PoC: multi-defect scoring (blur + dark + glare + compression).

    Features:
    - Blur: camera-normalized Laplacian variance (cam_A/B have different optics)
    - Dark: lum_p95 (absolute threshold; night originals stay above 70)
    - Glare: largest connected saturated blob (local, not global mean)
    - Compression: JPEG 8×8 blockiness ratio

    Badness normalization: each feature → [0,1] via calibrated thresholds.
    Aggregation: weighted sum (blur 0.35, dark 0.30, glare 0.25, jpeg 0.10).
    Score ∈ [0, 100]; higher = review first.

    Decode failures: score=100 (within normal range), pred_defect_type="multiple".
    """
    images: pd.DataFrame = data["images"]
    params = load_params(ctx.config)
    rows = []

    for rec in images.itertuples(index=False):
        base = {"image_id": rec.image_id, "path": rec.path,
                "light": rec.light, "camera_id": rec.camera_id, "split": rec.split}

        try:
            img = load_rgb(ctx.input_dir / rec.path)
        except Exception as exc:
            ctx.audit.log(actor="pipeline", action="decode_failed", item_id=rec.image_id,
                          after={"error": type(exc).__name__, "path": rec.path})
            # Decode failure = worst-case within [0,100] range (not above it)
            rows.append(base | {
                "score": 100.0,
                "pred_defect_type": "multiple",
                "pred_action": "REVIEW",
                "b_blur": np.nan, "b_dark": np.nan, "b_glare": np.nan, "b_jpeg": np.nan,
                "reason": f"decode_failed:{type(exc).__name__}",
            })
            continue

        # Extract features
        gray = to_gray(img)
        lap_var = laplacian_variance(img)
        lum_p95 = float(np.percentile(gray, 95))
        glare_blob = glare_blob_fraction(gray, threshold=250)
        blockiness = blockiness_ratio(gray)

        # Badness normalization
        badness = compute_badness(lap_var, lum_p95, glare_blob, blockiness,
                                  rec.camera_id, params)

        # Aggregation
        score = aggregate_score(badness, params)
        pred_defect_type = infer_defect_type(badness, params)
        pred_action = "REVIEW" if score > params["pred_action_threshold"] else ""

        rows.append(base | {
            "score": score,
            "pred_defect_type": pred_defect_type,
            "pred_action": pred_action,
            "b_blur": badness[0], "b_dark": badness[1],
            "b_glare": badness[2], "b_jpeg": badness[3],
            "reason": f"wsum={score:.1f} blur={badness[0]:.2f} dark={badness[1]:.2f} "
                      f"glare={badness[2]:.2f} jpeg={badness[3]:.2f}",
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Top-B by score (descending), with deterministic tie-break on image_id.

    Evaluator uses mergesort (stable) → tie-break by original row order.
    We explicitly sort by (score DESC, image_id ASC) to ensure determinism.
    """
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first)")

    # Deterministic ranking: primary sort by score DESC, tie-break by image_id ASC
    ranked = scored.sort_values(["score", "image_id"], ascending=[False, True], kind="mergesort")

    q = make_review_queue(ranked, id_col="image_id", score_col="score", budget=budget,
                          reason_col="reason" if "reason" in ranked.columns else None,
                          action_col="pred_action" if "pred_action" in ranked.columns else None,
                          slice_col="light" if "light" in ranked.columns else None,
                          evidence_col="path" if "path" in ranked.columns else None)
    write_review_queue(q, ctx.out("review_queue.csv"))
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Render the offline contact sheet; apply reviewer overrides if they exist.

    T02 override semantics, using the standard `override_value` column:
      reject  (no value)  -> reviewer says "this image is fine": push score to the
                             bottom so it drops out of any top-B selection
      edit    (score)     -> replace the score with the reviewer's
      approve             -> keep the model score, recorded in the audit log
    The raw scored table is copied, never mutated; every change is audited.
    """
    render_contact_sheet(queue, ctx.out("contact_sheet.html"), image_root=ctx.input_dir,
                         title="T02 · top-20 suspected defects (PoC multi-defect)")

    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if not reviewed_path.exists():
        return scored

    reviewed = load_review_decisions(reviewed_path)
    decisions = reviewed.reviewer_decision

    # A decision only counts as "resolved" if it settles the item.
    # skip / escalate mean the reviewer did NOT clear the item -> still pending.
    resolved = decisions.isin({"approve", "reject", "edit"})
    ctx.stats["n_reviewed"] = int(len(reviewed))
    ctx.stats["n_resolved"] = int(resolved.sum())
    ctx.stats["n_skipped"] = int((decisions == "skip").sum())
    ctx.stats["n_escalated"] = int((decisions == "escalate").sum())

    final = apply_overrides(scored, reviewed, id_col="image_id", value_col="score", audit=ctx.audit)

    reject = reviewed[(decisions == "reject") & (reviewed.override_value.str.strip() == "")]
    for r in reject.itertuples(index=False):
        mask = final.image_id == r.item_id
        if not mask.any():
            continue
        before = final.loc[mask, "score"].tolist()
        # Reviewer cleared this item: drop it to the bottom of the ranking while
        # staying inside the score contract ([0, 100], finite) and clearing the
        # REVIEW / defect-type predictions so the output is self-consistent.
        final.loc[mask, "score"] = 0.0
        for col, val in (("pred_action", ""), ("pred_defect_type", "none")):
            if col in final.columns:
                final.loc[mask, col] = val
        ctx.audit.log(actor=r.reviewer, action="override:reject", item_id=r.item_id,
                      before=before[0] if len(before) == 1 else before, after=0.0,
                      reason=r.review_note or "reviewer: no defect")

    # Track confirmed defects for decision policy: only `approve` confirms a defect.
    approved = reviewed[decisions == "approve"]
    rejected = reviewed[decisions == "reject"]
    ctx.stats["n_confirmed_defects"] = int(len(approved))
    ctx.stats["confirmed_defect_ids"] = approved.item_id.tolist()
    ctx.stats["n_rejected"] = int(len(rejected))
    ctx.stats["rejected_ids"] = rejected.item_id.tolist()

    for r in approved.itertuples(index=False):
        ctx.audit.log(actor=r.reviewer, action="override:approve", item_id=r.item_id,
                      reason=r.review_note or "reviewer: defect confirmed")
    return final


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Batch decision policy: top-B review queue is risk-weighted sample of full batch.

    Decision logic:
    - No reviewer file → HOLD (triage pending review)
    - All top-B reviewed, zero confirmed defects → KEEP (batch clean)
    - At least one confirmed defect in top-B → RECAPTURE (batch contaminated)
    - Review incomplete → HOLD (awaiting completion)

    Only `approve` / `reject` / `edit` count as resolved. `skip` and `escalate`
    leave the item pending, so a queue filled with them is NOT a clean batch.

    Applies to full batch (96 images), not just top-20.
    76 unreviewed images share the batch decision.
    """
    from .common.review import AuditLog  # noqa: F401  (kept explicit for readers)

    n = int(ctx.stats.get("n_items", len(final)))
    budget = int(ctx.param("budget", 20))
    n_reviewed = int(ctx.stats.get("n_reviewed", 0))
    n_resolved = int(ctx.stats.get("n_resolved", n_reviewed))
    n_skipped = int(ctx.stats.get("n_skipped", 0))
    n_escalated = int(ctx.stats.get("n_escalated", 0))
    confirmed_ids = ctx.stats.get("confirmed_defect_ids", [])
    n_confirmed = len(confirmed_ids)

    owner = ctx.config.get("owner", "TODO-owner")
    evidence_files = [str(ctx.out(get_track(ctx.track).pred_file)),
                      str(ctx.out("review_queue.csv"))]

    # No reviewer file → HOLD (pending review)
    if n_reviewed == 0:
        return Decision(
            status="HOLD",
            reason_code="BASELINE_ONLY",
            reason=f"PoC multi-defect pipeline; top-{budget} queue awaits human review before batch decision",
            owner=owner,
            scope=ctx.track,
            evidence=evidence_files,
            metrics={"n_images": n, "batch_size": n, "budget": budget, "n_reviewed": 0,
                     "confirmed_defects": 0},
        )

    # Escalated items need a higher-level decision → HOLD regardless of progress
    if n_escalated > 0:
        return Decision(
            status="HOLD",
            reason_code="REVIEW_ESCALATED",
            reason=f"{n_escalated} item(s) escalated by reviewer in top-{budget}; "
                   f"batch decision deferred to escalation owner",
            owner=owner,
            scope=ctx.track,
            evidence=evidence_files + [str(ctx.out("review_queue_reviewed.csv")),
                                       str(ctx.out("audit_log.jsonl"))],
            metrics={"n_images": n, "batch_size": n, "budget": budget, "n_reviewed": n_reviewed,
                     "n_resolved": n_resolved, "n_escalated": n_escalated,
                     "n_skipped": n_skipped},
        )

    # Review incomplete (skip/escalate do not settle an item) → HOLD
    if n_resolved < budget:
        return Decision(
            status="HOLD",
            reason_code="REVIEW_INCOMPLETE",
            reason=f"Resolved {n_resolved}/{budget} top items "
                   f"({n_skipped} skipped, {n_escalated} escalated); awaiting completion before batch decision",
            owner=owner,
            scope=ctx.track,
            evidence=evidence_files + [str(ctx.out("review_queue_reviewed.csv"))],
            metrics={"batch_size": n, "budget": budget, "n_reviewed": n_reviewed,
                     "n_resolved": n_resolved, "n_skipped": n_skipped,
                     "review_completion": round(n_resolved / budget, 3)},
        )

    # All top-B resolved, zero defects → KEEP (batch clean)
    if n_confirmed == 0:
        return Decision(
            status="KEEP",  # maps to GO
            reason_code="REVIEW_COMPLETE_BATCH_CLEAN",
            reason=f"Top-{budget} resolved with zero confirmed defects; full batch ({n} images) released",
            owner=owner,
            scope=ctx.track,
            evidence=evidence_files + [str(ctx.out("review_queue_reviewed.csv")),
                                       str(ctx.out("audit_log.jsonl"))],
            metrics={"n_images": n, "batch_size": n, "budget": budget, "n_reviewed": n_reviewed,
                     "n_resolved": n_resolved, "confirmed_defects": 0},
        )

    # At least one defect confirmed → RECAPTURE (batch contaminated)
    return Decision(
        status="RECAPTURE",  # maps to REWORK
        reason_code="DEFECT_CONFIRMED_IN_BATCH",
        reason=f"{n_confirmed} defect(s) confirmed in top-{budget}; full batch ({n} images) requires rework",
        owner=owner,
        scope=ctx.track,
        evidence=evidence_files + [str(ctx.out("review_queue_reviewed.csv")),
                                   str(ctx.out("audit_log.jsonl"))],
        metrics={"n_images": n, "batch_size": n, "budget": budget, "n_reviewed": n_reviewed,
                 "confirmed_defects": n_confirmed,
                 "defect_image_ids": confirmed_ids[:10]},  # first 10 for brevity
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)

    # ranked_review.csv must be ranked: sort AFTER review so reviewer overrides
    # are reflected. Same deterministic tie-break as rank().
    # Rejected items sit at score 0.0 and tie with clean images, so an explicit
    # sort key pushes them behind every unrejected item (reviewer cleared them).
    rejected_ids = set(ctx.stats.get("rejected_ids", []))
    final = final.assign(
        _rejected=final["image_id"].astype(str).isin(rejected_ids).astype(int)
    )
    ranked = final.sort_values(["score", "_rejected", "image_id"],
                               ascending=[False, True, True], kind="mergesort")
    ranked = ranked.drop(columns=["_rejected"])
    ranked[spec.pred_columns + [c for c in ranked.columns if c not in spec.pred_columns]].to_csv(
        ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
