"""YOUR PoC PIPELINE — integrated by Member 1 (Lead / Integrator & Decision Gate).

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   call T07 detector, compute image QC/risk scores, render redacted previews
    03 rank      prioritise top-B unique images into review_queue.csv + contact_sheet.html
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit_log.jsonl
    05 decide    GO / HOLD / REWORK risk gate with reason_code + owner, write outputs

Required output for T07: out/<pred_file> (`redactions.csv`) with columns
`["image_id", "x", "y", "w", "h"]`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import brightness_stats, laplacian_variance, load_rgb
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track
from .t07_detector import DETECTOR_INFO, detect_image

T07_BOX_COLUMNS = ["image_id", "x", "y", "w", "h"]


def _require_t07(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    if spec.track != "t07":
        raise NotImplementedError(
            f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
            f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
        )


def _clamp_box(box: dict[str, Any], width: int, height: int) -> dict[str, Any] | None:
    x = float(box["x"])
    y = float(box["y"])
    w = float(box["w"])
    h = float(box["h"])
    x0 = max(0.0, min(float(width), x))
    y0 = max(0.0, min(float(height), y))
    x1 = max(0.0, min(float(width), x + w))
    y1 = max(0.0, min(float(height), y + h))
    cw, ch = x1 - x0, y1 - y0
    if cw <= 0.0 or ch <= 0.0:
        return None
    return {
        "x": round(x0, 2),
        "y": round(y0, 2),
        "w": round(cw, 2),
        "h": round(ch, 2),
        "type": str(box.get("type", "unknown")),
        "conf": float(np.clip(float(box.get("conf", 0.5)), 0.0, 1.0)),
        "reason": str(box.get("reason", "")),
    }


def _union_area_frac(boxes: list[dict[str, Any]], width: int, height: int) -> float:
    if not boxes or width <= 0 or height <= 0:
        return 0.0
    mask = np.zeros((height, width), dtype=bool)
    for b in boxes:
        x0 = max(0, int(np.floor(b["x"])))
        y0 = max(0, int(np.floor(b["y"])))
        x1 = min(width, int(np.ceil(b["x"] + b["w"])))
        y1 = min(height, int(np.ceil(b["y"] + b["h"])))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True
    return float(mask.sum() / (width * height))


def _render_blurred_image(img_rgb: np.ndarray, boxes: list[dict[str, Any]], out_path: Path, radius: int) -> None:
    """Create redacted (pseudonymised) preview without modifying source fixtures."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pil_img = Image.fromarray(img_rgb.astype(np.uint8))
    H, W = img_rgb.shape[:2]
    for b in boxes:
        x0 = max(0, int(np.floor(b["x"])))
        y0 = max(0, int(np.floor(b["y"])))
        x1 = min(W, int(np.ceil(b["x"] + b["w"])))
        y1 = min(H, int(np.ceil(b["y"] + b["h"])))
        if x1 > x0 and y1 > y0:
            patch = pil_img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(radius=radius))
            pil_img.paste(patch, (x0, y0))
    pil_img.save(out_path, format="JPEG", quality=92)


