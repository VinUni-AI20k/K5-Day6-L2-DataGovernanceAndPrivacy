""" Tests for the T08 delete-request pipeline (success + failure/edge cases).   [P5]"""
import json
from pathlib import Path

import pandas as pd
import yaml

from src import main as runner
from src.pipeline import ACTIONS, classify
from tools.t08_selfcheck import selfcheck

FX = "fixtures/t08_deletion"


def _cfg(tmp_path, **params):
    p = tmp_path / "lab.yaml"
    base = {"dry_run": True, "permitted_acl": ["data-platform"], "legal_hold_inherit": True}
    p.write_text(yaml.safe_dump({"track": "t08", "input": FX, "owner": "test-dpo", "seed": 42, "offline": True,
                                 "strict_provenance": True, "params": base | params}), encoding="utf-8")
    return str(p)


def _run(tmp_path, out, pipeline=None, **params):
    argv = ["--config", _cfg(tmp_path, **params), "--output", str(out), "--offline"]
    return runner.main(argv + (["--pipeline", pipeline] if pipeline else []))


def _read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _graph():
    return {a["artefact_id"]: a for a in _read_json(f"{FX}/data_graph.json")["artefacts"]}


def test_end_to_end_contract_and_no_false_delete(tmp_path):
    out = tmp_path / "poc"
    assert _run(tmp_path, out) == 0
    for f in ["actions.csv", "review_queue.csv", "contact_sheet.html", "dry_run_diff.csv", "request_summary.csv",
              "audit_log.jsonl", "decision.json", "decision_log.csv"]:
        assert (out / f).exists(), f
    act = pd.read_csv(out / "actions.csv")
    assert set(act.action) <= set(ACTIONS)
    assert not act.duplicated(["request_id", "artefact_id"]).any()
    g = _graph()
    for r in act.itertuples():          # an exception is never deleted
        a = g[r.artefact_id]
        risky = a["legal_hold"] or a["acl"] != ["data-platform"] or not a["origin_known"] or len(a["subject_ids"]) > 1
        assert not (risky and r.action == "delete"), r
    assert set(act[act.artefact_id.isin(["a0043", "a0099"])].action) == {"retain_legal_hold"}
    # lineage completeness: every artefact tagged with a requested subject is in the plan, nothing else
    subj = {r["subject_id"]: r["request_id"] for r in _read_json(f"{FX}/requests.json")}
    expected = {(subj[s], aid) for aid, a in g.items() for s in a["subject_ids"] if s in subj}
    assert expected == set(zip(act.request_id, act.artefact_id))
    # every artefact acted on has an audit entry; dry-run by default; unreviewed exceptions -> HOLD
    logged = {json.loads(l)["item_id"] for l in (out / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()}
    assert set(act.artefact_id) <= logged
    assert not (out / "mock_store_tombstones.json").exists()
    assert _read_json(out / "decision.json")["status"] == "HOLD"
    # review queue = exactly the exceptions
    q = pd.read_csv(out / "review_queue.csv")
    assert len(q) == int((act.action != "delete").sum())


def test_matches_internal_key(tmp_path):
    out = tmp_path / "poc"
    assert _run(tmp_path, out) == 0
    r = selfcheck(str(out / "actions.csv"), "reports/t08_internal_key.csv")
    assert r["false_delete"] == 0 and len(r["mismatches"]) == 0


def test_mock_delete_is_idempotent(tmp_path):
    out = tmp_path / "poc"
    assert _run(tmp_path, out, dry_run=False) == 0
    first = (out / "actions.csv").read_text(encoding="utf-8")
    s1 = _read_json(out / "run_info.json")["stats"]
    assert _run(tmp_path, out, dry_run=False) == 0
    s2 = _read_json(out / "run_info.json")["stats"]
    assert (out / "actions.csv").read_text(encoding="utf-8") == first
    assert s1["new_deletes"] > 0 and s2["new_deletes"] == 0 and s2["already_deleted"] == s1["new_deletes"]


def test_review_override_applied_and_invalid_value_rejected(tmp_path):
    out = tmp_path / "poc"
    assert _run(tmp_path, out) == 0
    q = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    q["reviewer"] = "dpo@test"
    q["reviewer_decision"] = "approve"
    i = q.index[q.item_id == "DR-004:a0075"][0]
    q.loc[i, ["reviewer_decision", "override_value", "review_note"]] = ["edit", "delete", "origin confirmed by owner"]
    j = q.index[q.item_id == "DR-008:a0156"][0]
    q.loc[j, ["reviewer_decision", "review_note"]] = ["reject", "vendor must delete"]
    q.to_csv(out / "review_queue_reviewed.csv", index=False)
    assert _run(tmp_path, out) == 0
    act = pd.read_csv(out / "actions.csv").set_index(["request_id", "artefact_id"])
    assert act.loc[("DR-004", "a0075"), "action"] == "delete"
    assert act.loc[("DR-008", "a0156"), "action"] == "escalate"          # reject never becomes delete
    assert act.loc[("DR-002", "a0043"), "source"] == "human"
    assert _read_json(out / "decision.json")["status"] == "GO"
    log = [json.loads(l) for l in (out / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e["action"] == "review:edit" and e["item_id"] == "a0075" and e["actor"] == "dpo@test" for e in log)

    q.loc[i, "override_value"] = "nuke"                                   # not an allowed action
    q.to_csv(out / "review_queue_reviewed.csv", index=False)
    assert _run(tmp_path, out) == 2


def test_review_row_without_reviewer_fails(tmp_path):
    out = tmp_path / "poc"
    assert _run(tmp_path, out) == 0
    q = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    q.loc[0, "reviewer_decision"] = "approve"                             # decision but no owner
    q.to_csv(out / "review_queue_reviewed.csv", index=False)
    assert _run(tmp_path, out) == 2


def test_policy_precedence():
    req = {"identity_verified": True}
    base = {"type": "frame", "acl": ["data-platform"], "origin_known": True, "legal_hold": None, "subject_ids": ["s1"]}
    acl = ["data-platform"]
    assert classify(base, "s1", req, acl, True, [])[0] == "delete"
    worst = base | {"legal_hold": "LH-1", "subject_ids": ["s1", "s2"], "acl": ["vendor-x"], "origin_known": False}
    assert classify(worst, "s1", req, acl, True, [])[1] == "LEGAL_HOLD"                 # hold beats everything
    assert classify(base, "s1", req, acl, True, ["a1:LH-1"])[1] == "LEGAL_HOLD_INHERITED"
    assert classify(base, "s1", req, acl, False, ["a1:LH-1"])[0] == "delete"            # inherit switch off
    assert classify(base, "s1", {"identity_verified": False}, acl, True, [])[1] == "IDENTITY_NOT_VERIFIED"
    assert classify(base | {"acl": ["vendor-x"], "subject_ids": ["s1", "s2"]}, "s1", req, acl, True, [])[1] == "NO_DELETE_PERMISSION"
    assert classify(base | {"origin_known": False}, "s1", req, acl, True, [])[1] == "UNKNOWN_ORIGIN"
    assert classify(base | {"subject_ids": ["s1", "s2"]}, "s1", req, acl, True, [])[1] == "MULTI_SUBJECT"


def test_baseline_shows_both_failure_modes(tmp_path):
    out = tmp_path / "baseline"
    assert _run(tmp_path, out, pipeline="src.baselines.t08_raw_only") == 0
    act = pd.read_csv(out / "actions.csv")
    g = _graph()
    assert {g[a]["type"] for a in act.artefact_id} == {"raw_video"}       # copies/embeddings left behind
    assert {"a0043", "a0099"} <= set(act.artefact_id)                     # held raw deleted = false delete
    r = selfcheck(str(out / "actions.csv"), "reports/t08_internal_key.csv")
    assert r["false_delete"] >= 1
