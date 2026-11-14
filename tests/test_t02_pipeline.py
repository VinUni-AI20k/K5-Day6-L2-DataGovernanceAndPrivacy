import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import main
from src.common.contact_sheet import render_contact_sheet
from src.common.context import RunContext
from src.common.manifest import build_manifest
from src.common.review import AuditLog, T02_REASON_CODES, T02_REVIEW_COLUMNS, load_t02_review_decisions
from src.pipeline import _image_path, _measure_images, _tail_risk, load, process, rank

FIXTURE = Path("fixtures/t02_raw_qc")


def _context(output: Path, input_dir: Path = FIXTURE) -> RunContext:
    output.mkdir(parents=True, exist_ok=True)
    return RunContext(
        track="t02", input_dir=input_dir, output_dir=output,
        config={"owner": "Test QC", "strict_provenance": True, "params": {"budget": 20, "eval_split": "eval"}},
        seed=42, rng=np.random.default_rng(42), audit=AuditLog(output / "audit_log.jsonl"),
    )


def _export_review(queue_path: Path, review_path: Path, actions: dict[str, tuple[str, str, str, str]]) -> pd.DataFrame:
    q = pd.read_csv(queue_path, dtype=str).fillna("")
    for image_id, (action, reviewer, codes, note) in actions.items():
        ix = q.index[q.image_id == image_id]
        assert len(ix) == 1
        i = ix[0]
        q.loc[i, "action"] = action
        q.loc[i, "reviewer"] = reviewer
        q.loc[i, "review_reason_codes"] = codes
        q.loc[i, "review_note"] = note
        q.loc[i, "reviewed_at"] = "2026-11-14T10:00:00Z"
        q.loc[i, "review_session_seconds"] = "12.5"
    q.to_csv(review_path, index=False)
    return q


def _direct_review_row(**changes) -> pd.DataFrame:
    row = {c: "" for c in T02_REVIEW_COLUMNS}
    row.update({
        "review_stage": "qc", "queue_id": "q-1", "rank": "1", "image_id": "img-1", "score": "0.4",
        "reason": "blur=0.8", "light": "day", "camera_id": "cam_A", "evidence_path": "images/img-1.jpg",
        "review_history": "", "reviewer": "qc user", "action": "KEEP", "review_reason_codes": "no_defect",
        "review_note": "", "reviewed_at": "2026-11-14T10:00:00Z", "review_session_seconds": "1.25",
    })
    row.update(changes)
    return pd.DataFrame([row], columns=T02_REVIEW_COLUMNS)


def test_dev_tail_normalization_orders_blurry_before_sharp():
    risk, _ = _tail_risk(pd.Series([10.0, 400.0]), pd.Series([100.0, 200.0, 300.0, 400.0]), "low")
    assert risk[0] > risk[1]


def test_dev_tail_normalization_orders_high_tail_risk_and_constant_dev_outlier():
    risk, _ = _tail_risk(pd.Series([2.25, 3.0]), pd.Series([0.0, 1.0, 2.0, 3.0]), "high")
    assert risk.tolist() == [0.0, 1.0]
    degenerate, _ = _tail_risk(pd.Series([2.0, 3.0]), pd.Series([2.0, 2.0, 2.0]), "high")
    assert degenerate.tolist() == [0.0, 1.0]
    degenerate_low, _ = _tail_risk(pd.Series([2.0, 1.0]), pd.Series([2.0, 2.0, 2.0]), "low")
    assert degenerate_low.tolist() == [0.0, 1.0]


