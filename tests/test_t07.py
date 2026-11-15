"""T07 group tests: detector, reviewer overrides, baselines and the one-command pipeline.

Success paths and failure/edge paths are both covered (README: >= 2 group tests).
The detector tests draw their own synthetic scene with the public renderer in
``tools/synth/scene.py`` — no fixture ground truth is read.
"""
import json

import cv2
import numpy as np
import pandas as pd
import pytest

from src import main as runner
from src import pipeline
from src.metrics.detection import region_coverage
from src.t07_baseline import blur_all_boxes, haar_boxes, load_haar_cascade, naive_color_boxes
from src.t07_detector import DETECTOR_INFO, detect_image, image_condition
from tools.synth.scene import SceneSpec, render_scene

T07 = ["--track", "t07", "--offline", "--seed", "42"]


def _scene(seed=7, **kw):
    spec = SceneSpec(seed=seed, width=640, height=360, faces=4, plates=True, face_min=22, face_max=44, **kw)
    img, objs = render_scene(spec)
    return np.asarray(img), objs


def _coverage(obj, boxes, shape):
    return region_coverage((obj.x, obj.y, obj.w, obj.h), [[b["x"], b["y"], b["w"], b["h"]] for b in boxes], shape)


# ------------------------------------------------------------------ detector: success
def test_detector_covers_rendered_faces_and_plates():
    img, objs = _scene()
    boxes = detect_image(img)
    assert boxes, "detector returned nothing on a clean daytime scene"
    for b in boxes:
        assert set(b) >= {"x", "y", "w", "h", "type", "conf"}
        assert b["type"] in {"face", "plate"} and 0.0 <= b["conf"] <= 1.0
        assert b["w"] > 0 and b["h"] > 0 and b["x"] >= 0 and b["y"] >= 0
    faces = [o for o in objs if o.cls == "face"]
    covered = [o for o in faces if _coverage(o, boxes, img.shape[:2]) >= 0.9]
    assert len(covered) >= len(faces) - 1, f"only {len(covered)}/{len(faces)} faces covered >= 0.9"
    # the redaction must stay local: nowhere near "blur everything"
    area = sum(b["w"] * b["h"] for b in boxes) / float(img.shape[0] * img.shape[1])
    assert area < 0.2


def test_detector_ignores_pedestrian_heads_and_signs():
    """Hard negatives of the brief: pedestrian heads (seen from behind) and round signs are not PII."""
    spec = SceneSpec(seed=3, width=640, height=360, faces=0, plates=False, n_peds=4, n_signs=2, n_cars=0, n_bikes=0)
    img, _ = render_scene(spec)
    faces = [b for b in detect_image(np.asarray(img)) if b["type"] == "face"]
    assert faces == []


def test_detector_is_deterministic():
    img, _ = _scene(seed=11)
    assert detect_image(img) == detect_image(img.copy())
    assert DETECTOR_INFO["mode"] == "poc_offline"


# ------------------------------------------------------------- detector: failure / edge
def test_detector_blank_image_returns_no_boxes():
    assert detect_image(np.full((360, 640, 3), 128, np.uint8)) == []
    cond = image_condition(np.zeros((360, 640, 3), np.uint8))
    assert cond["dark"] and cond["blur"]


@pytest.mark.parametrize("bad", [np.zeros((360, 640), np.uint8), np.zeros((360, 640, 4), np.uint8), None])
def test_detector_rejects_non_rgb_input(bad):
    with pytest.raises(ValueError):
        detect_image(bad)


# --------------------------------------------------------------- reviewer override parser
def test_override_parser_accepts_documented_formats():
    assert pipeline._parse_override_boxes("10,20,30,40; 100,120,40,15", 640, 360)[1]["w"] == 40
    added = pipeline._parse_override_boxes("add: 5,5,10,10", 640, 360)
    assert len(added) == 1 and added[0]["conf"] == 1.0
    as_json = pipeline._parse_override_boxes('[{"x":1,"y":2,"w":3,"h":4,"type":"plate"},[9,9,5,5]]', 640, 360)
    assert [b["type"] for b in as_json] == ["plate", "reviewer"]
    # boxes are clamped to the image, boxes fully outside are dropped
    assert pipeline._parse_override_boxes("630,350,50,50", 640, 360)[0]["w"] == 10
    assert pipeline._parse_override_boxes("700,400,10,10", 640, 360) == []


