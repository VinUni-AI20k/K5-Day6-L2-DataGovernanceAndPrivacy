"""Tests for T07 human review + re-export (owner: Người 3). No ground truth needed."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.common.io import sha256_file
from src.common.review import AuditLog, load_review_decisions
from src.common.context import RunContext
from src.t07_export import export_images, export_redacted_images, image_sizes, validate_boxes, write_redactions
from src.t07_review import apply_review, build_queue, parse_override, review_step, write_queue_and_sheet

FX = Path("fixtures/t07_redaction")


@pytest.fixture
def images():
    return pd.read_csv(FX / "images.csv").head(3)


@pytest.fixture
def cands(images):
    rows = []
    for i, r in enumerate(images.itertuples()):
        rows.append(dict(region_id=f"{r.image_id}_f0", image_id=r.image_id, type="face", x=10 + i, y=20, w=20, h=24,
                         confidence=0.9, score=0.1 + i / 100, reason="test", slice="condition=normal", path=r.path))
        rows.append(dict(region_id=f"{r.image_id}_p0", image_id=r.image_id, type="plate", x=600, y=340, w=30, h=10,
                         confidence=0.3, score=0.9 - i / 100, reason="test", slice="size=small", path=r.path))
    return pd.DataFrame(rows)


def _reviewed(tmp_path, queue, decisions):
    """decisions: {region_id: (decision, override_value, reviewer)}"""
    q = queue.copy().astype(str)
    for rid, (dec, ov, who) in decisions.items():
        m = q.item_id == rid
        q.loc[m, "reviewer_decision"], q.loc[m, "override_value"], q.loc[m, "reviewer"] = dec, ov, who
        q.loc[m, "review_note"] = "unit test"
    p = tmp_path / "review_queue_reviewed.csv"
    q.to_csv(p, index=False)
    return p


def test_queue_respects_budget_and_order(cands):
    q = build_queue(cands, budget=4)
    assert len(q) == 4
    assert list(q.score) == sorted(q.score, reverse=True)
    assert q.item_id.iloc[0] == "pii_00_p0"


def test_windows_paths_open_on_any_os(tmp_path, cands):
    win = cands.assign(path=cands.path.str.replace("/", "\\"))       # as written by str(Path) on Windows
    q = build_queue(win, budget=2)
    assert not q.evidence_path.str.contains("\\\\", regex=False).any()
    _, hp = write_queue_and_sheet(q, win, tmp_path, FX)
    assert "missing:" not in hp.read_text(encoding="utf-8")


def test_contact_sheet_written(tmp_path, cands):
    q = build_queue(cands, budget=3)
    qp, hp = write_queue_and_sheet(q, cands, tmp_path, FX)
    assert qp.exists() and hp.exists()
    assert "Export decisions CSV" in hp.read_text(encoding="utf-8")


def test_reject_edit_escalate_and_audit(tmp_path, cands, images):
    q = build_queue(cands, budget=6)
    edit = json.dumps({"type": "face", "x": 630, "y": 350, "w": 40, "h": 40})   # clipped to 640x360
    add = json.dumps([{"type": "plate", "x": 100, "y": 100, "w": 30, "h": 10},
                      {"type": "face", "x": 200, "y": 150, "w": 12, "h": 14}])
    p = _reviewed(tmp_path, q, {"pii_00_p0": ("reject", "", "an"), "pii_01_p0": ("edit", edit, "an"),
                                 "pii_02_p0": ("edit", add, "an"), "pii_00_f0": ("escalate", "", "an"),
                                 "pii_01_f0": ("approve", "", "an")})
    audit = AuditLog(tmp_path / "audit_log.jsonl")
    final, s = review_step(cands, q, p, audit, image_sizes(images))
    assert "pii_00_p0" not in set(final.region_id)                       # reject removes
    e = final.set_index("region_id").loc["pii_01_p0"]
    assert (e.type, e.x, e.y, e.w, e.h, e.source) == ("face", 630, 350, 10, 10, "reviewer")
    assert "pii_02_p0+add1" in set(final.region_id) and s["added"] == 1
    assert s["escalated"] == ["pii_00_f0"] and "pii_00_f0" in set(final.region_id)  # escalate keeps box
    assert s["pending"] == 1                                              # pii_02_f0 not decided
    assert validate_boxes(final, image_sizes(images)) == []
    ev = {e["item_id"]: e for e in audit.read()}
    assert ev["pii_00_p0"]["after"] is None and ev["pii_00_p0"]["before"]["type"] == "plate"
    assert ev["pii_01_p0"]["actor"] == "an" and ev["pii_01_p0"]["extra"]["region_id"] == "pii_01_p0"
    assert len(cands) == 6                                                # raw candidates untouched


def test_decision_without_reviewer_fails(tmp_path, cands):
    q = build_queue(cands, budget=3)
    p = _reviewed(tmp_path, q, {"pii_00_p0": ("reject", "", "")})
    with pytest.raises(ValueError, match="reviewer"):
        load_review_decisions(p)


@pytest.mark.parametrize("bad", ["", "{not json", '{"type":"car","x":1,"y":1,"w":5,"h":5}',
                                 '{"type":"face","x":1,"y":1,"w":0,"h":5}', '{"type":"face","x":1}',
                                 '{"type":"face","x":900,"y":900,"w":5,"h":5}'])
def test_bad_edit_json_fails_clearly(bad):
    with pytest.raises(ValueError, match="edit on r1"):
        parse_override(bad, "r1", (640, 360))


def test_stale_review_row_is_flagged(tmp_path, cands):
    q = build_queue(cands, budget=2)
    p = _reviewed(tmp_path, q, {"pii_00_p0": ("approve", "", "an")})
    final, s = review_step(cands[cands.region_id != "pii_00_p0"], q, p, None)
    assert s["stale"] == ["pii_00_p0"]


def test_export_does_not_touch_input_and_masks_pixels(tmp_path, cands, images):
    before = {p: sha256_file(FX / p) for p in images.path}
    m = export_images(cands, images, FX, tmp_path / "redacted_images")
    assert after_equal(before)
    assert len(m) == 3 and (m.n_regions == 2).all()
    assert (tmp_path / "redacted_images" / "pii_00.jpg").exists()
    with pytest.raises(ValueError, match="inside the input folder"):
        export_images(cands, images, FX, FX / "images")
    out = write_redactions(cands, tmp_path / "redactions.csv")
    assert list(pd.read_csv(out).columns[:5]) == ["image_id", "x", "y", "w", "h"]


def after_equal(before):
    return all(sha256_file(FX / p) == h for p, h in before.items())


def test_validate_boxes_catches_out_of_bounds(images):
    bad = pd.DataFrame([{"image_id": "pii_00", "x": 630, "y": 10, "w": 20, "h": 5}])
    assert validate_boxes(bad, image_sizes(images))[0]["problem"] == "invalid_box"


def _ctx(tmp_path):
    import numpy as np
    return RunContext(track="t07", input_dir=FX, output_dir=tmp_path, config={"params": {"budget": 15}}, seed=42,
                      rng=np.random.default_rng(42), audit=AuditLog(tmp_path / "audit_log.jsonl"))


def test_contract_apply_review_with_ctx(tmp_path, cands):
    """Same call as src/pipeline.py: apply_review(ctx, candidates, reviewed) -> DataFrame."""
    ctx = _ctx(tmp_path)
    q = build_queue(cands, budget=4)
    write_queue_and_sheet(q, cands, tmp_path, FX)
    p = _reviewed(tmp_path, q, {"pii_00_p0": ("reject", "", "han"), "pii_01_p0": ("escalate", "", "han")})
    final = apply_review(ctx, cands, load_review_decisions(p))
    assert isinstance(final, pd.DataFrame) and "pii_00_p0" not in set(final.region_id)
    s = ctx.stats["review"]
    assert s["escalated"] == ["pii_01_p0"] and s["pending"] == 2
    assert {e["action"] for e in ctx.audit.read()} == {"review:reject", "review:escalate"}
    # no reviewed rows yet (first run) -> everything kept, all queued items pending
    final0 = apply_review(_ctx(tmp_path / "first"), cands, pd.DataFrame())
    assert len(final0) == len(cands)


def test_contract_export_with_ctx_clamps_boxes(tmp_path, cands, images):
    ctx = _ctx(tmp_path)
    regions = pd.concat([cands, pd.DataFrame([dict(region_id="out", image_id="pii_00", type="face",
                                                   x=700, y=10, w=20, h=20)])], ignore_index=True)
    assert export_redacted_images(ctx, regions, images) is None
    assert (tmp_path / "redacted_images" / "pii_00.jpg").exists()
    e = ctx.stats["export"]
    assert e["n_images"] == 3 and e["n_regions_skipped"] == 1        # fully outside box skipped, not crashed