def test_process_high_tail_signals_raise_score(monkeypatch, tmp_path):
    measured = pd.DataFrame({
        "image_id": ["dev-0", "dev-1", "dev-2", "dev-3", "eval-reference", "eval-high-risk"],
        "path": ["x.jpg"] * 6,
        "camera_id": ["cam_A"] * 6,
        "light": ["day"] * 6,
        "split": ["dev"] * 4 + ["eval"] * 2,
        "laplacian_variance": [100.0, 200.0, 300.0, 400.0, 400.0, 400.0],
        "frac_dark": [0.0, 1.0, 2.0, 3.0, 2.25, 2.25],
        "glare_local_saturated_max": [0.0, 1.0, 2.0, 3.0, 2.25, 3.0],
        "jpeg_blockiness": [0.0, 1.0, 2.0, 3.0, 2.25, 3.0],
    })
    monkeypatch.setattr("src.pipeline._measure_images", lambda *_args, **_kwargs: measured.copy())
    scored = process(_context(tmp_path), {"images": pd.DataFrame()}).set_index("image_id")
    assert scored.loc["eval-high-risk", "risk_glare"] > scored.loc["eval-reference", "risk_glare"]
    assert scored.loc["eval-high-risk", "risk_compression"] > scored.loc["eval-reference", "risk_compression"]
    assert scored.loc["eval-high-risk", "score"] > scored.loc["eval-reference", "score"]


def test_t02_contact_sheet_uses_configured_export_filename(tmp_path):
    review_row = _direct_review_row().iloc[0].to_dict()
    review_row["reason"] = "</script><script>alert(1)</script>"
    page = render_contact_sheet(
        pd.DataFrame([review_row], columns=T02_REVIEW_COLUMNS), tmp_path / "review.html",
        export_filename="senior_review_queue_reviewed.csv", reason_codes_col="review_reason_codes",
        reason_codes_allowed=T02_REASON_CODES,
    ).read_text(encoding="utf-8")
    assert 'const EXPORT_FILENAME = "senior_review_queue_reviewed.csv";' in page
    assert "a.download = EXPORT_FILENAME;" in page
    assert "JSON.parse(EXPORT_FILENAME)" not in page
    assert "validDecision(c, dec)" in page
    assert "no_defect is valid only with KEEP" in page
    assert 'class="ov"' not in page
    assert "</script><script>alert(1)</script>" not in page
    assert r"\u003c/script>\u003cscript>alert(1)" in page


def test_contact_sheet_only_shows_override_when_csv_has_column(tmp_path):
    queue = pd.DataFrame([{"rank": 1, "item_id": "x", "override_value": ""}])
    page = render_contact_sheet(queue, tmp_path / "generic.html").read_text(encoding="utf-8")
    assert 'class="ov"' in page
    assert "const HAS_OVERRIDE = true;" in page


def test_rank_uses_only_eval_top20_and_keeps_all_ids_in_ranking(tmp_path):
    ctx = _context(tmp_path)
    rows = pd.DataFrame({
        "image_id": [f"id-{i}" for i in range(24)],
        "score": np.arange(24, dtype=float),
        "split": ["dev"] * 4 + ["eval"] * 20,
        "path": [f"images/id-{i}.jpg" for i in range(24)],
        "camera_id": ["cam_A"] * 24, "light": ["day"] * 24, "reason": ["test"] * 24,
    })
    queue = rank(ctx, rows)
    assert len(rows) == 24
    assert len(queue) == 20
    assert queue.image_id.tolist() == [f"id-{i}" for i in range(23, 3, -1)]
    assert set(queue.review_stage) == {"qc"}
    assert queue.queue_id.nunique() == 1


@pytest.mark.parametrize("budget", [0, -1])
def test_rank_rejects_nonpositive_review_budget(tmp_path, budget):
    ctx = _context(tmp_path)
    ctx.config["params"]["budget"] = budget
    scored = pd.DataFrame({"image_id": ["x"], "score": [0.5], "split": ["eval"]})
    with pytest.raises(ValueError, match="review budget must be positive"):
        rank(ctx, scored)


