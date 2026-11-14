"""Reproducible development check with manually specified expected actions."""
from pathlib import Path
import json
import sys
import time
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def command(*args):
    subprocess.run([sys.executable, "-X", "utf8", *args], cwd=ROOT, check=True)


def main():
    # Dùng output mới mỗi lần để không mang review/state cũ sang bộ kiểm tra.
    suffix = time.strftime("%Y%m%d_%H%M%S") + "_" + str(time.time_ns() % 1000000)
    base = "out/selfcheck_" + suffix
    for label, pipeline in (("baseline", "src.t08_baseline"), ("poc", "src.pipeline")):
        output = base + "/" + label
        command("-m", "src.main", "--config", "configs/t08_demo.yaml", "--pipeline", pipeline,
                "--output", output, "--run-name", label, "--offline", "--seed", "42")
        command("-m", "src.evaluate", "--config", "configs/t08_demo.yaml", "--track", "t08",
                "--gt", "examples/t08_demo/expected_actions.csv", "--pred", output + "/actions.csv",
                "--run-name", label, "--out", f"reports/demo_metrics_{label}.json")
    command("-m", "src.compare", "reports/demo_metrics_baseline.json", "reports/demo_metrics_poc.json",
            "--out", "reports/demo_baseline_vs_poc.md")
    (ROOT / "reports/demo_evaluation_scope.json").write_text(json.dumps({
        "source": "hand-authored development example", "official_instructor_score": False,
        "n_requests": 2, "n_artefacts": 9, "n_expected_request_artefact_pairs": 10,
        "mode": "prediction/dry-run; no real human review, no execution",
        "expected_actions": "examples/t08_demo/expected_actions.csv",
        "output": base
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
