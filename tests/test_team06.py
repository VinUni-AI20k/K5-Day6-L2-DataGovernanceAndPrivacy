"""Team 6 starter checks; QA owner: Lê Trần Phi Hùng, 2A202603353."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from src.common.context import RunContext
from src.common.io import resolve_config
from src.main import main
from src.team06.data import load_inputs


def _ctx(input_dir, output_dir):
    return RunContext(
        track="t02", input_dir=Path(input_dir), output_dir=output_dir,
        config=resolve_config("configs/lab.yaml"), seed=42, rng=np.random.default_rng(42),
    )


def test_team06_loads_verified_images_without_changing_splits(tmp_path):
    data = load_inputs(_ctx("fixtures/t02_raw_qc", tmp_path))
    assert len(data["images"]) == 96
    assert data["images"].split.value_counts().to_dict() == {"dev": 56, "eval": 40}
    assert data["images"].image_id.is_unique


def test_team06_rejects_tampered_metadata(tmp_path):
    copied = tmp_path / "input"
    shutil.copytree("fixtures/t02_raw_qc", copied)
    with (copied / "images.csv").open("a", encoding="utf-8") as f:
        f.write("unexpected,data\n")
    with pytest.raises(ValueError, match="provenance check failed"):
        load_inputs(_ctx(copied, tmp_path / "out"))


def test_team06_baseline_stub_reports_its_owner(tmp_path, capsys):
    status = main(["--track", "t02", "--pipeline", "src.team06.baseline", "--output", str(tmp_path), "--offline"])
    assert status == 3
    assert "Phạm Văn Dương" in capsys.readouterr().err
    info = json.loads((tmp_path / "run_info.json").read_text(encoding="utf-8"))
    assert info["status"] == 3 and info["seed"] == 42
    assert not (tmp_path / "ranked_review.csv").exists()
