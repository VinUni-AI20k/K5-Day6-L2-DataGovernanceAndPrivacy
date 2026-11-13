"""Procedural *synthetic* driving-scene renderer (no real people, no real plates).

Used only to build fixtures/ so the lab works fully offline and PII-free.
Every object is returned with its exact bbox, so ground truth is known.
"""
from __future__ import annotations

import string
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CLASSES = ["car", "pedestrian", "motorbike", "sign"]
SKIN = [(241, 194, 167), (224, 172, 105), (198, 134, 66), (141, 85, 36), (255, 219, 172)]


@dataclass
class SceneSpec:
    seed: int
    width: int = 320
    height: int = 180
    time: str = "day"            # day | dusk | night
    weather: str = "clear"       # clear | rain | fog (rendered later via corruptions)
    route: str = "urban"         # urban | highway | alley
    n_cars: int = 3
    n_peds: int = 2
    n_bikes: int = 1
    n_signs: int = 1
    faces: int = 0               # synthetic faces (T07)
    plates: bool = False         # draw synthetic plates on cars (T07)
    face_min: int = 10
    face_max: int = 26
    jitter: tuple[int, int] = (0, 0)   # camera shift in px (bursts / near-dups)
    occlude_faces: bool = False


@dataclass
class SceneObject:
    cls: str
    x: float
    y: float
    w: float
    h: float
    attrs: dict = field(default_factory=dict)


def _sky(time: str):
    return {"day": ((120, 170, 230), (200, 225, 250)), "dusk": ((90, 70, 120), (240, 150, 90)), "night": ((5, 8, 25), (25, 30, 55))}[time]


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def synthetic_plate_text(rng: np.random.Generator) -> str:
    """Clearly fake format 'SYN-12A·345' so it cannot be mistaken for a real plate."""
    return f"SYN-{rng.integers(10, 99)}{rng.choice(list(string.ascii_uppercase))}·{rng.integers(100, 999)}"


