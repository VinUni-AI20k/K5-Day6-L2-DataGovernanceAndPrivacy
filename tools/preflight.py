"""5-minute preflight before the lab (run with Wi-Fi OFF).

    python -m tools.preflight

Checks: Python version, packages, fixtures + manifests, offline guard, optional real data,
optional model weights, and that no secret token is tracked by git.
"""
from __future__ import annotations

import importlib
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"
results: list[tuple[str, str]] = []
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".txt", ".csv", ".json", ".toml", ".sh", ".cfg", ".ini", ""}


def check(status: str, msg: str) -> None:
    results.append((status, msg))
    print(f"[{status}] {msg}")


def main() -> int:
    v = sys.version_info
    check(OK if (v.major, v.minor) >= (3, 10) else FAIL, f"Python {v.major}.{v.minor}.{v.micro} (lab target 3.11)")
    for mod in ["numpy", "pandas", "PIL", "cv2", "sklearn", "scipy", "matplotlib", "yaml", "pytest"]:
        try:
            m = importlib.import_module(mod)
            check(OK, f"import {mod} {getattr(m, '__version__', '')}")
        except Exception as e:  # noqa: BLE001
            check(WARN if mod in ("cv2", "matplotlib") else FAIL, f"import {mod}: {e}")

    from src.common.manifest import verify_manifest
    from src.metrics.tracks import TRACKS

    for t, spec in sorted(TRACKS.items()):
        d = ROOT / "fixtures" / spec.fixture_dir
        probs = verify_manifest(d / "manifest.csv") if (d / "manifest.csv").exists() else ["missing manifest"]
        # gt/ ships only with the instructor overlay; verify it when present
        if (d / "gt" / "manifest.csv").exists():
            probs += verify_manifest(d / "gt" / "manifest.csv")
        check(OK if not probs else FAIL, f"{t} fixtures/{spec.fixture_dir} ({'hashes match' if not probs else probs[:2]})")

    from src.common.offline import NetworkBlockedError, disable_offline_guard, enable_offline_guard

    enable_offline_guard()
    try:
        socket.create_connection(("example.com", 80), timeout=1)
        check(FAIL, "offline guard did not block network")
    except NetworkBlockedError:
        check(OK, "offline guard blocks outbound network")
    except OSError:
        check(OK, "offline guard active (network unavailable anyway)")
    finally:
        disable_offline_guard()

    real = ROOT / "data" / "real"
    if real.exists():
        packs = list(real.rglob("manifest.csv"))
        bad = [str(m) for m in packs if verify_manifest(m)]
        check(OK if not bad else FAIL, f"data/real present ({len(packs)} packs)" + (f" - bad: {bad}" if bad else ""))
    else:
        check(WARN, "data/real not present (optional; instructor runs tools/download_real_samples.py before class)")
    models = ROOT / "models_optional"
    check(OK if models.exists() else WARN,
          "models_optional/ present" if models.exists() else "models_optional/ not present (only for pretrained T07/T14 models)")

    try:
        tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).split()
    except Exception:  # noqa: BLE001
        check(WARN, "not a git repo — skipped secret scan")
    else:
        leak = []
        for f in tracked:
            p = ROOT / f
            if p.suffix in TEXT_SUFFIXES and p.is_file() and p.stat().st_size < 2_000_000:
                if re.search(r"hf_[A-Za-z0-9]{30,}", p.read_text(errors="ignore")):
                    leak.append(f)
        check(OK if not leak else FAIL, "no HF token in tracked files" if not leak else f"TOKEN LEAK in {leak}")
        check(OK if ".env" not in tracked else FAIL, ".env not tracked by git")

    n_fail = sum(s == FAIL for s, _ in results)
    print(f"\npreflight: {n_fail} FAIL, {sum(s == WARN for s, _ in results)} WARN")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
