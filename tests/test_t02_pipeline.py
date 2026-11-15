"""Group QA tests for T02 pipeline (success E2E, human override + audit, failure/edge)."""
import json

import pandas as pd

from src import main as runner
from src.common.review import REVIEW_COLUMNS


def test_t02_poc_end_to_end(tmp_path):
    out = tmp_path / "poc"
    rc = runner.main(
        ["--config", "configs/lab.yaml", "--track", "t02", "--output", str(out), "--run-name", "poc", "--offline", "--seed", "42"]
    )
    assert rc == 0
    for fname in ["ranked_review.csv", "review_queue.csv", "contact_sheet.html", "decision.json", "decision_log.csv", "run_info.json"]:
        assert (out / fname).exists(), f"missing {fname}"

    pred = pd.read_csv(out / "ranked_review.csv")
    assert len(pred) == 96
    for col in ["image_id", "score", "pred_defect_type", "pred_action"]:
        assert col in pred.columns
    dec = json.loads((out / "decision.json").read_text(encoding="utf-8"))
    assert dec["status"] in {"HOLD", "GO", "REWORK"}
    assert dec["owner"]


def test_t02_human_override_writes_audit_log(tmp_path):
    out = tmp_path / "poc_review"
    assert runner.main(["--config", "configs/lab.yaml", "--track", "t02", "--output", str(out), "--offline", "--seed", "42"]) == 0

    q = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    target_id = q.loc[0, "item_id"]
    q.loc[0, "reviewer"] = "huudang-de"
    q.loc[0, "reviewer_decision"] = "edit"
    q.loc[0, "override_value"] = "KEEP"
    q.loc[0, "review_note"] = "qa verified false alarm"
    q.to_csv(out / "review_queue_reviewed.csv", index=False)

    rc = runner.main(["--config", "configs/lab.yaml", "--track", "t02", "--output", str(out), "--offline", "--seed", "42"])
    assert rc == 0
    assert (out / "audit_log.jsonl").exists()
    events = [json.loads(line) for line in (out / "audit_log.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(ev["action"] == "override:edit" and ev["item_id"] == target_id and ev["after"] == "KEEP" for ev in events)

    pred = pd.read_csv(out / "ranked_review.csv")
    assert pred.loc[pred["image_id"] == target_id, "pred_action"].iloc[0] == "KEEP"


def test_t02_review_missing_reviewer_fails_loudly(tmp_path):
    out = tmp_path / "poc_bad_review"
    out.mkdir(parents=True)
    bad = pd.DataFrame([{c: "" for c in REVIEW_COLUMNS}])
    bad.loc[0, ["rank", "item_id", "score", "reviewer_decision", "override_value"]] = ["1", "img_00_0", "0.9", "edit", "KEEP"]
    bad.to_csv(out / "review_queue_reviewed.csv", index=False)

    rc = runner.main(["--config", "configs/lab.yaml", "--track", "t02", "--output", str(out), "--offline", "--seed", "42"])
    assert rc == 2
