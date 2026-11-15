"""Integrated five-stage PoC pipeline for T07 face/plate redaction."""
from __future__ import annotations

import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import load_review_decisions
from .metrics.tracks import get_track
from .t07_contract import (
    load_images,
    validate_candidates,
    validate_final_regions,
)
from .t07_detector import detect_and_score
from .t07_export import export_redacted_images, write_redactions
from .t07_review import apply_review, build_queue, write_queue_and_sheet


# ------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    """Verify provenance and load the public image inventory."""
    if ctx.track != "t07":
       raise NotImplementedError(f"This pipeline implements T07, not {ctx.track}")

    manifest_path = ctx.input_dir / "manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)

    problems = verify_manifest(manifest_path)
    if problems:
        ctx.audit.log(
            actor="pipeline",
            action="provenance_problems",
            item_id=str(manifest_path),
            after=problems[:20],
        )
        if ctx.config.get("strict_provenance", True):
            raise ValueError(
                f"Provenance check failed with {len(problems)} problems; "
                f"first problems: {problems[:3]}"
            )

    images = load_images(ctx.input_dir)
    ctx.stats["n_images"] = int(len(images))
    return {"images": images}


# ---------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Detect faces/plates and validate all candidate boxes."""
    candidates = detect_and_score(ctx, data["images"])
    candidates = validate_candidates(candidates, data["images"])

    candidates.to_csv(ctx.out("candidates.csv"), index=False)

    ctx.stats["n_candidates"] = int(len(candidates))
    ctx.stats["n_faces"] = int((candidates["type"] == "face").sum())
    ctx.stats["n_plates"] = int((candidates["type"] == "plate").sum())
    ctx.stats["n_invalid_boxes"] = 0

    return candidates


# ------------------------------------------------------------- 03 rank
def rank(
    ctx: RunContext,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    """Create the fixed-budget review queue and offline contact sheet."""
    budget = int(ctx.param("budget", 15))
    queue = build_queue(candidates, budget=budget)

    write_queue_and_sheet(
        queue=queue,
        cands=candidates,
        out_dir=ctx.output_dir,
        image_root=ctx.input_dir,
        title="T07 face/plate redaction review queue",
    )

    ctx.stats["review_budget"] = budget
    ctx.stats["n_queued"] = int(len(queue))
    return queue


# ----------------------------------------------------------- 04 review
def review(
    ctx: RunContext,
    candidates: pd.DataFrame,
    queue: pd.DataFrame,
) -> pd.DataFrame:
    """Apply reviewer decisions when a reviewed queue is available."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"

    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
    else:
        reviewed = pd.DataFrame(
            columns=[
                "item_id",
                "reviewer_decision",
                "reviewer",
                "override_value",
                "review_note",
            ]
        )

    final_regions = apply_review(ctx, candidates, reviewed)
    return final_regions


# ----------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final_regions: pd.DataFrame) -> Decision:
    """Create a release decision from the review state."""
    review_stats = ctx.stats.get("review", {})
    pending = int(review_stats.get("pending", 0))
    escalated = list(review_stats.get("escalated", []))
    stale = list(review_stats.get("stale", []))

    evidence = [
        str(ctx.out("redactions.csv")),
        str(ctx.out("review_queue.csv")),
        str(ctx.out("audit_log.jsonl")),
    ]

    if len(final_regions) == 0:
        return Decision(
            status="HOLD",
            reason_code="NO_REDACTIONS",
            reason="No face or plate redaction regions were produced.",
            owner=str(ctx.config.get("owner") or "T07 Data Owner"),
            scope="t07-poc",
            evidence=evidence,
        )

    if escalated:
        return Decision(
            status="REWORK",
            reason_code="REVIEW_ESCALATED",
            reason=f"{len(escalated)} queued regions were escalated.",
            owner=str(ctx.config.get("owner") or "T07 Data Owner"),
            scope="t07-poc",
            evidence=evidence,
            metrics={"escalated": len(escalated), "pending": pending},
        )

    if stale:
        return Decision(
            status="REWORK",
            reason_code="STALE_REVIEW",
            reason=f"{len(stale)} review decisions do not match current candidates.",
            owner=str(ctx.config.get("owner") or "T07 Data Owner"),
            scope="t07-poc",
            evidence=evidence,
            metrics={"stale": len(stale), "pending": pending},
        )

    if pending > 0:
        return Decision(
            status="REWORK",
            reason_code="REVIEW_PENDING",
            reason=f"{pending} queued regions still require human review.",
            owner=str(ctx.config.get("owner") or "T07 Data Owner"),
            scope="t07-poc",
            evidence=evidence,
            metrics={"pending": pending},
        )

    return Decision(
        status="GO",
        reason_code="REVIEW_COMPLETE",
        reason="All queued regions were reviewed with no escalation.",
        owner=str(ctx.config.get("owner") or "T07 Data Owner"),
        scope="t07-poc",
        evidence=evidence,
        metrics={
            "final_regions": int(len(final_regions)),
            "pending": 0,
            "escalated": 0,
        },
    )


def run(ctx: RunContext) -> None:
    """Run all five mandatory T07 stages."""
    spec = get_track(ctx.track)

    data = load(ctx)
    candidates = process(ctx, data)
    queue = rank(ctx, candidates)
    final_regions = review(ctx, candidates, queue)

    final_regions = validate_final_regions(
        final_regions,
        data["images"],
    )

    ctx.stats["n_final_regions"] = int(len(final_regions))

    write_redactions(
        final_regions,
        ctx.out(spec.pred_file),
    )

    export_redacted_images(
        ctx,
        final_regions,
        data["images"],
    )

    release_decision = decide(ctx, final_regions)
    write_decision(
        release_decision,
        ctx.out("decision.json"),
        ctx.out("decision_log.csv"),
    )