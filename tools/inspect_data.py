"""EDA cho T02 Raw QC Triage (không đọc ground truth).

Usage:
    python -m tools.inspect_data                      # thống kê metadata + feature trên split dev
    python -m tools.inspect_data --out reports/eda    # ghi thêm CSV

Hai phần:
  1. Metadata (images.csv): đếm theo camera / light / split, kiểm tra split chia theo cảnh gốc.
     Chỉ dùng cột metadata nên an toàn với mọi split.
  2. Feature ảnh (Laplacian variance, độ sáng, tỉ lệ pixel tối/cháy): mặc định chỉ tính trên split
     `dev`, vì luật bài lab cấm tune ngưỡng bằng split eval.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.common.image_ops import brightness_stats, laplacian_variance, load_rgb

DEFAULT_INPUT = Path("fixtures/t02_raw_qc")


def scene_of(image_id: str) -> str:
    """img_03_2 -> img_03 (4 biến thể cùng một cảnh gốc)."""
    return "_".join(image_id.split("_")[:2])


def metadata_report(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    df = df.assign(scene=df.image_id.map(scene_of))
    out = {
        "by_split": df.groupby("split").size().rename("n_images").to_frame(),
        "by_camera": df.groupby(["split", "camera_id"]).size().rename("n_images").to_frame(),
        "by_light": df.groupby(["split", "light"]).size().rename("n_images").to_frame(),
        "camera_x_light": df.groupby(["camera_id", "light"]).size().rename("n_images").to_frame(),
    }
    scenes = df.groupby("scene").agg(n_images=("image_id", "size"), n_splits=("split", "nunique"),
                                     n_cameras=("camera_id", "nunique"), n_lights=("light", "nunique"))
    out["scenes"] = scenes
    return out


def feature_table(df: pd.DataFrame, root: Path) -> pd.DataFrame:
    rows = []
    for r in df.itertuples():
        img = load_rgb(root / r.path)
        bs = brightness_stats(img)
        rows.append({"image_id": r.image_id, "camera_id": r.camera_id, "light": r.light, "split": r.split,
                     "lap_var": laplacian_variance(img), "mean": bs["mean"], "frac_dark": bs["frac_dark"],
                     "frac_saturated": bs["frac_saturated"], "p95": bs["p95"]})
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--split", default="dev", help="split dùng để tính feature (mặc định dev; không tune bằng eval)")
    ap.add_argument("--out", type=Path, default=None, help="thư mục ghi CSV (tuỳ chọn)")
    a = ap.parse_args(argv)

    df = pd.read_csv(a.input / "images.csv")
    rep = metadata_report(df)
    pd.set_option("display.width", 140)
    for name in ("by_split", "by_camera", "by_light", "camera_x_light"):
        print(f"\n== {name} ==\n{rep[name].to_string()}")

    sc = rep["scenes"]
    leak = sc[sc.n_splits > 1]
    print(f"\n== scenes ==\nsố cảnh gốc: {len(sc)} | ảnh/cảnh: {sorted(sc.n_images.unique())} | "
          f"cảnh nằm ở >1 split (rò rỉ): {len(leak)}")
    print("cảnh có >1 camera hoặc >1 light:", int(((sc.n_cameras > 1) | (sc.n_lights > 1)).sum()))

    sub = df[df.split == a.split]
    feats = feature_table(sub, a.input)
    print(f"\n== feature trên split={a.split} (N={len(feats)}) ==")
    cols = ["lap_var", "mean", "frac_dark", "frac_saturated"]
    summ = feats.groupby(["camera_id", "light"])[cols].agg(["count", "median"]).round(4)
    print(summ.to_string())

    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        for k, v in rep.items():
            v.to_csv(a.out / f"meta_{k}.csv")
        feats.to_csv(a.out / f"features_{a.split}.csv", index=False)
        print(f"\nđã ghi CSV vào {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
