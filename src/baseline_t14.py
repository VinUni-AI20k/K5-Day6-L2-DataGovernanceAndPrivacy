"""T14 baseline: auto-predict with the DEFAULT threshold and export WITHOUT review (task spec, section 4).

    python -m src.main --track t14 --config configs/lab.yaml --pipeline src.baseline_t14 \
        --output out/baseline --run-name baseline --offline --seed 42

Same class adapter and same threshold param as the PoC (same pool / seed / config); what it does NOT do:
no box clipping, no suspicion ranking, no human review. It is the bar the PoC must beat.
"""
from __future__ import annotations

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.io import write_json
from .metrics.tracks import get_track
from .t14_tools import PRED_COLUMNS, build_class_map, load_inputs, map_classes, validate_predictions


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load_inputs(ctx.input_dir)
    class_map = build_class_map(data["label_map"], data["taxonomy"], ctx.param("class_alias"))
    thr = float(ctx.param("conf_threshold", 0.25))
    boxes = map_classes(data["preds"], class_map)
    pred = boxes[boxes["conf"] >= thr][PRED_COLUMNS].reset_index(drop=True)
    pred.to_csv(ctx.out(spec.pred_file), index=False)
    invalid = validate_predictions(pred, data["taxonomy"], data["images"])
    qa = {"n_exported": int(len(pred)), "n_invalid": int(len(invalid)),
          "invalid_label_rate": round(len(invalid) / len(pred), 4) if len(pred) else 0.0, "conf_threshold": thr}
    write_json(ctx.out("qa_report.json"), qa)
    ctx.stats.update({"n_items": int(len(boxes)), **qa})
    write_decision(Decision("HOLD", "BASELINE_ONLY", "Baseline: auto labels, default threshold, no review - never release on this",
                            ctx.config.get("owner", "baseline"), ctx.track, [str(ctx.out(spec.pred_file))], qa),
                   ctx.out("decision.json"), ctx.out("decision_log.csv"))