def test_load_rejects_image_paths_missing_from_manifest(tmp_path):
    input_dir = tmp_path / "input"
    image_dir = input_dir / "images"
    image_dir.mkdir(parents=True)
    (image_dir / "one.jpg").write_bytes(b"fixture image placeholder")
    pd.DataFrame([{
        "image_id": "img-one", "path": "images/one.jpg", "camera_id": "cam_A", "light": "day", "split": "dev",
    }]).to_csv(input_dir / "images.csv", index=False)
    build_manifest(input_dir, ["images.csv"], "test fixture", "CC0-1.0").to_csv(input_dir / "manifest.csv", index=False)
    with pytest.raises(ValueError, match="metadata_path_not_in_manifest"):
        load(_context(tmp_path / "out", input_dir))


@pytest.mark.parametrize("path", ["../outside.jpg", "C:/outside.jpg"])
def test_image_path_rejects_paths_outside_input_root(tmp_path, path):
    ctx = _context(tmp_path / "out", tmp_path / "input")
    ctx.input_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="escapes input folder"):
        _image_path(ctx, pd.Series({"image_id": "img-one", "path": path}))


def test_missing_image_error_names_id_and_path(tmp_path):
    ctx = _context(tmp_path)
    images = pd.DataFrame([{
        "image_id": "missing-7", "path": "images/missing-7.jpg", "camera_id": "cam_A", "light": "day", "split": "dev",
    }])
    with pytest.raises(FileNotFoundError, match="missing-7.*images.*missing-7.jpg"):
        _measure_images(ctx, images, include_extra=False)


@pytest.mark.parametrize("changes, message", [
    ({"review_stage": "senior_qc"}, "stage"),
    ({"queue_id": "old-queue"}, "queue_id"),
    ({"image_id": "foreign-image"}, "not in this queue"),
    ({"action": "DELETE"}, "invalid action"),
    ({"reviewer": ""}, "reviewer is required"),
    ({"action": "HOLD", "review_reason_codes": "other", "review_note": ""}, "review_note is required"),
    ({"review_reason_codes": "blur;not-a-code"}, "invalid review_reason_code"),
    ({"action": "HOLD", "review_reason_codes": "no_defect", "review_note": "hold"}, "no_defect is valid only"),
    ({"review_session_seconds": "-1"}, "non-negative"),
    ({"review_session_seconds": "inf"}, "non-negative"),
    ({"reviewed_at": "not-a-time"}, "ISO-8601 timestamp"),
    ({"reviewed_at": "2026-11-14T10:00:00"}, "with timezone"),
])
def test_review_import_rejects_invalid_stage_queue_or_decision(tmp_path, changes, message):
    path = tmp_path / "review.csv"
    _direct_review_row(**changes).to_csv(path, index=False)
    with pytest.raises(ValueError, match=message):
        load_t02_review_decisions(path, "qc", "q-1", ["img-1"])


def test_review_import_rejects_missing_columns_and_duplicate_items(tmp_path):
    path = tmp_path / "review.csv"
    row = _direct_review_row()
    row.drop(columns=["queue_id"]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="missing required T02 columns.*queue_id"):
        load_t02_review_decisions(path, "qc", "q-1", ["img-1"])
    row = pd.concat([_direct_review_row(), _direct_review_row()], ignore_index=True)
    row.to_csv(path, index=False)
    with pytest.raises(ValueError, match="duplicate image_id"):
        load_t02_review_decisions(path, "qc", "q-1", ["img-1"])


