"""T07 human-in-the-loop: review queue, contact sheet, reviewer decisions -> final regions + audit log.

Input = candidate DataFrame from the detector/ranking step (owner: Người 1), schema CANDIDATE_COLUMNS:
    region_id,image_id,type,x,y,w,h,confidence,score,reason,slice,path
(`score` higher = review first; `path` = image path relative to the input folder.)

Reviewer decisions (column `reviewer_decision` in review_queue_reviewed.csv):
    approve  : keep the box as is
    reject   : false positive -> remove the region (it will NOT be redacted)
    edit     : replace type/coordinates with the JSON in `override_value`, e.g.
               {"type":"face","x":100,"y":50,"w":40,"h":35}
               a JSON *list* of such objects = first one replaces the region, the rest are ADDED as new
               regions (use it for a face/plate the detector missed next to the queued one)
    escalate : keep the box redacted AND flag the run (decision step should not GO)
    skip     : no action yet (counted as pending)
Every applied decision is appended to the audit log (reviewer, action, region_id, before, after, reason, ts).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.review import AuditLog, load_review_decisions, make_review_queue, write_review_queue

CANDIDATE_COLUMNS = ["region_id", "image_id", "type", "x", "y", "w", "h",
                     "confidence", "score", "reason", "slice", "path"]
REGION_TYPES = {"face", "plate"}
BOX_KEYS = ("x", "y", "w", "h")


# ------------------------------------------------------------------ helpers
def check_candidates(cands: pd.DataFrame) -> None:
    missing = [c for c in CANDIDATE_COLUMNS if c not in cands.columns]
    if missing:
        raise ValueError(f"candidate DataFrame missing columns {missing}; expected {CANDIDATE_COLUMNS}")
    dup = cands["region_id"].astype(str).duplicated()
    if dup.any():
        raise ValueError(f"duplicate region_id in candidates: {cands.loc[dup, 'region_id'].tolist()[:5]}")


def portable_path(p) -> str:
    """'images\\pii_00.jpg' (written on Windows) -> 'images/pii_00.jpg' so it also opens on macOS/Linux."""
    return str(p).replace("\\", "/")


def _box(row) -> dict:
    return {"type": str(row["type"]), **{k: int(row[k]) for k in BOX_KEYS}}


def clip_box(x: float, y: float, w: float, h: float, width: int, height: int) -> tuple[int, int, int, int]:
    """Clip a box to the image; returns (x, y, w, h) ints, w/h may become 0 if fully outside."""
    x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
    x1, y1 = min(int(width), int(round(x + w))), min(int(height), int(round(y + h)))
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def parse_override(value: str, region_id: str, size: tuple[int, int] | None = None) -> list[dict]:
    """Parse `override_value` of an `edit` row -> list of validated boxes (clipped to `size`=(W,H))."""
    if not str(value).strip():
        raise ValueError(f"edit on {region_id}: override_value is empty; expected JSON like "
                         '{"type":"face","x":100,"y":50,"w":40,"h":35}')
    try:
        obj = json.loads(value)
    except json.JSONDecodeError as e:
        raise ValueError(f"edit on {region_id}: override_value is not valid JSON ({e.msg}): {value!r}") from None
    items = obj if isinstance(obj, list) else [obj]
    if not items:
        raise ValueError(f"edit on {region_id}: empty JSON list")
    boxes = []
    for it in items:
        if not isinstance(it, dict) or any(k not in it for k in ("type", *BOX_KEYS)):
            raise ValueError(f"edit on {region_id}: each box needs keys type,x,y,w,h; got {it!r}")
        t = str(it["type"]).strip().lower()
        if t not in REGION_TYPES:
            raise ValueError(f"edit on {region_id}: type must be one of {sorted(REGION_TYPES)}, got {t!r}")
        try:
            x, y, w, h = (float(it[k]) for k in BOX_KEYS)
        except (TypeError, ValueError):
            raise ValueError(f"edit on {region_id}: x,y,w,h must be numbers; got {it!r}") from None
        if w <= 0 or h <= 0:
            raise ValueError(f"edit on {region_id}: w and h must be > 0; got {it!r}")
        if size is not None:
            x, y, w, h = clip_box(x, y, w, h, *size)
            if w == 0 or h == 0:
                raise ValueError(f"edit on {region_id}: box lies outside the image {size}: {it!r}")
        boxes.append({"type": t, "x": int(round(x)), "y": int(round(y)), "w": int(round(w)), "h": int(round(h))})
    return boxes


# ------------------------------------------------------------------ queue + contact sheet
def build_queue(cands: pd.DataFrame, budget: int = 15) -> pd.DataFrame:
    """Top-`budget` regions by score (ties broken by region_id for determinism)."""
    check_candidates(cands)
    c = cands.sort_values(["score", "region_id"], ascending=[False, True], kind="mergesort").copy()
    c["path"] = c["path"].map(portable_path)
    c["suggested_action"] = c["confidence"].map(lambda v: "approve" if float(v) >= 0.5 else "check: reject or edit")
    c["reason"] = c["type"].astype(str) + " conf=" + c["confidence"].astype(float).round(2).astype(str) + " | " + c["reason"].astype(str)
    return make_review_queue(c, id_col="region_id", score_col="score", budget=budget, reason_col="reason",
                             action_col="suggested_action", slice_col="slice", evidence_col="path")


def write_queue_and_sheet(queue: pd.DataFrame, cands: pd.DataFrame, out_dir: Path, image_root: Path,
                          title: str = "T07 redaction review queue") -> tuple[Path, Path]:
    """Write review_queue.csv + contact_sheet.html (before image + image with the suspect box drawn)."""
    out_dir = Path(out_dir)
    q_path = write_review_queue(queue, out_dir / "review_queue.csv")
    by_id = cands.assign(region_id=cands["region_id"].astype(str)).set_index("region_id")
    boxes = {}
    for rid in queue["item_id"]:
        r = by_id.loc[rid]
        color = "red" if r["type"] == "face" else "orange"
        boxes[rid] = [{"x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"], "color": color,
                       "label": f'{r["type"]} {float(r["confidence"]):.2f}'}]
    sheet_df = queue.assign(before_path=queue["evidence_path"])
    html_path = render_contact_sheet(sheet_df, out_dir / "contact_sheet.html", image_col="evidence_path",
                                     before_image_col="before_path", image_root=image_root, title=title,
                                     boxes_by_item=boxes)
    return q_path, html_path


# ------------------------------------------------------------------ apply decisions
def apply_decisions(cands: pd.DataFrame, reviewed: pd.DataFrame, audit: AuditLog | None,
                    sizes: dict[str, tuple[int, int]] | None = None,
                    queue_ids: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Apply reviewer decisions to the candidates. Raw `cands` is never modified.

    reviewed : output of common.review.load_review_decisions (only rows with a decision; reviewer validated)
    sizes    : {image_id: (W, H)} to clip edited boxes
    queue_ids: region ids that were in the queue (to count pending = queued but not decided)
    Returns (final regions DataFrame with column `source` = auto|reviewer, summary dict).
    """
    check_candidates(cands)
    final = cands.copy()
    final["region_id"] = final["region_id"].astype(str)
    final["source"] = "auto"
    summary = {"n_reviewed": 0, "approve": 0, "reject": 0, "edit": 0, "escalate": 0, "skip": 0,
               "added": 0, "stale": [], "escalated": []}
    added_rows = []
    for r in reviewed.itertuples(index=False):
        rid, dec, who, note = str(r.item_id), r.reviewer_decision, r.reviewer, r.review_note
        mask = final["region_id"] == rid
        if not mask.any():
            summary["stale"].append(rid)        # review file does not match this run's candidates
            if audit:
                audit.log(actor=who, action="review:stale", item_id=rid, reason=note, reviewer=who, region_id=rid)
            continue
        summary["n_reviewed"] += 1
        summary[dec] += 1
        row = final.loc[mask].iloc[0]
        before = _box(row)
        after = before
        if dec == "reject":
            final = final.loc[~mask]
            after = None
        elif dec == "edit":
            size = (sizes or {}).get(str(row["image_id"]))
            boxes = parse_override(r.override_value, rid, size)
            first, extra = boxes[0], boxes[1:]
            for k, v in first.items():
                final.loc[mask, k] = v
            final.loc[mask, "source"] = "reviewer"
            for i, b in enumerate(extra, 1):
                new = row.to_dict() | b | {"region_id": f"{rid}+add{i}", "source": "reviewer",
                                           "confidence": 1.0, "reason": f"added by reviewer {who}"}
                added_rows.append(new)
            summary["added"] += len(extra)
            after = boxes if extra else first
        elif dec == "escalate":
            summary["escalated"].append(rid)    # box stays redacted (fail-safe)
        if audit:
            audit.log(actor=who, action=f"review:{dec}", item_id=rid, before=before, after=after, reason=note,
                      reviewer=who, region_id=rid, image_id=str(row["image_id"]))
    if added_rows:
        final = pd.concat([final, pd.DataFrame(added_rows)], ignore_index=True)
    decided = set(reviewed["item_id"].astype(str)) - {i for i in reviewed.loc[reviewed.reviewer_decision == "skip", "item_id"].astype(str)}
    summary["pending"] = len([q for q in (queue_ids or []) if q not in decided])
    return final.reset_index(drop=True), summary


