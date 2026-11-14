"""T02's required global-Laplacian baseline (threshold calibrated on dev)."""
from __future__ import annotations

from .common.context import RunContext
from .pipeline import _run


def run(ctx: RunContext) -> None:
    _run(ctx, baseline=True)
