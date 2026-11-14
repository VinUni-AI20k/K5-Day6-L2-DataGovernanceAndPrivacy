"""T14 tests: adapter, geometry, review loop and the end-to-end pipeline. None of them needs gt/ (not distributed)."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.t14_tools import (build_class_map, load_inputs, map_classes, normalise_boxes, parse_override,
                           validate_predictions)

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "fixtures" / "t14_auto_annotation"


def run_main(out: Path, pipeline: str | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "src.main", "--config", "configs/lab.yaml", "--track", "t14", "--input", str(FX),
           "--output", str(out), "--run-name", "poc", "--offline", "--seed", "42"]
    if pipeline:
        cmd += ["--pipeline", pipeline]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------ adapter (success + failure)
def test_class_map_converts_coco_ids_to_taxonomy_names():
    d = load_inputs(FX)
    cm = build_class_map(d["label_map"], d["taxonomy"])
    # model ids are COCO-style and DIFFER from taxonomy ids (taxonomy: car=0, model: person=0)
    assert cm == {0: "pedestrian", 2: "car", 3: "motorbike", 11: "sign"}
    mapped = map_classes(d["preds"], cm)
    assert set(mapped["class"]) <= set(d["taxonomy"].values())


def test_unmapped_model_class_fails_loudly():
    d = load_inputs(FX)
    with pytest.raises(ValueError, match="no alias"):
        build_class_map({**d["label_map"], 7: "truck"}, d["taxonomy"])          # a van/truck has no taxonomy class
    cm = build_class_map(d["label_map"], d["taxonomy"])
    with pytest.raises(ValueError, match="not in the model label_map"):
        map_classes(pd.DataFrame({"class_id": [0, 99]}), cm)


def test_wrong_alias_would_still_be_a_valid_file_but_is_caught_by_validator_rules():
    """Failure mode #1: a wrong map exports 'valid' rows. The adapter must refuse an alias outside the taxonomy."""
    d = load_inputs(FX)
    with pytest.raises(ValueError, match="not in the taxonomy"):
        build_class_map(d["label_map"], d["taxonomy"], {"person": "bicycle"})


# ------------------------------------------------------------------ geometry
def test_normalise_clips_out_of_bounds_and_drops_empty_boxes():
    imgs = pd.DataFrame({"image_id": ["a"], "path": ["images/a.jpg"], "width": [100], "height": [50]})
    df = pd.DataFrame({"image_id": ["a"] * 3, "x": [90.0, -5.0, 200.0], "y": [10.0, 10.0, 10.0],
                       "w": [20.0, 10.0, 10.0], "h": [10.0, 10.0, 10.0]})
    out, dropped = normalise_boxes(df, imgs)
    assert dropped == 1                                              # fully outside -> no area
    assert out["clipped"].tolist() == [True, True]
    assert out.loc[0, "w"] == 10.0 and out.loc[1, "x"] == 0.0 and out.loc[1, "w"] == 5.0
    assert validate_predictions(out.assign(**{"class": "car"}), {0: "car"}, imgs).empty


def test_parse_override_formats_and_errors():
    names = {"car", "pedestrian"}
    assert parse_override("car", names) == {"class": "car"}
    assert parse_override("1,2,3,4", names) == {"box": (1.0, 2.0, 3.0, 4.0)}
    assert parse_override("pedestrian, 1,2,3,4", names) == {"class": "pedestrian", "box": (1.0, 2.0, 3.0, 4.0)}
    for bad in ("", "van", "1,2,3", "car,a,b,c,d"):
        with pytest.raises(ValueError):
            parse_override(bad, names)


