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
    assert not pd.read_csv(m).path.str.startswith("gt/").any(), "GT must not be listed in the input manifest"


@pytest.mark.parametrize("track", sorted(TRACKS))
def test_ground_truth_path_is_in_gt_folder(track):
    assert TRACKS[track].default_gt.startswith("gt/")


@pytest.mark.requires_gt
@pytest.mark.parametrize("track", sorted(TRACKS))
def test_ground_truth_files_match_manifest(track):
    spec = TRACKS[track]
    assert verify_manifest(FX / spec.fixture_dir / "gt" / "manifest.csv") == []
    assert (FX / spec.fixture_dir / spec.default_gt).exists()


def test_synthetic_sources_only():
    for m in list(FX.glob("*/manifest.csv")) + list(FX.glob("*/gt/manifest.csv")):
        df = pd.read_csv(m)
        assert df.source.str.startswith("synthetic").all(), m