def test_hold_escalates_with_history_and_reruns_are_idempotent(tmp_path):
    out = tmp_path / "out"
    assert main.main(["--track", "t02", "--output", str(out), "--offline"]) == 0
    qc = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    image_id = qc.iloc[0].image_id
    _export_review(out / "review_queue.csv", out / "review_queue_reviewed.csv", {
        image_id: ("HOLD", "QC One", "insufficient_evidence", "Need senior QC review.")
    })
    assert main.main(["--track", "t02", "--output", str(out), "--offline"]) == 0
    senior = pd.read_csv(out / "senior_review_queue.csv", dtype=str).fillna("")
    assert senior.image_id.tolist() == [image_id]
    assert json.loads(senior.iloc[0].review_history)[0]["reviewer"] == "QC One"
    _export_review(out / "senior_review_queue.csv", out / "senior_review_queue_reviewed.csv", {
        image_id: ("HOLD", "Senior One", "other", "Escalating to domain owner.")
    })
    assert main.main(["--track", "t02", "--output", str(out), "--offline"]) == 0
    domain = pd.read_csv(out / "domain_owner_review_queue.csv", dtype=str).fillna("")
    history = json.loads(domain.iloc[0].review_history)
    assert [event["reviewer"] for event in history] == ["QC One", "Senior One"]
    _export_review(out / "domain_owner_review_queue.csv", out / "domain_owner_review_queue_reviewed.csv", {
        image_id: ("HOLD", "Domain Owner", "insufficient_evidence", "Keep on hold pending evidence.")
    })
    assert main.main(["--track", "t02", "--output", str(out), "--offline"]) == 0
    decision = json.loads((out / "decision.json").read_text(encoding="utf-8"))
    assert decision["status"] == "HOLD"
    assert "eval top-20 review queue only" in decision["reason"]
    audit_path = out / "audit_log.jsonl"
    audit_count = len(audit_path.read_text(encoding="utf-8").splitlines())
    decision_count = len(pd.read_csv(out / "decision_log.csv"))
    assert audit_count == 3 and decision_count == 1
    assert main.main(["--track", "t02", "--output", str(out), "--offline"]) == 0
    assert len(audit_path.read_text(encoding="utf-8").splitlines()) == audit_count
    assert len(pd.read_csv(out / "decision_log.csv")) == decision_count

    # A changed QC decision is a new override event, and the active queue result changes.
    old_qc = pd.read_csv(out / "review_queue_reviewed.csv", dtype=str).fillna("")
    ix = old_qc.index[old_qc.image_id == image_id][0]
    old_qc.loc[ix, ["action", "review_reason_codes", "review_note", "reviewed_at"]] = [
        "RECAPTURE", "blur", "Blur prevents annotation.", "2026-11-14T10:05:00Z"
    ]
    for other_ix in old_qc.index[old_qc.index != ix]:
        old_qc.loc[other_ix, ["reviewer", "action", "review_reason_codes", "review_note", "reviewed_at", "review_session_seconds"]] = [
            "QC Two", "KEEP", "no_defect", "", "2026-11-14T10:06:00Z", "12.5"
        ]
    old_qc.to_csv(out / "review_queue_reviewed.csv", index=False)
    (out / "senior_review_queue_reviewed.csv").unlink()
    (out / "domain_owner_review_queue_reviewed.csv").unlink()
    assert main.main(["--track", "t02", "--output", str(out), "--offline"]) == 0
    assert json.loads((out / "decision.json").read_text(encoding="utf-8"))["status"] == "REWORK"
    events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert any(event["action"] == "review_override" and event["item_id"] == image_id for event in events)
    assert len(pd.read_csv(out / "decision_log.csv")) == decision_count + 1


def test_all_keeps_produce_queue_scoped_go(tmp_path):
    out = tmp_path / "out"
    assert main.main(["--track", "t02", "--output", str(out), "--offline"]) == 0
    queue = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    actions = {
        image_id: ("KEEP", "QC One", "no_defect", "")
        for image_id in queue.image_id
    }
    _export_review(out / "review_queue.csv", out / "review_queue_reviewed.csv", actions)
    assert main.main(["--track", "t02", "--output", str(out), "--offline"]) == 0
    decision = json.loads((out / "decision.json").read_text(encoding="utf-8"))
    assert decision["status"] == "GO"
    assert "eval top-20 review queue only" in decision["reason"]
    assert "does not approve release of the full batch" in decision["reason"]
