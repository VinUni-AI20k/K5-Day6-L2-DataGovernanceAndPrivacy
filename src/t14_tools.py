"""T14 helpers: class adapter, box normalisation, suspicion score, review application, validated export.

Pure functions (no I/O except `load_inputs` and the exporters) so that `src/pipeline.py`
(PoC) and `src/baseline_t14.py` (baseline) share exactly the same adapter and validator.
Nothing here reads `fixtures/*/gt/`.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .metrics.detection import iou_xywh   # reuse the lab's own IoU (same one eval_t14 uses)

PRED_COLUMNS = ["image_id", "class", "x", "y", "w", "h", "conf"]

# Model class name (model_card label_map) -> project taxonomy name. Override via params.class_alias.
DEFAULT_ALIAS = {"person": "pedestrian", "car": "car", "motorcycle": "motorbike", "stop sign": "sign"}


# --------------------------------------------------------------------------- load
def load_inputs(input_dir) -> dict:
    d = Path(input_dir)
    taxonomy = {int(k): str(v) for k, v in yaml.safe_load((d / "taxonomy.yaml").read_text(encoding="utf-8"))["classes"].items()}
    card = yaml.safe_load((d / "model_card_fixture.yaml").read_text(encoding="utf-8"))
    return {
        "taxonomy": taxonomy,
        "label_map": {int(k): str(v) for k, v in card["label_map"].items()},
        "model_card": card,
        "images": pd.read_csv(d / "images.csv"),
        "preds": pd.read_csv(d / "model_predictions_fixture.csv"),
    }


# --------------------------------------------------------------------------- class adapter
def build_class_map(label_map: dict[int, str], taxonomy: dict[int, str], alias: dict[str, str] | None = None) -> dict[int, str]:
    """Model class id -> taxonomy class NAME. Fails loudly: a wrong mapping still exports a valid file."""
    alias = DEFAULT_ALIAS | (alias or {})
    names = set(taxonomy.values())
    out: dict[int, str] = {}
    for cid, name in label_map.items():
        target = alias.get(name)
        if target is None:
            raise ValueError(f"model class {cid}={name!r} has no alias to the project taxonomy {sorted(names)}; set params.class_alias")
        if target not in names:
            raise ValueError(f"alias {name!r} -> {target!r} is not in the taxonomy {sorted(names)}")
        out[int(cid)] = target
    return out


def map_classes(preds: pd.DataFrame, class_map: dict[int, str]) -> pd.DataFrame:
    unknown = sorted(set(preds["class_id"].astype(int)) - set(class_map))
    if unknown:
        raise ValueError(f"prediction class_id {unknown} not in the model label_map {sorted(class_map)}")
    out = preds.copy()
    out["class"] = out["class_id"].astype(int).map(class_map)
    return out


def add_box_ids(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["box_id"] = out["image_id"].astype(str) + "#" + out.groupby("image_id").cumcount().astype(str)
    return out


# --------------------------------------------------------------------------- geometry
def normalise_boxes(df: pd.DataFrame, images: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Clip boxes to the image; flag `clipped`; drop boxes that end up with no area. Returns (df, n_dropped)."""
    m = df.merge(images[["image_id", "width", "height", "path"]], on="image_id", how="left")
    if m["width"].isna().any():
        raise ValueError("predictions reference an image_id that is not in images.csv")
    x0 = m["x"].clip(lower=0)
    y0 = m["y"].clip(lower=0)
    x1 = (m["x"] + m["w"]).clip(upper=m["width"])
    y1 = (m["y"] + m["h"]).clip(upper=m["height"])
    m["clipped"] = (x0 != m["x"]) | (y0 != m["y"]) | (x1 != m["x"] + m["w"]) | (y1 != m["y"] + m["h"])
    m["x"], m["y"], m["w"], m["h"] = x0, y0, x1 - x0, y1 - y0
    bad = (m["w"] <= 0) | (m["h"] <= 0)
    return m[~bad].reset_index(drop=True), int(bad.sum())


def flag_class_confusion(df: pd.DataFrame, iou_thr: float = 0.5) -> pd.Series:
    """True for boxes that overlap (IoU >= thr) another box of a DIFFERENT class in the same image."""
    flag = pd.Series(False, index=df.index)
    for _, g in df.groupby("image_id"):
        idx = list(g.index)
        for i in range(len(idx)):
            for j in range(i + 1, len(idx)):
                a, b = g.loc[idx[i]], g.loc[idx[j]]
                if a["class"] != b["class"] and iou_xywh((a.x, a.y, a.w, a.h), (b.x, b.y, b.w, b.h)) >= iou_thr:
                    flag[idx[i]] = flag[idx[j]] = True
    return flag


