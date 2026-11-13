"""One-command PoC runner (lab contract).

    python -m src.main --input fixtures/t02_raw_qc --config configs/lab.yaml --output out/
    python -m src.main --offline --seed 42                       # values from configs/lab.yaml

Exit codes: 0 OK · 2 bad/missing input · 3 pipeline not implemented · 4 network blocked (--offline)
            5 pipeline tried to read ground truth
The heavy lifting lives in your pipeline module (default: src/pipeline.py).
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

from .common.context import RunContext
from .common.gt_guard import GroundTruthAccessError, disable_gt_guard, enable_gt_guard
from .common.io import config_hash, git_sha, resolve_config, set_seed, write_json
from .common.offline import NetworkBlockedError, enable_offline_guard
from .common.review import AuditLog
from .common.timer import machine_info
from .metrics.tracks import get_track

DEFAULT_CONFIG = "configs/lab.yaml"


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Day06 Data Lab — one-command PoC")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="YAML config (default configs/lab.yaml)")
    ap.add_argument("--track", help="t01..t14 (overrides config)")
    ap.add_argument("--input", help="input folder (overrides config)")
    ap.add_argument("--output", help="output folder (overrides config)")
    ap.add_argument("--seed", type=int, help="random seed (overrides config; default 42)")
    ap.add_argument("--run-name", default=None, help="e.g. baseline / poc")
    ap.add_argument("--pipeline", default=None, help="python module with run(ctx) (default src.pipeline)")
    ap.add_argument("--offline", action="store_true", help="block all network access")
    ap.add_argument("--allow-gt-read", action="store_true", help="disable ground-truth guard (justify in report!)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    if not Path(a.config).exists():
        print(f"[main] config not found: {a.config}", file=sys.stderr)
        return 2
    cfg = resolve_config(a.config, a.track, {"input": a.input, "output": a.output, "seed": a.seed,
                                             "run_name": a.run_name, "pipeline": a.pipeline})
    offline = a.offline or bool(cfg.get("offline", False))
    if offline:
        enable_offline_guard()
    track = cfg.get("track")
    if not track:
        print("[main] no track set: pass --track tXX or set `track:` in the config", file=sys.stderr)
        return 2
    spec = get_track(track)
    seed = int(cfg.get("seed", 42))
    in_dir = Path(cfg.get("input") or f"fixtures/{spec.fixture_dir}")
    out_dir = Path(cfg.get("output") or "out")
    if not in_dir.exists():
        print(f"[main] input folder not found: {in_dir}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = set_seed(seed)
    ctx = RunContext(track=spec.track, input_dir=in_dir, output_dir=out_dir, config=cfg, seed=seed, rng=rng,
                     run_name=cfg.get("run_name") or "poc", offline=offline, audit=AuditLog(out_dir / "audit_log.jsonl"))
    module_name = cfg.get("pipeline") or "src.pipeline"
    print(f"[main] track={spec.track} ({spec.title}) input={in_dir} output={out_dir} seed={seed} offline={offline} pipeline={module_name}")
    if not a.allow_gt_read:
        enable_gt_guard()
    t0 = time.perf_counter()
    status = 0
    try:
        mod = importlib.import_module(module_name)
        mod.run(ctx)
    except NotImplementedError as e:
        print(f"[main] NOT IMPLEMENTED: {e}", file=sys.stderr)
        status = 3
    except NetworkBlockedError as e:
        print(f"[main] {e}", file=sys.stderr)
        status = 4
    except GroundTruthAccessError as e:
        print(f"[main] {e}", file=sys.stderr)
        status = 5
    except (FileNotFoundError, ValueError, KeyError) as e:
        traceback.print_exc()
        print(f"[main] input/data error: {e}", file=sys.stderr)
        status = 2
    finally:
        disable_gt_guard()
    seconds = round(time.perf_counter() - t0, 4)
    pred_path = out_dir / spec.pred_file
    check = {"pred_file": str(pred_path), "exists": pred_path.exists()}
    if status == 0:
        if not pred_path.exists():
            print(f"[main] pipeline finished but {pred_path} was not written", file=sys.stderr)
            status = 2
        else:
            cols = list(pd.read_csv(pred_path, nrows=0).columns)
            missing = [c for c in spec.pred_columns if c not in cols]
            check["missing_columns"] = missing
            if missing:
                print(f"[main] {pred_path} missing required columns {missing}", file=sys.stderr)
                status = 2
    write_json(out_dir / "run_info.json", {
        "track": spec.track, "run_name": ctx.run_name, "status": status, "seed": seed, "offline": offline,
        "input": str(in_dir), "output": str(out_dir), "pipeline": module_name, "config_hash": config_hash(cfg),
        "git_sha": git_sha(), "runtime_seconds": seconds, "stats": ctx.stats, "machine": machine_info(), "output_check": check,
    })
    print(f"[main] status={status} runtime={seconds}s -> {out_dir/'run_info.json'}")
    return status


if __name__ == "__main__":
    sys.exit(main())
