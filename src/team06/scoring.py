"""PoC scoring — Nguyễn Nhật Hạ, 2A202603325.

TODO: call features.extract_features and combine features with dev-frozen params.
Return image_id, path, camera_id, light, split, score, reason,
pred_defect_type and pred_action. score must be finite; higher = review first.
One row per input image. Suggested actions: KEEP / RECAPTURE / REVIEW.
"""
from __future__ import annotations

import pandas as pd

from ..common.context import RunContext


def score_images(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Score data['images']; tune only on dev and preserve all original IDs/splits."""
    raise NotImplementedError("T02 PoC: Nguyễn Nhật Hạ must implement score_images(ctx, data)")