# --------------------------------------------------------------------------- suspicion score
def add_suspicion(df: pd.DataFrame, thr: float, params: dict | None = None) -> pd.DataFrame:
    """Review priority (higher = look first). Weights are params so they can be frozen before eval."""
    p = params or {}
    out = df.copy()
    conf = out["conf"].astype(float)
    mid = 1 - (conf - 0.5).abs() * 2
    near = 1 - (conf - thr).abs() / float(p.get("near_thr_band", 0.15))
    out["uncertainty"] = np.maximum(mid, near).clip(0, 1)
    out["small"] = (out["w"] * out["h"]) < float(p.get("small_area_px", 150))
    out["confusion"] = flag_class_confusion(out, float(p.get("confusion_iou", 0.5)))
    out["score"] = (
        float(p.get("w_uncertain", 0.5)) * out["uncertainty"]
        + float(p.get("w_small", 0.3)) * out["small"].astype(float)
        + float(p.get("w_clipped", 0.2)) * out["clipped"].astype(float)
        + float(p.get("w_confusion", 0.3)) * out["confusion"].astype(float)
    ).round(6)

    def _reason(r) -> str:
        flags = []
        if r["conf"] < thr:
            flags.append("below_threshold")
        elif 0.35 <= r["conf"] <= 0.65:
            flags.append("mid_conf")
        if r["small"]:
            flags.append("small")
        if r["clipped"]:
            flags.append("clipped")
        if r["confusion"]:
            flags.append("class_confusion")
        return ";".join(flags) or "low_priority"

    out["reason"] = out.apply(_reason, axis=1)
    return out


# --------------------------------------------------------------------------- human review
def parse_override(value: str, taxonomy_names: set[str]) -> dict:
    """`edit` override formats: 'pedestrian' | 'x,y,w,h' | 'pedestrian,x,y,w,h'."""
    parts = [s.strip() for s in str(value).split(",") if s.strip() != ""]
    if not parts:
        raise ValueError("edit needs an override_value (class name, 'x,y,w,h' or 'class,x,y,w,h')")
    res: dict = {}
    if parts[0] in taxonomy_names:
        res["class"] = parts.pop(0)
    if parts:
        try:
            nums = [float(s) for s in parts]
        except ValueError as e:
            raise ValueError(f"bad override_value {value!r}: {e}") from None
        if len(nums) != 4:
            raise ValueError(f"bad override_value {value!r}: box needs 4 numbers x,y,w,h")
        res["box"] = tuple(nums)
    if not res:
        raise ValueError(f"bad override_value {value!r}")
    return res


def _snap(row) -> dict:
    return {"class": row["class"], "x": round(float(row["x"]), 2), "y": round(float(row["y"]), 2),
            "w": round(float(row["w"]), 2), "h": round(float(row["h"]), 2), "kept": bool(row["kept"])}


