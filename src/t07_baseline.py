"""Offline baseline for T07 face/plate redaction.

The baseline deliberately uses only algorithms bundled with OpenCV: a Haar
cascade for faces and an edge/shape heuristic for plates.  It never reads the
instructor-only ground truth and never downloads model weights.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest


IMAGE_COLUMNS = ["image_id", "path", "width", "height", "split"]
REDACTION_COLUMNS = ["image_id", "x", "y", "w", "h"]

FACE_PADDING = 0.15
PLATE_PADDING = 0.10
NMS_IOU_THRESHOLD = 0.50


def _load_images(ctx: RunContext) -> pd.DataFrame:
    """Load public input metadata and enforce the baseline data contract."""
    manifest_path = ctx.input_dir / "manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    problems = verify_manifest(manifest_path)
    if problems:
        raise ValueError(f"T07 provenance check failed: {problems[:3]}")

    images_path = ctx.input_dir / "images.csv"
    images = pd.read_csv(images_path, dtype={"image_id": str, "path": str, "split": str})
    missing = [column for column in IMAGE_COLUMNS if column not in images.columns]
    if missing:
        raise ValueError(f"T07 images.csv missing required columns {missing}")
    if images["image_id"].duplicated().any():
        raise ValueError("T07 images.csv contains duplicate image_id values")

    images = images.copy()
    for column in ("width", "height"):
        images[column] = pd.to_numeric(images[column], errors="coerce")
    if images[["width", "height"]].isna().any().any() or (images[["width", "height"]] <= 0).any().any():
        raise ValueError("T07 images.csv contains invalid image dimensions")
    if not set(images["split"]).issubset({"dev", "eval"}):
        raise ValueError("T07 images.csv contains an unknown split")

    root = ctx.input_dir.resolve()
    for row in images.itertuples(index=False):
        image_path = (root / row.path).resolve()
        if not image_path.is_relative_to(root):
            raise ValueError(f"T07 image path escapes input directory: {row.path}")
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
    return images


def _clip_and_pad_box(
    x: int,
    y: int,
    w: int,
    h: int,
    image_width: int,
    image_height: int,
    padding: float,
) -> tuple[int, int, int, int]:
    """Apply fixed proportional padding and clamp the box to image bounds."""
    pad_x = int(round(w * padding))
    pad_y = int(round(h * padding))
    left = max(0, int(x) - pad_x)
    top = max(0, int(y) - pad_y)
    right = min(int(image_width), int(x + w) + pad_x)
    bottom = min(int(image_height), int(y + h) + pad_y)
    return left, top, right - left, bottom - top


def _iou(a: dict, b: dict) -> float:
    left = max(a["x"], b["x"])
    top = max(a["y"], b["y"])
    right = min(a["x"] + a["w"], b["x"] + b["w"])
    bottom = min(a["y"] + a["h"], b["y"] + b["h"])
    intersection = max(0, right - left) * max(0, bottom - top)
    union = a["w"] * a["h"] + b["w"] * b["h"] - intersection
    return float(intersection / union) if union > 0 else 0.0


def _nms(regions: list[dict], threshold: float = NMS_IOU_THRESHOLD) -> list[dict]:
    """Deterministic non-maximum suppression for candidates of one type."""
    ordered = sorted(
        regions,
        key=lambda box: (-float(box["confidence"]), box["y"], box["x"], box["w"], box["h"]),
    )
    kept: list[dict] = []
    for candidate in ordered:
        if all(_iou(candidate, selected) <= threshold for selected in kept):
            kept.append(candidate)
    return kept


def _detect_faces(
    image: np.ndarray,
    detector: cv2.CascadeClassifier | None,
    image_width: int,
    image_height: int,
) -> list[dict]:
    if detector is None:
        return _detect_synthetic_face_shapes(image, image_width, image_height)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    detections = detector.detectMultiScale(
        gray,
        scaleFactor=1.10,
        minNeighbors=4,
        minSize=(18, 18),
    )
    regions: list[dict] = []
    for x, y, w, h in detections:
        px, py, pw, ph = _clip_and_pad_box(
            int(x), int(y), int(w), int(h), image_width, image_height, FACE_PADDING
        )
        if pw > 0 and ph > 0:
            regions.append(
                {
                    "type": "face",
                    "x": px,
                    "y": py,
                    "w": pw,
                    "h": ph,
                    # Haar does not expose a calibrated probability in this API.
                    "confidence": 0.50,
                    "score": 0.50,
                    "reason": "opencv_haar_face",
                }
            )
    return _nms(regions)


def _detect_synthetic_face_shapes(
    image: np.ndarray,
    image_width: int,
    image_height: int,
) -> list[dict]:
    """Declared offline fallback when an OpenCV wheel omits Haar XML data.

    The public fixture uses deliberately synthetic warm-coloured circular face
    shapes.  This weak fallback is fixture-oriented and is not suitable for
    real people; that limitation is reported in the data protocol.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    # Two broad warm-colour bands cover normal and dark synthetic faces.
    mask_light = cv2.inRange(hsv, np.array([3, 35, 80]), np.array([28, 230, 255]))
    mask_dark = cv2.inRange(hsv, np.array([3, 45, 35]), np.array([28, 255, 150]))
    mask = cv2.bitwise_or(mask_light, mask_dark)
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions: list[dict] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = float(cv2.contourArea(contour))
        box_area = float(w * h)
        if w < 6 or h < 6 or box_area < 35 or box_area > 3000:
            continue
        aspect_ratio = w / max(h, 1)
        perimeter = float(cv2.arcLength(contour, True))
        circularity = 4.0 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0.0
        fill_ratio = area / max(box_area, 1.0)
        if not 0.60 <= aspect_ratio <= 1.45:
            continue
        if circularity < 0.45 or fill_ratio < 0.45:
            continue
        px, py, pw, ph = _clip_and_pad_box(
            x, y, w, h, image_width, image_height, FACE_PADDING
        )
        confidence = float(np.clip(0.55 * circularity + 0.45 * fill_ratio, 0, 1))
        regions.append(
            {
                "type": "face",
                "x": px,
                "y": py,
                "w": pw,
                "h": ph,
                "confidence": confidence,
                "score": confidence,
                "reason": "declared_synthetic_shape_fallback",
            }
        )
    return _nms(regions)


