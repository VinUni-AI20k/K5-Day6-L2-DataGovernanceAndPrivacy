"""Laplacian baseline — Phạm Văn Dương, 2A202603332.

TODO: implement score_baseline using a single whole-image Laplacian threshold.
Higher sharpness means lower suspicion: document how the score is oriented.
Freeze threshold on dev. Match the PoC's pool, seed and review budget.
This scaffold is NOT a random or completed baseline.
"""
from __future__ import annotations

import pandas as pd

from ..common.context import RunContext


def score_baseline(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Return the same scored-table columns as team06.scoring.score_images."""
    raise NotImplementedError("T02 Laplacian baseline: Phạm Văn Dương must implement score_baseline(ctx, data)")


def run(ctx: RunContext) -> None:
    """Entry point for src.main --pipeline src.team06.baseline (exit 3 until implemented)."""
    if ctx.track != "t02":
        raise ValueError("Team 6 baseline supports T02 only")
    from ..pipeline import run_pipeline

    run_pipeline(ctx, scorer=score_baseline)
