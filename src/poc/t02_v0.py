"""T02 PoC v0 — group-relative physics features + provisional thresholds.

Features (4 dimensions, one per defect):
    bright_ratio  = bright / 2nd-highest bright in group   -> dark
    lap_ratio     = lap / max lap in group                 -> blur
    block_ratio   = block / 2nd-lowest block in group      -> compression
    blob          = largest saturated blob / image area    -> glare (absolute)

Score = max of per-defect normalised margins (continuous, >1 beyond severity 2).
This is a v0 for queue comparison only: thresholds are provisional (14 dev
labels), not frozen, and must be re-calibrated when all 56 dev labels exist.

    python -m src.main --track t02 --input fixtures/t02_raw_qc \
        --output out/poc_v0 --run-name poc_v0 \
        --pipeline src.poc.t02_v0 --offline
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import ndimage

from ..common.context import RunContext
from ..common.image_ops import brightness_stats, laplacian_variance, load_rgb, to_gray

# Provisional thresholds: lo = first defect region, hi = severity 2.
DARK_LO, DARK_HI = 0.50, 0.05
BLUR_LO, BLUR_HI = 0.05, 0.003
GLARE_LO, GLARE_HI = 0.0005, 0.005
COMP_LO, COMP_HI = 1.50, 2.20


def blockiness(g: np.ndarray) -> float:
    """8x8 block-boundary gradient vs interior, averaged over H/V."""
    g = g[: (g.shape[0] // 8) * 8, : (g.shape[1] // 8) * 8]
    d_h = np.abs(np.diff(g, axis=1))
    d_v = np.abs(np.diff(g, axis=0))
    bh, ih = d_h[:, 7::8].mean(), np.delete(d_h, np.s_[7::8], axis=1).mean()
    bv, iv = d_v[7::8, :].mean(), np.delete(d_v, np.s_[7::8], axis=0).mean()
    return float((bh / max(ih, 1e-6) + bv / max(iv, 1e-6)) / 2)


def extract(images: pd.DataFrame, input_dir) -> pd.DataFrame:
    rows = []
    for r in images.itertuples():
        img = load_rgb(input_dir / r.path)
        g = to_gray(img)
        sat = g > 250
        lab, n = ndimage.label(sat)
        blob = 0.0 if n == 0 else int(np.bincount(lab.ravel())[1:].max()) / g.size
        rows.append(
            {
                "image_id": r.image_id,
                "grp": r.image_id.rsplit("_", 1)[0],
                "lap": laplacian_variance(img),
                "bright": brightness_stats(img)["mean"],
                "blob": float(blob),
                "block": blockiness(g),
            }
        )
    return pd.DataFrame(rows)


def second_highest(s: pd.Series) -> float:
    return float(s.nlargest(2).iloc[-1]) if len(s) >= 2 else float(s.max())


def second_lowest(s: pd.Series) -> float:
    return float(s.nsmallest(2).iloc[-1]) if len(s) >= 2 else float(s.min())


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("grp")
    df = df.copy()
    df["lap_ratio"] = df["lap"] / g["lap"].transform("max").clip(lower=1e-6)
    df["bright_ratio"] = df["bright"] / g["bright"].transform(second_highest).clip(lower=1e-6)
    df["block_ratio"] = df["block"] / g["block"].transform(second_lowest).clip(lower=1e-6)

    # continuous margins (>0 = defect region, 1 = severity-2 boundary)
    s_dark = (DARK_LO - df["bright_ratio"]) / (DARK_LO - DARK_HI)
    s_blur = (BLUR_LO - df["lap_ratio"]) / (BLUR_LO - BLUR_HI)
    s_comp = (df["block_ratio"] - COMP_LO) / (COMP_HI - COMP_LO)
    s_glare = np.log10(df["blob"].clip(lower=1e-9) / GLARE_LO) / np.log10(GLARE_HI / GLARE_LO)
    scores = pd.DataFrame(
        {"dark": s_dark.clip(lower=0), "blur": s_blur.clip(lower=0),
         "compression": s_comp.clip(lower=0), "glare": s_glare.clip(lower=0)}
    )
    df["score"] = scores.max(axis=1)
    df["pred_defect_type"] = scores.idxmax(axis=1).where(df["score"] > 0, "none")

    def severity(row) -> int:
        d = row["pred_defect_type"]
        if d == "dark":
            return 2 if row["bright_ratio"] <= DARK_HI else 1
        if d == "blur":
            return 2 if row["lap_ratio"] <= BLUR_HI else 1
        if d == "compression":
            return 2 if row["block_ratio"] >= COMP_HI else 1
        if d == "glare":
            return 2 if row["blob"] >= GLARE_HI else 1
        return 0

    df["pred_severity"] = df.apply(severity, axis=1)
    df["pred_action"] = np.where(df["pred_severity"] == 2, "RECAPTURE", "KEEP")
    return df.sort_values("score", ascending=False, kind="mergesort")


def run(ctx: RunContext) -> None:
    images = pd.read_csv(ctx.input_dir / "images.csv")
    scored = score_frame(extract(images, ctx.input_dir))
    pred_path = ctx.out("ranked_review.csv")
    scored[
        ["image_id", "score", "pred_defect_type", "pred_severity", "pred_action"]
    ].to_csv(pred_path, index=False)
    ctx.stats["n_items"] = int(len(scored))
    ctx.stats["n_flagged"] = int((scored["pred_defect_type"] != "none").sum())
    print(
        f"[t02_v0] {pred_path} | {len(scored)} images | "
        f"flagged={ctx.stats['n_flagged']} | "
        f"types={scored.loc[scored.pred_defect_type != 'none', 'pred_defect_type'].value_counts().to_dict()}"
    )