def _detect_plates(
    image: np.ndarray,
    image_width: int,
    image_height: int,
) -> list[dict]:
    """Find plate-like rectangles using edges, morphology, and shape filters."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 60, 180)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    closed = cv2.dilate(closed, np.ones((3, 3), dtype=np.uint8), iterations=1)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    image_area = float(image_width * image_height)
    regions: list[dict] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = float(w * h)
        if w < 25 or h < 8 or area < 250 or area > image_area * 0.12:
            continue
        aspect_ratio = w / max(h, 1)
        if not 2.0 <= aspect_ratio <= 6.5:
            continue
        rectangularity = float(cv2.contourArea(contour)) / max(area, 1.0)
        if rectangularity < 0.30:
            continue
        roi_edges = edges[y : y + h, x : x + w]
        edge_density = float(np.count_nonzero(roi_edges)) / max(area, 1.0)
        if not 0.04 <= edge_density <= 0.65:
            continue

        aspect_score = max(0.0, 1.0 - abs(aspect_ratio - 4.0) / 4.0)
        confidence = float(np.clip(0.45 * rectangularity + 0.35 * aspect_score + 0.20 * min(edge_density * 4, 1), 0, 1))
        px, py, pw, ph = _clip_and_pad_box(
            x, y, w, h, image_width, image_height, PLATE_PADDING
        )
        if pw > 0 and ph > 0:
            regions.append(
                {
                    "type": "plate",
                    "x": px,
                    "y": py,
                    "w": pw,
                    "h": ph,
                    "confidence": confidence,
                    "score": confidence,
                    "reason": "edge_shape_plate",
                }
            )
    return _nms(regions)


def _validate_redactions(regions: pd.DataFrame, images: pd.DataFrame) -> pd.DataFrame:
    """Validate the final public output without consulting ground truth."""
    missing = [column for column in REDACTION_COLUMNS if column not in regions.columns]
    if missing:
        raise ValueError(f"T07 redactions missing required columns {missing}")
    out = regions.copy()
    for column in ("x", "y", "w", "h"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if out[["x", "y", "w", "h"]].isna().any().any():
        raise ValueError("T07 redactions contain non-numeric coordinates")

    sizes = images[["image_id", "width", "height"]]
    checked = out.merge(sizes, on="image_id", how="left", validate="many_to_one")
    invalid = (
        checked["width"].isna()
        | checked["height"].isna()
        | (checked["x"] < 0)
        | (checked["y"] < 0)
        | (checked["w"] <= 0)
        | (checked["h"] <= 0)
        | (checked["x"] + checked["w"] > checked["width"])
        | (checked["y"] + checked["h"] > checked["height"])
    )
    if invalid.any():
        raise ValueError(f"T07 redactions contain {int(invalid.sum())} invalid boxes")
    return out


def _blur_regions(image: np.ndarray, regions: list[dict]) -> np.ndarray:
    output = image.copy()
    for region in regions:
        x, y, w, h = (int(region[key]) for key in ("x", "y", "w", "h"))
        roi = output[y : y + h, x : x + w]
        if roi.size == 0:
            continue
        # A strong pixelation is deterministic and avoids invalid Gaussian kernels
        # for very small candidate boxes.
        tiny_width = max(1, w // 12)
        tiny_height = max(1, h // 12)
        tiny = cv2.resize(roi, (tiny_width, tiny_height), interpolation=cv2.INTER_LINEAR)
        output[y : y + h, x : x + w] = cv2.resize(tiny, (w, h), interpolation=cv2.INTER_NEAREST)
    return output


def run(ctx: RunContext) -> None:
    """Run the no-review baseline and write detector plus blur-all outputs."""
    images = _load_images(ctx)
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    face_detector: cv2.CascadeClassifier | None = None
    face_backend = "synthetic_shape_fallback"
    if cascade_path.is_file():
        loaded_detector = cv2.CascadeClassifier(str(cascade_path))
        if loaded_detector.empty():
            raise ValueError(f"Could not load OpenCV Haar cascade: {cascade_path}")
        face_detector = loaded_detector
        face_backend = "opencv_haar"

    output_image_dir = ctx.output_dir / "redacted_images"
    output_image_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    for image_row in images.sort_values("image_id", kind="stable").itertuples(index=False):
        input_path = ctx.input_dir / image_row.path
        image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Could not decode T07 image: {input_path}")
        actual_height, actual_width = image.shape[:2]
        if actual_width != int(image_row.width) or actual_height != int(image_row.height):
            raise ValueError(
                f"Image dimensions disagree with images.csv for {image_row.image_id}: "
                f"actual={actual_width}x{actual_height}, declared={image_row.width}x{image_row.height}"
            )

        candidates = _detect_faces(image, face_detector, actual_width, actual_height)
        candidates.extend(_detect_plates(image, actual_width, actual_height))
        # Avoid exact duplicate geometry across detector types in the evaluator input.
        unique: dict[tuple[int, int, int, int], dict] = {}
        for candidate in sorted(candidates, key=lambda item: (-item["confidence"], item["type"])):
            key = tuple(int(candidate[column]) for column in ("x", "y", "w", "h"))
            unique.setdefault(key, candidate)
        candidates = sorted(unique.values(), key=lambda item: (item["y"], item["x"], item["type"]))

        for index, candidate in enumerate(candidates):
            rows.append(
                {
                    "image_id": str(image_row.image_id),
                    "x": int(candidate["x"]),
                    "y": int(candidate["y"]),
                    "w": int(candidate["w"]),
                    "h": int(candidate["h"]),
                    "region_id": f"baseline:{image_row.image_id}:{index:03d}",
                    "type": candidate["type"],
                    "confidence": round(float(candidate["confidence"]), 6),
                    "score": round(float(candidate["score"]), 6),
                    "reason": candidate["reason"],
                    "slice": f"type={candidate['type']}",
                    "path": str(image_row.path),
                    "split": str(image_row.split),
                }
            )

        redacted = _blur_regions(image, candidates)
        destination = output_image_dir / Path(image_row.path).name
        if not cv2.imwrite(str(destination), redacted):
            raise ValueError(f"Could not write redacted image: {destination}")

    output_columns = REDACTION_COLUMNS + [
        "region_id", "type", "confidence", "score", "reason", "slice", "path", "split"
    ]
    redactions = pd.DataFrame(rows, columns=output_columns)
    if len(redactions):
        redactions = redactions.sort_values(
            ["image_id", "y", "x", "w", "h"], kind="stable"
        ).reset_index(drop=True)
    redactions = _validate_redactions(redactions, images)
    redactions.to_csv(ctx.out("redactions.csv"), index=False)

    blur_all = images[["image_id", "width", "height"]].copy()
    blur_all["x"] = 0
    blur_all["y"] = 0
    blur_all["w"] = blur_all["width"].astype(int)
    blur_all["h"] = blur_all["height"].astype(int)
    blur_all[REDACTION_COLUMNS].to_csv(ctx.out("redactions_blur_all.csv"), index=False)

    n_faces = int((redactions["type"] == "face").sum()) if len(redactions) else 0
    n_plates = int((redactions["type"] == "plate").sum()) if len(redactions) else 0
    ctx.stats.update(
        {
            "n_items": int(len(images)),
            "n_redactions": int(len(redactions)),
            "n_faces": n_faces,
            "n_plates": n_plates,
            "n_blur_all_regions": int(len(blur_all)),
            "face_backend": face_backend,
        }
    )
    if ctx.audit is not None:
        ctx.audit.log(
            actor="t07_baseline",
            action="baseline_export",
            item_id=ctx.run_name,
            after={"images": len(images), "redactions": len(redactions)},
            reason="Offline detector baseline completed without human review",
        )

    write_decision(
        Decision(
            status="HOLD",
            reason_code="BASELINE_ONLY",
            reason="Offline detector baseline has no human review and is not release-ready.",
            owner=str(ctx.config.get("owner") or "T07 baseline owner"),
            scope="t07-baseline",
            evidence=[str(ctx.out("redactions.csv")), str(ctx.out("redactions_blur_all.csv"))],
        ),
        ctx.out("decision.json"),
        ctx.out("decision_log.csv"),
    )
