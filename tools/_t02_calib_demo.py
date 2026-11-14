import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage

sys.path.insert(0, r"C:\Users\hanng\day6")
from src.common.image_ops import load_rgb, to_gray, laplacian_variance, brightness_stats
from src.common import corruptions as C

D = Path(r"C:\Users\hanng\day6\fixtures\t02_raw_qc")


def blockiness(g):
    g = g[: (g.shape[0] // 8) * 8, : (g.shape[1] // 8) * 8]
    d_h = np.abs(np.diff(g, axis=1))
    d_v = np.abs(np.diff(g, axis=0))
    bh = d_h[:, 7::8].mean(); ih = np.delete(d_h, np.s_[7::8], axis=1).mean()
    bv = d_v[7::8, :].mean(); iv = np.delete(d_v, np.s_[7::8], axis=0).mean()
    return float((bh / max(ih, 1e-6) + bv / max(iv, 1e-6)) / 2)


def features(img):
    g = to_gray(img)
    b = brightness_stats(img)
    sat = g > 250
    lab, n = ndimage.label(sat)
    blob = 0.0 if n == 0 else int(np.bincount(lab.ravel())[1:].max()) / g.size
    return {
        "lap": laplacian_variance(img),
        "mean": b["mean"],
        "frac_dark": b["frac_dark"],
        "sat_frac": float(sat.mean()),
        "blob": blob,
        "block": blockiness(g),
    }


PARENTS = {
    "img_00_1 (day, cam_B)": "images/img_00_1.jpg",
    "img_02_0 (day, cam_A)": "images/img_02_0.jpg",
    "img_04_1 (dusk, cam_A)": "images/img_04_1.jpg",
    "img_01_0 (night, cam_A)": "images/img_01_0.jpg",
}

rows = []
for name, rel in PARENTS.items():
    parent = load_rgb(D / rel)
    base = features(parent)
    for tname in ["blur", "dark", "glare", "jpeg"]:
        for sev in (1, 2):
            img = C.apply(tname, parent, sev, seed=42)
            f = features(img)
            rows.append({
                "parent": name, "transform": tname, "sev": sev,
                "lap_ratio": round(f["lap"] / max(base["lap"], 1e-6), 3),
                "bright_ratio": round(f["mean"] / max(base["mean"], 1e-6), 3),
                "frac_dark": round(f["frac_dark"], 3),
                "sat_frac": round(f["sat_frac"], 4),
                "blob": round(f["blob"], 4),
                "block_ratio": round(f["block"] / max(base["block"], 1e-6), 3),
            })

df = pd.DataFrame(rows)
print("=== FEATURE SHIFT KHI INJECT CORRUPTION (ty le so voi parent) ===")
print(df.to_string(index=False))
print()
print("=== TONG HOP THEO TRANSFORM ===")
for t in ["blur", "dark", "glare", "jpeg"]:
    sub = df[df["transform"] == t]
    print(f"\n-- {t} --")
    print(sub.groupby("sev")[["lap_ratio", "bright_ratio", "frac_dark", "sat_frac", "blob", "block_ratio"]]
          .agg(["min", "max"]).round(3).to_string())

print()
print("=== CLEAN PARENT (khong inject) — de so sanh ===")
clean = []
for name, rel in PARENTS.items():
    f = features(load_rgb(D / rel))
    clean.append({"parent": name, "lap": round(f["lap"], 1), "mean": round(f["mean"], 1),
                  "frac_dark": round(f["frac_dark"], 3), "sat_frac": round(f["sat_frac"], 4),
                  "blob": round(f["blob"], 4), "block": round(f["block"], 2)})
print(pd.DataFrame(clean).to_string(index=False))
