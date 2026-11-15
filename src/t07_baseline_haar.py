"""Optional T07 reference baseline: stock OpenCV Haar face cascade (see ``src/t07_baseline.py``)."""
from __future__ import annotations

from .common.context import RunContext
from .t07_baseline import run_mode


def run(ctx: RunContext) -> None:
    run_mode(ctx, "haar")
