"""T02 Raw QC Triage: lõi tính feature + chấm điểm (thuần numpy/PIL, test được độc lập).

Ý tưởng PoC:
  1. Mỗi ảnh tính 4 nhóm feature: sharpness (log Laplacian var / var ảnh), brightness (mean),
     glare cục bộ (tỉ lệ pixel cháy sáng ở ô lưới tệ nhất), JPEG blockiness.
  2. Chuẩn hoá ROBUST theo nhóm, thống kê lấy CHỈ từ split dev (không dùng nhãn):
       - blur        chuẩn hoá theo camera_id  -> xử lý cam_B quang học mềm
       - dark, glare chuẩn hoá theo light      -> ảnh đêm không bị loại hết
       - compression chuẩn hoá toàn cục
  3. sub-score = robust z theo hướng "xấu"; score = max(sub-score);
     pred_defect_type = argmax; pred_action = RECAPTURE nếu score >= tau.

Mọi tham số nằm trong DEFAULT_CFG; ghi đè qua configs/tracks/t02.yaml và CHỐT trước khi chạy eval.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

DEFECTS = ("blur", "dark", "glare", "compression")

DEFAULT_CFG = {
    "tau": 2.5,                 # ngưỡng robust-z để RECAPTURE (chốt a priori, không tune trên eval)
    "grid": (3, 4),             # lưới ô (hàng, cột) cho glare cục bộ
    "sat_level": 245.0,         # pixel >= mức này coi là cháy sáng
    "min_group_size": 3,        # nhóm dev ít hơn -> dùng thống kê toàn cục
    "use_group_norm": True,     # ablation: tắt -> chuẩn hoá toàn cục
    "use_local_glare": True,    # ablation: tắt -> glare tính trên toàn ảnh
    "features": list(DEFECTS),  # ablation: bớt feature
    # sàn cho độ lệch chuẩn robust, tránh z bùng nổ khi MAD ~ 0
    "min_scale": {"blur": 0.15, "dark": 6.0, "glare": 0.02, "compression": 0.05},
    "group_by": {"blur": "camera_id", "dark": "light", "glare": "light", "compression": None},
}


# ----------------------------------------------------------------------------- load
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_inputs(input_dir: str | Path, verify_hash: bool = True) -> pd.DataFrame:
    """Đọc images.csv và kiểm sha256 theo manifest.csv. Không đụng vào gt/."""
    input_dir = Path(input_dir)
    images_csv = input_dir / "images.csv"
    if not images_csv.exists():
        raise FileNotFoundError(f"thiếu {images_csv}")
    df = pd.read_csv(images_csv)
    need = {"image_id", "path", "camera_id", "light", "split"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"images.csv thiếu cột: {sorted(missing)}")

    if verify_hash:
        man_path = input_dir / "manifest.csv"
        if not man_path.exists():
            raise FileNotFoundError(f"thiếu {man_path}")
        man = pd.read_csv(man_path)
        expected = dict(zip(man["path"].astype(str), man["sha256"].astype(str)))
        bad = []
        for p in df["path"].astype(str):
            exp = expected.get(p)
            if exp is None:
                bad.append((p, "không có trong manifest"))
            elif sha256_file(input_dir / p) != exp:
                bad.append((p, "sha256 lệch"))
        if bad:
            raise ValueError(f"{len(bad)} file lỗi integrity, ví dụ: {bad[:3]}")
    return df


# ------------------------------------------------------------------------- features
def to_gray(img: np.ndarray) -> np.ndarray:
    img = np.asarray(img, dtype=np.float64)
    if img.ndim == 3:
        img = img[..., :3] @ np.array([0.299, 0.587, 0.114])
    if img.ndim != 2 or img.shape[0] < 8 or img.shape[1] < 8:
        raise ValueError(f"ảnh không hợp lệ, shape={img.shape}")
    return img


def laplacian_var(g: np.ndarray) -> float:
    lap = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4 * g[1:-1, 1:-1]
    return float(lap.var())


def local_sat_frac(g: np.ndarray, grid=(3, 4), level=245.0) -> float:
    """Tỉ lệ pixel cháy sáng ở ô lưới TỆ NHẤT -> bắt glare cục bộ (vd vùng biển số)."""
    rows = np.array_split(np.arange(g.shape[0]), grid[0])
    cols = np.array_split(np.arange(g.shape[1]), grid[1])
    return float(max((g[np.ix_(r, c)] >= level).mean() for r in rows for c in cols))


def blockiness(g: np.ndarray) -> float:
    """Tỉ số chênh lệch tại biên khối 8x8 / trong khối. ~1 = không blocking, >1 = JPEG nặng."""
    dx = np.abs(np.diff(g, axis=1))
    dy = np.abs(np.diff(g, axis=0))
    bx = (np.arange(dx.shape[1]) % 8) == 7
    by = (np.arange(dy.shape[0]) % 8) == 7
    boundary = np.concatenate([dx[:, bx].ravel(), dy[by, :].ravel()]).mean()
    inner = np.concatenate([dx[:, ~bx].ravel(), dy[~by, :].ravel()]).mean()
    return float(np.log((boundary + 1.0) / (inner + 1.0)))


def image_features(img: np.ndarray, cfg: dict | None = None) -> dict:
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    g = to_gray(img)
    glare = (local_sat_frac(g, cfg["grid"], cfg["sat_level"]) if cfg["use_local_glare"]
             else float((g >= cfg["sat_level"]).mean()))
    lv = laplacian_var(g)
    return {
        # sharpness chuẩn hoá theo tương phản của chính ảnh: ảnh tối/đêm có Laplacian var
        # thấp vì biên độ thấp, KHÔNG phải vì mờ -> chia cho var(g) để tách 2 hiện tượng.
        "f_blur": float(np.log(lv / (g.var() + 1e-6) + 1e-6)),   # thấp = mờ
        "f_lapvar": float(np.log(lv + 1.0)),                      # Laplacian thô (cho baseline)
        "f_dark": float(g.mean()),                          # thấp = tối
        "f_glare": glare,                                   # cao = lóa
        "f_compression": blockiness(g),                     # cao = nén nặng
        "f_p95": float(np.percentile(g, 95)),               # phụ, để phân tích
    }


# ------------------------------------------------------------------------- scoring
_BAD_HIGH = {"blur": False, "dark": False, "glare": True, "compression": True}


def _robust(x: pd.Series, floor: float) -> tuple[float, float]:
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) * 1.4826
    return med, max(mad, floor)


def fit_reference(feats: pd.DataFrame, cfg: dict | None = None) -> dict:
    """Thống kê tham chiếu (median, scale) theo nhóm, CHỈ từ hàng split == 'dev'. Không dùng nhãn."""
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    dev = feats[feats["split"] == "dev"]
    if dev.empty:
        raise ValueError("không có ảnh split=dev để làm tham chiếu")
    ref = {}
    for d in cfg["features"]:
        col, floor = f"f_{d}", cfg["min_scale"][d]
        key = cfg["group_by"][d] if cfg["use_group_norm"] else None
        entry = {"_global": _robust(dev[col], floor), "key": key, "groups": {}}
        if key:
            for gval, sub in dev.groupby(key):
                if len(sub) >= cfg["min_group_size"]:
                    entry["groups"][gval] = _robust(sub[col], floor)
        ref[d] = entry
    return ref


def score_features(feats: pd.DataFrame, ref: dict, cfg: dict | None = None) -> pd.DataFrame:
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    out = feats.copy()
    for d in cfg["features"]:
        e = ref[d]
        meds, scales = [], []
        for _, row in out.iterrows():
            med, sc = e["groups"].get(row[e["key"]], e["_global"]) if e["key"] else e["_global"]
            meds.append(med)
            scales.append(sc)
        z = (out[f"f_{d}"] - np.array(meds)) / np.array(scales)
        out[f"s_{d}"] = np.clip(z if _BAD_HIGH[d] else -z, 0, None)
    s_cols = [f"s_{d}" for d in cfg["features"]]
    out["score"] = out[s_cols].max(axis=1)
    out["pred_defect_type"] = out[s_cols].idxmax(axis=1).str[2:]
    flagged = out["score"] >= cfg["tau"]
    out.loc[~flagged, "pred_defect_type"] = "none"
    out["pred_action"] = np.where(flagged, "RECAPTURE", "KEEP")
    return out


def compute_all_features(df: pd.DataFrame, input_dir: str | Path, cfg: dict | None = None) -> pd.DataFrame:
    input_dir = Path(input_dir)
    rows = []
    for r in df.itertuples(index=False):
        with Image.open(input_dir / r.path) as im:
            arr = np.asarray(im.convert("RGB"))
        rows.append(image_features(arr, cfg))
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def run_poc(df: pd.DataFrame, input_dir: str | Path, cfg: dict | None = None) -> pd.DataFrame:
    """images.csv đã load -> DataFrame đủ cột ranked_review.csv, sắp score giảm dần."""
    feats = compute_all_features(df, input_dir, cfg)
    ref = fit_reference(feats, cfg)
    scored = score_features(feats, ref, cfg)
    return scored.sort_values("score", ascending=False, kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------------ baseline
def run_baseline(df: pd.DataFrame, input_dir: str | Path, threshold: float | None = None) -> pd.DataFrame:
    """Baseline theo đề: MỘT ngưỡng Laplacian toàn ảnh, không chuẩn hoá nhóm.
    score = -log(lap_var): càng mờ càng cao. Ngưỡng mặc định = phân vị 25% của dev (chốt a priori)."""
    feats = compute_all_features(df, input_dir)
    if threshold is None:
        threshold = float(np.percentile(feats.loc[feats["split"] == "dev", "f_lapvar"], 25))
    out = feats.copy()
    out["score"] = -out["f_lapvar"]
    flagged = out["f_lapvar"] < threshold
    out["pred_defect_type"] = np.where(flagged, "blur", "none")
    out["pred_action"] = np.where(flagged, "RECAPTURE", "KEEP")
    out.attrs["threshold"] = threshold
    return out.sort_values("score", ascending=False, kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------------ decision
def batch_decision(ranked: pd.DataFrame, split: str = "eval", max_recapture_rate: float = 0.3) -> tuple[str, str]:
    """Quyết định cấp batch. Trả (decision, reason_code) cho common.decision."""
    sub = ranked[ranked["split"] == split] if "split" in ranked else ranked
    rate = float((sub["pred_action"] == "RECAPTURE").mean()) if len(sub) else 0.0
    if rate == 0:
        return "GO", "NO_DEFECT_FLAGGED"
    if rate <= max_recapture_rate:
        return "GO", f"RECAPTURE_FLAGGED_{rate:.0%}_WITHIN_LIMIT"
    return "HOLD", f"RECAPTURE_RATE_{rate:.0%}_ABOVE_{max_recapture_rate:.0%}"


OUTPUT_COLS = ["image_id", "score", "pred_defect_type", "pred_action",
               "split", "camera_id", "light", "path",
               "s_blur", "s_dark", "s_glare", "s_compression",
               "f_blur", "f_lapvar", "f_dark", "f_glare", "f_compression"]


def to_output(ranked: pd.DataFrame) -> pd.DataFrame:
    out = ranked[[c for c in OUTPUT_COLS if c in ranked.columns]].copy()
    # cột reason (giống random_baseline) để contact sheet / reviewer thấy lý do
    out.insert(2, "reason", np.where(out["pred_defect_type"] == "none", "ok", "suspect_" + out["pred_defect_type"]))
    return out
