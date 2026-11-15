"""Bảng 1 · Baseline vs PoC — generated, never typed by hand.

    python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json [--out reports/table1_baseline_vs_poc.md]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .common.report import compare_runs


def _print_safe(text: str) -> None:
    """Windows consoles default to cp1252; avoid UnicodeEncodeError on Δ/·/→."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # non-TextIO stdout
        pass
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("poc")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    md = compare_runs(a.baseline, a.poc)
    _print_safe(md)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(md + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
