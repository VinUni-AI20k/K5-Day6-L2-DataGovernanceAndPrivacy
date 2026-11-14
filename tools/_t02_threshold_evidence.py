"""Phan bo group-relative features tren toan bo 96 anh (khong dung nhan).
Muc dich: xem co 'khoang trong' tu nhien de dat threshold hay khong.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

sys.path.insert(0, r"C:\Users\hanng\day6")
from src.common.image_ops import load_rgb, to_gray, laplacian_variance, brightness_stats
from src.poc.t02_v1 import second_highest, second_lowest

D = Path(r"C:\Users\hanng\day6\fixtures\t02_raw_qc")


def blockiness(g):
    g = g[: (g.shape[0] // 8) * 8, : (g.shape[1] // 8) * 8]
    d_h = np.abs(np.diff(g, axis=1))
    d_v = np.abs(np.diff(g, axis=0))
    bh = d_h[:, 7::8].mean(); ih = np.delete(d_h, np.s_[7::8], axis=1).mean()
    bv = d_v[7::8, :].mean(); iv = np.delete(d_v, np.s_[7::8], axis=0).mean()
    return float((bh / max(ih, 1e-6) + bv / max(iv, 1e-6)) / 2)


imgs = pd.read_csv(D / "images.csv")
rows = []
for r in imgs.itertuples():
    img = load_rgb(D / r.path)
    g = to_gray(img)
    b = brightness_stats(img)
    sat = g > 250
    lab, n = ndimage.label(sat)
    blob = 0.0 if n == 0 else int(np.bincount(lab.ravel())[1:].max()) / g.size
    rows.append({
        "image_id": r.image_id, "grp": r.image_id.rsplit("_", 1)[0],
        "camera": r.camera_id, "light": r.light, "split": r.split,
        "lap": laplacian_variance(img), "bright": b["mean"],
        "frac_dark": b["frac_dark"], "sat_frac": float(sat.mean()),
        "blob": blob, "block": blockiness(g),
    })
df = pd.DataFrame(rows)

gmax_lap = df.groupby("grp")["lap"].transform("max")
g2_bright = df.groupby("grp")["bright"].transform(second_highest)
g2_block = df.groupby("grp")["block"].transform(second_lowest)
df["lap_ratio"] = df["lap"] / gmax_lap.clip(lower=1e-6)
df["bright_ratio"] = df["bright"] / g2_bright.clip(lower=1e-6)
df["block_ratio"] = df["block"] / g2_block.clip(lower=1e-6)
df.to_csv(r"C:\Users\hanng\day6\tools\_t02_features_grp.csv", index=False)

print("=== TOP 12 lap_ratio THAP NHAT (nghi blur) ===")
print(df.nsmallest(12, "lap_ratio")[["image_id", "light", "lap", "lap_ratio", "block_ratio", "bright_ratio"]].round(3).to_string(index=False))

print("\n=== TOP 12 bright_ratio THAP NHAT (nghi dark) ===")
print(df.nsmallest(12, "bright_ratio")[["image_id", "light", "bright", "bright_ratio", "frac_dark"]].round(3).to_string(index=False))

print("\n=== TOP 12 block_ratio CAO NHAT (nghi jpeg) ===")
print(df.nlargest(12, "block_ratio")[["image_id", "light", "block", "block_ratio", "lap_ratio"]].round(3).to_string(index=False))

print("\n=== TOP 12 blob CAO NHAT (nghi glare) ===")
print(df.nlargest(12, "blob")[["image_id", "light", "sat_frac", "blob", "bright_ratio"]].round(4).to_string(index=False))

print("\n=== SO ANH VUOT NGUONG CU (tren 96 anh) ===")
cands = {
    "lap_ratio < 0.40 (blur)": (df.lap_ratio < 0.40).sum(),
    "lap_ratio < 0.20": (df.lap_ratio < 0.20).sum(),
    "lap_ratio < 0.10": (df.lap_ratio < 0.10).sum(),
    "bright_ratio < 0.50 (dark)": (df.bright_ratio < 0.50).sum(),
    "bright_ratio < 0.30": (df.bright_ratio < 0.30).sum(),
    "block_ratio > 1.80 (jpeg)": (df.block_ratio > 1.80).sum(),
    "block_ratio > 2.20": (df.block_ratio > 2.20).sum(),
    "blob > 0.001 (glare)": (df.blob > 0.001).sum(),
    "blob > 0.002": (df.blob > 0.002).sum(),
}
for k, v in cands.items():
    print(f"{k:34s} -> {v:3d} anh")

print("\n=== PHAN BO lap_ratio THEO NHOM (4 gia tri/nhom) ===")
print(df.groupby("grp")["lap_ratio"].apply(lambda s: ",".join(f"{x:.2f}" for x in sorted(s))).to_string())
