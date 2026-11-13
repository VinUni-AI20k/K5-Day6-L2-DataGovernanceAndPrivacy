"""RunContext passed to every pipeline stage."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .review import AuditLog


@dataclass
class RunContext:
    track: str
    input_dir: Path
    output_dir: Path
    config: dict
    seed: int
    rng: np.random.Generator
    run_name: str = "poc"
    offline: bool = True
    audit: AuditLog | None = None
    stats: dict = field(default_factory=dict)   # put n_items, timings, etc. here

    def out(self, name: str) -> Path:
        p = self.output_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def param(self, key: str, default=None):
        """Track params live under config['params'] (see configs/tracks/*.yaml)."""
        return (self.config.get("params") or {}).get(key, default)
