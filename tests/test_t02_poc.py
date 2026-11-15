"""Group tests for the T02 PoC v1 (frozen algorithm) + decision policy.

Covers the rubric: >=2 team tests (success + edge/failure).
Run: pytest -q tests/test_t02_poc.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.pipeline import decide
from src.poc.t02_v1 import DARK_LO, blockiness, score_frame


def _row(image_id: str, lap: float, bright: float, blob: float, block: float) -> dict:
    grp = image_id.rsplit("_", 1)[0]
    return {"image_id": image_id, "grp": grp, "lap": lap, "bright": bright, "blob": blob, "block": block}


class _Ctx:
    def __init__(self):
        self.config = {"owner": "test-owner"}
        self.track = "t02"

    def out(self, name):
        return f"out/{name}"


# ------------------------------------------------------------------ success
def test_score_frame_flags_dark_image_and_severity2():
    """A dark image in a group of bright ones is flagged 'dark'; severity 2 below DARK_HI."""
    df = pd.DataFrame(
        [
            _row("g_0", lap=100.0, bright=200.0, blob=0.0, block=1.0),
            _row("g_1", lap=100.0, bright=210.0, blob=0.0, block=1.0),
            _row("g_2", lap=100.0, bright=200.0, blob=0.0, block=1.0),
            _row("g_3", lap=100.0, bright=0.10 * 200.0, blob=0.0, block=1.0),  # ratio 0.10 <= DARK_HI
        ]
    )
    out = score_frame(df).set_index("image_id")
    dark = out.loc["g_3"]
    clean = out.loc["g_0"]
    assert dark["pred_defect_type"] == "dark"
    assert dark["pred_severity"] == 2
    assert dark["pred_action"] == "RECAPTURE"
    assert dark["score"] > clean["score"]
    assert clean["pred_defect_type"] == "none" and clean["pred_severity"] == 0


def test_decision_policy_rework_hold_go():
    """Frozen step-05 policy: any sev2 -> REWORK; else any sev1 -> HOLD; else GO."""
    ctx = _Ctx()
    rework = decide(ctx, pd.DataFrame({"pred_severity": [0, 1, 2]}))
    hold = decide(ctx, pd.DataFrame({"pred_severity": [0, 1, 0]}))
    go = decide(ctx, pd.DataFrame({"pred_severity": [0, 0, 0]}))
    assert rework.status == "REWORK" and rework.reason_code == "SEV2_PREDICTED"
    assert hold.status == "HOLD" and hold.reason_code == "SEV1_REVIEW"
    assert go.status == "GO" and go.reason_code == "NO_DEFECT_FLAGGED"


# ------------------------------------------------------------------ edge
def test_single_image_group_does_not_crash_and_stays_clean():
    """Edge: a group with one image has no siblings -> normalisation falls back to itself."""
    df = pd.DataFrame([_row("solo_0", lap=50.0, bright=120.0, blob=0.0, block=1.0)])
    out = score_frame(df).iloc[0]
    assert out["pred_defect_type"] == "none"
    assert out["pred_severity"] == 0 and out["pred_action"] == "KEEP"
    assert out["score"] == 0.0


def test_blockiness_zero_on_uniform_image():
    """A uniform image has no block boundaries -> blockiness exactly 0."""
    g = np.full((64, 96), 128, dtype=np.float64)
    assert blockiness(g) == 0.0
