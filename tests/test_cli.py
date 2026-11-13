"""Lab contract: one-command run, offline guard, GT guard, evaluate + compare."""
import json
import socket
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src import compare, evaluate
from src import main as runner
from src.common.gt_guard import GroundTruthAccessError, disable_gt_guard, enable_gt_guard
from src.common.offline import NetworkBlockedError, disable_offline_guard, enable_offline_guard


def test_template_pipeline_fails_clearly_not_silently(tmp_path):
    rc = runner.main(["--track", "t02", "--output", str(tmp_path), "--offline"])
    assert rc == 3                                   # NotImplemented -> explicit exit code
    info = json.loads((tmp_path / "run_info.json").read_text())
    assert info["status"] == 3 and info["seed"] == 42


def test_random_baseline_end_to_end_and_evaluate(tmp_path):
    out = tmp_path / "baseline"
    rc = runner.main(["--track", "t02", "--pipeline", "src.examples.random_baseline", "--output", str(out), "--offline", "--seed", "42", "--run-name", "baseline"])
    assert rc == 0
    for f in ["ranked_review.csv", "review_queue.csv", "contact_sheet.html", "decision.json", "decision_log.csv", "run_info.json"]:
        assert (out / f).exists(), f
    mb = tmp_path / "metrics_baseline.json"
    assert evaluate.main(["--track", "t02", "--pred", str(out / "ranked_review.csv"), "--run-name", "baseline", "--out", str(mb)]) == 0
    payload = json.loads(mb.read_text())
    prim = [m for m in payload["metrics"] if m["primary"]][0]
    assert prim["denominator"] == 20 and payload["seed"] == 42
    # same seed -> identical output (reproducibility)
    out2 = tmp_path / "baseline2"
    runner.main(["--track", "t02", "--pipeline", "src.examples.random_baseline", "--output", str(out2), "--offline", "--seed", "42"])
    assert (out / "ranked_review.csv").read_text() == (out2 / "ranked_review.csv").read_text()
    md = tmp_path / "t1.md"
    assert compare.main([str(mb), str(mb), "--out", str(md)]) == 0
    assert "Defect Recall@B" in md.read_text()


def test_missing_input_folder_exit_2(tmp_path):
    assert runner.main(["--track", "t02", "--input", str(tmp_path / "nope"), "--output", str(tmp_path)]) == 2


def test_offline_guard_blocks_network():
    enable_offline_guard()
    try:
        with pytest.raises(NetworkBlockedError):
            socket.create_connection(("huggingface.co", 443), timeout=1)
    finally:
        disable_offline_guard()


def test_gt_guard_blocks_ground_truth_reads():
    enable_gt_guard()
    try:
        with pytest.raises(GroundTruthAccessError):
            pd.read_csv("fixtures/t02_raw_qc/gt/labels.csv")
        pd.read_csv("fixtures/t02_raw_qc/images.csv")   # inputs are fine
    finally:
        disable_gt_guard()


def test_cli_module_invocation():
    r = subprocess.run([sys.executable, "-m", "src.evaluate", "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--pred" in r.stdout
