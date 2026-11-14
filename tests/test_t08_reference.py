"""Tests with hand-authored cases; TEST_ONLY is not a real reviewer."""
import copy
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.common.context import RunContext
from src.common.review import AuditLog
from src.pipeline import load, process, rank, review, decide
from src.t08.input_data import load_input
from src.t08.lineage import find_related
from src.t08.policy import propose_action
from src.t08.executor import execute_mock

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def context(tmp_path):
    inp, out = tmp_path / "input", tmp_path / "out"
    inp.mkdir()
    out.mkdir()
    for name in ("requests.json", "data_graph.json"):
        (inp / name).write_bytes((ROOT / "examples/t08_demo" / name).read_bytes())
    with (inp / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["file_id", "path", "source", "license", "split", "group_id", "sha256"])
        writer.writeheader()
        for name in ("requests.json", "data_graph.json"):
            writer.writerow({"file_id": name, "path": name, "source": "hand-authored test", "license": "CC0", "split": "dev", "group_id": "test",
                             "sha256": hashlib.sha256((inp / name).read_bytes()).hexdigest()})
    return RunContext(track="t08", input_dir=inp, output_dir=out,
                      config={"owner": "TEST_ONLY", "params": {"actor": "data-platform", "dry_run": True}},
                      seed=42, rng=np.random.default_rng(42), audit=AuditLog(out / "audit_log.jsonl"))


def plan(ctx):
    data = load(ctx)
    proposed = process(ctx, data)
    return data, proposed, rank(ctx, proposed)


def approve_safe(ctx, queue):
    q = queue.copy()
    mask = q.suggested_action == "delete"
    q.loc[mask, "reviewer"] = "TEST_ONLY"
    q.loc[mask, "reviewer_decision"] = "approve"
    q.to_csv(ctx.out("review_queue_reviewed.csv"), index=False)


def test_loader_and_scope(context):
    data, proposed, queue = plan(context)
    assert len(data["requests"]) == 2 and len(data["artefacts"]) == 9
    assert len(proposed) == 10 and len(queue) == 10
    assert not proposed.item_id.duplicated().any()
    a = find_related(data["requests"][0], data["artefacts"])
    assert {x["artefact_id"] for x in a} == {"rawA", "frameA", "backupA", "holdA", "vendorA", "unknownA", "shared", "inferred"}
    assert next(x for x in a if x["artefact_id"] == "inferred")["_scope_inferred"]


def test_duplicate_id_fails(context):
    p = context.input_dir / "data_graph.json"
    graph = json.loads(p.read_text())
    graph["artefacts"].append(copy.deepcopy(graph["artefacts"][0]))
    p.write_text(json.dumps(graph))
    with pytest.raises(ValueError, match="Duplicate artefact"):
        load_input(context.input_dir)


def test_manifest_tampering_fails(context):
    p = context.input_dir / "requests.json"
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(ValueError, match="provenance"):
        load(context)


def test_traversal_cycle_terminates():
    arts = [{"artefact_id": "x", "subject_ids": ["A"], "parent_ids": ["y"]},
            {"artefact_id": "y", "subject_ids": ["A"], "parent_ids": ["x"]}]
    assert [a["artefact_id"] for a in find_related({"subject_id": "A"}, arts)] == ["x", "y"]


def test_shared_parent_does_not_expand_into_other_subject():
    arts = [{"artefact_id": "shared", "subject_ids": ["A", "B"], "parent_ids": []},
            {"artefact_id": "cropB", "subject_ids": ["B"], "parent_ids": ["shared"]}]
    assert [a["artefact_id"] for a in find_related({"subject_id": "A"}, arts)] == ["shared"]


@pytest.mark.parametrize("key,action,reason", [
    ("rawA", "delete", "SINGLE_SUBJECT_AUTHORIZED"),
    ("holdA", "retain_legal_hold", "LEGAL_HOLD"),
    ("vendorA", "escalate", "NO_PERMISSION"),
    ("unknownA", "escalate", "UNKNOWN_ORIGIN"),
    ("shared", "escalate", "MULTI_SUBJECT"),
    ("inferred", "escalate", "SUBJECT_UNCONFIRMED"),
])
def test_policy_cases(context, key, action, reason):
    data = load_input(context.input_dir)
    art = next(a for a in find_related(data["requests"][0], data["artefacts"]) if a["artefact_id"] == key)
    row = propose_action(data["requests"][0], art, "data-platform")
    assert (row["action"], row["reason_code"]) == (action, reason)


def test_identity_actor_and_missing_parent(context):
    data = load_input(context.input_dir)
    req, art = copy.deepcopy(data["requests"][0]), copy.deepcopy(data["artefacts"][0])
    req["identity_verified"] = False
    assert propose_action(req, art, "data-platform")["reason_code"] == "IDENTITY_UNVERIFIED"
    req["identity_verified"] = True
    assert propose_action(req, art, "intruder")["reason_code"] == "NO_PERMISSION"
    art["_missing_parents"] = ["gone"]
    assert propose_action(req, art, "data-platform")["reason_code"] == "MISSING_PARENT"


