"""Offline T07 detector used by the integrated PoC pipeline.

This detector is deterministic and does not read ground truth.
It reuses the fixture-oriented face and plate algorithms from the baseline.
"""
from __future__ import annotations

import cv2
import pandas as pd

from .t07_baseline import _detect_plates, _detect_synthetic_face_shapes
from .t07_contract import CANDIDATE_COLUMNS


def _size_slice(w: int, h: int) -> str:
    """Assign a public size slice without using ground truth."""
    area = int(w) * int(h)
    if area < 32 * 32:
        return "small"
    if area < 96 * 96:
        return "medium"
    return "large"


def detect_and_score(ctx, images: pd.DataFrame) -> pd.DataFrame:
    """Detect face/plate candidates and assign review-priority scores.

    A higher score means the candidate should be reviewed earlier.
    Low-confidence candidates therefore receive a higher review score.
    """
    rows: list[dict] = []

    for image_row in images.sort_values("image_id", kind="stable").itertuples(index=False):
        image_path = ctx.input_dir / str(image_row.path)
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Could not decode T07 image: {image_path}")

        actual_height, actual_width = image.shape[:2]
        expected_width = int(image_row.width)
        expected_height = int(image_row.height)

        if actual_width != expected_width or actual_height != expected_height:
            raise ValueError(
                f"Image dimensions disagree with images.csv for {image_row.image_id}: "
                f"actual={actual_width}x{actual_height}, "
                f"declared={expected_width}x{expected_height}"
            )

        # The fixture-oriented detector is deterministic across Windows/macOS.
        candidates = _detect_synthetic_face_shapes(
            image,
            actual_width,
            actual_height,
        )
        candidates.extend(
            _detect_plates(
                image,
                actual_width,
                actual_height,
            )
        )

        # Remove exact duplicate geometry deterministically.
        unique: dict[tuple[int, int, int, int], dict] = {}
        for candidate in sorted(
            candidates,
            key=lambda item: (
                -float(item["confidence"]),
                item["type"],
                item["y"],
                item["x"],
            ),
        ):
            geometry = tuple(
                int(candidate[column])
                for column in ("x", "y", "w", "h")
            )
            unique.setdefault(geometry, candidate)

        candidates = sorted(
            unique.values(),
            key=lambda item: (
                item["y"],
                item["x"],
                item["type"],
            ),
        )

        for index, candidate in enumerate(candidates):
            confidence = float(candidate["confidence"])
            width = int(candidate["w"])
            height = int(candidate["h"])
            region_type = str(candidate["type"])
            size_slice = _size_slice(width, height)

            rows.append(
                {
                    "region_id": f"poc:{image_row.image_id}:{index:03d}",
                    "image_id": str(image_row.image_id),
                    "type": region_type,
                    "x": int(candidate["x"]),
                    "y": int(candidate["y"]),
                    "w": width,
                    "h": height,
                    "confidence": round(confidence, 6),
                    "score": round(1.0 - confidence, 6),
                    "reason": (
                        f"{candidate['reason']}; "
                        f"low-confidence review priority"
                    ),
                    "slice": f"type={region_type}|size={size_slice}",
                    "path": str(image_row.path).replace("\\", "/"),
                }
            )

    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)