# ------------------------------------------------------------------ end to end
def test_pipeline_end_to_end_is_valid_reproducible_and_holds_without_review(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert run_main(a).returncode == 0
    assert run_main(b).returncode == 0
    pred = pd.read_csv(a / "predictions.csv")
    assert list(pred.columns[:7]) == ["image_id", "class", "x", "y", "w", "h", "conf"]
    assert set(pred["class"]) <= {"car", "pedestrian", "motorbike", "sign"}
    qa = json.loads((a / "qa_report.json").read_text(encoding="utf-8"))
    assert qa["n_invalid"] == 0 and qa["yolo_ok"] and qa["coco_ok"]
    dec = json.loads((a / "decision.json").read_text(encoding="utf-8"))
    assert (dec["status"], dec["reason_code"]) == ("HOLD", "NOT_REVIEWED")     # valid file != reviewed file
    assert sha(a / "predictions.csv") == sha(b / "predictions.csv")            # seed 42 -> same bytes
    assert len(pd.read_csv(a / "review_queue.csv")) == 30


def test_baseline_exports_out_of_bounds_boxes_that_the_poc_fixes(tmp_path):
    base, poc = tmp_path / "base", tmp_path / "poc"
    assert run_main(base, "src.baseline_t14").returncode == 0
    assert run_main(poc).returncode == 0
    nb = json.loads((base / "qa_report.json").read_text(encoding="utf-8"))["n_invalid"]
    npoc = json.loads((poc / "qa_report.json").read_text(encoding="utf-8"))["n_invalid"]
    assert nb > 0 and npoc == 0


def _reviewed_from_queue(out: Path, edit_box: str = "10,10,20,20") -> pd.DataFrame:
    q = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    q["reviewer"], q["reviewer_decision"] = "tester", "approve"
    q.loc[0, "reviewer_decision"] = "reject"
    q.loc[1, ["reviewer_decision", "override_value"]] = ["edit", edit_box]
    return q


def test_review_loop_applies_reject_and_edit_logs_audit_and_reaches_go(tmp_path):
    out = tmp_path / "poc"
    assert run_main(out).returncode == 0
    q = _reviewed_from_queue(out)
    rejected, edited = q.loc[0, "item_id"], q.loc[1, "item_id"]
    q.to_csv(out / "review_queue_reviewed.csv", index=False)
    assert run_main(out).returncode == 0
    pred = pd.read_csv(out / "predictions.csv")
    assert rejected not in set(pred["box_id"])                                  # deleted by the reviewer
    row = pred[pred["box_id"] == edited].iloc[0]
    assert (row["x"], row["y"], row["w"], row["h"]) == (10.0, 10.0, 20.0, 20.0)  # edited box
    diff = pd.read_csv(out / "correction_diff.csv")
    assert len(diff) == 30 and set(diff["decision"]) == {"approve", "reject", "edit"}
    actions = {json.loads(l)["action"] for l in (out / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()}
    assert {"review:reject", "review:edit", "review:approve"} <= actions
    dec = json.loads((out / "decision.json").read_text(encoding="utf-8"))
    assert (dec["status"], dec["reason_code"]) == ("GO", "REVIEWED_AND_VALID")


def test_partial_review_stays_on_hold(tmp_path):
    out = tmp_path / "poc"
    assert run_main(out).returncode == 0
    _reviewed_from_queue(out).head(3).to_csv(out / "review_queue_reviewed.csv", index=False)
    assert run_main(out).returncode == 0
    assert json.loads((out / "decision.json").read_text(encoding="utf-8"))["reason_code"] == "REVIEW_INCOMPLETE"


@pytest.mark.parametrize("mutate,why", [
    (lambda q: q.assign(reviewer=""), "decision without reviewer"),
    (lambda q: q.assign(item_id=["zz#9"] * len(q)), "item outside the queue"),
    (lambda q: q.assign(reviewer_decision="maybe"), "unknown decision value"),
])
def test_bad_review_file_is_rejected_with_exit_2(tmp_path, mutate, why):
    out = tmp_path / "poc"
    assert run_main(out).returncode == 0
    mutate(_reviewed_from_queue(out)).to_csv(out / "review_queue_reviewed.csv", index=False)
    assert run_main(out).returncode == 2, why


def test_missed_box_addition_needs_a_reviewer_and_is_exported(tmp_path):
    out = tmp_path / "poc"
    assert run_main(out).returncode == 0
    add = pd.DataFrame([{"image_id": "aa_00", "class": "car", "x": 5, "y": 5, "w": 30, "h": 20, "reviewer": "", "note": "van missed"}])
    add.to_csv(out / "review_additions.csv", index=False)
    assert run_main(out).returncode == 2                                        # owner is mandatory
    add.loc[0, "reviewer"] = "tester"
    add.to_csv(out / "review_additions.csv", index=False)
    assert run_main(out).returncode == 0
    pred = pd.read_csv(out / "predictions.csv")
    assert (pred["source"] == "human").sum() == 1