def _parse_override_boxes(raw_val: str, width: int, height: int) -> list[dict[str, Any]]:
    """Parse reviewer `override_value` into clamped boxes.

    Supported formats:
      - JSON list of dicts/arrays: `[{"x":10,"y":20,"w":30,"h":40}]` or `[[10,20,30,40]]`
      - Semicolon-separated boxes: `10,20,30,40; 100,120,40,15`
    """
    text = raw_val.strip()
    if text.lower().startswith("add:"):
        text = text[4:].strip()
    elif text.startswith("+"):
        text = text[1:].strip()
    if not text:
        return []

    raw_boxes: list[dict[str, Any]] = []
    if text.startswith("["):
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError(f"override JSON must be a list, got {type(parsed).__name__}")
        for entry in parsed:
            if isinstance(entry, dict):
                raw_boxes.append({"x": entry["x"], "y": entry["y"], "w": entry["w"], "h": entry["h"],
                                  "type": entry.get("type", "reviewer"), "conf": 1.0, "reason": "reviewer_edit"})
            elif isinstance(entry, (list, tuple)) and len(entry) == 4:
                raw_boxes.append({"x": entry[0], "y": entry[1], "w": entry[2], "h": entry[3],
                                  "type": "reviewer", "conf": 1.0, "reason": "reviewer_edit"})
            else:
                raise ValueError(f"invalid box entry in override JSON: {entry!r}")
    else:
        for chunk in [c.strip() for c in text.split(";") if c.strip()]:
            parts = [p.strip() for p in chunk.split(",")]
            if len(parts) != 4:
                raise ValueError(f"override box must have 4 numbers `x,y,w,h`, got {chunk!r}")
            x, y, w, h = (float(p) for p in parts)
            raw_boxes.append({"x": x, "y": y, "w": w, "h": h, "type": "reviewer", "conf": 1.0, "reason": "reviewer_edit"})

    clamped: list[dict[str, Any]] = []
    for b in raw_boxes:
        cb = _clamp_box(b, width, height)
        if cb is not None:
            clamped.append(cb)
    return clamped


def _condition_slice(mean_bri: float, lap_var: float, dark_thr: float, blur_thr: float) -> str:
    tags = []
    if mean_bri < dark_thr:
        tags.append("dark")
    if lap_var < blur_thr:
        tags.append("blur")
    return "+".join(tags) if tags else "normal"


