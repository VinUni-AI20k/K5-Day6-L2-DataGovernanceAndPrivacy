"""Small I/O helpers: config, seeds, hashing, JSON/CSV, git metadata."""
from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def load_config(path: str | os.PathLike | None, overrides: dict | None = None) -> dict:
    """Load a YAML config. If it has `track_config: <path>`, that file is merged first."""
    cfg: dict[str, Any] = {}
    if path:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        base = cfg.get("track_config")
        if base:
            base_path = Path(path).parent / base if not Path(base).is_absolute() else Path(base)
            with open(base_path, "r", encoding="utf-8") as f:
                base_cfg = yaml.safe_load(f) or {}
            cfg = deep_merge(base_cfg, cfg)
    if overrides:
        cfg = deep_merge(cfg, {k: v for k, v in overrides.items() if v is not None})
    return cfg


def deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def set_seed(seed: int = 42) -> np.random.Generator:
    """Seed python/numpy and return a numpy Generator. Always log the seed you used."""
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    return np.random.default_rng(seed)


def sha256_file(path: str | os.PathLike, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_hash(cfg: dict) -> str:
    return sha256_text(json.dumps(cfg, sort_keys=True, default=str))[:12]


def read_json(path: str | os.PathLike) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | os.PathLike, obj: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=_json_default)
    return p


def _json_default(o: Any):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    return str(o)


def git_sha(short: bool = True) -> str | None:
    try:
        args = ["git", "rev-parse", "--short" if short else "--verify", "HEAD"]
        return subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def ensure_dir(path: str | os.PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


GROUP_KEYS = ("group_id", "owner", "seed", "offline", "strict_provenance", "output")


def resolve_config(config_path: str | os.PathLike, track: str | None = None, overrides: dict | None = None) -> dict:
    """Load the group config; if `track` differs from the config's track, switch to
    configs/tracks/<track>.yaml but keep group-level keys (owner, seed, offline, ...)."""
    base = load_config(config_path) if config_path and Path(config_path).exists() else {}
    if track and track[:3].lower() != str(base.get("track", ""))[:3].lower():
        tpath = Path(config_path).parent / "tracks" / f"{track[:3].lower()}.yaml"
        tcfg = load_config(tpath) if tpath.exists() else {"track": track[:3].lower()}
        base = deep_merge(tcfg, {k: base[k] for k in GROUP_KEYS if k in base})
    return deep_merge(base, {k: v for k, v in (overrides or {}).items() if v is not None})
