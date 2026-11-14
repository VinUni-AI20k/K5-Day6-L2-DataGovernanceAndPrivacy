"""Image features — Nguyễn Nhật Hạ, 2A202603325.

TODO: blur, brightness, local glare and compression features using local images.
Keep image_id and metadata so scoring and slice analysis can join by ID.
Building blocks already exist in src.common.image_ops; do not use gt/.
"""
from __future__ import annotations

import pandas as pd

from ..common.context import RunContext


def extract_features(ctx: RunContext, images: pd.DataFrame) -> pd.DataFrame:
    """Return one feature row per image_id; resolve image paths via ctx.input_dir."""
    raise NotImplementedError("T02 features: Nguyễn Nhật Hạ must implement extract_features(ctx, images)")
