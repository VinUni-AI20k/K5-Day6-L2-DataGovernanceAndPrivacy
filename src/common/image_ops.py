"""Low-level image primitives (numpy + Pillow only; OpenCV optional).

These are building blocks, not answers: e.g. a single global Laplacian
threshold is exactly the *baseline* of T02 — your PoC must do better.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy.fft import dct
from scipy.ndimage import convolve

_LAPLACE = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)


def load_rgb(path: str | Path) -> np.ndarray:
    """HxWx3 uint8."""
    return np.asarray(Image.open(path).convert("RGB"))


def to_gray(img: np.ndarray) -> np.ndarray:
    """float32 HxW in [0,255]."""
    if img.ndim == 2:
        return img.astype(np.float32)
    return (0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]).astype(np.float32)


def crop(img: np.ndarray, x: float, y: float, w: float, h: float) -> np.ndarray:
    H, W = img.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, int(x + w)), min(H, int(y + h))
    return img[y0:y1, x0:x1]


def laplacian_variance(img: np.ndarray) -> float:
    """Classic sharpness proxy (higher = sharper)."""
    g = to_gray(img)
    return float(convolve(g, _LAPLACE, mode="reflect").var())


def brightness_stats(img: np.ndarray) -> dict:
    g = to_gray(img)
    return {
        "mean": float(g.mean()),
        "std": float(g.std()),
        "p05": float(np.percentile(g, 5)),
        "p95": float(np.percentile(g, 95)),
        "frac_dark": float((g < 30).mean()),
        "frac_saturated": float((g > 245).mean()),
    }


def color_histogram(img: np.ndarray, bins: int = 16) -> np.ndarray:
    """Concatenated, L1-normalised per-channel histogram (len = 3*bins)."""
    hs = [np.histogram(img[..., c], bins=bins, range=(0, 256))[0] for c in range(3)]
    h = np.concatenate(hs).astype(np.float64)
    return h / max(h.sum(), 1.0)


def ahash(img: np.ndarray, size: int = 8) -> np.ndarray:
    g = np.asarray(Image.fromarray(to_gray(img).astype(np.uint8)).resize((size, size), Image.BILINEAR), dtype=np.float32)
    return (g > g.mean()).flatten()


def dhash(img: np.ndarray, size: int = 8) -> np.ndarray:
    g = np.asarray(Image.fromarray(to_gray(img).astype(np.uint8)).resize((size + 1, size), Image.BILINEAR), dtype=np.float32)
    return (g[:, 1:] > g[:, :-1]).flatten()


def phash(img: np.ndarray, size: int = 8, highfreq_factor: int = 4) -> np.ndarray:
    n = size * highfreq_factor
    g = np.asarray(Image.fromarray(to_gray(img).astype(np.uint8)).resize((n, n), Image.BILINEAR), dtype=np.float32)
    d = dct(dct(g, axis=0, norm="ortho"), axis=1, norm="ortho")[:size, :size]
    med = np.median(d.flatten()[1:])
    return (d > med).flatten()


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.count_nonzero(a != b))


def hash_hex(bits: np.ndarray) -> str:
    v = 0
    for bit in bits.astype(int):
        v = (v << 1) | int(bit)
    return f"{v:0{len(bits) // 4}x}"
