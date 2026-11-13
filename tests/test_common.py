"""Review queue / overrides / audit log / decision / oracle."""
import pandas as pd
import pytest

from src.common.audit_oracle import AuditOracle, BudgetExceededError
from src.common.decision import Decision, canonical_status, write_decision
from src.common.review import AuditLog, apply_overrides, load_review_decisions, make_review_queue, write_review_queue


def test_review_roundtrip_and_overrides(tmp_path):
    df = pd.DataFrame({"image_id": ["a", "b", "c"], "score": [0.2, 0.9, 0.5], "label": ["x", "y", "z"]})
    q = make_review_queue(df, "image_id", "score", budget=2)
    assert list(q.item_id) == ["b", "c"]
    q.loc[0, ["reviewer", "reviewer_decision", "override_value", "review_note"]] = ["tin", "edit", "Y2", "wrong class"]
    p = write_review_queue(q, tmp_path / "rq.csv")
    reviewed = load_review_decisions(p)
    log = AuditLog(tmp_path / "audit.jsonl")
    out = apply_overrides(df, reviewed, "image_id", "label", audit=log)
    assert out.loc[out.image_id == "b", "label"].item() == "Y2"
    assert df.loc[df.image_id == "b", "label"].item() == "y"      # raw untouched
    assert log.read()[0]["actor"] == "tin"


def test_review_requires_owner(tmp_path):
    q = make_review_queue(pd.DataFrame({"id": ["a"], "score": [1.0]}), "id", "score", 1)
    q.loc[0, "reviewer_decision"] = "approve"
    p = write_review_queue(q, tmp_path / "rq.csv")
    with pytest.raises(ValueError, match="no `reviewer`"):
        load_review_decisions(p)


def test_decision_validation(tmp_path):
    assert canonical_status("accept") == "GO" and canonical_status("RECAPTURE") == "REWORK"
    with pytest.raises(ValueError):
        Decision(status="MAYBE", reason_code="X", reason="", owner="me")
    with pytest.raises(ValueError):
        Decision(status="GO", reason_code="X", reason="", owner=" ")
    d = Decision(status="HOLD", reason_code="LOW_N", reason="too few samples", owner="QA lead")
    write_decision(d, tmp_path / "d.json", tmp_path / "log.csv")
    write_decision(d, tmp_path / "d.json", tmp_path / "log.csv")
    assert len(pd.read_csv(tmp_path / "log.csv")) == 2


def test_audit_oracle_budget():
    o = AuditOracle("fixtures/t12_vendor_batches/gt/hidden_errors.csv", "sample_id", "is_error", "batch_id", budget_per_group=2)
    o.inspect(["V1_0000", "V1_0001"])
    o.inspect(["V1_0000"])                     # re-inspecting is free
    with pytest.raises(BudgetExceededError):
        o.inspect(["V1_0002"])
