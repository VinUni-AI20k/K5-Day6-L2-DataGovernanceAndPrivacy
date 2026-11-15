"""T02 · Baseline theo đề: MỘT ngưỡng Laplacian toàn ảnh (càng mờ điểm càng cao). Không chuẩn hóa nhóm.

    python -m src.main --track t02 --pipeline src.t02_baseline --output out/baseline --run-name baseline --offline --seed 42
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common.context import RunContext
from .common.image_ops import laplacian_variance, load_rgb
from .t02_poc import finish, load_images


def baseline_scores(images: pd.DataFrame, input_dir) -> pd.DataFrame:
    rows = []
    for r in images.itertuples(index=False):
        try:
            lv = laplacian_variance(load_rgb(f"{input_dir}/{r.path}"))
            ok = True
        except Exception:  # noqa: BLE001
            lv, ok = np.nan, False
        rows.append({"image_id": r.image_id, "laplacian_var": lv, "ok": ok})
    df = images.merge(pd.DataFrame(rows), on="image_id")
    df["score"] = np.where(df["ok"], -df["laplacian_var"], np.inf)
    df["reason"] = "low_laplacian"
    return df


def run(ctx: RunContext) -> None:
    images = load_images(ctx)
    finish(ctx, baseline_scores(images, ctx.input_dir), "Baseline Laplacian")
