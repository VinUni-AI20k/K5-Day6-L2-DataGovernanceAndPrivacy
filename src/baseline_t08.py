"""T08 baseline, as specified in docs/tracks/T08.md section 4:
"delete ONE raw copy found by filename, do not look for derived data or backups".

It is intentionally naive - no lineage, no legal-hold / permission / multi-subject checks - and is
the bar the PoC (src/pipeline.py) must beat on the same input, same seed.

    python -m src.main --track t08 --pipeline src.baseline_t08 --output out/baseline --run-name baseline --offline --seed 42
"""
from __future__ import annotations

import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .metrics.tracks import get_track
from .pipeline import load


def raw_by_filename(artefacts: list[dict], subject_id: str) -> str | None:
    """First raw video whose filename mentions the subject (e.g. drive_subj_01_001.mp4)."""
    hits = sorted(a["artefact_id"] for a in artefacts
                  if a.get("type") == "raw_video" and subject_id in str(a.get("filename", "")))
    return hits[0] if hits else None


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)                                    # same input + provenance check as the PoC
    rows = []
    for rq in data["requests"]:
        aid = raw_by_filename(data["artefacts"], rq["subject_id"])
        if aid is None:
            continue
        rows.append({"request_id": rq["request_id"], "artefact_id": aid, "action": "delete"})
        ctx.audit.log(actor="baseline", action="plan:delete", item_id=aid, after="delete",
                      reason="BASELINE_RAW_BY_FILENAME", request_id=rq["request_id"])
    ctx.stats["n_items"] = len(rows)
    pd.DataFrame(rows, columns=spec.pred_columns).to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(
        Decision(status="HOLD", reason_code="BASELINE_ONLY",
                 reason="Baseline deletes one raw file per request and checks no exception: never act on this",
                 owner=ctx.config.get("owner", "baseline"), scope=ctx.track, evidence=[str(ctx.out(spec.pred_file))]),
        ctx.out("decision.json"), ctx.out("decision_log.csv"))
