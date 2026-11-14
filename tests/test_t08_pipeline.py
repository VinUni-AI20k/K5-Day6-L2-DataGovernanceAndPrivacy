"""T08 end to end on the fixture: one command, idempotency, review overrides, failure paths."""
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from src import main as runner
from src.t08_policy import ACTIONS

FX = Path("fixtures/t08_deletion")
GRAPH = json.loads((FX / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]


def run_poc(out, *extra):
    return runner.main(["--track", "t08", "--output", str(out), "--offline", "--seed", "42", "--run-name", "poc", *extra])


def audit(out):
    return [json.loads(line) for line in (out / "audit_log.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def review(out, decisions, reviewer="tester"):
    """decisions: {item_id: (reviewer_decision, override_value, note)} -> out/review_queue_reviewed.csv"""
    q = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    for item, (dec, val, note) in decisions.items():
        assert item in set(q.item_id), item
        q.loc[q.item_id == item, ["reviewer", "reviewer_decision", "override_value", "review_note"]] = [reviewer, dec, val, note]
    q.to_csv(out / "review_queue_reviewed.csv", index=False)


# ------------------------------------------------------------------ success path
def test_poc_end_to_end_one_command(tmp_path):
    assert run_poc(tmp_path) == 0
    for f in ["actions.csv", "audit_log.jsonl", "dry_run_plan.csv", "review_queue.csv", "contact_sheet.html",
              "mock_store_state.json", "deletion_evidence.json", "request_summary.csv", "decision.json", "run_info.json"]:
        assert (tmp_path / f).exists(), f
    act = pd.read_csv(tmp_path / "actions.csv")
    assert not act.duplicated(["request_id", "artefact_id"]).any()
    assert set(act.action) <= set(ACTIONS)
    # every pair where the requester is tagged on the artefact has a row
    reqs = json.loads((FX / "requests.json").read_text(encoding="utf-8"))
    scope = {(q["request_id"], a["artefact_id"]) for q in reqs for a in GRAPH if q["subject_id"] in a["subject_ids"]}
    assert scope <= set(zip(act.request_id, act.artefact_id))
    # audit trace: every acted artefact has an entry keyed by artefact_id (what eval_t08 checks)
    assert set(act.artefact_id) <= {e["item_id"] for e in audit(tmp_path)}
    d = json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))
    assert (d["status"], d["reason_code"]) == ("HOLD", "EXCEPTIONS_PENDING_REVIEW") and d["owner"].strip()


def test_no_exception_artefact_is_deleted_by_the_machine(tmp_path):
    assert run_poc(tmp_path) == 0
    deleted = set(pd.read_csv(tmp_path / "actions.csv").query("action == 'delete'").artefact_id)
    by_id = {a["artefact_id"]: a for a in GRAPH}
    for aid in deleted:
        a = by_id[aid]
        assert not a["legal_hold"] and a["origin_known"] and a["acl"] == ["data-platform"] and len(a["subject_ids"]) == 1, aid
    held_raw = {a["artefact_id"] for a in GRAPH if a["legal_hold"]}
    held_lineage = {a["artefact_id"] for a in GRAPH if set(a["parent_ids"]) & held_raw}
    assert held_raw and not (deleted & (held_raw | held_lineage))
    tomb = json.loads((tmp_path / "mock_store_state.json").read_text(encoding="utf-8"))["tombstones"]
    assert set(tomb) == deleted                                   # mock store matches the plan, residual = 0


def test_second_run_is_idempotent(tmp_path):
    out = tmp_path / "a"
    assert run_poc(out) == 0
    first = {f: (out / f).read_bytes() for f in ("actions.csv", "mock_store_state.json", "review_queue.csv")}
    assert json.loads((out / "deletion_evidence.json").read_text())["newly_deleted"] > 0
    assert run_poc(out) == 0                                      # same folder: resume on existing tombstones
    ev = json.loads((out / "deletion_evidence.json").read_text())
    assert (ev["newly_deleted"], ev["newly_linked"], ev["changed_state"]) == (0, 0, False)
    assert first == {f: (out / f).read_bytes() for f in first}
    assert run_poc(tmp_path / "b") == 0                           # clean folder: same plan
    assert (tmp_path / "b" / "actions.csv").read_bytes() == first["actions.csv"]


def test_dry_run_plans_but_deletes_nothing(tmp_path):
    cfg = tmp_path / "dry.yaml"
    cfg.write_text("track: t08\ninput: fixtures/t08_deletion\nowner: tester\nparams: {dry_run: true}\n", encoding="utf-8")
    out = tmp_path / "out"
    assert run_poc(out, "--config", str(cfg)) == 0
    assert not (out / "mock_store_state.json").exists()
    ev = json.loads((out / "deletion_evidence.json").read_text())
    assert ev["mode"] == "dry_run" and ev["tombstones_total"] == 0 and ev["n_delete_pairs"] > 0
    assert json.loads((out / "decision.json").read_text(encoding="utf-8"))["status"] == "HOLD"


# ------------------------------------------------------------------ human review
def test_review_override_is_applied_logged_and_executed(tmp_path):
    assert run_poc(tmp_path) == 0
    q = pd.read_csv(tmp_path / "review_queue.csv", dtype=str).fillna("")
    decisions = {i: ("approve", "", "ok") for i in q.item_id}
    for item in ("DR-006|a0123", "DR-007|a0123"):                 # frame shared by subj_08+subj_09, both requested
        decisions[item] = ("edit", "delete", "both subjects verified")
    review(tmp_path, decisions, reviewer="Nguyễn Đức")
    assert run_poc(tmp_path) == 0
    act = pd.read_csv(tmp_path / "actions.csv").set_index("item_id")
    assert act.at["DR-006|a0123", "action"] == act.at["DR-007|a0123", "action"] == "delete"
    assert act.at["DR-006|a0123", "machine_action"] == "escalate"   # machine decision kept for the diff
    assert act.at["DR-006|a0126", "action"] == "escalate"           # approved rows are unchanged
    over = [e for e in audit(tmp_path) if e["action"] == "override:edit"]
    assert {(e["item_id"], e["extra"]["request_id"]) for e in over} == {("a0123", "DR-006"), ("a0123", "DR-007")}
    assert all(e["before"] == "escalate" and e["after"] == "delete" and e["actor"] == "Nguyen Duc" for e in over)
    ev = json.loads((tmp_path / "deletion_evidence.json").read_text())
    assert (ev["newly_deleted"], ev["newly_linked"]) == (1, 1)      # only the newly approved artefact is deleted
    d = json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))
    assert (d["status"], d["reason_code"]) == ("GO", "PLAN_EXECUTED_EXCEPTIONS_TRACKED")
    # audit log must stay ASCII: eval_t08 reads it with the platform default encoding
    (tmp_path / "audit_log.jsonl").read_bytes().decode("ascii")


