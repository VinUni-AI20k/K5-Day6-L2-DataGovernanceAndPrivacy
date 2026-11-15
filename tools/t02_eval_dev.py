"""Đo baseline và PoC trên nhãn dev TỰ GÁN (labels/dev_labels.csv). Chỉ dùng split=dev; không đọc gt/.

    python -m tools.t02_eval_dev                       # chạy cả baseline + PoC trong bộ nhớ
    python -m tools.t02_eval_dev --budget 28           # B mặc định = 50% số ảnh dev đã gán nhãn (giống tỷ lệ 20/40 của eval)
In: Recall@B, Precision@B, AP, và false alarm theo light / camera trong top-B.
N nhỏ -> số chỉ mang tính tham khảo (có khoảng Wilson 95%).
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from src.common.io import load_config
from src.t02_baseline import baseline_scores
from src.t02_scoring import score_images


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def average_precision(y_sorted: list[int]) -> float:
    hits, s = 0, 0.0
    for i, y in enumerate(y_sorted, 1):
        if y:
            hits += 1
            s += hits / i
    return s / hits if hits else float("nan")


def evaluate(df: pd.DataFrame, labels: pd.DataFrame, budget: int) -> dict:
    m = df.merge(labels, on="image_id").sort_values("score", ascending=False, kind="mergesort").reset_index(drop=True)
    pos = int(m["is_defect"].sum())
    top = m.head(budget)
    tp = int(top["is_defect"].sum())
    out = {"n": len(m), "n_defect": pos, "B": budget, "recall@B": tp / pos if pos else float("nan"),
           "precision@B": tp / max(1, len(top)), "AP": average_precision(m["is_defect"].tolist()),
           "recall_ci": wilson(tp, pos)}
    clean = m[m["is_defect"] == 0]
    for col in ("light", "camera_id"):
        for g, sub in clean.groupby(col):
            out[f"false_alarm[{col}={g}]"] = f"{int(sub['image_id'].isin(top['image_id']).sum())}/{len(sub)}"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="fixtures/t02_raw_qc")
    ap.add_argument("--labels", default="labels/dev_labels.csv")
    ap.add_argument("--config", default="configs/lab.yaml")
    ap.add_argument("--budget", type=int, default=None)
    a = ap.parse_args(argv)

    lab = pd.read_csv(a.labels)
    lab = lab[lab["is_defect"].astype(str).str.strip().isin(["0", "1"])].copy()
    lab["is_defect"] = lab["is_defect"].astype(int)
    if lab.empty:
        print("[eval-dev] chưa có nhãn: điền labels/dev_labels.csv (is_defect 0/1) rồi chạy lại")
        return 2
    images = pd.read_csv(Path(a.input) / "images.csv")
    images = images[images["split"] == "dev"]                       # KHÔNG bao giờ chấm trên eval
    lab = lab[lab["image_id"].isin(images["image_id"])][["image_id", "is_defect"]]
    budget = a.budget or max(1, round(0.5 * len(lab)))
    cfg = load_config(a.config) if Path(a.config).exists() else {}
    # chuẩn hóa nhóm tính trên TOÀN bộ ảnh dev (giống lúc chạy thật: nhóm dựa vào đặc trưng, không dùng nhãn)
    base = baseline_scores(images, a.input)
    poc = score_images(images, a.input, cfg)
    for name, df in (("baseline", base), ("poc", poc)):
        r = evaluate(df.drop(columns=[c for c in ("is_defect",) if c in df]), lab, budget)
        print(f"\n== {name} (dev, N={r.pop('n')}, defects={r.pop('n_defect')}, B={r.pop('B')}) ==")
        for k, v in r.items():
            print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
