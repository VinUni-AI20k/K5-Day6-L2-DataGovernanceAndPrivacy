"""Machine-readable metrics files + Baseline-vs-PoC table (Bảng 1 of the report).

Numbers in reports/ must come from scripts, never typed by hand.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .io import git_sha, read_json, write_json
from .timer import machine_info


@dataclass
class MetricResult:
    name: str                       # e.g. "Defect Recall@B"
    value: float | None
    direction: str                  # "higher" or "lower" is better
    unit: str = ""                  # e.g. "fraction of GT defects", "ms", "count"
    numerator: float | None = None
    denominator: float | None = None
    n: int | None = None            # number of evaluation units
    slice: str = "all"
    primary: bool = False
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.direction not in {"higher", "lower"}:
            raise ValueError("direction must be 'higher' or 'lower'")


def safe_div(num: float, den: float) -> float | None:
    return None if not den else num / den


def write_metrics(
    path: str | Path,
    run_name: str,
    track: str,
    metrics: list[MetricResult],
    seed: int | None = None,
    config: dict | None = None,
    runtime_seconds: float | None = None,
    n_items: int | None = None,
    extra: dict | None = None,
) -> Path:
    payload = {
        "run_name": run_name,
        "track": track,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "seed": seed,
        "n_items": n_items,
        "runtime_seconds": runtime_seconds,
        "runtime_per_100_items_s": (round(100 * runtime_seconds / n_items, 4) if runtime_seconds and n_items else None),
        "machine": machine_info(),
        "config": config or {},
        "metrics": [asdict(m) for m in metrics],
        "extra": extra or {},
    }
    return write_json(path, payload)


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def compare_runs(baseline_path: str | Path, poc_path: str | Path) -> str:
    """Markdown table: metric | baseline | PoC | Δ abs | Δ rel | direction | N."""
    b = read_json(baseline_path)
    p = read_json(poc_path)
    key = lambda m: (m["name"], m.get("slice", "all"))  # noqa: E731
    bmap = {key(m): m for m in b["metrics"]}
    lines = [
        f"Baseline: `{b.get('run_name')}` (git {b.get('git_sha')}, seed {b.get('seed')}) · "
        f"PoC: `{p.get('run_name')}` (git {p.get('git_sha')}, seed {p.get('seed')})",
        "",
        "| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in p["metrics"]:
        bm = bmap.get(key(m))
        bv = bm["value"] if bm else None
        pv = m["value"]
        d_abs = (pv - bv) if (bv is not None and pv is not None) else None
        if d_abs is None:
            d_rel = "n/a"
        elif bv == 0:
            d_rel = "baseline=0"
        else:
            d_rel = f"{100 * d_abs / abs(bv):+.1f}%"
        name = ("**" + m["name"] + "**") if m.get("primary") else m["name"]
        unit = f" ({m['unit']})" if m.get("unit") else ""
        lines.append(
            f"| {name}{unit} | {m.get('slice', 'all')} | {_fmt(bv)} | {_fmt(pv)} | "
            f"{_fmt(d_abs) if d_abs is not None else 'n/a'} | {d_rel} | {m['direction']} | {m.get('n')} |"
        )
    rt_b, rt_p = b.get("runtime_per_100_items_s"), p.get("runtime_per_100_items_s")
    lines.append(f"| Runtime / 100 items (s) | all | {_fmt(rt_b)} | {_fmt(rt_p)} | | | lower | |")
    return "\n".join(lines)