def test_one_sided_approval_of_a_shared_frame_is_blocked(tmp_path):
    assert run_poc(tmp_path) == 0
    review(tmp_path, {"DR-006|a0123": ("edit", "delete", "approved for subj_08 only")})
    assert run_poc(tmp_path) == 0
    act = pd.read_csv(tmp_path / "actions.csv").set_index("item_id")
    assert (act.at["DR-006|a0123", "action"], act.at["DR-006|a0123", "reason_code"]) == ("escalate", "CONFLICTING_ACTIONS")
    assert "a0123" not in json.loads((tmp_path / "mock_store_state.json").read_text())["tombstones"]
    assert any(e["action"] == "delete_blocked_conflict" and e["item_id"] == "a0123" for e in audit(tmp_path))


# ------------------------------------------------------------------ failure / edge paths
def test_invalid_override_value_stops_the_run(tmp_path):
    assert run_poc(tmp_path) == 0
    review(tmp_path, {"DR-008|a0156": ("edit", "purge", "typo")})
    assert run_poc(tmp_path) == 2


def test_direct_legal_hold_cannot_be_overridden_to_delete(tmp_path):
    assert run_poc(tmp_path) == 0
    review(tmp_path, {"DR-002|a0043": ("edit", "delete", "subject insists")})
    assert run_poc(tmp_path) == 2
    assert "a0043" not in json.loads((tmp_path / "mock_store_state.json").read_text())["tombstones"]


def test_stale_review_file_is_skipped_not_applied(tmp_path):
    assert run_poc(tmp_path) == 0
    q = pd.read_csv(tmp_path / "review_queue.csv", dtype=str).fillna("")
    row = q.item_id == "DR-008|a0156"
    q.loc[row, ["suggested_action", "reviewer", "reviewer_decision", "override_value"]] = ["delete", "tester", "edit", "delete"]
    q.to_csv(tmp_path / "review_queue_reviewed.csv", index=False)
    assert run_poc(tmp_path) == 0
    act = pd.read_csv(tmp_path / "actions.csv").set_index("item_id")
    assert act.at["DR-008|a0156", "action"] == "escalate"
    assert any(e["action"] == "review_stale_skipped" for e in audit(tmp_path))


def test_state_from_another_input_is_refused(tmp_path):
    out = tmp_path / "out"
    assert run_poc(out) == 0
    other = tmp_path / "t08_other"
    shutil.copytree(FX, other)
    reqs = json.loads((other / "requests.json").read_text(encoding="utf-8"))[:3]
    (other / "requests.json").write_text(json.dumps(reqs), encoding="utf-8")
    cfg = tmp_path / "loose.yaml"                                  # edited copy: hashes no longer match the manifest
    cfg.write_text("track: t08\nowner: tester\nstrict_provenance: false\nparams: {dry_run: false}\n", encoding="utf-8")
    assert run_poc(out, "--config", str(cfg), "--input", str(other)) == 2
    assert run_poc(tmp_path / "fresh", "--config", str(cfg), "--input", str(other)) == 0


def test_tampered_input_fails_provenance_check(tmp_path):
    other = tmp_path / "t08_tampered"
    shutil.copytree(FX, other)
    (other / "requests.json").write_text("[]", encoding="utf-8")
    assert run_poc(tmp_path / "out", "--input", str(other)) == 2


# ------------------------------------------------------------------ baseline
def test_baseline_deletes_only_raw_and_ignores_legal_hold(tmp_path):
    rc = runner.main(["--track", "t08", "--pipeline", "src.baseline_t08", "--output", str(tmp_path), "--offline",
                      "--seed", "42", "--run-name", "baseline"])
    assert rc == 0
    act = pd.read_csv(tmp_path / "actions.csv")
    by_id = {a["artefact_id"]: a for a in GRAPH}
    assert len(act) == 10 and {by_id[a]["type"] for a in act.artefact_id} == {"raw_video"}
    assert sum(bool(by_id[a]["legal_hold"]) for a in act.artefact_id) == 2     # documented failure: deletes held data
    assert json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))["status"] == "HOLD"