def render_scene(spec: SceneSpec) -> tuple[np.ndarray, list[SceneObject]]:
    rng = np.random.default_rng(spec.seed)
    W, H = spec.width, spec.height
    jx, jy = spec.jitter
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    horizon = int(H * (0.42 + rng.uniform(-0.04, 0.04))) + jy
    top, bottom = _sky(spec.time)
    for yy in range(max(horizon, 1)):
        t = yy / max(horizon, 1)
        c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        d.line([(0, yy), (W, yy)], fill=c)
    ground = {"day": (95, 120, 80), "dusk": (70, 70, 60), "night": (15, 18, 20)}[spec.time]
    d.rectangle([0, horizon, W, H], fill=ground)
    # buildings
    bx = -int(rng.integers(0, 20)) + jx
    while bx < W:
        bw = int(rng.integers(W // 14, W // 6))
        bh = int(rng.integers(H // 10, H // 3)) if spec.route != "highway" else int(rng.integers(H // 30, H // 12))
        shade = int(rng.integers(60, 160)) if spec.time != "night" else int(rng.integers(15, 40))
        tint = rng.integers(-15, 15, 3)
        col = tuple(int(np.clip(shade + t, 0, 255)) for t in tint)
        d.rectangle([bx, horizon - bh, bx + bw, horizon], fill=col)
        if spec.time == "night":
            for _ in range(int(rng.integers(1, 5))):
                wx = bx + int(rng.integers(2, max(3, bw - 4)))
                wy = horizon - int(rng.integers(3, max(4, bh - 2)))
                d.rectangle([wx, wy, wx + 2, wy + 2], fill=(250, 220, 120))
        bx += bw + int(rng.integers(0, 6))
    # road
    road_w_top = {"urban": 0.18, "highway": 0.3, "alley": 0.08}[spec.route] * W
    road_w_bot = {"urban": 0.9, "highway": 1.2, "alley": 0.5}[spec.route] * W
    cx = W / 2 + jx
    road_col = {"day": (90, 90, 95), "dusk": (70, 68, 72), "night": (30, 30, 35)}[spec.time]
    d.polygon([(cx - road_w_top / 2, horizon), (cx + road_w_top / 2, horizon), (cx + road_w_bot / 2, H), (cx - road_w_bot / 2, H)], fill=road_col)
    lane_col = (230, 230, 210) if spec.time != "night" else (150, 150, 130)
    for k in range(6):
        t0, t1 = k / 6, k / 6 + 0.07
        y0, y1 = horizon + t0 * (H - horizon), horizon + t1 * (H - horizon)
        d.line([(cx, y0), (cx, y1)], fill=lane_col, width=max(1, int(1 + 3 * t0)))

    objs: list[SceneObject] = []

    def depth_scale(y):
        return 0.15 + 0.85 * (y - horizon) / max(1, (H - horizon))

    # cars
    for _ in range(spec.n_cars):
        yb = rng.uniform(horizon + 0.15 * (H - horizon), H - 2)
        s = depth_scale(yb)
        cw, ch = 0.22 * W * s, 0.13 * W * s
        x = cx + rng.uniform(-0.45, 0.45) * road_w_bot * s - cw / 2
        y = yb - ch
        col = tuple(int(v) for v in rng.integers(30, 230, 3))
        d.rounded_rectangle([x, y + ch * 0.3, x + cw, y + ch], radius=max(1, int(ch * 0.15)), fill=col)
        d.rectangle([x + cw * 0.18, y, x + cw * 0.82, y + ch * 0.4], fill=tuple(int(c * 0.8) for c in col))
        d.rectangle([x + cw * 0.24, y + ch * 0.05, x + cw * 0.76, y + ch * 0.32], fill=(150, 190, 210) if spec.time != "night" else (40, 50, 60))
        if spec.time == "night":
            d.ellipse([x + cw * 0.05, y + ch * 0.55, x + cw * 0.2, y + ch * 0.7], fill=(255, 60, 40))
            d.ellipse([x + cw * 0.8, y + ch * 0.55, x + cw * 0.95, y + ch * 0.7], fill=(255, 60, 40))
        attrs = {}
        if spec.plates and cw > 30:
            pw, ph = cw * 0.36, max(6.0, ch * 0.16)
            px, py = x + (cw - pw) / 2, y + ch * 0.68
            d.rectangle([px, py, px + pw, py + ph], fill=(245, 245, 235), outline=(20, 20, 20))
            txt = synthetic_plate_text(rng)
            d.text((px + 1, py), txt, fill=(10, 10, 10), font=_font(max(6, int(ph * 0.8))))
            objs.append(SceneObject("plate", px, py, pw, ph, {"text": txt}))
            attrs["plate"] = txt
        objs.append(SceneObject("car", x, y, cw, ch, attrs))
    # pedestrians
    for _ in range(spec.n_peds):
        yb = rng.uniform(horizon + 0.1 * (H - horizon), H - 2)
        s = depth_scale(yb)
        ph, pw = 0.22 * H * s * 1.6, 0.05 * W * s * 1.4
        side = rng.choice([-1, 1])
        x = cx + side * rng.uniform(0.3, 0.7) * road_w_bot * s - pw / 2
        y = yb - ph
        col = tuple(int(v) for v in rng.integers(20, 200, 3))
        d.rectangle([x, y + ph * 0.25, x + pw, y + ph], fill=col)
        d.ellipse([x + pw * 0.1, y, x + pw * 0.9, y + ph * 0.25], fill=SKIN[int(rng.integers(0, len(SKIN)))])
        objs.append(SceneObject("pedestrian", x, y, pw, ph))
    # motorbikes
    for _ in range(spec.n_bikes):
        yb = rng.uniform(horizon + 0.2 * (H - horizon), H - 2)
        s = depth_scale(yb)
        bw, bh = 0.08 * W * s, 0.16 * H * s * 1.5
        x = cx + rng.uniform(-0.4, 0.4) * road_w_bot * s - bw / 2
        y = yb - bh
        d.ellipse([x, y + bh * 0.7, x + bw * 0.4, y + bh], fill=(20, 20, 20))
        d.ellipse([x + bw * 0.6, y + bh * 0.7, x + bw, y + bh], fill=(20, 20, 20))
        d.rectangle([x + bw * 0.15, y + bh * 0.45, x + bw * 0.85, y + bh * 0.8], fill=tuple(int(v) for v in rng.integers(80, 255, 3)))
        d.rectangle([x + bw * 0.3, y, x + bw * 0.7, y + bh * 0.5], fill=tuple(int(v) for v in rng.integers(20, 120, 3)))
        objs.append(SceneObject("motorbike", x, y, bw, bh))
    # signs
    for _ in range(spec.n_signs):
        s = rng.uniform(0.4, 1.0)
        sx = rng.choice([rng.uniform(0.02, 0.2), rng.uniform(0.8, 0.95)]) * W + jx
        r = 0.035 * W * s
        top_y = horizon - rng.uniform(0.05, 0.25) * H
        d.line([(sx, top_y + r), (sx, horizon + 0.15 * H)], fill=(120, 120, 120), width=max(1, int(r / 4)))
        d.ellipse([sx - r, top_y - r, sx + r, top_y + r], fill=(220, 30, 30), outline=(250, 250, 250))
        objs.append(SceneObject("sign", sx - r, top_y - r, 2 * r, 2 * r))
    # synthetic faces (cartoon ovals — no real identity)
    for _ in range(spec.faces):
        fs = float(rng.uniform(spec.face_min, spec.face_max))
        fx = float(rng.uniform(2, W - fs - 2))
        fy = float(rng.uniform(horizon - 0.25 * H, H - fs - 2))
        skin = SKIN[int(rng.integers(0, len(SKIN)))]
        if spec.time == "night":
            skin = tuple(int(c * 0.35) for c in skin)
        d.ellipse([fx, fy, fx + fs * 0.8, fy + fs], fill=skin, outline=tuple(int(c * 0.7) for c in skin))
        ex = max(1, fs * 0.08)
        d.ellipse([fx + fs * 0.2, fy + fs * 0.35, fx + fs * 0.2 + ex, fy + fs * 0.35 + ex], fill=(20, 20, 20))
        d.ellipse([fx + fs * 0.5, fy + fs * 0.35, fx + fs * 0.5 + ex, fy + fs * 0.35 + ex], fill=(20, 20, 20))
        d.line([(fx + fs * 0.25, fy + fs * 0.72), (fx + fs * 0.55, fy + fs * 0.72)], fill=(120, 40, 40), width=1)
        occluded = False
        if spec.occlude_faces and rng.random() < 0.5:
            d.rectangle([fx - 1, fy + fs * 0.45, fx + fs * 0.85, fy + fs * 1.05], fill=tuple(int(v) for v in rng.integers(40, 120, 3)))
            occluded = True
        objs.append(SceneObject("face", fx, fy, fs * 0.8, fs, {"occluded": occluded}))
    arr = np.asarray(img)
    return arr, objs
