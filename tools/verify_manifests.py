"""Verify every manifest.csv under fixtures/ (and data/real/ if present).

    python -m tools.verify_manifests [paths...]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.manifest import verify_manifest  # noqa: E402


def main(argv: list[str]) -> int:
    roots = [Path(p) for p in argv] or [ROOT / "fixtures", ROOT / "data" / "real"]
    manifests = sorted(m for r in roots if r.exists() for m in ([r] if r.name == "manifest.csv" else r.rglob("manifest.csv")))
    bad = 0
    for m in manifests:
        probs = verify_manifest(m)
        shown = m.relative_to(ROOT) if m.is_relative_to(ROOT) else m
        extra = f"  ({len(probs)} problems, e.g. {probs[0]})" if probs else ""
        print(f"{'OK  ' if not probs else 'FAIL'} {shown}{extra}")
        bad += bool(probs)
    print(f"{len(manifests)} manifests, {bad} failing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
