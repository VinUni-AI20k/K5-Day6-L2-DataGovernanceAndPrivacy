"""Trivial T07 baseline: blur the whole image (see ``src/t07_baseline.py``)."""
from __future__ import annotations

from .common.context import RunContext
from .t07_baseline import run_mode


def run(ctx: RunContext) -> None:
    run_mode(ctx, "blur_all")
