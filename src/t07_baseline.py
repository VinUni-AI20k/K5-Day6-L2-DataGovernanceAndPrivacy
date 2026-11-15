"""T07 baselines (no review queue, no human audit) — run through the same `src.main` runner.

    python -m src.main --track t07 --pipeline src.t07_baseline         --output out/baseline --run-name baseline --offline --seed 42
    python -m src.main --track t07 --pipeline src.t07_baseline_blurall --output out/baseline_blurall --run-name baseline_blurall --offline --seed 42
    python -m src.main --track t07 --pipeline src.t07_baseline_haar    --output out/baseline_haar --run-name baseline_haar --offline --seed 42

* ``naive_color`` — the group's "default detector + fixed blur" baseline: one generic skin-colour
                    threshold and one white threshold, connected components, no shape test, no eye
                    test, no padding, no handling of dark/blurred frames, no confidence, no queue.
                    Uses only core OpenCV calls, so it runs with every OpenCV allowed by requirements.txt.
* ``blur_all``    — trivial baseline: one box covering the whole image. Miss rate is 0 by
                    construction, but it must FAIL the over-redaction guardrail.
* ``haar``        — optional reference: OpenCV's stock Haar frontal-face cascade (vendored in
                    models_optional/). `cv2.CascadeClassifier` only exists in OpenCV 4.x or in
                    opencv-contrib 5.x; with plain OpenCV 5.x this mode stops with a clear message.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import load_rgb
from .common.manifest import verify_manifest
from .metrics.tracks import get_track

BOX_COLUMNS = ["image_id", "x", "y", "w", "h"]


def _load_images(ctx: RunContext) -> pd.DataFrame:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems and ctx.config.get("strict_provenance", True):
        raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    return pd.read_csv(ctx.input_dir / "images.csv")


CASCADE_NAME = "haarcascade_frontalface_default.xml"


def load_haar_cascade() -> "cv2.CascadeClassifier":
    """Stock OpenCV frontal-face cascade: vendored copy first (same file on every machine),
    then the copy shipped inside OpenCV 4.x wheels. No download."""
    if not hasattr(cv2, "CascadeClassifier"):
        raise FileNotFoundError(
            f"cv2.CascadeClassifier is not available in OpenCV {cv2.__version__} "
            "(needs OpenCV 4.x or opencv-contrib 5.x); the Haar reference baseline is optional")
    candidates = [Path(__file__).resolve().parent.parent / "models_optional" / CASCADE_NAME]
    data_dir = getattr(getattr(cv2, "data", None), "haarcascades", None)
    if data_dir:
        candidates.append(Path(data_dir) / CASCADE_NAME)
    for path in candidates:
        if path.exists():
            cascade = cv2.CascadeClassifier(str(path))
            if not cascade.empty():
                return cascade
    raise FileNotFoundError(f"OpenCV Haar cascade not found in: {[str(c) for c in candidates]}")


def haar_boxes(img_rgb: np.ndarray, cascade: "cv2.CascadeClassifier") -> list[dict[str, Any]]:
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    found = cascade.detectMultiScale(gray)          # library defaults: scaleFactor=1.1, minNeighbors=3
    return [{"x": int(x), "y": int(y), "w": int(w), "h": int(h), "type": "face"} for (x, y, w, h) in found]


def naive_color_boxes(img_rgb: np.ndarray) -> list[dict[str, Any]]:
    """Untuned colour thresholds: any skin-like blob is a face, any white wide blob is a plate."""
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    out: list[dict[str, Any]] = []
    skin = ((h <= 25) & (s >= 40) & (s <= 200) & (v >= 60)).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(skin, connectivity=8)
    for i in range(1, n):
        x, y, w, hh, area = (int(t) for t in stats[i])
        if area >= 30 and w <= 120 and hh <= 120:
            out.append({"x": x, "y": y, "w": w, "h": hh, "type": "face"})
    white = ((v >= 200) & (s <= 40)).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    for i in range(1, n):
        x, y, w, hh, area = (int(t) for t in stats[i])
        if area >= 20 and w > hh and w <= 120:
            out.append({"x": x, "y": y, "w": w, "h": hh, "type": "plate"})
    return out


def blur_all_boxes(img_rgb: np.ndarray) -> list[dict[str, Any]]:
    H, W = img_rgb.shape[:2]
    return [{"x": 0, "y": 0, "w": int(W), "h": int(H), "type": "all"}]


def run_mode(ctx: RunContext, mode: str) -> None:
    spec = get_track(ctx.track)
    if spec.track != "t07":
        raise NotImplementedError("src.t07_baseline only implements track t07")
    images = _load_images(ctx)
    cascade = None
    if mode == "haar":
        cascade = load_haar_cascade()
    rows: list[dict[str, Any]] = []
    for r in images.itertuples(index=False):
        img = load_rgb(ctx.input_dir / str(r.path))
        if mode == "haar":
            boxes = haar_boxes(img, cascade)
        elif mode == "blur_all":
            boxes = blur_all_boxes(img)
        else:
            boxes = naive_color_boxes(img)
        for b in boxes:
            rows.append({"image_id": str(r.image_id), **b})
    out = pd.DataFrame(rows, columns=BOX_COLUMNS + ["type"])
    out.to_csv(ctx.out(spec.pred_file), index=False)
    ctx.stats.update({"n_items": int(len(images)), "n_images": int(len(images)), "n_final_boxes": int(len(out)),
                      "baseline_mode": mode, "n_reviewed": 0})
    owner = str(ctx.config.get("owner", "")).strip() or "TODO-owner"
    dec = Decision(status="HOLD", reason_code="BASELINE_NO_HUMAN_REVIEW",
                   reason=f"Baseline '{mode}' has no review queue and no human audit; never released.",
                   owner=owner, scope=ctx.track, evidence=[str(ctx.out(spec.pred_file))],
                   metrics={"n_images": int(len(images)), "n_final_boxes": int(len(out)), "baseline_mode": mode})
    ctx.audit.log(actor=owner, action=f"decision:{dec.canonical}", item_id=ctx.track,
                  after={"status": dec.status, "reason_code": dec.reason_code}, reason=dec.reason)
    write_decision(dec, ctx.out("decision.json"), ctx.out("decision_log.csv"))


def run(ctx: RunContext) -> None:
    run_mode(ctx, "naive_color")
