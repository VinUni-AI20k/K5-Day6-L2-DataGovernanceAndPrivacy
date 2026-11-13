"""Fixture integrity: manifests match files, GT kept separate, no real-PII markers."""
from pathlib import Path

import pandas as pd
import pytest

from src.common.manifest import MANIFEST_COLUMNS, verify_manifest
from src.metrics.tracks import TRACKS

FX = Path("fixtures")


@pytest.mark.parametrize("track", sorted(TRACKS))
def test_manifest_hashes_match(track):
    d = FX / TRACKS[track].fixture_dir
    m = d / "manifest.csv"
    assert m.exists(), f"{m} missing"
    assert list(pd.read_csv(m, nrows=0).columns) == MANIFEST_COLUMNS
    assert verify_manifest(m) == []
    assert verify_manifest(d / "gt" / "manifest.csv") == []
    assert not pd.read_csv(m).path.str.startswith("gt/").any(), "GT must not be listed in the input manifest"


@pytest.mark.parametrize("track", sorted(TRACKS))
def test_ground_truth_lives_in_gt_folder(track):
    spec = TRACKS[track]
    assert spec.default_gt.startswith("gt/")
    assert (FX / spec.fixture_dir / spec.default_gt).exists()


def test_synthetic_sources_only():
    for m in list(FX.glob("*/manifest.csv")) + list(FX.glob("*/gt/manifest.csv")):
        df = pd.read_csv(m)
        assert df.source.str.startswith("synthetic").all(), m
