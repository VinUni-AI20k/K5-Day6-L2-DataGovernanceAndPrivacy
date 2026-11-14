"""T07 detector module (owned by Member 2 — Core Algorithm).

Member 1 (Lead / Integrator) created this interface contract so Member 2 can
develop the offline CPU face + plate detector independently without merge
conflicts in ``src/pipeline.py``.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .common.context import RunContext

DETECTOR_INFO: dict[str, str] = {
    "name": "t07_detector_stub",
    "version": "0.1.0",
    "mode": "stub",
    "license": "internal-lab",
    "notes": "Interface stub — Member 2 replaces detect_image() with offline face/plate PoC detector.",
}


def detect_image(img_rgb: np.ndarray, image_row: dict[str, Any], ctx: RunContext) -> list[dict[str, Any]]:
    """Detect PII regions (synthetic faces and plates) in a single RGB image.

    Args:
        img_rgb: HxWx3 uint8 RGB numpy array.
        image_row: Metadata dict from ``images.csv`` (``image_id``, ``path``,
            ``width``, ``height``, ``split``, ...).
        ctx: Pipeline ``RunContext`` (use ``ctx.rng`` / ``ctx.param(...)``).

    Returns:
        List of candidate box dicts. Each dict must include:
            - ``x`` (float): top-left x in pixels
            - ``y`` (float): top-left y in pixels
            - ``w`` (float): width in pixels (> 0)
            - ``h`` (float): height in pixels (> 0)
            - ``type`` (str): ``"face"`` or ``"plate"``
            - ``conf`` (float): confidence in ``[0.0, 1.0]``
            - ``reason`` (str, optional): short diagnostic tag
    """
    _ = (img_rgb, image_row, ctx)
    # TODO (Member 2): implement offline CPU face + plate detector + padding,
    # and update DETECTOR_INFO["mode"] = "poc_offline".
    return []

