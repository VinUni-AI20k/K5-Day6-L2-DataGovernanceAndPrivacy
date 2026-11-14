"""Human Review & Demo — Nguyễn Tuấn Minh, 2A202603349.

TODO: render contact sheet, apply approve/reject/edit/escalate/skip semantics,
validate IDs against the queue and log before/after changes to ctx.audit.
Preserve raw scores; edit pred_action/labels instead of tuning scores on eval.
"""
from __future__ import annotations

import pandas as pd

from ..common.context import RunContext
from ..common.review import load_review_decisions


def apply_human_review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Pass through without human decisions; fail explicitly until overrides are implemented."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    ctx.stats["n_reviewed"] = 0
    if not reviewed_path.exists():
        return scored.copy()
    reviewed = load_review_decisions(reviewed_path)
    ctx.stats["n_reviewed"] = len(reviewed)
    if reviewed.empty:
        return scored.copy()
    raise NotImplementedError("T02 review: Nguyễn Tuấn Minh must apply reviewer decisions and write audit evidence")
