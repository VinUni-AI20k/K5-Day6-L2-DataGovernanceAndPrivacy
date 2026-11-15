"""Unit tests for Group's T13 Active Learning Pipeline.

Contract requires >= 2 group tests:
1. Success test: end-to-end pipeline run produces valid selected.csv (K=20), review queue, contact sheet, and decision.
2. Failure/Edge test: handling missing features or corrupt inputs with clear exceptions.
3. Review test: verifying human review override behavior and audit logging.
4. Reproducibility test: identical seed produces bit-for-bit identical selection.
5. Runner contract test: main runner execution, run_info.json metadata validation (status=0, seed=42).
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src import main as runner
from src.common.context import RunContext
from src.common.review import AuditLog
from src.pipeline import load, process, rank, review, decide, run

FX_T13 = Path("fixtures/t13_rare_mining")


@pytest.fixture
def t13_context(tmp_path):
    input_dir = FX_T13
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
    assert "rank" in selected_df.columns, "selected.csv must have rank column"
    assert len(selected_df) == 20, "Must select exactly K=20 samples"
    assert selected_df["image_id"].nunique() == 20, "Selected images must be distinct"
    assert list(selected_df["rank"]) == list(range(1, 21)), "Ranks must be 1 to 20 sequentially"

    # Verify selected images belong to original pool
    pool_images = pd.read_csv(FX_T13 / "images.csv")
    valid_ids = set(pool_images["image_id"])
    assert set(selected_df["image_id"]).issubset(valid_ids), "Selected IDs contain images not in pool"

    # Verify review artifacts: queue and offline contact sheet
    queue_file = ctx.out("review_queue.csv")
    assert queue_file.exists(), "review_queue.csv must be generated"
    queue_df = pd.read_csv(queue_file)
    assert len(queue_df) == 20, "Review queue must have top K=20 items"
    assert queue_df["score"].is_monotonic_decreasing, "Review queue must be ranked descending by score"

    contact_file = ctx.out("contact_sheet.html")
    assert contact_file.exists(), "contact_sheet.html must be generated"
    assert contact_file.stat().st_size > 0, "contact_sheet.html must not be empty"

    # Verify decision artifact
    decision_file = ctx.out("decision.json")
    assert decision_file.exists(), "decision.json must be written"
    dec_data = json.loads(decision_file.read_text())
    assert dec_data["status"] in ("GO", "HOLD", "REWORK")
    assert dec_data["reason_code"] != "POLICY_NOT_IMPLEMENTED"
    assert dec_data["owner"] == "Nguyen Hoang Dieu"

    # Verify decision log
    assert (ctx.out("decision_log.csv")).exists(), "decision_log.csv must exist"


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


def test_t13_pipeline_reproducibility(tmp_path):
    """Test 4: Reproducibility - Two independent runs with the same seed yield identical selections."""
    out_1 = tmp_path / "run_1"
    out_2 = tmp_path / "run_2"
    out_1.mkdir()
    out_2.mkdir()

    cfg = {
        "track": "t13",
        "owner": "TestQA",
        "params": {"k": 20, "redundancy_penalty": 0.65},
        "strict_provenance": True,
    }

    ctx1 = RunContext(
        track="t13",
        input_dir=FX_T13,
        output_dir=out_1,
        config=cfg,
        seed=42,
        rng=np.random.default_rng(42),
        run_name="rep_1",
        offline=True,
        audit=AuditLog(out_1 / "audit_log.jsonl"),
    )
    ctx2 = RunContext(
        track="t13",
        input_dir=FX_T13,
        output_dir=out_2,
        config=cfg,
        seed=42,
        rng=np.random.default_rng(42),
        run_name="rep_2",
        offline=True,
        audit=AuditLog(out_2 / "audit_log.jsonl"),
    )

    run(ctx1)
    run(ctx2)

    df1 = pd.read_csv(out_1 / "selected.csv")
    df2 = pd.read_csv(out_2 / "selected.csv")
    pd.testing.assert_frame_equal(df1, df2)


def test_t13_main_runner_contract(tmp_path):
    """Test 5: Main runner contract - End-to-end execution via src.main produces run_info.json with status=0."""
    out_dir = tmp_path / "main_run"
    rc = runner.main([
        "--track", "t13",
        "--input", str(FX_T13),
        "--output", str(out_dir),
        "--offline",
        "--seed", "42",
        "--run-name", "runner_test"
    ])
    assert rc == 0, f"Expected returncode 0, got {rc}"

    # Verify run_info.json metadata
    info_path = out_dir / "run_info.json"
    assert info_path.exists(), "run_info.json must be written by src.main"
    info = json.loads(info_path.read_text())
    assert info["status"] == 0, f"Expected status 0 in run_info.json, got {info.get('status')}"
    assert info["seed"] == 42, f"Expected seed 42 in run_info.json, got {info.get('seed')}"
    assert info["track"] == "t13", f"Expected track t13 in run_info.json, got {info.get('track')}"
    assert info["offline"] is True, "Offline flag must be recorded as True"

    # Verify key artifacts produced by runner
    assert (out_dir / "selected.csv").exists(), "selected.csv must exist"
    assert (out_dir / "contact_sheet.html").exists(), "contact_sheet.html must exist"
    assert (out_dir / "contact_sheet.html").stat().st_size > 0, "contact_sheet.html must not be empty"

