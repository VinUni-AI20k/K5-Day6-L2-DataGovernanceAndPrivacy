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

import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    data = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}
    # TODO: load the tables/images your track needs, e.g.
    # data["images"] = pd.read_csv(ctx.input_dir / "images.csv")
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    spec = get_track(ctx.track)
    raise NotImplementedError(
        f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
        f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
    )


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Top-budget items by score; build review queue and render contact sheet with Before/After + bboxes."""
    budget = int(ctx.param("budget", 10))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first), "
                         "or adapt rank() to your track")
    
    # Create review queue with top-budget items
    q = make_review_queue(
        scored, 
        id_col=scored.columns[0], 
        score_col="score", 
        budget=budget,
        reason_col="reason" if "reason" in scored.columns else None,
        action_col="suggested_action" if "suggested_action" in scored.columns else None,
        slice_col="slice" if "slice" in scored.columns else None,
        evidence_col="evidence_path" if "evidence_path" in scored.columns else None,
    )
    
    # Map before_path from scored to q if it exists
    if "before_path" in scored.columns:
        scored_map = scored.set_index(scored.columns[0])[["before_path"]].to_dict("index")
        q["before_path"] = q["item_id"].apply(lambda x: scored_map.get(x, {}).get("before_path", ""))
    
    # Write review queue CSV
    write_review_queue(q, ctx.out("review_queue.csv"))
    
    # Prepare boxes_by_item if objects.csv exists
    boxes_by_item = {}
    objects_file = ctx.input_dir / "objects.csv"
    if objects_file.exists():
        try:
            objects = pd.read_csv(objects_file)
            if all(c in objects.columns for c in ["item_id", "x", "y", "w", "h"]):
                for item_id in q["item_id"]:
                    item_boxes = objects[objects["item_id"].astype(str) == str(item_id)]
                    if len(item_boxes) > 0:
                        boxes_by_item[str(item_id)] = [
                            {
                                "x": row["x"],
                                "y": row["y"],
                                "w": row["w"],
                                "h": row["h"],
                                "label": row.get("label", ""),
                                "color": row.get("color", "red"),
                            }
                            for _, row in item_boxes.iterrows()
                        ]
        except Exception as e:
            ctx.audit.log(actor="pipeline", action="objects_load_error", item_id="objects.csv", after=str(e))
    
    # Render contact sheet with Before/After comparison
    before_col = "before_path" if "before_path" in q.columns else None
    render_contact_sheet(
        q,
        ctx.out("contact_sheet.html"),
        image_col="evidence_path",
        before_image_col=before_col,
        image_root=ctx.input_dir,
        boxes_by_item=boxes_by_item,
        title=f"Review Queue - {ctx.track}",
    )
    
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Apply human review decisions: if review_queue_reviewed.csv exists, load it and apply overrides to pred_unusable."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if not reviewed_path.exists():
        return scored
    
    # Load reviewed decisions
    reviewed = load_review_decisions(reviewed_path)
    ctx.stats["n_reviewed"] = len(reviewed)
    
    # Apply overrides to pred_unusable column
    if "pred_unusable" in scored.columns:
        final = apply_overrides(
            scored,
            reviewed,
            id_col=scored.columns[0],
            value_col="pred_unusable",
            audit=ctx.audit,
        )
        # Robust casting: convert to numeric, handle errors, fill NaN with 0, then to int (0/1)
        final["pred_unusable"] = pd.to_numeric(final["pred_unusable"], errors="coerce").fillna(0).astype(int)
        return final
    
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Release decision policy:
    - HOLD if provenance manifest is missing
    - REWORK if unusable_rate exceeds max_unusable_rate
    - GO if QC and provenance checks pass
    """
    owner = ctx.config.get("owner", "Member5-T03")
    
    # Check provenance: transform_manifest.csv must exist
    provenance_manifest = ctx.output_dir / "transform_manifest.csv"
    if not provenance_manifest.exists():
        return Decision(
            status="HOLD",
            reason_code="MISSING_PROVENANCE_MANIFEST",
            reason="Transform manifest (provenance record) is missing. Cannot proceed without provenance documentation.",
            owner=owner,
            scope=ctx.track,
            evidence=[str(provenance_manifest)],
            metrics={"total_items": len(final)},
        )
    
    # Check unusable rate threshold
    if "pred_unusable" in final.columns:
        unusable_rate = final["pred_unusable"].mean()
        max_unusable_rate = float(ctx.param("max_unusable_rate", 0.30))
        
        metrics = {
            "total_items": len(final),
            "unusable_count": int(final["pred_unusable"].sum()),
            "unusable_rate": float(unusable_rate),
            "max_unusable_rate": max_unusable_rate,
        }
        
        if unusable_rate > max_unusable_rate:
            return Decision(
                status="REWORK",
                reason_code="UNUSABLE_RATE_EXCEEDED",
                reason=f"Unusable rate {unusable_rate:.2%} exceeds threshold {max_unusable_rate:.2%}. Data quality issues require rework.",
                owner=owner,
                scope=ctx.track,
                evidence=[str(ctx.output_dir / "review_queue_reviewed.csv")] if (ctx.output_dir / "review_queue_reviewed.csv").exists() else [],
                metrics=metrics,
            )
    else:
        metrics = {"total_items": len(final)}
    
    # All checks passed: GO
    return Decision(
        status="GO",
        reason_code="QC_AND_PROVENANCE_PASSED",
        reason="Data passes QC checks and provenance validation. Ready for release.",
        owner=owner,
        scope=ctx.track,
        evidence=[str(provenance_manifest)] if provenance_manifest.exists() else [],
        metrics=metrics,
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
