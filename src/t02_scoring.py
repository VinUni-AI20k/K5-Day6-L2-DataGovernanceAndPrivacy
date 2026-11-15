"""T02 · Thành viên 2 — chuẩn hóa theo nhóm, chấm điểm, gán loại lỗi.

score cao = nghi lỗi hơn. score = max(0, z_blur, z_dark, z_glare, z_compression),
trong đó z là robust z-score (median/MAD) tính TRONG NHÓM (camera_id, light).
Nhóm < min_group ảnh -> lùi về nhóm `light`, rồi toàn bộ.
Mọi tham số nằm ở DEFAULT_SCORE_PARAMS; ghi đè qua configs/lab.yaml -> params.t02.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .t02_features import DEFAULT_FEATURE_PARAMS, FEATURE_COLUMNS, extract_features

DEFAULT_SCORE_PARAMS = {
    "group_levels": [["camera_id", "light"], ["light"], []],   # thứ tự lùi nhóm
    "min_group": 6,
    "scale_floor": {"blur": 0.10, "dark": 2.0, "glare": 0.02, "compression": 0.05},
    "none_threshold": 1.5,     # score < ngưỡng này -> loại lỗi 'none', hành động KEEP
    "weights": {"blur": 1.0, "dark": 1.0, "glare": 1.0, "compression": 1.0},
}

# loại lỗi -> (cột đặc trưng, dấu: +1 = giá trị lớn là xấu, -1 = giá trị nhỏ là xấu, dùng log?)
COMPONENTS = {
    "blur": ("blur_pct", -1, True),
    "dark": ("p95", -1, False),
    "glare": ("glare_max_cell", +1, False),
    "compression": ("blockiness", +1, False),
}
DEFECT_NAMES = list(COMPONENTS)


def load_params(config: dict | None) -> tuple[dict, dict]:
    """Lấy (feature_params, score_params) từ config['params']['t02'] (nếu có) đè lên mặc định."""
    t02 = ((config or {}).get("params") or {}).get("t02") or {}
    feat = {**DEFAULT_FEATURE_PARAMS, **(t02.get("features") or {})}
    sc = {**DEFAULT_SCORE_PARAMS, **{k: v for k, v in t02.items() if k != "features"}}
    sc["scale_floor"] = {**DEFAULT_SCORE_PARAMS["scale_floor"], **(t02.get("scale_floor") or {})}
    sc["weights"] = {**DEFAULT_SCORE_PARAMS["weights"], **(t02.get("weights") or {})}
    return feat, sc


def build_feature_table(images: pd.DataFrame, input_dir: str | Path, feature_params: dict | None = None) -> pd.DataFrame:
    """images: images.csv (image_id, path, camera_id, light, split). Trả bảng đặc trưng, mỗi ảnh một dòng."""
    root = Path(input_dir)
    rows = []
    for r in images.itertuples(index=False):
        f = extract_features(root / r.path, feature_params)
        rows.append({"image_id": r.image_id, **f})
    feats = pd.DataFrame(rows)
    return images.merge(feats, on="image_id", how="left")


def _transform(df: pd.DataFrame, name: str) -> pd.Series:
    col, sign, use_log = COMPONENTS[name]
    x = df[col].astype(float)
    if use_log:
        x = np.log1p(x.clip(lower=0))
    return x * sign          # sau bước này: giá trị càng LỚN càng XẸ


def _group_keys(df: pd.DataFrame, levels: list[list[str]], min_group: int) -> pd.Series:
    """Cho mỗi dòng, chọn mức nhóm nhỏ nhất còn đủ min_group ảnh ok. Trả khóa dạng chuỗi."""
    ok = df["ok"].astype(bool)
    keys = pd.Series("", index=df.index, dtype=object)
    chosen = pd.Series(False, index=df.index)
    for lvl in levels:
        if lvl:
            k = df[lvl].astype(str).agg("|".join, axis=1)
        else:
            k = pd.Series("ALL", index=df.index)
        size = k[ok].map(k[ok].value_counts())
        size = size.reindex(df.index).fillna(0)
        use = (~chosen) & (size >= min_group)
        keys[use] = ("/".join(lvl) or "ALL") + "=" + k[use]
        chosen |= use
    keys[~chosen] = "ALL=ALL"
    return keys


def score_table(feats: pd.DataFrame, score_params: dict | None = None) -> pd.DataFrame:
    """feats: build_feature_table(). Trả DataFrame cùng thứ tự với cột z_*, score, pred_defect_type, pred_action."""
    sp = {**DEFAULT_SCORE_PARAMS, **(score_params or {})}
    df = feats.copy().reset_index(drop=True)
    df["ok"] = df["ok"].fillna(False).astype(bool)
    keys = _group_keys(df, sp["group_levels"], int(sp["min_group"]))
    df["group_used"] = keys
    ok = df["ok"]
    for name in DEFECT_NAMES:
        x = _transform(df, name)
        z = pd.Series(np.nan, index=df.index)
        floor = sp["scale_floor"][name]
        for g, idx in df[ok].groupby(keys[ok]).groups.items():
            xs = x.loc[idx]
            med = xs.median()
            mad = 1.4826 * (xs - med).abs().median()
            z.loc[idx] = (xs - med) / max(mad, floor)
        df[f"z_{name}"] = z
    zcols = [f"z_{n}" for n in DEFECT_NAMES]
    weighted = pd.concat([df[f"z_{n}"] * sp["weights"][n] for n in DEFECT_NAMES], axis=1)
    weighted.columns = DEFECT_NAMES
    df["score"] = np.where(ok, weighted.max(axis=1).clip(lower=0), np.inf)
    # idxmax sập nếu cả dòng NaN (ảnh hỏng): thay bằng 0 rồi che lại bằng `ok`
    arg = weighted.fillna(0.0).idxmax(axis=1).where(ok)
    flagged = ok & (df["score"] >= sp["none_threshold"])
    df["pred_defect_type"] = np.where(flagged, arg, np.where(ok, "none", "unreadable"))
    df["pred_action"] = np.where(df["pred_defect_type"] == "none", "KEEP", "RECAPTURE")
    df["reason"] = df["pred_defect_type"]
    return df


def score_images(images: pd.DataFrame, input_dir: str | Path, config: dict | None = None) -> pd.DataFrame:
    """Đường tắt cho pipeline: images.csv + thư mục input + config -> bảng đã chấm điểm."""
    feat_p, score_p = load_params(config)
    return score_table(build_feature_table(images, input_dir, feat_p), score_p)
