import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import pytest

# Ground truth and the fixture generator live in the private instructor repo, not here.
# Tests that need them run only after the instructor overlay is installed.
HAS_GT = (ROOT / "fixtures" / "t02_raw_qc" / "gt").is_dir()


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_gt: needs fixtures/*/gt/ from the instructor overlay")


def pytest_collection_modifyitems(config, items):
    if HAS_GT:
        return
    skip = pytest.mark.skip(reason="ground truth not distributed (instructor overlay not installed)")
    for item in items:
        if "requires_gt" in item.keywords:
            item.add_marker(skip)
