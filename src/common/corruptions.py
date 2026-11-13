"""Deterministic corruption / augmentation functions with severity 0–2.

Use for: T02 (inject defects), T03 (synthetic hard data — NOT real weather),
T10 (shift simulation), stress tests. Always record (transform, severity, seed,
parent_image) in a manifest so provenance is traceable.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter

# severity -> parameter tables (documented so groups can cite them in reports)
BLUR_RADIUS = {0: 0.0, 1: 2.0, 2: 5.0}
DARK_GAMMA = {0: 1.0, 1: 2.2, 2: 3.5}
DARK_GAIN = {0: 1.0, 1: 0.45, 2: 0.2}
GLARE_STRENGTH = {0: 0.0, 1: 0.6, 2: 1.0}
JPEG_QUALITY = {0: 95, 1: 15, 2: 5}
FOG_DENSITY = {0: 0.0, 1: 0.45, 2: 0.75}
NOISE_SIGMA = {0: 0.0, 1: 12.0, 2: 30.0}


def _pil(img: np.ndarray) -> Image.Image:
    return Image.fromarray(img.astype(np.uint8))


def blur(img: np.ndarray, severity: int = 1, **_) -> np.ndarray:
    r = BLUR_RADIUS[severity]
    return img.copy() if r == 0 else np.asarray(_pil(img).filter(ImageFilter.GaussianBlur(r)))


def motion_blur(img: np.ndarray, severity: int = 1, **_) -> np.ndarray:
    k = {0: 1, 1: 9, 2: 21}[severity]
    if k == 1:
        return img.copy()
    out = np.zeros_like(img, dtype=np.float32)
    for s in range(k):
        out += np.roll(img.astype(np.float32), s - k // 2, axis=1)
    return (out / k).clip(0, 255).astype(np.uint8)


def dark(img: np.ndarray, severity: int = 1, **_) -> np.ndarray:
    x = img.astype(np.float32) / 255.0
    x = (x ** DARK_GAMMA[severity]) * DARK_GAIN[severity]
    return (x * 255).clip(0, 255).astype(np.uint8)


def glare(img: np.ndarray, severity: int = 1, rng: np.random.Generator | None = None, center=None, radius_frac: float = 0.35, **_) -> np.ndarray:
    s = GLARE_STRENGTH[severity]
    if s == 0:
        return img.copy()
    rng = rng or np.random.default_rng(0)
    H, W = img.shape[:2]
    cx, cy = center if center is not None else (rng.uniform(0.2, 0.8) * W, rng.uniform(0.1, 0.5) * H)
    yy, xx = np.mgrid[0:H, 0:W]
    r = radius_frac * max(H, W)
    mask = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (r / 2) ** 2)))
    out = img.astype(np.float32) + (s * 255.0 * mask)[..., None]
    return out.clip(0, 255).astype(np.uint8)


def jpeg(img: np.ndarray, severity: int = 1, **_) -> np.ndarray:
    buf = io.BytesIO()
    _pil(img).save(buf, format="JPEG", quality=JPEG_QUALITY[severity])
    return np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))


def fog(img: np.ndarray, severity: int = 1, **_) -> np.ndarray:
    d = FOG_DENSITY[severity]
    H = img.shape[0]
    grad = np.linspace(1.0, 0.6, H)[:, None, None]  # denser at top/horizon
    a = d * grad
    out = img.astype(np.float32) * (1 - a) + 220.0 * a
    return out.clip(0, 255).astype(np.uint8)


def noise(img: np.ndarray, severity: int = 1, rng: np.random.Generator | None = None, **_) -> np.ndarray:
    rng = rng or np.random.default_rng(0)
    s = NOISE_SIGMA[severity]
    return (img.astype(np.float32) + rng.normal(0, s, img.shape)).clip(0, 255).astype(np.uint8)


def night(img: np.ndarray, severity: int = 1, rng: np.random.Generator | None = None, **_) -> np.ndarray:
    """Dark + blue tint + sensor noise (simulation only — not a real night image)."""
    x = dark(img, severity).astype(np.float32)
    x[..., 2] *= 1.15
    x[..., 0] *= 0.9
    return noise(x.clip(0, 255).astype(np.uint8), min(severity, 1), rng=rng)


def color_tint(img: np.ndarray, severity: int = 1, **_) -> np.ndarray:
    gain = {0: (1, 1, 1), 1: (1.15, 1.0, 0.85), 2: (1.35, 1.0, 0.7)}[severity]
    return (img.astype(np.float32) * np.array(gain)).clip(0, 255).astype(np.uint8)


def rain(img: np.ndarray, severity: int = 1, rng: np.random.Generator | None = None, **_) -> np.ndarray:
    if severity == 0:
        return img.copy()
    rng = rng or np.random.default_rng(0)
    H, W = img.shape[:2]
    out = img.astype(np.float32) * 0.85
    n = {1: H * W // 600, 2: H * W // 200}[severity]
    xs, ys = rng.integers(0, W, n), rng.integers(0, H, n)
    length = {1: 6, 2: 12}[severity]
    for x, y in zip(xs, ys):
        y1 = min(H, y + length)
        x1 = min(W - 1, x + 1)
        out[y:y1, x:x1 + 1] = out[y:y1, x:x1 + 1] * 0.4 + 200 * 0.6
    return blur(out.clip(0, 255).astype(np.uint8), 0 if severity == 1 else 1)


TRANSFORMS = {
    "blur": blur,
    "motion_blur": motion_blur,
    "dark": dark,
    "glare": glare,
    "jpeg": jpeg,
    "fog": fog,
    "noise": noise,
    "night": night,
    "color_tint": color_tint,
    "rain": rain,
}


def apply(name: str, img: np.ndarray, severity: int, seed: int = 42, **kw) -> np.ndarray:
    if name not in TRANSFORMS:
        raise KeyError(f"unknown transform {name!r}; available: {sorted(TRANSFORMS)}")
    if severity not in (0, 1, 2):
        raise ValueError("severity must be 0, 1 or 2")
    return TRANSFORMS[name](img, severity=severity, rng=np.random.default_rng(seed), **kw)
