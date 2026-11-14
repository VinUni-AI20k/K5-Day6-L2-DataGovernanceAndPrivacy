"""Decision policy — Hoàng Trọng Trà, 2A202603342.

TODO: define per-image KEEP/RECAPTURE/REVIEW and run GO/HOLD/REWORK criteria.
Freeze criteria before eval. Do not turn unreviewed items into automatic GO.
"""
from __future__ import annotations

import pandas as pd

from ..common.context import RunContext
from ..common.decision import Decision


def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Conservative scaffold; not evidence that a release has passed QA."""
    return Decision(
        status="HOLD",
        reason_code="POLICY_NOT_IMPLEMENTED",
        reason="Team 6 decision policy has not been implemented or approved",
        owner=ctx.config["owner"],
        scope=ctx.track,
    )