def apply_review(boxes: pd.DataFrame, reviewed: pd.DataFrame, taxonomy: dict[int, str], audit=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """approve = keep (rescues a below-threshold box) · reject = delete · edit = new class/box · escalate/skip = no change."""
    names = set(taxonomy.values())
    out = boxes.copy().set_index("box_id", drop=False)
    out["decision"] = out.get("decision", "")
    out["reviewed_by"] = out.get("reviewed_by", "")
    diffs = []
    for r in reviewed.itertuples(index=False):
        bid = r.item_id
        if bid not in out.index:
            raise ValueError(f"reviewed item {bid!r} is not a known box_id")
        before = _snap(out.loc[bid])
        d = r.reviewer_decision
        if d == "approve":
            out.loc[bid, "kept"] = True
        elif d == "reject":
            out.loc[bid, "kept"] = False
        elif d == "edit":
            ov = parse_override(r.override_value, names)
            if "class" in ov:
                out.loc[bid, "class"] = ov["class"]
            if "box" in ov:
                x, y, w, h = ov["box"]
                W, H = float(out.loc[bid, "width"]), float(out.loc[bid, "height"])
                x0, y0, x1, y1 = max(0.0, x), max(0.0, y), min(W, x + w), min(H, y + h)
                if x1 <= x0 or y1 <= y0:
                    raise ValueError(f"edited box for {bid!r} has no area inside the image")
                out.loc[bid, ["x", "y", "w", "h"]] = [x0, y0, x1 - x0, y1 - y0]
            out.loc[bid, "kept"] = True
        out.loc[bid, "decision"] = d
        out.loc[bid, "reviewed_by"] = r.reviewer
        after = _snap(out.loc[bid])
        diffs.append({"box_id": bid, "decision": d, "reviewer": r.reviewer, "note": r.review_note,
                      **{f"before_{k}": v for k, v in before.items()}, **{f"after_{k}": v for k, v in after.items()}})
        if audit:
            audit.log(actor=r.reviewer, action=f"review:{d}", item_id=bid, before=before, after=after, reason=r.review_note)
    return out.reset_index(drop=True), pd.DataFrame(diffs)


ADDITION_COLUMNS = ["image_id", "class", "x", "y", "w", "h", "reviewer", "note"]


def add_missed(boxes: pd.DataFrame, additions: pd.DataFrame, taxonomy: dict[int, str], images: pd.DataFrame, audit=None) -> pd.DataFrame:
    """Boxes the model missed, added by a human (review_additions.csv). Reviewer is mandatory."""
    miss = [c for c in ADDITION_COLUMNS if c not in additions.columns]
    if miss:
        raise ValueError(f"review_additions.csv missing columns {miss}")
    names = set(taxonomy.values())
    size = images.set_index("image_id")[["width", "height", "path"]]
    rows = []
    for k, r in enumerate(additions.fillna("").to_dict("records")):
        if str(r["reviewer"]).strip() == "":
            raise ValueError(f"addition #{k} has no reviewer (owner is mandatory)")
        if r["class"] not in names:
            raise ValueError(f"addition #{k}: class {r['class']!r} not in taxonomy {sorted(names)}")
        if r["image_id"] not in size.index:
            raise ValueError(f"addition #{k}: unknown image_id {r['image_id']!r}")
        W, H = float(size.loc[r["image_id"], "width"]), float(size.loc[r["image_id"], "height"])
        x, y, w, h = (float(r[c]) for c in ("x", "y", "w", "h"))
        x0, y0, x1, y1 = max(0.0, x), max(0.0, y), min(W, x + w), min(H, y + h)
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"addition #{k} has no area inside the image")
        bid = f"NEW:{r['image_id']}#{k}"
        rows.append({"box_id": bid, "image_id": r["image_id"], "class": r["class"], "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
                     "conf": 1.0, "clipped": False, "width": W, "height": H, "path": size.loc[r["image_id"], "path"],
                     "kept": True, "source": "human", "decision": "add", "reviewed_by": r["reviewer"], "score": 0.0,
                     "reason": "missed_by_model"})
        if audit:
            audit.log(actor=r["reviewer"], action="review:add", item_id=bid, after={"class": r["class"], "box": [x0, y0, x1 - x0, y1 - y0]}, reason=str(r["note"]))
    return pd.concat([boxes, pd.DataFrame(rows)], ignore_index=True) if rows else boxes


# --------------------------------------------------------------------------- validate + export
def validate_predictions(pred: pd.DataFrame, taxonomy: dict[int, str], images: pd.DataFrame) -> pd.DataFrame:
    """Rows that would count as invalid labels (same rule as eval_t14). Empty = OK."""
    m = pred.drop(columns=["width", "height"], errors="ignore").merge(
        images[["image_id", "width", "height"]], on="image_id", how="left")
    reasons = pd.Series("", index=m.index)
    for cond, why in (
        (~m["class"].astype(str).isin(set(taxonomy.values())), "unknown_class"),
        ((m["w"] <= 0) | (m["h"] <= 0), "non_positive_size"),
        ((m["x"] < 0) | (m["y"] < 0), "negative_origin"),
        ((m["x"] + m["w"] > m["width"] + 0.5) | (m["y"] + m["h"] > m["height"] + 0.5), "out_of_bounds"),
        (m["width"].isna(), "unknown_image"),
    ):
        reasons = reasons.where(~cond, reasons + why + ";")
    return m[reasons != ""].assign(problem=reasons[reasons != ""])


def final_predictions(final: pd.DataFrame) -> pd.DataFrame:
    p = final[final["kept"].astype(bool)].copy()
    for c in ("x", "y", "w", "h"):
        p[c] = p[c].astype(float).round(2)
    p["conf"] = p["conf"].astype(float).round(3)
    extra = [c for c in ("box_id", "source", "decision", "reviewed_by") if c in p.columns]
    return p[PRED_COLUMNS + extra].reset_index(drop=True)


