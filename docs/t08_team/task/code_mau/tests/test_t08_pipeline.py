"""Người C · test end-to-end T08 (success + edge/failure + idempotency + resume)."""
import json
import shutil

import pandas as pd
import pytest

from src import main as runner
from src.common.manifest import build_manifest, write_manifest
from src.common.review import AuditLog
from src.t08.store import MockStore

FIX = "fixtures/t08_deletion"
ACTIONS = {"delete", "retain_legal_hold", "escalate"}


def _run(out, inp=FIX, pipeline=None):
    args = ["--track", "t08", "--input", str(inp), "--output", str(out), "--offline", "--seed", "42"]
    if pipeline:
        args += ["--pipeline", pipeline]
    return runner.main(args)


def _copy_fixture(tmp_path, mutate):
    """Bản sao fixture đã sửa + manifest mới (mini fixture cho edge case)."""
    d = tmp_path / "fx"
    shutil.copytree(FIX, d, ignore=shutil.ignore_patterns("gt"))
    reqs = json.loads((d / "requests.json").read_text(encoding="utf-8"))
    mutate(reqs)
    (d / "requests.json").write_text(json.dumps(reqs, indent=1), encoding="utf-8")
    write_manifest(build_manifest(d, ["data_graph.json", "requests.json"], "test", "CC0-1.0"), d / "manifest.csv")
    return d


# ---------- success
def test_poc_contract(tmp_path):
    assert _run(tmp_path / "poc") == 0
    a = pd.read_csv(tmp_path / "poc" / "actions.csv")
    assert {"request_id", "artefact_id", "action"} <= set(a.columns)
    assert not a.duplicated(["request_id", "artefact_id"]).any()
    assert set(a.action) <= ACTIONS
    for f in ["audit_log.jsonl", "review_queue.csv", "decision.json", "decision_log.csv", "deletion_plan.csv"]:
        assert (tmp_path / "poc" / f).exists(), f


def test_every_action_has_audit_entry(tmp_path):
    _run(tmp_path / "poc")
    a = pd.read_csv(tmp_path / "poc" / "actions.csv")
    logged = {e["item_id"] for e in AuditLog(tmp_path / "poc" / "audit_log.jsonl").read()}
    assert set(a.artefact_id) <= logged


def test_idempotent_two_runs(tmp_path):
    _run(tmp_path / "r1")
    _run(tmp_path / "r2")
    assert (tmp_path / "r1" / "actions.csv").read_text() == (tmp_path / "r2" / "actions.csv").read_text()


# ---------- failure modes đề bắt phân tích
def test_legal_hold_never_deleted(tmp_path):
    _run(tmp_path / "poc")
    a = pd.read_csv(tmp_path / "poc" / "actions.csv")
    assert not ((a.artefact_id.isin(["a0043", "a0099"])) & (a.action == "delete")).any()
    assert (a[a.request_id == "DR-002"].action != "delete").all()   # cả cây của raw bị hold


def test_other_persons_data_not_deleted(tmp_path):
    _run(tmp_path / "poc")
    a = pd.read_csv(tmp_path / "poc" / "actions.csv")
    row = a[(a.request_id == "DR-001") & (a.artefact_id == "a0011")]   # frame chung subj_00 + subj_01
    assert row.action.tolist() == ["escalate"]
    graph = {x["artefact_id"]: x for x in json.loads(open(f"{FIX}/data_graph.json", encoding="utf-8").read())["artefacts"]}
    reqs = {r["request_id"]: r["subject_id"] for r in json.loads(open(f"{FIX}/requests.json", encoding="utf-8").read())}
    for r in a.itertuples():   # không có dòng nào ngoài phạm vi subject
        assert reqs[r.request_id] in graph[r.artefact_id]["subject_ids"], r


def test_baseline_only_raw(tmp_path):
    assert _run(tmp_path / "base", pipeline="src.t08.baseline") == 0
    b = pd.read_csv(tmp_path / "base" / "actions.csv")
    assert len(b) == 10 and (b.action == "delete").all()


# ---------- edge cases (mini fixture)
def test_tampered_input_fails(tmp_path):
    d = tmp_path / "fx"
    shutil.copytree(FIX, d, ignore=shutil.ignore_patterns("gt"))
    (d / "requests.json").write_text("[]", encoding="utf-8")     # đổi file nhưng không đổi manifest
    assert _run(tmp_path / "out", inp=d) == 2


def test_unverified_identity_escalates_everything(tmp_path):
    d = _copy_fixture(tmp_path, lambda reqs: reqs[0].update(identity_verified=False))
    assert _run(tmp_path / "out", inp=d) == 0
    a = pd.read_csv(tmp_path / "out" / "actions.csv")
    assert (a[a.request_id == "DR-001"].action == "escalate").all()


def test_store_resume_after_crash(tmp_path):
    _run(tmp_path / "poc")
    a = pd.read_csv(tmp_path / "poc" / "actions.csv")
    audit = AuditLog(tmp_path / "audit.jsonl")
    with pytest.raises(RuntimeError):
        MockStore(tmp_path / "state.json").execute(a, audit, fail_after=5)
    stats = MockStore(tmp_path / "state.json").execute(a, audit)          # resume
    n_delete = a[a.action == "delete"].artefact_id.nunique()
    assert stats["skipped_already_deleted"] == 5
    assert len(json.loads((tmp_path / "state.json").read_text())["deleted"]) == n_delete
