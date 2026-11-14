"""Data & Provenance — Nguyễn Quốc Hưng, 2A202603324.

Starter loader: verify the original manifest and read T02 image metadata.
TODO: add camera/light summaries, failure cases and an internal-label protocol.
Never read instructor ground truth or rewrite fixture manifests to hide errors.
"""
from __future__ import annotations

import pandas as pd

from ..common.context import RunContext
from ..common.manifest import verify_manifest

IMAGE_COLUMNS = ["image_id", "path", "camera_id", "light", "split"]


def load_inputs(ctx: RunContext) -> dict:
    """Return {manifest: DataFrame | None, images: DataFrame} for T02.

    Image paths remain relative to ctx.input_dir; both dev and eval are retained.
    Threshold fitting must use dev only, not the complete returned table.
    """
    if ctx.track != "t02":
        raise ValueError("Team 6 load_inputs supports T02 only")
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        if ctx.audit is not None:
            ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")

    images = pd.read_csv(ctx.input_dir / "images.csv", dtype={"image_id": str})
    missing = [c for c in IMAGE_COLUMNS if c not in images.columns]
    if missing:
        raise ValueError(f"images.csv missing required columns: {missing}")
    if images[IMAGE_COLUMNS].isna().any().any():
        raise ValueError("images.csv contains missing required metadata")
    if images.image_id.duplicated().any():
        raise ValueError("images.csv contains duplicate image_id values")
    if not images.split.isin(["dev", "eval"]).all():
        raise ValueError("T02 split must be dev or eval")
    return {"manifest": pd.read_csv(manifest) if manifest.exists() else None, "images": images}
