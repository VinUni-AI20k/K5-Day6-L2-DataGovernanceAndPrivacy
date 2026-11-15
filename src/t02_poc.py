"""T02 · PoC pipeline chạy được độc lập (để thử trước khi dán vào src/pipeline.py).

    python -m src.main --track t02 --pipeline src.t02_poc --output out/poc --run-name poc --offline --seed 42
    python -m src.main --track t02 --pipeline src.t02_baseline --output out/baseline --run-name baseline --offline --seed 42

Thành viên 3 có thể gọi trực tiếp `score_images(...)` trong `process()` của src/pipeline.py.
"""
from __future__ import annotations

import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import make_review_queue, write_review_queue
from .metrics.tracks import get_track
from .t02_scoring import score_images

OUT_COLUMNS = ["image_id", "score", "pred_defect_type", "pred_action"]


def load_images(ctx: RunContext) -> pd.DataFrame:
    manifest = ctx.input_dir / "manifest.csv"
    if manifest.exists():
        problems = verify_manifest(manifest)
        if problems:
            ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
            if ctx.config.get("strict_provenance", True):
                raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    return pd.read_csv(ctx.input_dir / "images.csv")


def finish(ctx: RunContext, scored: pd.DataFrame, label: str) -> None:
    """Rank -> review queue + contact sheet -> ranked_review.csv -> decision."""
    spec = get_track(ctx.track)
    budget = int(ctx.param("budget", 20))
    ctx.stats["n_items"] = len(scored)
    scored = scored.assign(slice=scored["camera_id"].astype(str) + "/" + scored["light"].astype(str))
    q = make_review_queue(scored, "image_id", "score", budget, reason_col="reason",
                          action_col="pred_action" if "pred_action" in scored else None,
                          slice_col="slice", evidence_col="path")
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(q, ctx.out("contact_sheet.html"), image_root=ctx.input_dir, title=f"T02 {label} · top-{budget}")
    ranked = scored.sort_values("score", ascending=False, kind="mergesort")
    cols = [c for c in OUT_COLUMNS if c in ranked.columns]
    out = ranked[cols].copy()
    out["score"] = out["score"].replace([float("inf")], 1e9)   # CSV an toàn cho evaluator
    out.to_csv(ctx.out(spec.pred_file), index=False)
    n_flag = int((ranked["pred_action"] == "RECAPTURE").sum()) if "pred_action" in ranked else budget
    write_decision(
        Decision(status="HOLD", reason_code="PENDING_HUMAN_REVIEW",
                 reason=f"{label}: {n_flag}/{len(ranked)} ảnh nghi lỗi; chờ reviewer xác nhận top-{budget} trước khi KEEP/RECAPTURE",
                 owner=ctx.config.get("owner", "TODO-owner"), scope=ctx.track,
                 evidence=[str(ctx.out(spec.pred_file)), str(ctx.out("review_queue.csv"))],
                 metrics={"n_items": len(ranked), "n_flagged": n_flag, "budget": budget}),
        ctx.out("decision.json"), ctx.out("decision_log.csv"))


def run(ctx: RunContext) -> None:
    images = load_images(ctx)                                  # 01 load
    scored = score_images(images, ctx.input_dir, ctx.config)   # 02 process
    finish(ctx, scored, "PoC")                                 # 03 rank · 04 review · 05 decide
