"""Bộ test TỰ SINH có nhãn chắc chắn để kiểm tra logic T02 (không dùng fixtures, không đụng gt/).

Mỗi ảnh = một cảnh sạch (tools/synth/scene.py, seed riêng, KHÁC fixtures) + tuỳ chọn một lỗi (corruptions.py).
  - 3 mức sáng: day / dusk / night (ảnh đêm sạch là hard negative)
  - cam_A nét, cam_B mềm hơn (hard negative: mềm nhưng KHÔNG lỗi)
  - ~40% ảnh có lỗi: blur | dark | glare | compression, mức 1 hoặc 2
Nhãn ghi ở labels_selftest.csv (không nằm trong gt/ nên không bị GT guard chặn).

    python -m tools.t02_selftest                    # 5 seed x 120 ảnh, in baseline vs PoC
    python -m tools.t02_selftest --seeds 10 --n 160
Giới hạn: ảnh synthetic dễ hơn ảnh thật; chỉ chứng minh LOGIC đúng, không chứng minh tổng quát hoá.
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter

from src.common import corruptions
from src.common.io import load_config
from src.t02_baseline import baseline_scores
from src.t02_scoring import score_images
from tools.synth.scene import SceneSpec, render_scene
from tools.t02_eval_dev import wilson

DEFECTS = ["blur", "dark", "glare", "compression"]
_TO_CORRUPTION = {"blur": "blur", "dark": "dark", "glare": "glare", "compression": "jpeg"}


def make_set(out_dir: str | Path, seed: int, n: int = 120, p_defect: float = 0.4) -> pd.DataFrame:
    out = Path(out_dir)
    (out / "images").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    lights = rng.permutation(["day"] * (n // 2) + ["dusk"] * (n // 4) + ["night"] * (n - n // 2 - n // 4))
    cams = rng.permutation(["cam_A"] * (2 * n // 3) + ["cam_B"] * (n - 2 * n // 3))
    rows = []
    for i in range(n):
        iid = f"st{seed}_{i:03d}"
        spec = SceneSpec(seed=1_000_000 + seed * 10_000 + i, time=str(lights[i]),
                         route=str(rng.choice(["urban", "highway", "alley"])),
                         n_cars=int(rng.integers(1, 5)), n_peds=int(rng.integers(0, 3)))
        img, _ = render_scene(spec)
        if cams[i] == "cam_B":                                     # quang học mềm hơn, vẫn là ảnh TỐT
            img = np.asarray(Image.fromarray(img).filter(ImageFilter.GaussianBlur(float(rng.uniform(0.7, 1.1)))))
        is_def = bool(rng.random() < p_defect)
        dtype, sev = "none", 0
        if is_def:
            dtype, sev = str(rng.choice(DEFECTS)), int(rng.choice([1, 2]))
            img = corruptions.apply(_TO_CORRUPTION[dtype], img, severity=sev, seed=seed * 1000 + i)
        Image.fromarray(img).save(out / "images" / f"{iid}.jpg", quality=90)
        rows.append({"image_id": iid, "path": f"images/{iid}.jpg", "camera_id": cams[i], "light": lights[i],
                     "split": "selftest", "is_defect": int(is_def), "defect_type": dtype, "severity": sev})
    df = pd.DataFrame(rows)
    df[["image_id", "path", "camera_id", "light", "split"]].to_csv(out / "images.csv", index=False)
    df[["image_id", "is_defect", "defect_type", "severity"]].to_csv(out / "labels_selftest.csv", index=False)
    return df


def _avg_precision(y: list[int]) -> float:
    hits, s = 0, 0.0
    for k, v in enumerate(y, 1):
        if v:
            hits += 1
            s += hits / k
    return s / hits if hits else float("nan")


def evaluate(scored: pd.DataFrame, labels: pd.DataFrame, budget: int) -> dict:
    m = scored[["image_id", "score"] + [c for c in ("pred_defect_type",) if c in scored]].merge(labels, on="image_id")
    m = m.sort_values("score", ascending=False, kind="mergesort").reset_index(drop=True)
    pos = int(m["is_defect"].sum())
    top = m.head(budget)
    tp = int(top["is_defect"].sum())
    r = {"recall@B": tp / pos, "precision@B": tp / budget, "AP": _avg_precision(m["is_defect"].tolist()),
         "R-precision": int(m.head(pos)["is_defect"].sum()) / pos}
    for t in DEFECTS:
        sub = m[m["defect_type"] == t]
        r[f"recall[{t}]"] = sub["image_id"].isin(top["image_id"]).mean() if len(sub) else np.nan
    for s in (1, 2):
        sub = m[m["severity"] == s]
        r[f"recall[sev{s}]"] = sub["image_id"].isin(top["image_id"]).mean() if len(sub) else np.nan
    clean = m[m["is_defect"] == 0]
    for col, name in (("light", "light"), ("camera_id", "camera")):
        for g, sub in clean.merge(scored[["image_id", col]], on="image_id").groupby(col):
            r[f"false_alarm[{name}={g}]"] = sub["image_id"].isin(top["image_id"]).mean()
    if "pred_defect_type" in m:
        d = m[m["is_defect"] == 1]
        r["type_accuracy"] = float((d["pred_defect_type"] == d["defect_type"]).mean())
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed-start", type=int, default=1, help="seed đầu (seed 1-8 đã dùng để chọn percentile; dùng >=101 để kiểm chứng)")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--budget-frac", type=float, default=0.5, help="B = frac * N (eval thật: 20/40 = 0.5)")
    ap.add_argument("--config", default="configs/lab.yaml")
    ap.add_argument("--keep", default=None, help="giữ ảnh sinh ra ở thư mục này (seed đầu tiên) để xem bằng mắt")
    a = ap.parse_args(argv)
    cfg = load_config(a.config) if Path(a.config).exists() else {}
    B = max(1, round(a.budget_frac * a.n))
    res = {"baseline": [], "poc": []}
    for seed in range(a.seed_start, a.seed_start + a.seeds):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(a.keep) if (a.keep and seed == a.seed_start) else Path(tmp)
            df = make_set(d, seed, a.n)
            images = pd.read_csv(d / "images.csv")
            labels = df[["image_id", "is_defect", "defect_type", "severity"]]
            res["baseline"].append(evaluate(baseline_scores(images, d), labels, B))
            res["poc"].append(evaluate(score_images(images, d, cfg), labels, B))
    print(f"self-test: {a.seeds} seed x N={a.n}, B={B}, ~{int(40)}% ảnh lỗi\n")
    keys = list(res["poc"][0])
    print(f"{'metric':32s} {'baseline':>16s} {'poc':>16s}")
    for k in keys:
        cells = []
        for name in ("baseline", "poc"):
            v = np.array([r.get(k, np.nan) for r in res[name]], dtype=float)
            cells.append("-" if np.isnan(v).all() else f"{np.nanmean(v):.3f} ±{np.nanstd(v):.3f}")
        print(f"{k:32s} {cells[0]:>16s} {cells[1]:>16s}")
    wins = sum(p["recall@B"] > b["recall@B"] for p, b in zip(res["poc"], res["baseline"]))
    ties = sum(p["recall@B"] == b["recall@B"] for p, b in zip(res["poc"], res["baseline"]))
    print(f"\nPoC > baseline (recall@B) ở {wins}/{a.seeds} seed, hòa {ties}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
