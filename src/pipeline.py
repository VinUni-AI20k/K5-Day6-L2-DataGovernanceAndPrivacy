"""T14 PoC pipeline: Auto-Annotation + Human QC Exporter.

Run (offline, seed 42):
    python -m src.main --track t14 --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42

Steps (contract of the lab):
    01 load      manifest/provenance check + fixtures + class adapter inputs
    02 process   model class_id -> taxonomy, clip boxes, confidence filter, suspicion score
    03 rank      review queue of budget B (out/review_queue.csv + contact_sheet.html)
    04 review    apply out/review_queue_reviewed.csv (approve/reject/edit) and out/review_additions.csv (missed boxes)
    05 decide    validate + export (CSV, YOLO, COCO) then GO / HOLD / REWORK with reason_code + owner

The prediction file is a SIMULATED fixture, not real model inference: never report it as model accuracy.
The pipeline never reads fixtures/*/gt/. Thresholds/weights are params (configs/lab.yaml), frozen before eval.
"""
from __future__ import annotations

import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.io import write_json
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track
from .t14_tools import (add_box_ids, add_missed, add_suspicion, apply_review, build_class_map, export_coco, export_yolo,
                        final_predictions, load_inputs, map_classes, normalise_boxes, roundtrip_check, validate_predictions)


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    data = load_inputs(ctx.input_dir)
    data["manifest"] = pd.read_csv(manifest)
    data["class_map"] = build_class_map(data["label_map"], data["taxonomy"], ctx.param("class_alias"))
    ctx.audit.log(actor="pipeline", action="class_map", item_id="label_map", after=data["class_map"])
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """One row per model box with flags + `kept` (passes the confidence filter) + suspicion `score`."""
    thr = float(ctx.param("conf_threshold", 0.25))
    boxes = add_box_ids(map_classes(data["preds"], data["class_map"]))
    boxes, n_zero = normalise_boxes(boxes, data["images"])
    boxes["kept"] = boxes["conf"] >= thr
    boxes["source"] = "model"
    boxes = add_suspicion(boxes, thr, ctx.config.get("params") or {})
    ctx.stats.update({"conf_threshold": thr, "n_model_boxes": int(len(data["preds"])), "n_zero_area_dropped": n_zero,
                      "n_clipped": int(boxes["clipped"].sum()), "n_below_threshold": int((~boxes["kept"]).sum())})
    boxes.to_csv(ctx.out("boxes_all.csv"), index=False)       # full scored table: used by tools/t14_eval_dev.py
    return boxes


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    budget = int(ctx.param("budget", 30))
    s = scored.assign(action=scored["kept"].map({True: "keep (check)", False: "dropped by conf filter (rescue?)"}))
    q = make_review_queue(s, id_col="box_id", score_col="score", budget=budget, reason_col="reason",
                          action_col="action", slice_col="class", evidence_col="path")
    write_review_queue(q, ctx.out("review_queue.csv"))
    by_id = scored.set_index("box_id")
    boxes_by_item = {}
    for bid in q["item_id"]:
        img = by_id.loc[bid, "image_id"]
        others = scored[(scored["image_id"] == img) & (scored["box_id"] != bid)].to_dict("records")
        me = by_id.loc[bid]
        boxes_by_item[bid] = (
            [{"x": o["x"], "y": o["y"], "w": o["w"], "h": o["h"], "label": o["class"], "color": "gray"} for o in others]
            + [{"x": me["x"], "y": me["y"], "w": me["w"], "h": me["h"], "label": f"{me['class']} {me['conf']:.2f}", "color": "red"}]
        )
    render_contact_sheet(q, ctx.out("contact_sheet.html"), image_root=ctx.input_dir, boxes_by_item=boxes_by_item,
                         title="T14 review queue (red = box to check, gray = other boxes)")
    ctx.stats["queue_size"] = int(len(q))
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, data: dict, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    final = scored.assign(decision="", reviewed_by="")
    ctx.stats.update({"n_reviewed": 0, "n_added": 0})
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        unknown = sorted(set(reviewed["item_id"]) - set(queue["item_id"]))
        if unknown:
            raise ValueError(f"reviewed file has items outside the review queue: {unknown[:5]}")
        final, diff = apply_review(final, reviewed, data["taxonomy"], ctx.audit)
        diff.to_csv(ctx.out("correction_diff.csv"), index=False)
        ctx.stats["n_reviewed"] = int(len(reviewed))
    add_path = ctx.output_dir / "review_additions.csv"
    if add_path.exists():
        adds = pd.read_csv(add_path)
        final = add_missed(final, adds, data["taxonomy"], data["images"], ctx.audit)
        ctx.stats["n_added"] = int(len(adds))
    return final