def test_no_review_means_no_execution(context):
    _, proposed, q = plan(context)
    context.config["params"]["dry_run"] = False
    final = execute_mock(context, review(context, proposed, q))
    assert (final.execution_status == "pending_approval").sum() == 4
    assert not context.out("mock_state.json").exists()
    assert decide(context, final).status == "HOLD"


def test_dry_run_then_execute_and_idempotency(context):
    before = (context.input_dir / "data_graph.json").read_bytes()
    _, proposed, q = plan(context)
    approve_safe(context, q)
    final = review(context, proposed, q)
    dry = execute_mock(context, final)
    assert (dry.execution_status == "planned_delete").sum() == 4
    assert not context.out("mock_state.json").exists()
    context.config["params"]["dry_run"] = False
    first = execute_mock(context, final)
    second = execute_mock(context, final)
    assert (first.execution_status == "deleted").sum() == 4
    assert (second.execution_status == "already_deleted").sum() == 4
    state = json.loads(context.out("mock_state.json").read_text())
    assert len(state["deleted"]) == 4
    assert (context.input_dir / "data_graph.json").read_bytes() == before
    logs = context.audit.read()
    assert len([r for r in logs if r["action"] == "mock_delete_intent"]) == 4
    assert all("request_id" in r["extra"] for r in logs)


@pytest.mark.parametrize("tamper", ["stale", "duplicate", "unknown"])
def test_invalid_review_rejected(context, tamper):
    _, proposed, q = plan(context)
    if tamper == "stale":
        q["plan_hash"] = "OLD_PLAN"
    elif tamper == "duplicate":
        q = pd.concat([q, q.iloc[[0]]], ignore_index=True)
    else:
        q.loc[0, "item_id"] = "REQ-Z::unknown"
    q.to_csv(context.out("review_queue_reviewed.csv"), index=False)
    with pytest.raises(ValueError):
        review(context, proposed, q)


@pytest.mark.parametrize("key,target", [("vendorA", "delete"), ("holdA", "escalate")])
def test_review_cannot_bypass_blocker(context, key, target):
    _, proposed, q = plan(context)
    mask = q.item_id == "REQ-A::" + key
    q.loc[mask, ["reviewer", "reviewer_decision", "override_value", "review_note"]] = [
        "TEST_ONLY", "edit", target, "test bypass"]
    q.to_csv(context.out("review_queue_reviewed.csv"), index=False)
    with pytest.raises(ValueError):
        review(context, proposed, q)


def test_safe_delete_can_be_escalated(context):
    _, proposed, q = plan(context)
    mask = q.item_id == "REQ-A::rawA"
    q.loc[mask, ["reviewer", "reviewer_decision", "override_value", "review_note"]] = [
        "TEST_ONLY", "edit", "escalate", "Need more evidence"]
    q.to_csv(context.out("review_queue_reviewed.csv"), index=False)
    final = review(context, proposed, q)
    row = final.loc[final.item_id == "REQ-A::rawA"].iloc[0]
    assert row.action == "escalate" and not row.execution_approved


def test_executor_rechecks_policy(context):
    _, proposed, _ = plan(context)
    mask = proposed.artefact_id == "vendorA"
    proposed.loc[mask, ["action", "execution_approved", "reviewer"]] = ["delete", True, "TEST_ONLY"]
    with pytest.raises(ValueError, match="policy blocks"):
        execute_mock(context, proposed)


def test_locked_executor_does_not_touch_existing_lock(context):
    _, proposed, _ = plan(context)
    context.out(".execution.lock").write_text("other process")
    with pytest.raises(ValueError, match="locked"):
        execute_mock(context, proposed)
    assert context.out(".execution.lock").read_text() == "other process"


def test_resume_after_state_written_before_completed_audit(context, monkeypatch):
    _, proposed, q = plan(context)
    approve_safe(context, q)
    final = review(context, proposed, q)
    context.config["params"]["dry_run"] = False
    original = context.audit.log
    def fail_once(*args, **kwargs):
        if kwargs.get("action") == "execution:deleted":
            raise OSError("simulated crash after atomic state")
        return original(*args, **kwargs)
    monkeypatch.setattr(context.audit, "log", fail_once)
    with pytest.raises(OSError):
        execute_mock(context, final)
    assert not context.out(".execution.lock").exists()
    monkeypatch.setattr(context.audit, "log", original)
    resumed = execute_mock(context, final)
    assert (resumed.execution_status == "already_deleted").sum() == 1
    assert (resumed.execution_status == "deleted").sum() == 3
    assert len(json.loads(context.out("mock_state.json").read_text())["deleted"]) == 4
