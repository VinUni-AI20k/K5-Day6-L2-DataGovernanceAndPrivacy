"""Data & Provenance guards (owner: Thành viên 2).

Covers the success path (hashes and split are sound today) and the failure mode
that actually bit us: a CRLF checkout silently changes a hashed text file, so
`src.main` aborts with a provenance error on a teammate's Windows machine.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from src.common.manifest import verify_manifest

ROOT = Path(__file__).resolve().parents[1]
TRACK_DIR = ROOT / "fixtures" / "t02_raw_qc"


def test_manifest_hashes_match():
    """Success path: fixtures on disk match the manifest they shipped with."""
    assert verify_manifest(TRACK_DIR / "manifest.csv") == []


def test_crlf_checkout_would_break_a_hashed_text_file():
    """Failure mode: LF -> CRLF changes the bytes, so the sha256 no longer matches.

    This is why `.gitattributes` marks `fixtures/**` as `-text`. The test documents
    the hazard; `test_gitattributes_protects_fixtures` checks the guard is in place.
    """
    man = pd.read_csv(TRACK_DIR / "manifest.csv")
    row = man[man.path == "images.csv"].iloc[0]
    raw = (TRACK_DIR / "images.csv").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row.sha256

    crlf = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    assert crlf != raw, "fixture already has CRLF endings — this test needs an LF file"
    assert hashlib.sha256(crlf).hexdigest() != row.sha256


def test_gitattributes_protects_fixtures():
    """The guard: git must not apply eol conversion inside fixtures/."""
    ga = ROOT / ".gitattributes"
    assert ga.exists(), "missing .gitattributes — a CRLF checkout will break provenance"
    try:
        out = subprocess.run(["git", "check-attr", "text", "--", "fixtures/t02_raw_qc/images.csv"],
                             cwd=ROOT, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git not available")
    if out.returncode != 0:
        pytest.skip("not a git work tree")
    assert "text: unset" in out.stdout, f"eol conversion not disabled for fixtures: {out.stdout.strip()}"


def test_split_is_scene_disjoint():
    """No original scene may appear in both dev and eval (near-duplicate leakage)."""
    df = pd.read_csv(TRACK_DIR / "images.csv")
    scene = df.image_id.str.rsplit("_", n=1).str[0]
    per_scene = df.assign(scene=scene).groupby("scene")["split"].nunique()
    leaked = sorted(per_scene[per_scene > 1].index)
    assert leaked == [], f"scenes in both splits: {leaked}"


def test_every_eval_stratum_is_represented_in_dev():
    """Known gap, asserted so it cannot change silently under us.

    cam_A/night appears only at eval, so a per-(camera, light) threshold cannot be
    calibrated for it. The pipeline must fall back to a coarser grouping; see
    reports/data_audit_t02.md.
    """
    df = pd.read_csv(TRACK_DIR / "images.csv")
    cross = pd.crosstab([df.camera_id, df.light], df.split)
    uncalibratable = sorted(f"{a}/{b}" for a, b in cross[(cross.get("eval", 0) > 0)
                                                        & (cross.get("dev", 0) == 0)].index)
    assert uncalibratable == ["cam_A/night"], (
        f"stratum coverage changed: {uncalibratable} — revisit the normalisation grouping")
