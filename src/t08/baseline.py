"""Baseline đề T08 (người B): chỉ xoá bản raw theo filename, không tìm derived/backup."""
import json

import pandas as pd

from src.common.decision import Decision, write_decision
from src.common.manifest import verify_manifest

from .graph import load_graph


def run(ctx):
    problems = verify_manifest(ctx.input_dir / "manifest.csv")
    if problems:
        raise ValueError(f"provenance check failed: {problems[:3]}")
    reqs = json.loads((ctx.input_dir / "requests.json").read_text(encoding="utf-8"))
    arts = load_graph(ctx.input_dir / "data_graph.json")
    rows = []
    for req in reqs:
        prefix = f"drive_{req['subject_id']}_"
        for aid, a in sorted(arts.items()):
            if a["type"] == "raw_video" and a.get("filename", "").startswith(prefix):
                rows.append({"request_id": req["request_id"], "artefact_id": aid, "action": "delete"})
                ctx.audit.log(actor="baseline", action="delete", item_id=aid, reason="filename match",
                              request_id=req["request_id"])
    pd.DataFrame(rows, columns=["request_id", "artefact_id", "action"]).to_csv(ctx.out("actions.csv"), index=False)
    ctx.stats["n_items"] = len(rows)
    write_decision(Decision(status="GO", reason_code="BASELINE_FILENAME_ONLY", reason="Baseline deletes raw by filename",
                            owner=ctx.config.get("owner", "baseline"), scope="t08-baseline"),
                   ctx.out("decision.json"), ctx.out("decision_log.csv"))
