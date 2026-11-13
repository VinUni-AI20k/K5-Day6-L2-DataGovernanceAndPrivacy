import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import pytest

# Ground truth and the fixture generator live in the private instructor repo, not here.
# Tests that need them run only after the instructor overlay is installed.
# Every task fixture ships a gt/ directory in the overlay. A partial copy must fail loudly
# instead of silently skipping the evaluator tests for the missing tasks.
_TASK_DIRS = sorted(p for p in (ROOT / "fixtures").glob("t[0-9][0-9]_*") if p.is_dir())
_MISSING_GT = [p.name for p in _TASK_DIRS if not (p / "gt").is_dir()]
HAS_GT = bool(_TASK_DIRS) and not _MISSING_GT
PARTIAL_GT = bool(_MISSING_GT) and len(_MISSING_GT) < len(_TASK_DIRS)


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_gt: needs fixtures/*/gt/ from the instructor overlay")


def pytest_collection_modifyitems(config, items):
    if PARTIAL_GT:
        raise pytest.UsageError(
            "instructor overlay is incomplete; gt/ missing for: " + ", ".join(_MISSING_GT)
        )
    if HAS_GT:
        return
    skip = pytest.mark.skip(reason="ground truth not distributed (instructor overlay not installed)")
    for item in items:
        if "requires_gt" in item.keywords:
            item.add_marker(skip)
