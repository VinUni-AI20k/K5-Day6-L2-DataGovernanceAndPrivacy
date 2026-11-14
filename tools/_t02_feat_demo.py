import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, r"C:\Users\hanng\day6")
from src.common.image_ops import load_rgb, to_gray, laplacian_variance, brightness_stats
from scipy import ndimage

D = Path(r"C:\Users\hanng\day6\fixtures\t02_raw_qc")
imgs = pd.read_csv(D / "images.csv")


def blockiness(g):
    d_h = np.abs(np.diff(g, axis=1))
    d_v = np.abs(np.diff(g, axis=0))
    bh = d_h[:, 7::8].mean()
    ih = np.delete(d_h, np.s_[7::8], axis=1).mean()
    bv = d_v[7::8, :].mean()
    iv = np.delete(d_v, np.s_[7::8], axis=0).mean()
    return float((bh / max(ih, 1e-6) + bv / max(iv, 1e-6)) / 2)


def glare_stats(g):
    sat = g > 250
    lab, n = ndimage.label(sat)
    largest = 0 if n == 0 else int(np.bincount(lab.ravel())[1:].max())
    return float(sat.mean()), largest / g.size


rows = []
for r in imgs.itertuples():
    img = load_rgb(D / r.path)
    g = to_gray(img)
    b = brightness_stats(img)
    sf, blob = glare_stats(g)
    rows.append({
        "image_id": r.image_id, "grp": r.image_id.rsplit("_", 1)[0],
        "camera": r.camera_id, "light": r.light,
        "lap": round(laplacian_variance(img), 1),
        "bright": round(b["mean"], 1), "dark_frac": round(b["frac_dark"], 3),
        "sat_frac": round(sf, 4), "blob": round(blob, 4),
        "block": round(blockiness(g), 2),
    })
df = pd.DataFrame(rows)
df.to_csv(r"C:\Users\hanng\day6\tools\_t02_features.csv", index=False)

for grp in ["img_00", "img_02", "img_04", "img_01"]:
    sub = df[df.grp == grp].copy()
    print(f"\n=== {grp} ({sub.camera.iloc[0]}, {sub.light.iloc[0]}) ===")
    print(sub[["image_id", "lap", "bright", "dark_frac", "sat_frac", "blob", "block"]].to_string(index=False))
    med = sub[["lap", "bright", "sat_frac", "block"]].median()
    sub["lap_ratio"] = (sub.lap / med.lap).round(2)
    sub["bright_ratio"] = (sub.bright / med.bright).round(2)
    sub["sat_ratio"] = (sub.sat_frac / max(med.sat_frac, 1e-6)).round(1)
    sub["block_ratio"] = (sub.block / med.block).round(2)
    print("--- ty le so voi median nhom ---")
    print(sub[["image_id", "lap_ratio", "bright_ratio", "sat_ratio", "block_ratio"]].to_string(index=False))
