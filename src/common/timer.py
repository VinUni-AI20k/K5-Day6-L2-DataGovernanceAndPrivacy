"""Timing helper — the rubric asks for ms/item or runtime per 100 items on CPU."""
from __future__ import annotations

import platform
import time
from contextlib import contextmanager


@contextmanager
def timed(stats: dict, key: str = "seconds"):
    t0 = time.perf_counter()
    try:
        yield stats
    finally:
        stats[key] = round(time.perf_counter() - t0, 4)


def per_item_ms(seconds: float, n_items: int) -> float | None:
    return round(1000.0 * seconds / n_items, 3) if n_items else None


def machine_info() -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
    }
