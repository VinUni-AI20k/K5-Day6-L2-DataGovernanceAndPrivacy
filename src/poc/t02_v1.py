"""T02 PoC v1 — calibrated on all 56 dev labels, thresholds FROZEN.

Calibration protocol
--------------------
* Labels: reports/dev_labels.csv, 56/56 dev images
  - 22 clean, 34 defective
  - 15 defective rows have a defect_type (14 typed clean + 15 typed defects)
  - 19 defective rows are severity-only (`defect_type` blank); they are used
    for the binary thresholds but not for type/severity calibration.
* `lo` for each feature = midpoint between the most extreme clean value and the
  closest typed positive, rounded *toward the defect side* (up for
  lower-is-worse features, down for higher-is-worse features).  A typed positive
  that falls on the clean side of that midpoint (img_08_2 for blur) is reported
  as not separable by this feature and excluded from the midpoint.
* `hi` = severity-2 boundary, calibrated on typed rows only, rounded *toward
  the clean side* (down for lower-is-worse, up for higher-is-worse):
  - gap between severity 1 and 2 -> geometric midpoint (blur)
  - overlap -> min typed severity-2 value (compression)
  - no typed severity 2 -> min(sev1)/1.2 (dark) or max(sev1)*1.2 (glare)
* No eval image or eval label is read here.  Re-run:
      python tools/_t02_calibrate.py
      python -m src.main --track t02 --input fixtures/t02_raw_qc \
          --output out/poc_v1 --run-name poc_v1 \
          --pipeline src.poc.t02_v1 --offline
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import ndimage

from ..common.context import RunContext
from ..common.image_ops import brightness_stats, laplacian_variance, load_rgb, to_gray

# Frozen on 56 dev labels (see reports/t02_calibration.json).
DARK_LO, DARK_HI = 0.596, 0.124
BLUR_LO, BLUR_HI = 0.205, 0.032
GLARE_LO, GLARE_HI = 0.0022, 0.006
COMP_LO, COMP_HI = 1.47, 2.06

# When several features exceed their lo, the first match wins.
TYPE_PRIORITY = ("dark", "glare", "compression", "blur")


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
        {
            "dark": s_dark.clip(lower=0),
            "blur": s_blur.clip(lower=0),
            "compression": s_comp.clip(lower=0),
            "glare": s_glare.clip(lower=0),
        }
    )
    df["score"] = scores.max(axis=1)

    fired = scores > 0
    df["pred_defect_type"] = "none"
    for t in TYPE_PRIORITY:
        hit = fired[t] & (df["pred_defect_type"] == "none")
        df.loc[hit, "pred_defect_type"] = t

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
    return df.sort_values(["score", "image_id"], ascending=[False, True], kind="mergesort")


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
        f"[t02_v1] {pred_path} | {len(scored)} images | "
        f"flagged={ctx.stats['n_flagged']} | "
        f"types={scored.loc[scored.pred_defect_type != 'none', 'pred_defect_type'].value_counts().to_dict()}"
    )
