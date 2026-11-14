"""Baseline T02: một ngưỡng Laplacian variance toàn ảnh duy nhất (đúng như docs/tracks/T02.md §4).

    python -m src.main --track t02 --pipeline src.baseline_t02 --output out/baseline --run-name baseline --offline --seed 42

Ý tưởng: ảnh càng ít cạnh sắc (Laplacian variance thấp) càng nghi mờ -> điểm nghi lỗi cao.
    score = 1 / (1 + lap_var / ref)        # ref = median lap_var của split dev (không dùng nhãn)

Cố ý KHÔNG dùng camera_id, light, độ sáng hay bất kỳ feature nào khác: đây là mốc để PoC phải vượt qua và
để lộ ba failure mode của đề (ảnh đêm sạch bị báo nhầm, glare cục bộ bị bỏ sót, cam_B bị phạt oan).

Giao thức: `ref` chỉ tính từ split dev (56 ảnh) và không cần nhãn; split eval chỉ được chấm điểm, không tune.
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


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems and ctx.config.get("strict_provenance", True):
        raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")

    items = pd.read_csv(ctx.input_dir / "images.csv")                                   # 01 load
    items["lap_var"] = [laplacian_variance(load_rgb(ctx.input_dir / p)) for p in items.path]  # 02 process
    dev_split = ctx.config.get("params", {}).get("dev_split", "dev")
    ref = float(items.loc[items.split == dev_split, "lap_var"].median())               # chỉ dùng dev, không nhãn
    items["score"] = 1.0 / (1.0 + items.lap_var / ref)
    items["reason"] = items.lap_var.map(lambda v: f"global Laplacian var={v:.1f}")
    ctx.stats.update({"n_items": len(items), "lap_ref_dev_median": round(ref, 3)})

    budget = int(ctx.param("budget", 20))                                               # 03 rank
    ranked = items.sort_values("score", ascending=False, kind="mergesort").reset_index(drop=True)
    ranked["pred_action"] = np.where(ranked.index < budget, "RECAPTURE", "KEEP")
    q = make_review_queue(ranked, "image_id", "score", budget, reason_col="reason", action_col="pred_action",
                          slice_col="light", evidence_col="path")
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(q, ctx.out("contact_sheet.html"), image_root=ctx.input_dir,           # 04 review
                         title=f"T02 baseline (global Laplacian) top-{budget}")
    ranked[spec.pred_columns + [c for c in ranked.columns if c not in spec.pred_columns]].to_csv(
        ctx.out(spec.pred_file), index=False)
    write_decision(Decision(status="HOLD", reason_code="BASELINE_ONLY",                         # 05 decide
                            reason="Global-Laplacian baseline: reference bar, never release on this",
                            owner=ctx.config.get("owner", "baseline"), scope=ctx.track,
                            evidence=[str(ctx.out(spec.pred_file))]),
                   ctx.out("decision.json"), ctx.out("decision_log.csv"))