def review_step(cands: pd.DataFrame, queue: pd.DataFrame, reviewed_path: Path, audit: AuditLog | None,
                sizes: dict[str, tuple[int, int]] | None = None) -> tuple[pd.DataFrame, dict]:
    """Convenience for pipeline.review(): no reviewed file -> pass through with everything pending."""
    queue_ids = queue["item_id"].astype(str).tolist()
    if not Path(reviewed_path).exists():
        final = cands.copy()
        final["region_id"] = final["region_id"].astype(str)
        final["source"] = "auto"
        return final, {"n_reviewed": 0, "pending": len(queue_ids), "escalated": [], "stale": [],
                       "reviewed_file": None}
    reviewed = load_review_decisions(reviewed_path)   # fails loudly on missing reviewer / unknown decision
    final, summary = apply_decisions(cands, reviewed, audit, sizes, queue_ids)
    summary["reviewed_file"] = str(reviewed_path)
    return final, summary


# ------------------------------------------------------------------ integration contract (docs/T07_INTEGRATION_CONTRACT.md)
def apply_review(ctx, candidates: pd.DataFrame, reviewed: pd.DataFrame) -> pd.DataFrame:
    """Contract API used by src/pipeline.py.

    reviewed: rows from common.review.load_review_decisions (may be empty -> everything stays pending).
    Edited boxes are clipped to the image size from images.csv; every decision is appended to ctx.audit.
    The review summary (counts, escalated, pending, stale) is stored in ctx.stats["review"] so the decide
    step can return REWORK on escalate / pending / stale without re-reading the review file.
    """
    images = pd.read_csv(Path(ctx.input_dir) / "images.csv")
    sizes = {str(r.image_id): (int(r.width), int(r.height)) for r in images.itertuples()}
    queue_path = Path(ctx.output_dir) / "review_queue.csv"
    queue_ids = pd.read_csv(queue_path, dtype=str)["item_id"].tolist() if queue_path.exists() else []
    if reviewed is None or len(reviewed) == 0:
        reviewed = pd.DataFrame(columns=["item_id", "reviewer_decision", "reviewer", "override_value", "review_note"])
    final, summary = apply_decisions(candidates, reviewed, ctx.audit, sizes, queue_ids)
    ctx.stats["review"] = summary
    return final