# ---------------------------------------------------------------- 05 decide
def export(ctx: RunContext, data: dict, final: pd.DataFrame) -> dict:
    """Validate then write predictions.csv + YOLO + COCO; returns the QA report."""
    spec = get_track(ctx.track)
    pred = final_predictions(final)
    invalid = validate_predictions(pred, data["taxonomy"], data["images"])
    if len(invalid):
        invalid.to_csv(ctx.out("invalid_labels.csv"), index=False)
    pred.to_csv(ctx.out(spec.pred_file), index=False)
    export_yolo(pred, data["taxonomy"], data["images"], ctx.out("yolo/data.yaml").parent)
    export_coco(pred, data["taxonomy"], data["images"], ctx.out("coco.json"))
    rt = roundtrip_check(pred, data["taxonomy"], data["images"], ctx.out("yolo/data.yaml").parent, ctx.out("coco.json"))
    qa = {"n_exported": int(len(pred)), "n_invalid": int(len(invalid)),
          "invalid_label_rate": round(len(invalid) / len(pred), 4) if len(pred) else 0.0, **rt}
    write_json(ctx.out("qa_report.json"), qa)
    return qa


def decide(ctx: RunContext, qa: dict) -> Decision:
    """Policy frozen before eval. GO means 'format-valid AND reviewed', never 'accurate' (no GT here)."""
    n_q, n_r = int(ctx.stats.get("queue_size", 0)), int(ctx.stats.get("n_reviewed", 0))
    frac = n_r / n_q if n_q else 0.0
    need = float(ctx.param("min_review_fraction", 0.8))
    owner = ctx.config.get("owner", "TODO-owner")
    snap = {**qa, "queue_size": n_q, "n_reviewed": n_r, "review_fraction": round(frac, 3), "min_review_fraction": need}
    ev = [str(ctx.out("qa_report.json")), str(ctx.out("review_queue.csv"))]
    if qa["n_invalid"] > 0 or not (qa["yolo_ok"] and qa["coco_ok"]):
        return Decision("REWORK", "EXPORT_QA_FAILED", "Invalid labels or YOLO/COCO round-trip mismatch", owner, ctx.track, ev, snap)
    if n_r == 0:
        return Decision("HOLD", "NOT_REVIEWED", "Auto labels only: no human review applied yet", owner, ctx.track, ev, snap)
    if frac < need:
        return Decision("HOLD", "REVIEW_INCOMPLETE", f"Only {frac:.0%} of the review queue was reviewed (need {need:.0%})", owner, ctx.track, ev, snap)
    return Decision("GO", "REVIEWED_AND_VALID", "Queue reviewed and export passes validation (accuracy not asserted: no eval GT in this repo)", owner, ctx.track, ev, snap)


def run(ctx: RunContext) -> None:
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, data, scored, queue)
    qa = export(ctx, data, final)
    ctx.stats.update({"n_exported": qa["n_exported"], "n_invalid": qa["n_invalid"]})
    write_decision(decide(ctx, qa), ctx.out("decision.json"), ctx.out("decision_log.csv"))
