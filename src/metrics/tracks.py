"""One evaluator per track = the shared *metric contract*.

Each evaluator reads ground truth (fixtures/<track>/gt/...) and the group's
prediction file (out/<file>.csv), and returns MetricResult rows + a slice table.
Prediction schemas are documented in docs/tracks/TXX.md and in TRACKS below.

Do NOT change these definitions to make your numbers look better. If you think a
metric is wrong, argue it in the report and add an *extra* metric in your code.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd
import yaml

from ..common.report import MetricResult, safe_div
from . import detection as DE

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@dataclass
class EvalOutput:
    metrics: list[MetricResult]
    slices: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: list[str] = field(default_factory=list)


@dataclass
class TrackSpec:
    track: str
    title: str
    fixture_dir: str
    default_gt: str            # relative to fixture dir
    pred_file: str             # default prediction file name inside --output
    pred_columns: list[str]    # required columns
    evaluator: Callable[[Path, Path, dict], EvalOutput]
    params: dict = field(default_factory=dict)


def _m(name, value, direction, unit="", num=None, den=None, n=None, primary=False, slice="all", notes="") -> MetricResult:
    if isinstance(value, float) and math.isnan(value):
        value = None
    return MetricResult(name=name, value=None if value is None else float(value), direction=direction, unit=unit,
                        numerator=num, denominator=den, n=n, slice=slice, primary=primary, notes=notes)


def _need(df: pd.DataFrame, cols: list[str], what: str) -> None:
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise ValueError(f"{what} is missing required columns {miss}; has {list(df.columns)}")


def _fixture_dir_of(gt_path: Path) -> Path:
    return gt_path.parent.parent if gt_path.parent.name == "gt" else gt_path.parent


def _split(df: pd.DataFrame, cfg: dict, default: str) -> pd.DataFrame:
    s = cfg.get("split", default)
    if s in (None, "all") or "split" not in df.columns:
        return df
    return df[df["split"] == s]


# ----------------------------------------------------------------------------- T14
def eval_t14(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    fx = _fixture_dir_of(gt_path)
    tax = set(yaml.safe_load((fx / "taxonomy.yaml").read_text())["classes"].values())
    imgs = pd.read_csv(fx / "images.csv").set_index("image_id")
    gt = _split(pd.read_csv(gt_path), cfg, "eval")
    pred = pd.read_csv(pred_path)
    _need(pred, ["image_id", "class", "x", "y", "w", "h"], "predictions.csv (export)")
    split = cfg.get("split", "eval")
    pool = set(imgs.index) if split in (None, "all") else set(imgs.index[imgs.split == split])
    pred = pred[pred.image_id.isin(pool)].reset_index(drop=True)
    iou = float(cfg.get("iou", 0.5))
    r = DE.detection_prf(gt.reset_index(drop=True), pred, iou, True)
    W = pred.image_id.map(imgs.width)
    H = pred.image_id.map(imgs.height)
    invalid = (~pred["class"].astype(str).isin(tax)) | (pred.w <= 0) | (pred.h <= 0) | (pred.x < 0) | (pred.y < 0) | (pred.x + pred.w > W + 0.5) | (pred.y + pred.h > H + 0.5)
    ms = [
        _m(f"Detection F1@IoU{iou}", r["f1"], "higher", "class-aware greedy match", n=len(gt), primary=True),
        _m("Precision", r["precision"], "higher", "TP/(TP+FP)", r["tp"], r["tp"] + r["fp"]),
        _m("Recall", r["recall"], "higher", "TP/(TP+FN)", r["tp"], r["tp"] + r["fn"]),
        _m("Invalid-label rate", safe_div(int(invalid.sum()), len(pred)), "lower", "exported boxes with unknown class or out-of-bounds / exported boxes", int(invalid.sum()), len(pred)),
    ]
    rows = []
    for c, sub in gt.groupby("class"):
        rr = DE.detection_prf(sub.reset_index(drop=True), pred[pred["class"] == c].reset_index(drop=True), iou, True)
        rows.append({"slice": f"class={c}", "n": len(sub), "recall": rr["recall"], "precision": rr["precision"], "f1": rr["f1"]})
    small = gt[(gt.w * gt.h) < 150]
    if len(small):
        rr = DE.detection_prf(small.reset_index(drop=True), pred, iou, True)
        rows.append({"slice": "small_objects(<150px²)", "n": len(small), "recall": rr["recall"], "precision": None, "f1": None})
    return EvalOutput(ms, pd.DataFrame(rows))


TRACKS: dict[str, TrackSpec] = {
    "t14": TrackSpec("t14", "Auto-Annotation + Human QC Exporter", "t14_auto_annotation", "gt/gt_boxes.csv", "predictions.csv", ["image_id", "class", "x", "y", "w", "h"], eval_t14, {"iou": 0.5, "split": "eval"}),
}


def get_track(track: str) -> TrackSpec:
    t = track.lower()[:3]
    if t not in TRACKS:
        raise KeyError(f"unknown track {track!r}; choose one of {sorted(TRACKS)}")
    return TRACKS[t]


def default_gt_path(track: str) -> Path:
    spec = get_track(track)
    return FIXTURES / spec.fixture_dir / spec.default_gt


def infer_track_from_path(path: str | Path | None) -> str | None:
    """'fixtures/t14_auto_annotation/...' -> 't14' (lets the contract commands omit --track)."""
    if not path:
        return None
    parts = Path(path).resolve().parts
    for spec in TRACKS.values():
        if spec.fixture_dir in parts:
            return spec.track
    return None