def _compute_review_score(
    boxes: list[dict[str, Any]],
    mean_bri: float,
    lap_var: float,
    area_frac: float,
    dark_thr: float,
    blur_thr: float,
) -> tuple[float, str, str]:
    """Higher score = needs human review sooner."""
    reasons: list[str] = []
    score = 0.0

    if mean_bri < dark_thr:
        score += 0.30
        reasons.append("dark_image")
    if lap_var < blur_thr:
        score += 0.30
        reasons.append("blurry_image")

    if not boxes:
        score += 0.40
        reasons.append("zero_detections")
        suggested = "inspect_missed_pii"
    else:
        min_conf = min(b["conf"] for b in boxes)
        score += 0.50 * (1.0 - min_conf)
        if min_conf < 0.70:
            reasons.append("low_conf_box")
        if area_frac > 0.25:
            score += 0.25
            reasons.append("high_redaction_area")
        if any(min(b["w"], b["h"]) < 14 for b in boxes):
            score += 0.15
            reasons.append("small_region")
        suggested = "verify_boxes" if reasons else "approve_if_clean"

    if not reasons:
        reasons.append("routine_qa")
    return round(float(score), 6), ";".join(reasons), suggested


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")

    data: dict[str, Any] = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}
    if get_track(ctx.track).track != "t07":
        return data

    images_csv = ctx.input_dir / "images.csv"
    if not images_csv.exists():
        raise FileNotFoundError(f"missing required input file: {images_csv}")
    images = pd.read_csv(images_csv)
    req_cols = ["image_id", "path", "width", "height"]
    missing = [c for c in req_cols if c not in images.columns]
    if missing:
        raise ValueError(f"images.csv missing required columns {missing}")
    if images["image_id"].duplicated().any():
        dups = images.loc[images["image_id"].duplicated(), "image_id"].tolist()
        raise ValueError(f"images.csv has duplicate image_id rows: {dups[:5]}")

    for r in images.itertuples(index=False):
        img_path = ctx.input_dir / str(r.path)
        if not img_path.exists():
            raise FileNotFoundError(f"image path listed in images.csv not found: {img_path}")

    data["images"] = images
    ctx.stats["n_images"] = int(len(images))
    if "split" in images.columns:
        ctx.stats["split_counts"] = {str(k): int(v) for k, v in images["split"].value_counts().items()}
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    _require_t07(ctx)
    images: pd.DataFrame = data["images"]
    blur_radius = int(ctx.param("blur_radius", 12))
    dark_thr = float(ctx.param("dark_mean_threshold", 55.0))
    blur_thr = float(ctx.param("blur_laplacian_threshold", 60.0))

    ctx.stats["detector"] = dict(DETECTOR_INFO)
    redacted_dir = ctx.out("redacted")
    redacted_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    raw_box_rows: list[dict[str, Any]] = []
    for r in images.itertuples(index=False):
        row_dict = r._asdict()
        src_path = (ctx.input_dir / str(r.path)).resolve()
        img_rgb = load_rgb(src_path)
        H, W = img_rgb.shape[:2]
        width = int(getattr(r, "width", W))
        height = int(getattr(r, "height", H))

        bri = brightness_stats(img_rgb)
        lap = laplacian_variance(img_rgb)
        cond_slice = _condition_slice(bri["mean"], lap, dark_thr, blur_thr)

        candidates = detect_image(img_rgb, row_dict, ctx)
        boxes: list[dict[str, Any]] = []
        for b in candidates:
            cb = _clamp_box(b, width, height)
            if cb is not None:
                boxes.append(cb)
                raw_box_rows.append({"image_id": str(r.image_id), **cb})

        area_frac = _union_area_frac(boxes, width, height)
        after_path = (redacted_dir / f"{r.image_id}.jpg").resolve()
        _render_blurred_image(img_rgb, boxes, after_path, radius=blur_radius)

        score, reason, suggested = _compute_review_score(
            boxes, bri["mean"], lap, area_frac, dark_thr, blur_thr
        )
        rows.append(
            {
                "image_id": str(r.image_id),
                "split": str(getattr(r, "split", "all")),
                "width": width,
                "height": height,
                "score": score,
                "reason": reason,
                "suggested_action": suggested,
                "slice": cond_slice,
                "before_path": str(src_path),
                "evidence_path": str(after_path),
                "n_boxes": len(boxes),
                "redacted_area_frac": round(area_frac, 6),
                "mean_brightness": round(bri["mean"], 2),
                "laplacian_var": round(lap, 2),
                "boxes_json": json.dumps(boxes, ensure_ascii=False),
            }
        )

    scored = pd.DataFrame(rows)
    raw_df = pd.DataFrame(raw_box_rows, columns=T07_BOX_COLUMNS + ["type", "conf", "reason"])
    raw_df.to_csv(ctx.out("redactions_raw.csv"), index=False)
    scored.drop(columns=["boxes_json"]).to_csv(ctx.out("image_summary.csv"), index=False)

    ctx.stats["n_raw_boxes"] = int(len(raw_df))
    ctx.stats["mean_redacted_area_frac"] = round(float(scored["redacted_area_frac"].mean()), 6) if len(scored) else 0.0
    return scored


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Rank unique images (1 row per image) by review suspicion `score` and render contact sheet."""
    budget = int(ctx.param("budget", 15))
    if "score" not in scored.columns or "image_id" not in scored.columns:
        raise ValueError("rank(): process() output needs `image_id` and numeric `score` columns")

    per_image = scored.drop_duplicates(subset=["image_id"], keep="first").reset_index(drop=True)
    q = make_review_queue(
        per_image,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason" if "reason" in per_image.columns else None,
        action_col="suggested_action" if "suggested_action" in per_image.columns else None,
        slice_col="slice" if "slice" in per_image.columns else None,
        evidence_col="evidence_path" if "evidence_path" in per_image.columns else None,
    )
    write_review_queue(q, ctx.out("review_queue.csv"))

    if "before_path" in per_image.columns and "evidence_path" in per_image.columns:
        q_html = q.merge(per_image[["image_id", "before_path", "boxes_json"]], left_on="item_id", right_on="image_id", how="left")
        boxes_by_item: dict[str, list[dict[str, Any]]] = {}
        for row in q_html.itertuples(index=False):
            parsed = json.loads(row.boxes_json) if isinstance(row.boxes_json, str) and row.boxes_json else []
            boxes_by_item[str(row.item_id)] = [
                {
                    "x": b["x"],
                    "y": b["y"],
                    "w": b["w"],
                    "h": b["h"],
                    "label": f"{b.get('type', 'pii')} {b.get('conf', 0):.2f}",
                    "color": "lime" if b.get("type") == "plate" else "red",
                }
                for b in parsed
            ]
        render_contact_sheet(
            q_html,
            ctx.out("contact_sheet.html"),
            image_col="evidence_path",
            before_image_col="before_path",
            fields=("rank", "item_id", "score", "reason", "suggested_action", "slice"),
            title=f"T07 Redaction Review Queue (top-{len(q_html)})",
            image_root=None,
            boxes_by_item=boxes_by_item,
            embed=True,
        )
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Apply reviewer decisions from `review_queue_reviewed.csv` and emit final box rows."""
    _ = queue
    blur_radius = int(ctx.param("blur_radius", 12))
    boxes_by_img: dict[str, list[dict[str, Any]]] = {}
    meta_by_img: dict[str, dict[str, Any]] = {}
    for row in scored.itertuples(index=False):
        img_id = str(row.image_id)
        boxes_by_img[img_id] = json.loads(row.boxes_json) if row.boxes_json else []
        meta_by_img[img_id] = {
            "width": int(row.width),
            "height": int(row.height),
            "before_path": Path(str(row.before_path)),
            "evidence_path": Path(str(row.evidence_path)),
        }

    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    escalated_ids: list[str] = []
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = int(len(reviewed))
        for r in reviewed.itertuples(index=False):
            img_id = str(r.item_id)
            if img_id not in meta_by_img:
                continue
            meta = meta_by_img[img_id]
            before_boxes = list(boxes_by_img[img_id])
            dec = r.reviewer_decision
            ov_raw = str(r.override_value).strip()

            if dec == "approve":
                ctx.audit.log(actor=r.reviewer, action="review:approve", item_id=img_id,
                              before=before_boxes, after=before_boxes, reason=r.review_note)
            elif dec == "reject":
                new_boxes = _parse_override_boxes(ov_raw, meta["width"], meta["height"]) if ov_raw else []
                boxes_by_img[img_id] = new_boxes
                ctx.audit.log(actor=r.reviewer, action="override:reject", item_id=img_id,
                              before=before_boxes, after=new_boxes, reason=r.review_note)
            elif dec == "edit":
                parsed = _parse_override_boxes(ov_raw, meta["width"], meta["height"])
                is_add = ov_raw.lower().startswith("add:") or ov_raw.startswith("+")
                new_boxes = before_boxes + parsed if is_add else parsed
                boxes_by_img[img_id] = new_boxes
                ctx.audit.log(actor=r.reviewer, action="override:edit", item_id=img_id,
                              before=before_boxes, after=new_boxes, reason=r.review_note)
            elif dec == "escalate":
                escalated_ids.append(img_id)
                ctx.audit.log(actor=r.reviewer, action="review:escalate", item_id=img_id,
                              before=before_boxes, after=before_boxes, reason=r.review_note)
            elif dec == "skip":
                ctx.audit.log(actor=r.reviewer, action="review:skip", item_id=img_id,
                              reason=r.review_note)

            if dec in {"reject", "edit"} and meta["before_path"].exists():
                img_rgb = load_rgb(meta["before_path"])
                _render_blurred_image(img_rgb, boxes_by_img[img_id], meta["evidence_path"], radius=blur_radius)
    else:
        ctx.stats["n_reviewed"] = 0

    ctx.stats["escalated_ids"] = escalated_ids
    final_rows: list[dict[str, Any]] = []
    area_fracs: list[float] = []
    for row in scored.itertuples(index=False):
        img_id = str(row.image_id)
        meta = meta_by_img[img_id]
        img_boxes = boxes_by_img[img_id]
        area_fracs.append(_union_area_frac(img_boxes, meta["width"], meta["height"]))
        for b in img_boxes:
            final_rows.append(
                {
                    "image_id": img_id,
                    "x": b["x"],
                    "y": b["y"],
                    "w": b["w"],
                    "h": b["h"],
                    "type": b.get("type", "unknown"),
                    "conf": b.get("conf", 1.0),
                    "reason": b.get("reason", ""),
                }
            )

    ctx.stats["n_final_boxes"] = int(len(final_rows))
    ctx.stats["final_mean_redacted_area_frac"] = round(float(np.mean(area_fracs)), 6) if area_fracs else 0.0
    high_risk_thr = float(ctx.param("high_risk_score_threshold", 0.55))
    ctx.stats["n_high_risk_images"] = int((scored["score"] >= high_risk_thr).sum()) if len(scored) else 0

    if not final_rows:
        return pd.DataFrame(columns=T07_BOX_COLUMNS + ["type", "conf", "reason"])
    return pd.DataFrame(final_rows)


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    owner = str(ctx.config.get("owner", "")).strip() or "TODO-owner"
    spec = get_track(ctx.track)
    evidence = [str(ctx.out(spec.pred_file)), str(ctx.out("review_queue.csv")), str(ctx.out("audit_log.jsonl"))]

    n_images = int(ctx.stats.get("n_images", 0))
    n_boxes = int(len(final))
    n_reviewed = int(ctx.stats.get("n_reviewed", 0))
    n_high_risk = int(ctx.stats.get("n_high_risk_images", 0))
    escalated = list(ctx.stats.get("escalated_ids", []))
    mean_area = float(ctx.stats.get("final_mean_redacted_area_frac", 0.0))
    max_area = float(ctx.param("max_redacted_area_frac", 0.35))
    require_review = bool(ctx.param("require_review_for_high_risk", True))
    detector_mode = str((ctx.stats.get("detector") or {}).get("mode", "unknown"))

    metrics_snapshot = {
        "n_images": n_images,
        "n_final_boxes": n_boxes,
        "n_high_risk_images": n_high_risk,
        "n_reviewed": n_reviewed,
        "mean_redacted_area_frac": mean_area,
        "detector_mode": detector_mode,
    }

    if n_images == 0:
        dec = Decision(
            status="HOLD",
            reason_code="EMPTY_INPUT",
            reason="No images found to redact.",
            owner=owner,
            scope=ctx.track,
            evidence=evidence,
            metrics=metrics_snapshot,
        )
    elif escalated:
        dec = Decision(
            status="HOLD",
            reason_code="ESCALATED_BY_REVIEWER",
            reason=f"Reviewer escalated {len(escalated)} image(s): {escalated[:5]}.",
            owner=owner,
            scope=ctx.track,
            evidence=evidence,
            metrics=metrics_snapshot,
        )
    elif mean_area > max_area:
        dec = Decision(
            status="REWORK",
            reason_code="OVER_REDACTION_RISK",
            reason=f"Mean redacted area {mean_area:.3f} exceeds frozen threshold {max_area:.3f}; tune detector/padding.",
            owner=owner,
            scope=ctx.track,
            evidence=evidence,
            metrics=metrics_snapshot,
        )
    elif detector_mode == "stub" or n_boxes == 0:
        dec = Decision(
            status="REWORK",
            reason_code="DETECTOR_STUB_NO_DETECTIONS",
            reason="No PII boxes produced (detector is still in stub mode or returned 0 detections).",
            owner=owner,
            scope=ctx.track,
            evidence=evidence,
            metrics=metrics_snapshot,
        )
    elif require_review and n_high_risk > 0 and n_reviewed == 0:
        dec = Decision(
            status="HOLD",
            reason_code="NEEDS_HUMAN_REVIEW",
            reason=f"{n_high_risk} high-risk image(s) queued in review_queue.csv awaiting human sign-off.",
            owner=owner,
            scope=ctx.track,
            evidence=evidence,
            metrics=metrics_snapshot,
        )
    else:
        dec = Decision(
            status="GO",
            reason_code="REDACTION_QA_PASSED",
            reason=(
                f"Redacted/pseudonymised {n_boxes} region(s) across {n_images} images "
                f"(mean area {mean_area:.3f}, {n_reviewed} reviewed)."
            ),
            owner=owner,
            scope=ctx.track,
            evidence=evidence,
            metrics=metrics_snapshot,
        )

    ctx.audit.log(
        actor=owner,
        action=f"decision:{dec.canonical}",
        item_id=ctx.track,
        after={"status": dec.status, "reason_code": dec.reason_code, "metrics": metrics_snapshot},
        reason=dec.reason,
    )
    return dec


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    out_cols = spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]
    final[out_cols].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
