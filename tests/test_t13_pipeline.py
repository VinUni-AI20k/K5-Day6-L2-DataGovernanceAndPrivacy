"""Unit tests for Group's T13 Active Learning Pipeline.

Contract requires >= 2 group tests:
1. Success test: end-to-end pipeline run produces valid selected.csv (K=20), review queue, and decision.
2. Failure/Edge test: handling missing features or corrupt inputs with clear exceptions.
3. Review test: verifying human review override behavior and audit logging.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.common.context import RunContext
from src.common.review import AuditLog
from src.pipeline import load, process, rank, review, decide, run


@pytest.fixture
def t13_context(tmp_path):
    input_dir = Path("fixtures/t13_rare_mining")
    output_dir = tmp_path / "out_t13"
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "track": "t13",
        "owner": "Nguyen Hoang Dieu",
        "params": {"k": 20, "redundancy_penalty": 0.65},
        "strict_provenance": True,
    }
    rng = np.random.default_rng(42)
    ctx = RunContext(
        track="t13",
        input_dir=input_dir,
        output_dir=output_dir,
        config=cfg,
        seed=42,
        rng=rng,
        run_name="test_poc",
        offline=True,
        audit=AuditLog(output_dir / "audit_log.jsonl"),
    )
    return ctx


def test_t13_pipeline_success_e2e(t13_context):
    """Test 1: Success case - Full pipeline runs and produces 20 selected items with proper contract."""
    ctx = t13_context
    run(ctx)

    pred_file = ctx.out("selected.csv")
    assert pred_file.exists(), "selected.csv must be created"

    selected_df = pd.read_csv(pred_file)
    assert "image_id" in selected_df.columns, "selected.csv must have image_id"
    assert len(selected_df) == 20, "Must select exactly K=20 samples"
    assert selected_df["image_id"].nunique() == 20, "Selected images must be distinct"

    # Verify review artifacts
    queue_file = ctx.out("review_queue.csv")
    assert queue_file.exists(), "review_queue.csv must be generated"
    queue_df = pd.read_csv(queue_file)
    assert len(queue_df) == 20, "Review queue must have top K=20 items"

    # Verify decision artifact
    decision_file = ctx.out("decision.json")
    assert decision_file.exists(), "decision.json must be written"
    import json
    dec_data = json.loads(decision_file.read_text())
    assert dec_data["status"] in ("GO", "HOLD", "REWORK")
    assert dec_data["reason_code"] != "POLICY_NOT_IMPLEMENTED"
    assert dec_data["owner"] == "Nguyen Hoang Dieu"


def test_t13_pipeline_missing_features_failure(tmp_path):
    """Test 2: Edge/Failure case - Pipeline fails loudly when input feature table is missing."""
    empty_dir = tmp_path / "empty_input"
    empty_dir.mkdir()
    out_dir = tmp_path / "out_fail"
    out_dir.mkdir()

    # Create dummy images.csv without pool_features.csv
    pd.DataFrame({"image_id": ["img1"], "path": ["images/img1.jpg"]}).to_csv(empty_dir / "images.csv", index=False)

    ctx = RunContext(
        track="t13",
        input_dir=empty_dir,
        output_dir=out_dir,
        config={"track": "t13", "strict_provenance": False},
        seed=42,
        rng=None,
        run_name="fail_test",
        offline=True,
        audit=AuditLog(out_dir / "audit_log.jsonl"),
    )

    with pytest.raises(FileNotFoundError):
        load(ctx)


def test_t13_review_override_applied(t13_context):
    """Test 3: Human-in-the-loop - Reject decision in review queue is properly applied."""
    ctx = t13_context
    data = load(ctx)
    scored = process(ctx, data)
    queue = rank(ctx, scored)

    # Simulate human review rejection on top-1 candidate
    top1_id = queue.iloc[0]["item_id"]
    reviewed_queue = queue.copy()
    reviewed_queue.loc[0, "reviewer"] = "Reviewer_1"
    reviewed_queue.loc[0, "reviewer_decision"] = "reject"
    reviewed_queue.loc[0, "review_note"] = "False positive junk frame"

    reviewed_path = ctx.out("review_queue_reviewed.csv")
    reviewed_queue.to_csv(reviewed_path, index=False)

    final = review(ctx, scored, queue)

    # Top-1 rejected item should have is_selected = False or demoted score
    rejected_row = final[final["image_id"] == top1_id].iloc[0]
    assert not rejected_row["is_selected"], "Rejected item must not remain selected"
    assert ctx.stats.get("n_reviewed", 0) > 0, "Audit stats should record reviews"