def export_yolo(pred: pd.DataFrame, taxonomy: dict[int, str], images: pd.DataFrame, out_dir) -> Path:
    name2id = {v: k for k, v in taxonomy.items()}
    root = Path(out_dir)
    (root / "labels").mkdir(parents=True, exist_ok=True)
    for im in images.to_dict("records"):
        lines = []
        for b in pred[pred["image_id"] == im["image_id"]].to_dict("records"):
            cx, cy = (b["x"] + b["w"] / 2) / im["width"], (b["y"] + b["h"] / 2) / im["height"]
            lines.append(f"{name2id[b['class']]} {cx:.6f} {cy:.6f} {b['w'] / im['width']:.6f} {b['h'] / im['height']:.6f}")
        (root / "labels" / f"{im['image_id']}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    (root / "data.yaml").write_text(yaml.safe_dump({"path": ".", "names": {int(k): v for k, v in taxonomy.items()}}, sort_keys=True), encoding="utf-8")
    return root


def export_coco(pred: pd.DataFrame, taxonomy: dict[int, str], images: pd.DataFrame, path) -> Path:
    name2id = {v: k for k, v in taxonomy.items()}
    img_ids = {im["image_id"]: i + 1 for i, im in enumerate(images.to_dict("records"))}
    doc = {
        "images": [{"id": img_ids[im["image_id"]], "file_name": Path(im["path"]).name, "width": int(im["width"]), "height": int(im["height"])} for im in images.to_dict("records")],
        "categories": [{"id": int(k) + 1, "name": v} for k, v in sorted(taxonomy.items())],
        "annotations": [
            {"id": i + 1, "image_id": img_ids[b["image_id"]], "category_id": name2id[b["class"]] + 1,
             "bbox": [b["x"], b["y"], b["w"], b["h"]], "area": round(b["w"] * b["h"], 2), "iscrowd": 0, "score": b["conf"]}
            for i, b in enumerate(pred.to_dict("records"))
        ],
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return p


def _readback_yolo(out_dir, taxonomy, images) -> pd.DataFrame:
    rows = []
    for im in images.to_dict("records"):
        f = Path(out_dir) / "labels" / f"{im['image_id']}.txt"
        for line in f.read_text(encoding="utf-8").splitlines():
            c, cx, cy, w, h = line.split()
            w, h = float(w) * im["width"], float(h) * im["height"]
            rows.append({"image_id": im["image_id"], "class": taxonomy[int(c)], "x": float(cx) * im["width"] - w / 2,
                         "y": float(cy) * im["height"] - h / 2, "w": w, "h": h})
    return pd.DataFrame(rows, columns=["image_id", "class", "x", "y", "w", "h"])


def _readback_coco(path, taxonomy, images) -> pd.DataFrame:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    iid = {i["id"]: Path(i["file_name"]).stem for i in doc["images"]}
    cat = {c["id"]: c["name"] for c in doc["categories"]}
    return pd.DataFrame([{"image_id": iid[a["image_id"]], "class": cat[a["category_id"]], "x": a["bbox"][0], "y": a["bbox"][1],
                          "w": a["bbox"][2], "h": a["bbox"][3]} for a in doc["annotations"]], columns=["image_id", "class", "x", "y", "w", "h"])


def _max_err(a: pd.DataFrame, b: pd.DataFrame) -> float | None:
    """Max abs coordinate difference in px, or None if the two sets differ in size/class."""
    keys = ["image_id", "class", "x", "y", "w", "h"]
    a, b = a[keys].sort_values(keys).reset_index(drop=True), b[keys].sort_values(keys).reset_index(drop=True)
    if len(a) != len(b) or not (a["image_id"].equals(b["image_id"]) and a["class"].equals(b["class"])):
        return None
    return float((a[["x", "y", "w", "h"]] - b[["x", "y", "w", "h"]]).abs().to_numpy().max()) if len(a) else 0.0


def roundtrip_check(pred: pd.DataFrame, taxonomy: dict[int, str], images: pd.DataFrame, out_dir, coco_path, tol_px: float = 0.05) -> dict:
    """Read the exported YOLO and COCO files back and compare with the CSV (QA of the exporter itself)."""
    ref = pred.copy()
    ey = _max_err(ref, _readback_yolo(out_dir, taxonomy, images))
    ec = _max_err(ref, _readback_coco(coco_path, taxonomy, images))
    return {"yolo_max_err_px": ey, "coco_max_err_px": ec, "tol_px": tol_px, "n_boxes": int(len(ref)),
            "yolo_ok": ey is not None and ey <= tol_px, "coco_ok": ec is not None and ec <= tol_px}
