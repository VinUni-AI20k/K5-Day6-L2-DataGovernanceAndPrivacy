"""T07 offline CPU detector for synthetic faces and plates (PoC).

Classical computer vision only (OpenCV + NumPy): no model weights, no network,
deterministic. The detector is built for the *synthetic* fixture, whose drawing
rules are public in ``tools/synth/scene.py``:

* face  = skin-coloured ellipse (width = 0.8 x height) with a darker outline,
          two dark eyes and a mouth; optionally its lower half is hidden by an
          occluder rectangle;
* plate = near-white rectangle with a dark outline and dark text.

Hard negatives handled explicitly: pedestrian heads (skin ellipse that is wider
than tall and sits on a body rectangle), round red signs, motorbike wheels.

Interface (called by ``src/pipeline.py``)::

    detect_image(img_rgb, image_row, ctx) -> list[{x, y, w, h, type, conf, reason}]

All thresholds are frozen parameters (see ``DEFAULTS`` and
``reports/metric_contract.md``); they were tuned on the ``dev`` split only.
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

DETECTOR_INFO: dict[str, str] = {
    "name": "t07_classical_cv",
    "version": "1.0.0",
    "mode": "poc_offline",
    "license": "repo code; OpenCV (Apache-2.0)",
    "notes": "Colour/shape heuristics for synthetic faces + plates; CPU only; no weights.",
}

DEFAULTS: dict[str, float] = {
    "face_pad": 0.03,          # relative padding per side of a face box (fraction of w / h)
    "face_pad_px": 1.0,        # absolute padding per side (covers the 1 px outline of the ellipse)
    "plate_pad": 0.02,         # relative padding per side of a plate box
    "plate_pad_px": 1.0,       # absolute padding per side (covers the 1 px dark frame)
    "blur_grow": 0.12,         # extra growth of face boxes on blurred frames (soft edges)
    "min_conf": 0.30,          # boxes below this confidence are dropped
    "blur_laplacian_threshold": 60.0,
    "dark_mean_threshold": 55.0,
}


def _p(ctx: Any, key: str) -> float:
    if ctx is not None and hasattr(ctx, "param"):
        return float(ctx.param(key, DEFAULTS[key]))
    return float(DEFAULTS[key])


def _iou(a: tuple, b: tuple) -> float:
    ax0, ay0, ax1, ay1 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx0, by0, bx1, by1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    iw, ih = min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0)
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter)


def image_condition(img_rgb: np.ndarray, blur_thr: float = 60.0, dark_thr: float = 55.0) -> dict[str, Any]:
    """Global capture condition used to pick thresholds (sharp/blurred, day/dark)."""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    mean = float(gray.mean())
    return {"blur": lap < blur_thr, "dark": mean < dark_thr, "laplacian_var": lap, "mean_brightness": mean}


# --------------------------------------------------------------------------- faces
# Skin palette of the synthetic renderer (tools/synth/scene.py). Night scenes draw faces at 0.35x.
SKIN = np.array([(241, 194, 167), (224, 172, 105), (198, 134, 66), (141, 85, 36), (255, 219, 172)], dtype=np.float32)
NIGHT_SCALE = 0.35


def _palette_masks(img_rgb: np.ndarray, cond: dict[str, Any]) -> list[tuple[np.ndarray, bool]]:
    """One binary mask per skin tone (Chebyshev colour distance); tones never mix inside a face."""
    img = img_rgb.astype(np.float32)
    variants: list[tuple[np.ndarray, float]] = []
    tol = 34.0 if cond["blur"] else 24.0
    for tone in SKIN:
        variants.append((tone, tol))
        if cond["dark"]:
            variants.append((tone * NIGHT_SCALE, 13.0))
    masks = []
    for tone, t in variants:
        m = (np.abs(img - tone[None, None, :]).max(axis=2) <= t).astype(np.uint8)
        masks.append((m, bool(t < 20.0)))          # (mask, is_night_tone)
    return masks


def _eye_dip(gray: np.ndarray, filled: np.ndarray, x: int, y: int, w: int, h: int, fs: float) -> float:
    """Relative darkness of the darkest interior pixel in the eye band (0 = uniform blob)."""
    roi = filled[y:y + h, x:x + w]
    inner = cv2.erode(roi, np.ones((3, 3), np.uint8)) if min(w, h) >= 9 else roi
    if inner.sum() < 6:
        inner = roi
    g = gray[y:y + h, x:x + w].astype(np.float32)
    vals = g[inner > 0]
    if vals.size == 0:
        return 0.0
    med = float(np.median(vals))
    r0, r1 = int(fs * 0.28), min(h, int(np.ceil(fs * 0.52)) + 1)
    band = inner[r0:r1]
    if band.sum() == 0:
        return 0.0
    dark = float(g[r0:r1][band > 0].min())
    return max(0.0, (med - dark) / max(med, 1.0))


def _eye_dip_bbox(gray: np.ndarray, x: int, y: int, w: int, h: int, fs: float) -> float:
    """Eye test for a face whose lower half is hidden: the eyes sit on the cut edge of the blob,
    so look at the central columns of the lowest visible rows instead of the filled interior."""
    g = gray[y:y + h, x:x + w].astype(np.float32)
    if g.size == 0:
        return 0.0
    med = float(np.median(g))
    r0 = max(0, min(h - 1, int(fs * 0.28)))
    c0, c1 = int(w * 0.12), max(int(w * 0.12) + 1, int(np.ceil(w * 0.88)))
    band = g[r0:h, c0:c1]
    if band.size == 0:
        return 0.0
    return max(0.0, (med - float(band.min())) / max(med, 1.0))


def _body_below(img_rgb: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
    """True when a uniform, wider rectangle starts right under the blob (pedestrian body)."""
    H, W = img_rgb.shape[:2]
    ya, yb = y + h + 2, min(H, y + h + 2 + max(4, h // 2))
    xa, xb = max(0, x - max(2, w // 6)), min(W, x + w + max(2, w // 6))
    if yb - ya < 3 or xb - xa < 4:
        return False
    strip = img_rgb[ya:yb, xa:xb].reshape(-1, 3).astype(np.float32)
    return bool(strip.std(axis=0).max() < 14.0)


def detect_faces(img_rgb: np.ndarray, cond: dict[str, Any], blur_grow: float = 0.12) -> list[dict[str, Any]]:
    H, W = img_rgb.shape[:2]
    blurred = bool(cond["blur"])
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    out: list[dict[str, Any]] = []
    for mask, night_tone in _palette_masks(img_rgb, cond):
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if w < 5 or h < 4 or w > 72 or h > 84 or area < 14:
                continue
            comp = (labels[y:y + h, x:x + w] == i).astype(np.uint8)
            cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            filled_roi = np.zeros_like(comp)
            cv2.drawContours(filled_roi, cnts, -1, 1, thickness=-1)   # eyes / mouth become part of the blob
            filled = np.zeros((H, W), np.uint8)
            filled[y:y + h, x:x + w] = filled_roi
            fill = float(filled_roi.sum()) / float(w * h)
            aspect = w / float(h)
            if fill < 0.58:
                continue
            fs = w / 0.8                                  # full face height implied by the width
            dip = _eye_dip(gray, filled, x, y, w, h, fs)
            body = _body_below(img_rgb, x, y, w, h)
            has_eyes = dip >= 0.16
            full_shape = 0.64 <= aspect <= 0.97 and fill <= 0.93
            wide_shape = 0.97 < aspect <= 2.5               # occluded face top OR pedestrian head
            if blurred:
                # eyes are unreliable under blur: rely on shape and on the pedestrian-body test
                if not (0.6 <= aspect <= 1.02) or min(w, h) < 7:
                    continue
                if dip < 0.08 and body:
                    continue                               # blurred pedestrian head on its body
                conf, reason = (0.6, "face_blur") if dip >= 0.08 else (0.4, "face_blur_no_eyes")
                box = [x, y, w, max(h, int(round(fs)))]
                grow = blur_grow                           # blur shrinks the colour-matched core
                box = [box[0] - box[2] * grow, box[1] - box[3] * grow, box[2] * (1 + 2 * grow), box[3] * (1 + 2 * grow)]
            elif full_shape:
                if not has_eyes and (body or night_tone or min(w, h) >= 12 or min(w, h) < 7):
                    continue                               # eyeless skin ellipse: pedestrian head / dark patch
                conf = 0.55 + 0.4 * min(1.0, dip / 0.5) if has_eyes else 0.4
                reason = "face" if has_eyes else "face_no_eyes"
                box = [x, y, w, max(h, int(round(fs * 0.98)))]
            elif wide_shape:
                # a face cut by an occluder has a wide flat bottom edge; a pedestrian head is a full
                # ellipse (narrow bottom) with no eyes
                bottom_w = float(filled_roi[max(0, h - 2):h].sum(axis=1).max()) / float(w)
                if bottom_w < 0.72 or aspect < 1.3:
                    continue
                dip = max(dip, _eye_dip_bbox(gray, x, y, w, h, fs))
                if dip < 0.3:
                    continue
                conf = 0.45 + 0.3 * min(1.0, dip / 0.6)
                reason = "face_occluded"
                box = [x, y, w, int(round(fs))]            # extend down over the occluder
            else:
                continue
            if min(w, h) < 12:
                conf *= 0.9
                reason += "_small"
            if x <= 0 or y <= 0 or x + w >= W or y + h >= H:
                conf *= 0.9
            out.append({"x": float(box[0]), "y": float(box[1]), "w": float(box[2]), "h": float(box[3]), "type": "face",
                        "conf": round(float(np.clip(conf, 0.05, 0.99)), 3), "reason": reason})
    return out


# -------------------------------------------------------------------------- plates
def detect_plates(img_rgb: np.ndarray, cond: dict[str, Any]) -> list[dict[str, Any]]:
    H, W = img_rgb.shape[:2]
    blurred = bool(cond["blur"])
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    s, v = hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY).astype(int)
    if blurred:
        # blur mixes the white plate with its black text -> light grey: use a local-contrast test
        # -> a pale, colourless patch that is either brighter or clearly less saturated than the car
        white = ((s < 58) & (gray > 138)).astype(np.uint8)
        white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        kernel = np.ones((3, 5), np.uint8)
    else:
        white = ((v >= 185) & (s <= 45)).astype(np.uint8)
        kernel = np.ones((1, 7), np.uint8)   # bridge the gaps cut by the dark text
    closed = cv2.morphologyEx(white, cv2.MORPH_CLOSE, kernel)
    n, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    out: list[dict[str, Any]] = []
    for i in range(1, n):
        x, y, w, h, area = (int(t) for t in stats[i])
        if w < 9 or h < 4 or w > 110 or h > 34:
            continue
        aspect = w / float(h)
        if not (1.25 <= aspect <= 6.5):
            continue
        fill = area / float(w * h)
        if fill < 0.6:
            continue
        roi_gray = gray[y:y + h, x:x + w]
        roi_white = white[y:y + h, x:x + w]
        white_frac = float(roi_white.mean())
        dark_frac = float((roi_gray < 110).mean())
        if not blurred and (white_frac < 0.30 or dark_frac < 0.04):
            continue                       # lane marks / sign rims have no dark text inside
        if blurred:
            # ring test: the surroundings must be darker or more saturated than the patch
            ya, yb, xa, xb = max(0, y - 5), min(H, y + h + 5), max(0, x - 5), min(W, x + w + 5)
            ring = np.ones((yb - ya, xb - xa), bool)
            ring[y - ya:y - ya + h, x - xa:x - xa + w] = False
            ds = float(s[ya:yb, xa:xb][ring].mean()) - float(s[y:y + h, x:x + w].mean())
            dg = float(roi_gray.mean()) - float(gray[ya:yb, xa:xb][ring].mean())
            if ds < 22 and dg < 16:
                continue
            if w < 14 or h < 6 or aspect < 1.6:
                continue
        # the real plate has aspect ~3.8; a narrower blob is usually a plate partly hidden by
        # another object -> widen the box around the visible part so the hidden part is covered
        reason = "plate"
        bx, bw = x, w
        if aspect < 2.6 and 7 <= h <= 18 and white_frac >= 0.45 and not blurred:
            grow = min(int(round(3.8 * h)) - w, int(round(0.7 * w)))
            bx, bw = x - grow, w + 2 * grow
            reason = "plate_partial"
        conf = 0.35 + 0.35 * min(1.0, white_frac / 0.6) + 0.3 * min(1.0, dark_frac / 0.2)
        if blurred:
            conf = 0.5
            reason += "_blur"
        if reason.startswith("plate_partial"):
            conf *= 0.75
        if h < 8:
            conf *= 0.9
            reason += "_small"
        out.append({"x": bx, "y": y, "w": bw, "h": h, "type": "plate",
                    "conf": round(float(np.clip(conf, 0.05, 0.99)), 3), "reason": reason})
    return out


# --------------------------------------------------------------------------- public
def _pad(box: dict[str, Any], rel: float, abs_px: float, W: int, H: int) -> dict[str, Any]:
    dx, dy = box["w"] * rel + abs_px, box["h"] * rel + abs_px
    x0, y0 = max(0.0, box["x"] - dx), max(0.0, box["y"] - dy)
    x1, y1 = min(float(W), box["x"] + box["w"] + dx), min(float(H), box["y"] + box["h"] + dy)
    return {**box, "x": round(x0, 2), "y": round(y0, 2), "w": round(x1 - x0, 2), "h": round(y1 - y0, 2)}


def detect_image(img_rgb: np.ndarray, image_row: dict[str, Any] | None = None, ctx: Any = None) -> list[dict[str, Any]]:
    """Detect PII regions (synthetic faces and plates) in a single RGB image.

    Returns padded candidate boxes ``{x, y, w, h, type, conf, reason}`` sorted by confidence.
    """
    _ = image_row
    if img_rgb is None or img_rgb.ndim != 3 or img_rgb.shape[2] != 3:
        raise ValueError("detect_image expects an HxWx3 RGB uint8 array")
    img_rgb = np.ascontiguousarray(img_rgb.astype(np.uint8))
    H, W = img_rgb.shape[:2]
    cond = image_condition(img_rgb, _p(ctx, "blur_laplacian_threshold"), _p(ctx, "dark_mean_threshold"))
    min_conf = _p(ctx, "min_conf")
    faces = [_pad(b, _p(ctx, "face_pad"), _p(ctx, "face_pad_px"), W, H)
             for b in detect_faces(img_rgb, cond, _p(ctx, "blur_grow"))]
    plates = [_pad(b, _p(ctx, "plate_pad"), _p(ctx, "plate_pad_px"), W, H) for b in detect_plates(img_rgb, cond)]
    boxes = sorted([b for b in faces + plates if b["conf"] >= min_conf and b["w"] > 0 and b["h"] > 0],
                   key=lambda b: -b["conf"])
    keep: list[dict[str, Any]] = []
    for b in boxes:                       # NMS within the same type
        if all(k["type"] != b["type"] or _iou((b["x"], b["y"], b["w"], b["h"]), (k["x"], k["y"], k["w"], k["h"])) < 0.5
               for k in keep):
            keep.append(b)
    return keep
