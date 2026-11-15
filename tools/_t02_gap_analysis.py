"""Tim khoang trong tu nhien trong phan bo feature + doan composition moi nhom."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\hanng\day6")

df = pd.read_csv(r"C:\Users\hanng\day6\tools\_t02_features_grp.csv")


def show_sorted(col, ascending=True, n=96):
    s = df.sort_values(col, ascending=ascending)[["image_id", "light", col]]
    print(f"\n=== {col} ({'tang' if ascending else 'giam'} dan) ===")
    vals = s[col].to_numpy()
    for i in range(0, len(vals), 8):
        chunk = s.iloc[i:i + 8]
        print("  ".join(f"{r.image_id}:{getattr(r, col):.4g}" for r in chunk.itertuples()))


for c in ["lap_ratio", "bright_ratio", "block_ratio", "blob"]:
    show_sorted(c, ascending=(c in ("lap_ratio", "bright_ratio")), n=96)

print("\n=== CANDIDATE TYPE THEO CLUSTER (chi de tham khao, khong phai nhan) ===")


def guess(r):
    # thu tu uu tien: dark -> jpeg -> blur -> glare
    if r.bright_ratio < 0.30:
        return "dark"
    if r.block_ratio > 2.2:
        return "jpeg"
    if r.lap_ratio < 0.10:
        return "blur"
    if r.blob > 0.0005:
        return "glare"
    return "none"


df["guess"] = df.apply(guess, axis=1)
print(df.groupby("guess").size().to_string())
print()
for grp, sub in df.groupby("grp"):
    types = ",".join(sorted(sub.guess))
    print(f"{grp} ({sub.light.iloc[0]:5s}, {sub.camera.iloc[0]}): {types:22s} | " +
          "  ".join(f"{r.image_id}:{r.guess}" for r in sub.itertuples()))
