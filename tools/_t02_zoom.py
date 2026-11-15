"""Zoom crop + noise estimate de phan biet blur that vs noise/JPEG."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

sys.path.insert(0, r"C:\Users\hanng\day6")
from src.common.image_ops import load_rgb, to_gray

D = Path(r"C:\Users\hanng\day6\fixtures\t02_raw_qc")
imgs = pd.read_csv(D / "images.csv")
df = pd.read_csv(r"C:\Users\hanng\day6\tools\_t02_features_grp.csv").merge(imgs[["image_id", "path"]], on="image_id")

GROUPS = ["img_00", "img_03", "img_12", "img_19"]
CROP = (70, 55, 250, 155)  # x0,y0,x1,y1
SCALE = 3

print("=== NOISE / SHARPNESS ESTIMATES ===")
for grp in GROUPS:
    sub = df[df.grp == grp]
    print(f"\n-- {grp} ({sub.light.iloc[0]}, {sub.camera.iloc[0]}) --")
    for r in sub.itertuples():
        img = load_rgb(D / r.path)
        g = to_gray(img)
        resid = g - gaussian_filter(g, 1.2)
        mad = float(np.median(np.abs(resid - np.median(resid))) * 1.4826)
        # Tenengrad
        gx = np.abs(np.diff(g, axis=1)).mean()
        gy = np.abs(np.diff(g, axis=0)).mean()
        print(f"{r.image_id}: lap={r.lap:8.1f} lap_ratio={r.lap_ratio:5.3f} "
              f"noise_mad={mad:5.2f} grad={gx+gy:6.2f} block_ratio={r.block_ratio:5.2f}")

canvas = Image.new("RGB", ((CROP[2]-CROP[0])*SCALE*4 + 30, ((CROP[3]-CROP[1])*SCALE+22)*len(GROUPS)), "white")
d = ImageDraw.Draw(canvas)
for gi, grp in enumerate(GROUPS):
    sub = df[df.grp == grp]
    for i, r in enumerate(sub.itertuples()):
        im = Image.open(D / r.path).convert("RGB").crop(CROP)
        im = im.resize((im.width*SCALE, im.height*SCALE), Image.NEAREST)
        x = i*((CROP[2]-CROP[0])*SCALE + 8)
        y = gi*((CROP[3]-CROP[1])*SCALE + 22)
        canvas.paste(im, (x, y+18))
        d.text((x, y+2), f"{r.image_id} lap={r.lap:.0f} blk={r.block_ratio:.1f}", fill="black")
canvas.save(r"C:\Users\hanng\day6\out_analysis_t02_zoom.png")
print("\nsaved out_analysis_t02_zoom.png")
