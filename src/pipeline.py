"""src/pipeline.py — T08 (người A) · KHUNG A3: chạy được end-to-end với chính sách STUB.

Stub: mọi artefact có subject_id của request trong subject_ids -> action = "delete".
Chưa có lineage thật (B), luật thật (B), hàng chờ duyệt (D). Mục đích: `src.main` exit 0,
actions.csv đủ 158 dòng để cả nhóm chạy được. Sang A4 sẽ thay bằng bản nối module thật.
"""
import json

import pandas as pd

from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest

COLS = ["item_id", "request_id", "artefact_id", "artefact_type", "action",
        "reason_code", "rule_id", "score", "reviewed_by"]


def load(ctx):
    problems = verify_manifest(ctx.input_dir / "manifest.csv")
    if problems:
        raise ValueError(f"provenance check failed: {problems[:3]}")
    requests = json.loads((ctx.input_dir / "requests.json").read_text(encoding="utf-8"))
    artefacts = json.loads((ctx.input_dir / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]
    return {"requests": requests, "arts": {a["artefact_id"]: a for a in artefacts}}


def run(ctx):
    # BẮT BUỘC giữ: tests/test_cli.py chạy pipeline với track t02 và chờ exit 3.
    if ctx.track != "t08":
        raise NotImplementedError(f"this group pipeline only implements t08, got {ctx.track}")

    data = load(ctx)
    rows = [
        {"item_id": f"{r['request_id']}:{aid}", "request_id": r["request_id"], "artefact_id": aid,
         "artefact_type": a["type"], "action": "delete", "reason_code": "STUB", "rule_id": "STUB",
         "score": 0, "reviewed_by": ""}
        for r in data["requests"]
        for aid, a in sorted(data["arts"].items())
        if r["subject_id"] in a["subject_ids"]
    ]
    pd.DataFrame(rows, columns=COLS).to_csv(ctx.out("actions.csv"), index=False)
    write_decision(
        Decision("HOLD", "STUB", "pipeline stub - chua co chinh sach that", ctx.config["owner"], "t08-all"),
        ctx.out("decision.json"), ctx.out("decision_log.csv"))