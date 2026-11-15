"""Stable integration contract for the T07 detector, review, and export modules.

This module contains schema and geometry validation only. It deliberately does
not detect PII and never reads the instructor-only ground truth.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

IMAGE_COLUMNS = ["image_id", "path", "width", "height", "split"]
CANDIDATE_COLUMNS = [
    "region_id",
    "image_id",
    "type",
    "x",
    "y",
    "w",
    "h",
    "confidence",
    "score",
    "reason",
    "slice",
    "path",
]
REDACTION_COLUMNS = ["image_id", "x", "y", "w", "h"]
REGION_TYPES = {"face", "plate"}
RESOLVED_REVIEW_DECISIONS = {"approve", "reject", "edit"}


def _require_columns(df: pd.DataFrame, required: list[str], label: str) -> None:
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{label} missing required columns {missing}")


def load_images(input_dir: str | Path) -> pd.DataFrame:
    """Load and validate the public T07 image inventory."""
    root = Path(input_dir).resolve()
    path = root / "images.csv"
    images = pd.read_csv(path, dtype={"image_id": str, "path": str, "split": str})
    _require_columns(images, IMAGE_COLUMNS, "T07 images.csv")
    if images["image_id"].duplicated().any():
        duplicate = images.loc[images["image_id"].duplicated(), "image_id"].iloc[0]
        raise ValueError(f"T07 images.csv has duplicate image_id {duplicate!r}")
    for column in ("width", "height"):
        images[column] = pd.to_numeric(images[column], errors="coerce")
    if images[["width", "height"]].isna().any().any() or (images[["width", "height"]] <= 0).any().any():
        raise ValueError("T07 images.csv has invalid width/height")
    bad_splits = sorted(set(images["split"].astype(str)) - {"dev", "eval"})
    if bad_splits:
        raise ValueError(f"T07 images.csv has unknown splits {bad_splits}")
    for row in images.itertuples(index=False):
        image_path = (root / row.path).resolve()
        if not image_path.is_relative_to(root):
            raise ValueError(f"T07 image path escapes input folder: {row.path}")
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
    return images


def _coerce_box_columns(df: pd.DataFrame, label: str) -> pd.DataFrame:
    out = df.copy()
    for column in ("x", "y", "w", "h"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    values = out[["x", "y", "w", "h"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{label} contains non-finite box coordinates")
    return out


def invalid_box_mask(regions: pd.DataFrame, images: pd.DataFrame) -> pd.Series:
    """Return rows with unknown images or non-positive/out-of-bounds boxes."""
    sizes = images[["image_id", "width", "height"]].copy()
    merged = regions.merge(sizes, on="image_id", how="left", validate="many_to_one")
    invalid = (
        merged["width"].isna()
        | merged["height"].isna()
        | (merged["x"] < 0)
        | (merged["y"] < 0)
        | (merged["w"] <= 0)
        | (merged["h"] <= 0)
        | (merged["x"] + merged["w"] > merged["width"])
        | (merged["y"] + merged["h"] > merged["height"])
    )
    return pd.Series(invalid.to_numpy(), index=regions.index)


def validate_candidates(candidates: pd.DataFrame, images: pd.DataFrame) -> pd.DataFrame:
    """Validate the DataFrame returned by ``src.t07_detector.detect_and_score``."""
    _require_columns(candidates, CANDIDATE_COLUMNS, "T07 candidates")
    out = _coerce_box_columns(candidates, "T07 candidates")
    out["region_id"] = out["region_id"].astype(str)
    out["image_id"] = out["image_id"].astype(str)
    out["type"] = out["type"].astype(str).str.strip().str.lower()
    if out["region_id"].duplicated().any() or (out["region_id"].str.strip() == "").any():
        raise ValueError("T07 candidates require unique, non-empty region_id values")
    bad_types = sorted(set(out["type"]) - REGION_TYPES)
    if bad_types:
        raise ValueError(f"T07 candidates contain unknown region types {bad_types}")
    for column in ("confidence", "score"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
        if not np.isfinite(out[column].to_numpy(dtype=float)).all():
            raise ValueError(f"T07 candidates contain invalid {column} values")
    if ((out["confidence"] < 0) | (out["confidence"] > 1)).any():
        raise ValueError("T07 candidate confidence must be in [0, 1]")
    invalid = invalid_box_mask(out, images)
    if invalid.any():
        bad_ids = out.loc[invalid, "region_id"].head(5).tolist()
        raise ValueError(f"T07 candidates contain {int(invalid.sum())} invalid boxes, e.g. {bad_ids}")
    return out


def validate_final_regions(regions: pd.DataFrame, images: pd.DataFrame) -> pd.DataFrame:
    """Validate final post-review regions before redaction/export."""
    _require_columns(regions, REDACTION_COLUMNS, "T07 final regions")
    out = _coerce_box_columns(regions, "T07 final regions")
    out["image_id"] = out["image_id"].astype(str)
    if "region_id" in out.columns:
        out["region_id"] = out["region_id"].astype(str)
        if out["region_id"].duplicated().any() or (out["region_id"].str.strip() == "").any():
            raise ValueError("T07 final regions require unique, non-empty region_id values")
    if "type" in out.columns:
        out["type"] = out["type"].astype(str).str.strip().str.lower()
        bad_types = sorted(set(out["type"]) - REGION_TYPES)
        if bad_types:
            raise ValueError(f"T07 final regions contain unknown region types {bad_types}")
    invalid = invalid_box_mask(out, images)
    if invalid.any():
        raise ValueError(f"T07 final regions contain {int(invalid.sum())} invalid boxes")
    return out
