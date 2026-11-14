"""T02 Raw QC Triage — group pipeline (the 5 automated contract steps).

Contract (grader runs exactly this):
    python -m src.main --input fixtures/t02_raw_qc --config configs/lab.yaml --output out/

Algorithm = FROZEN PoC v1 (src/poc/t02_v1.py): group-relative features, thresholds
calibrated on all 56 dev labels BEFORE eval labels arrived (reports/t02_calibration.md).
Never reads fixtures/*/gt/; no network; seed 42.

Step 05 decide policy (frozen before eval):
    any predicted severity 2 -> REWORK (recapture needed)
    else any severity 1 flag -> HOLD (goes to the human review queue)
    else                     -> GO (release as-is)
"""
from __future__ import annotations

import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track
from .poc import t02_v1


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    return {"images": pd.read_csv(ctx.input_dir / "images.csv")}


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Group-relative features + frozen thresholds + continuous margin score."""
    scored = t02_v1.score_frame(t02_v1.extract(data["images"], ctx.input_dir))
    return scored.merge(data["images"][["image_id", "path"]], on="image_id", how="left")


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    budget = int(ctx.param("budget", 20))
    q = make_review_queue(
        scored, "image_id", "score", budget,
        reason_col="pred_defect_type", action_col="pred_action",
        slice_col="grp", evidence_col="path",
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Apply human overrides if a reviewed queue exists (out/review_queue_reviewed.csv)."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        final = apply(scored, reviewed, ctx)
        return final
    ctx.stats["n_reviewed"] = 0
    return scored


def apply(scored: pd.DataFrame, reviewed: pd.DataFrame, ctx: RunContext) -> pd.DataFrame:
    """`edit`/`reject` rows override pred_severity (e.g. override_value=2 → recapture)."""
    out = scored.copy()
    for r in reviewed.itertuples(index=False):
        if r.reviewer_decision in {"reject", "escalate"}:      # reviewer says this IS a defect
            mask = out["image_id"] == r.item_id
            out.loc[mask, "pred_severity"] = max(out.loc[mask, "pred_severity"], 1)
        if r.reviewer_decision in {"approve", "skip"}:          # reviewer cleared it
            mask = out["image_id"] == r.item_id
            out.loc[mask, "pred_severity"] = 0
        if r.reviewer_decision in {"edit", "reject"} and str(r.override_value) != "":
            mask = out["image_id"] == r.item_id
            out.loc[mask, "pred_severity"] = int(r.override_value)
        ctx.audit.log(actor=r.reviewer, action=f"review:{r.reviewer_decision}", item_id=r.item_id,
                      reason=r.review_note)
    out["pred_action"] = out["pred_severity"].map(lambda s: "RECAPTURE" if s >= 2 else "KEEP")
    return out


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    n_sev2 = int((final["pred_severity"] == 2).sum())
    n_sev1 = int((final["pred_severity"] == 1).sum())
    owner = ctx.config.get("owner", "pipeline")
    if n_sev2:
        return Decision(status="REWORK", reason_code="SEV2_PREDICTED",
                        reason=f"{n_sev2} images predicted severity 2 → recapture before release",
                        owner=owner, scope=ctx.track,
                        evidence=[str(ctx.out("ranked_review.csv")), str(ctx.out("review_queue.csv"))])
    if n_sev1:
        return Decision(status="HOLD", reason_code="SEV1_REVIEW",
                        reason=f"{n_sev1} images flagged severity 1 → human review queue",
                        owner=owner, scope=ctx.track,
                        evidence=[str(ctx.out("review_queue.csv"))])
    return Decision(status="GO", reason_code="NO_DEFECT_FLAGGED",
                    reason="no image crosses a frozen defect threshold", owner=owner, scope=ctx.track)


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    ctx.stats["n_flagged"] = int((final["pred_defect_type"] != "none").sum())
    final[["image_id", "score", "pred_defect_type", "pred_severity", "pred_action"]].to_csv(
        ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
