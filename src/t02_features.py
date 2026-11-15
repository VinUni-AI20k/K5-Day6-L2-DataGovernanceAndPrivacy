"""T02 · Thành viên 1/2 — trích đặc trưng chất lượng ảnh (blur / dark / glare / compression).

Mỗi ảnh -> một dict số. Không đọc ground truth, không cần mạng.
Ngưỡng và lưới nằm trong `DEFAULT_FEATURE_PARAMS` (ghi đè qua configs/lab.yaml: params.t02).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.ndimage import convolve

from .common.image_ops import brightness_stats, load_rgb, to_gray

_LAPLACE = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)

DEFAULT_FEATURE_PARAMS = {
    "grid": [4, 4],          # lưới ô (hàng, cột) cho độ nét và lóa cục bộ
    "blur_percentile": 75,   # percentile của phương sai Laplacian các ô (cao = chỉ nhìn ô có cạnh, bỏ ô phẳng như trời)
    "glare_thr": 245,        # pixel > ngưỡng này coi là cháy sáng
    "dark_p": 95,            # percentile độ sáng dùng cho "tối" (thấp = tối)
    "block": 8,              # kích thước khối JPEG
}

FEATURE_COLUMNS = ["blur_pct", "p95", "glare_max_cell", "blockiness"]
EXTRA_COLUMNS = ["mean_brightness", "frac_dark", "frac_saturated"]


def _cells(h: int, w: int, rows: int, cols: int):
    ys = np.linspace(0, h, rows + 1).astype(int)
    xs = np.linspace(0, w, cols + 1).astype(int)
    for i in range(rows):
        for j in range(cols):
            yield ys[i], ys[i + 1], xs[j], xs[j + 1]


def blockiness(gray: np.ndarray, block: int = 8) -> float:
    """Tỷ số |chênh lệch pixel kề| tại biên khối so với bên trong khối (>1 = có 'bậc thang' JPEG)."""
    ratios = []
    for axis in (1, 0):
        d = np.abs(np.diff(gray, axis=axis))
        idx = np.arange(d.shape[axis])
        on_edge = ((idx + 1) % block) == 0
        if on_edge.sum() == 0 or (~on_edge).sum() == 0:
            continue
        dd = d if axis == 1 else d.T
        edge, inner = dd[:, on_edge].mean(), dd[:, ~on_edge].mean()
        ratios.append(edge / (inner + 1e-6))
    return float(np.mean(ratios)) if ratios else float("nan")


def features_from_array(img: np.ndarray, params: dict | None = None) -> dict:
    p = {**DEFAULT_FEATURE_PARAMS, **(params or {})}
    gray = to_gray(img)
    h, w = gray.shape
    rows, cols = p["grid"]
    lap = convolve(gray, _LAPLACE, mode="reflect")
    cell_var, cell_glare = [], []
    for y0, y1, x0, x1 in _cells(h, w, rows, cols):
        cell_var.append(float(lap[y0:y1, x0:x1].var()))
        cell_glare.append(float((gray[y0:y1, x0:x1] > p["glare_thr"]).mean()))
    st = brightness_stats(img)
    return {
        "ok": True,
        "blur_pct": float(np.percentile(cell_var, p["blur_percentile"])),
        "p95": float(np.percentile(gray, p["dark_p"])),
        "glare_max_cell": float(max(cell_glare)),
        "blockiness": blockiness(gray, int(p["block"])),
        "mean_brightness": st["mean"],
        "frac_dark": st["frac_dark"],
        "frac_saturated": st["frac_saturated"],
    }


def extract_features(path: str | Path, params: dict | None = None) -> dict:
    """Ảnh thiếu/hỏng -> {'ok': False} (không crash pipeline)."""
    try:
        return features_from_array(load_rgb(path), params)
    except Exception as e:  # noqa: BLE001 - ảnh hỏng phải được báo, không dừng cả lô
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
