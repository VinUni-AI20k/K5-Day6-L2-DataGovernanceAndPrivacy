"""T07 re-export: final regions -> redactions.csv + redacted images (input images are never overwritten).

Output is *redacted / pseudonymised*, not anonymised: location, time and context can still identify people.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from .common.io import sha256_file

REQUIRED = ["image_id", "x", "y", "w", "h"]


def image_sizes(images: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """images.csv -> {image_id: (W, H)}."""
    return {str(r.image_id): (int(r.width), int(r.height)) for r in images.itertuples()}


def validate_boxes(regions: pd.DataFrame, sizes: dict[str, tuple[int, int]]) -> list[dict]:
    """Return a list of problems (empty = all boxes valid and inside their image)."""
    problems = []
    missing = [c for c in REQUIRED if c not in regions.columns]
    if missing:
        return [{"problem": "missing_columns", "columns": missing}]
    for r in regions.itertuples(index=False):
        iid = str(r.image_id)
        if iid not in sizes:
            problems.append({"problem": "unknown_image", "image_id": iid})
            continue
        W, H = sizes[iid]
        if not (r.w > 0 and r.h > 0 and r.x >= 0 and r.y >= 0 and r.x + r.w <= W and r.y + r.h <= H):
            problems.append({"problem": "invalid_box", "image_id": iid, "box": [r.x, r.y, r.w, r.h],
                             "region_id": getattr(r, "region_id", "")})
    return problems


def write_redactions(regions: pd.DataFrame, out_csv: Path) -> Path:
    """redactions.csv: required columns first, then helpful extras; deterministic order."""
    extras = [c for c in ("region_id", "type", "confidence", "source") if c in regions.columns]
    df = regions[REQUIRED + extras].copy()
    for c in ("x", "y", "w", "h"):
        df[c] = df[c].astype(int)
    df = df.sort_values(["image_id", "y", "x", "w", "h"], kind="mergesort")
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return out_csv


def _mask(img: np.ndarray, x: int, y: int, w: int, h: int, mode: str) -> bool:
    """Mask one box in place. The box is clamped to the image first; returns False if nothing is left."""
    H, W = img.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, int(x) + int(w)), min(H, int(y) + int(h))
    if x1 <= x0 or y1 <= y0:
        return False
    x, y, w, h = x0, y0, x1 - x0, y1 - y0
    roi = img[y:y + h, x:x + w]
    if mode == "solid":
        roi[:] = 0
        return True
    # pixelate (mosaic) then blur: hard to invert, still keeps rough scene colours for the task
    small = cv2.resize(roi, (max(1, w // 8), max(1, h // 8)), interpolation=cv2.INTER_AREA)
    mosaic = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    roi[:] = cv2.GaussianBlur(mosaic, (0, 0), 2)
    return True


def export_images(regions: pd.DataFrame, images: pd.DataFrame, input_dir: Path, out_dir: Path,
                  mode: str = "pixelate") -> pd.DataFrame:
    """Write one redacted copy per input image into out_dir; return an export manifest DataFrame."""
    input_dir, out_dir = Path(input_dir).resolve(), Path(out_dir).resolve()
    if out_dir == input_dir or input_dir in out_dir.parents:
        raise ValueError(f"refusing to write redacted images inside the input folder: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    by_img = {k: g for k, g in regions.groupby(regions["image_id"].astype(str))}
    rows = []
    for r in images.itertuples(index=False):
        iid = str(r.image_id)
        src = input_dir / Path(str(r.path))           # Path() handles '/' on Windows and macOS
        img = cv2.imread(str(src))
        if img is None:
            raise FileNotFoundError(f"cannot read input image {src}")
        boxes = by_img.get(iid)
        n = 0
        if boxes is not None:
            for b in boxes.itertuples(index=False):
                n += int(_mask(img, int(b.x), int(b.y), int(b.w), int(b.h), mode))
        dst = out_dir / f"{iid}.jpg"
        if dst.resolve() == src.resolve():
            raise ValueError(f"refusing to overwrite input image {src}")
        cv2.imwrite(str(dst), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rows.append({"image_id": iid, "split": getattr(r, "split", ""), "n_regions": n,
                     "redacted_path": dst.name, "sha256": sha256_file(dst)})
    manifest = pd.DataFrame(rows)
    manifest.to_csv(out_dir / "export_manifest.csv", index=False)
    return manifest


# ------------------------------------------------------------------ integration contract (docs/T07_INTEGRATION_CONTRACT.md)
def export_redacted_images(ctx, regions: pd.DataFrame, images: pd.DataFrame) -> None:
    """Contract API: write redacted copies to <output>/redacted_images/ (never touches fixture images).

    Mask style comes from params.redaction_mode (pixelate | solid, default pixelate). Export stats are kept in
    ctx.stats["export"]; out-of-image boxes are clamped, fully-outside boxes are skipped and counted.
    """
    mode = str(ctx.param("redaction_mode", "pixelate"))
    manifest = export_images(regions, images, ctx.input_dir, ctx.out("redacted_images"), mode=mode)
    ctx.stats["export"] = {"n_images": int(len(manifest)), "n_regions_masked": int(manifest["n_regions"].sum()),
                           "n_regions_skipped": int(len(regions) - manifest["n_regions"].sum()), "mode": mode}