@pytest.mark.parametrize("bad", ["10,20,30", "a,b,c,d", '{"x":1}'])
def test_override_parser_rejects_malformed_values(bad):
    with pytest.raises(ValueError):
        pipeline._parse_override_boxes(bad, 640, 360)


# ----------------------------------------------------------------------------- baselines
def test_baselines_produce_boxes_without_network():
    img, _ = _scene()
    assert blur_all_boxes(img) == [{"x": 0, "y": 0, "w": 640, "h": 360, "type": "all"}]
    naive = naive_color_boxes(img)
    assert naive and all(b["w"] > 0 and b["h"] > 0 and b["type"] in {"face", "plate"} for b in naive)


def test_haar_reference_is_optional_and_fails_clearly():
    """Plain OpenCV 5.x has no CascadeClassifier: the optional baseline must say so, not crash obscurely."""
    if hasattr(cv2, "CascadeClassifier"):
        img, _ = _scene()
        for b in haar_boxes(img, load_haar_cascade()):
            assert b["w"] > 0 and b["h"] > 0
    else:
        with pytest.raises(FileNotFoundError, match="CascadeClassifier"):
            load_haar_cascade()


# ----------------------------------------------------------------- pipeline: end to end
def test_pipeline_end_to_end_hold_then_go_after_review(tmp_path):
    out = tmp_path / "poc"
    assert runner.main(T07 + ["--output", str(out)]) == 0
    for f in ["redactions.csv", "redactions_raw.csv", "review_queue.csv", "contact_sheet.html",
              "decision.json", "decision_log.csv", "audit_log.jsonl", "run_info.json"]:
        assert (out / f).exists(), f
    red = pd.read_csv(out / "redactions.csv")
    assert list(red.columns[:5]) == ["image_id", "x", "y", "w", "h"] and len(red) > 0
    assert (red[["w", "h"]] > 0).all().all()
    queue = pd.read_csv(out / "review_queue.csv")
    assert len(queue) == 15                                        # review budget B
    assert queue["score"].is_monotonic_decreasing
    # no human sign-off yet -> the gate must not release
    assert json.loads((out / "decision.json").read_text())["status"] == "HOLD"

    # human review: reject every box of the top image, approve the rest
    queue = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    queue["reviewer"] = "pytest-reviewer"
    queue["reviewer_decision"] = "approve"
    top = queue.loc[0, "item_id"]
    queue.loc[0, ["reviewer_decision", "review_note"]] = ["reject", "unit test: drop all boxes"]
    queue.to_csv(out / "review_queue_reviewed.csv", index=False)
    assert runner.main(T07 + ["--output", str(out)]) == 0
    final = pd.read_csv(out / "redactions.csv")
    assert top not in set(final["image_id"])                       # override applied to the export
    decision = json.loads((out / "decision.json").read_text())
    assert decision["status"] == "GO" and decision["owner"]
    actions = [json.loads(line)["action"] for line in (out / "audit_log.jsonl").read_text().splitlines() if line.strip()]
    assert "override:reject" in actions and "review:approve" in actions and "decision:GO" in actions


def test_pipeline_is_reproducible_with_same_seed(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert runner.main(T07 + ["--output", str(a)]) == 0
    assert runner.main(T07 + ["--output", str(b)]) == 0
    assert (a / "redactions.csv").read_text() == (b / "redactions.csv").read_text()


def test_review_without_reviewer_name_is_rejected(tmp_path):
    out = tmp_path / "poc"
    assert runner.main(T07 + ["--output", str(out)]) == 0
    queue = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    queue.loc[0, "reviewer_decision"] = "approve"                  # decision without an owner
    queue.to_csv(out / "review_queue_reviewed.csv", index=False)
    assert runner.main(T07 + ["--output", str(out)]) == 2          # input/data error, not silent


def test_baseline_run_never_releases(tmp_path):
    out = tmp_path / "baseline"
    assert runner.main(T07 + ["--pipeline", "src.t07_baseline", "--output", str(out), "--run-name", "baseline"]) == 0
    assert json.loads((out / "decision.json").read_text())["status"] == "HOLD"
    out2 = tmp_path / "blurall"
    assert runner.main(T07 + ["--pipeline", "src.t07_baseline_blurall", "--output", str(out2)]) == 0
    assert len(pd.read_csv(out2 / "redactions.csv")) == 60
