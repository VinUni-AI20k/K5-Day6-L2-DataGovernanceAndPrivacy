"""src/pipeline.py — T08 (người A): load -> process (dry-run) -> rank -> review -> decide."""
import json
from pathlib import Path

import pandas as pd

from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, write_review_queue

from .t08 import graph, policy, review
from .t08.store import MockStore

POLICY_PATH = "configs/t08_policy.yaml"
COLS = ["item_id", "request_id", "artefact_id", "artefact_type", "action", "reason_code", "rule_id", "score", "reviewed_by"]


def load(ctx):
    problems = verify_manifest(ctx.input_dir / "manifest.csv")
    if problems:
        raise ValueError(f"provenance check failed: {problems[:3]}")
    return {"requests": json.loads((ctx.input_dir / "requests.json").read_text(encoding="utf-8")),
            "arts": graph.load_graph(ctx.input_dir / "data_graph.json"),
            "policy": policy.load_policy(ctx.param("policy_path", POLICY_PATH))}


def process(ctx, data):
    arts, ch = data["arts"], graph.children_map(data["arts"])
    rows = []
    for req in data["requests"]:
        for aid in graph.scope(arts, ch, req["subject_id"]):
            action, code, rule = policy.decide(aid, arts, req, data["policy"])
            rows.append({"item_id": f"{req['request_id']}:{aid}", "request_id": req["request_id"], "artefact_id": aid,
                         "artefact_type": arts[aid]["type"], "action": action, "reason_code": code, "rule_id": rule,
                         "score": 0 if action == "delete" else 1, "reviewed_by": ""})
            ctx.audit.log(actor="pipeline", action=f"plan:{action}", item_id=aid, reason=code, rule_id=rule,
                          request_id=req["request_id"])
    df = pd.DataFrame(rows, columns=COLS)
    df.to_csv(ctx.out("deletion_plan.csv"), index=False)
    return df


def decide_requests(ctx, actions, warns):
    owner = ctx.config.get("owner", "TODO-owner")
    statuses = []
    for rid, g in actions.groupby("request_id", sort=True):
        exc = g[g.action != "delete"]
        unsigned = int((exc.reviewed_by.fillna("") == "").sum())
        if unsigned:
            d = Decision("HOLD", "PENDING_DPO_REVIEW", f"{unsigned} exceptions not signed", owner, rid)
        elif (g.action == "retain_legal_hold").any():
            d = Decision("HOLD", "LEGAL_HOLD_ACTIVE", "retained until hold is lifted", owner, rid)
        else:
            d = Decision("GO", "ERASURE_COMPLETE" if exc.empty else "ERASURE_DONE_EXCEPTIONS_SIGNED", "request closed", owner, rid)
        write_decision(d, ctx.out(f"decisions/{rid}.json"), ctx.out("decision_log.csv"))
        statuses.append(d.status)
    if warns:
        write_decision(Decision("REWORK", "LINEAGE_INCONSISTENT", f"{len(warns)} lineage warnings", owner, "data-catalog",
                                metrics={"warnings": warns}), ctx.out("decisions/data-catalog.json"), ctx.out("decision_log.csv"))
    n_go = statuses.count("GO")
    overall = Decision("GO" if n_go == len(statuses) else "HOLD", "ALL_CLOSED" if n_go == len(statuses) else "OPEN_REQUESTS",
                       f"{n_go}/{len(statuses)} requests GO", owner, "t08-all")
    write_decision(overall, ctx.out("decision.json"), ctx.out("decision_log.csv"))


def run(ctx):
    if ctx.track != "t08":   # giữ test có sẵn tests/test_cli.py (chạy t02 -> phải exit 3)
        raise NotImplementedError(f"this group pipeline only implements t08, got {ctx.track}")
    data = load(ctx)
    actions = process(ctx, data)
    queue = review.build_queue(actions, int(ctx.param("budget", 100)))
    write_review_queue(queue, ctx.out("review_queue.csv"))
    review.render_review_table(queue, ctx.out("review_queue.html"))
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        actions = review.apply_review(actions, load_review_decisions(reviewed_path), ctx.audit)
    actions.to_csv(ctx.out("actions.csv"), index=False)
    ctx.stats["n_items"] = len(actions)
    if not ctx.param("dry_run", True):
        ctx.stats["store"] = MockStore(ctx.out("mock_store_state.json")).execute(actions, ctx.audit)
    decide_requests(ctx, actions, graph.lineage_warnings(data["arts"]))
