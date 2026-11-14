"""T08 baseline (docs/tracks/T08.md §4): delete the raw file by filename, ignore derived/backup.  [P5]

    python -m src.main --config configs/lab.yaml --pipeline src.baselines.t08_raw_only --output out/baseline --run-name baseline --offline --seed 42

No lineage, no exception check — the naive bar the PoC must beat. It exhibits both required
failure modes: copies/embeddings survive, and raw videos under legal hold get deleted anyway.
"""
from __future__ import annotations

import json

import pandas as pd

from ..common.context import RunContext
from ..common.decision import Decision, write_decision


def run(ctx: RunContext) -> None:
    graph = json.loads((ctx.input_dir / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]
    requests = json.loads((ctx.input_dir / "requests.json").read_text(encoding="utf-8"))
    rows = []
    for req in requests:
        s = req["subject_id"]
        for a in graph:
            if a.get("type") == "raw_video" and f"_{s}_" in (a.get("filename") or ""):
                rows.append({"request_id": req["request_id"], "artefact_id": a["artefact_id"], "action": "delete"})
                ctx.audit.log(actor="baseline", action="delete", item_id=a["artefact_id"],
                              reason=f"filename match {a['filename']}", request_id=req["request_id"])
    out = pd.DataFrame(rows, columns=["request_id", "artefact_id", "action"])
    out.to_csv(ctx.out("actions.csv"), index=False)
    ctx.stats["n_items"] = len(out)
    write_decision(Decision("HOLD", "BASELINE_ONLY", "Raw-only baseline: never use for real deletion",
                            ctx.config.get("owner", "baseline"), scope="t08", evidence=[str(ctx.out("actions.csv"))]),
                   ctx.out("decision.json"), ctx.out("decision_log.csv"))
