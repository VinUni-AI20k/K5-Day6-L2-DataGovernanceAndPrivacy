"""T07 — reproduce every submitted artefact with one cross-platform command (no make/bash needed).

    python -m tools.t07_run_all            # Windows: .\\.venv\\Scripts\\python.exe -m tools.t07_run_all

Steps (all offline, seed 42):
  1. baselines            -> out/baseline (naive colour), out/baseline_blurall, and out/baseline_haar when
                             the installed OpenCV still has CascadeClassifier (optional reference)
  2. PoC, no review       -> out/poc (decision HOLD), snapshot redactions_before_review.csv
  3. human review         -> copies the signed review file reports/review_queue.csv to
                             out/poc/review_queue_reviewed.csv and re-runs the PoC (audit log + decision)
  4. self-evaluation      -> reports/metrics_*.json, reports/table1*.md, reports/t07_selfcheck_slices.csv
                             against the group's dev mini gold set (reports/mini_gt/)
  5. evidence copies      -> reports/decision_log.csv, reports/audit_log.jsonl, reports/run_info_poc.json

The review file is human evidence: this script never invents reviewer decisions. Without
reports/review_queue.csv step 3 is skipped and the decision stays HOLD.
Official scores come from the instructor's hidden ground truth:
    python -m src.evaluate --track t07 --pred out/poc/redactions.csv --run-name poc --out reports/metrics_poc.json
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from src import compare, evaluate
from src import main as runner

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("out")
REPORTS = Path("reports")
MINI_GT = REPORTS / "mini_gt" / "gt_regions.csv"
COMMON = ["--track", "t07", "--offline", "--seed", "42"]


def _run(args: list[str]) -> None:
    rc = runner.main(args)
    if rc != 0:
        raise SystemExit(f"src.main {' '.join(args)} failed with exit code {rc}")


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    _run(COMMON + ["--pipeline", "src.t07_baseline", "--output", str(OUT / "baseline"), "--run-name", "baseline"])
    _run(COMMON + ["--pipeline", "src.t07_baseline_blurall", "--output", str(OUT / "baseline_blurall"),
                   "--run-name", "baseline_blurall"])
    import cv2
    has_haar = hasattr(cv2, "CascadeClassifier")      # OpenCV 4.x or opencv-contrib 5.x only
    if has_haar:
        _run(COMMON + ["--pipeline", "src.t07_baseline_haar", "--output", str(OUT / "baseline_haar"),
                       "--run-name", "baseline_haar"])
    else:
        print(f"[t07_run_all] OpenCV {cv2.__version__} has no CascadeClassifier -> optional Haar reference skipped")
    poc = OUT / "poc"
    poc_args = ["--config", "configs/lab.yaml"] + COMMON + ["--output", str(poc), "--run-name", "poc"]
    _run(poc_args)
    shutil.copyfile(poc / "redactions.csv", poc / "redactions_before_review.csv")

    signed = REPORTS / "review_queue.csv"
    if signed.exists():
        shutil.copyfile(signed, poc / "review_queue_reviewed.csv")
        _run(poc_args)
    else:
        print("[t07_run_all] reports/review_queue.csv not found -> no human review applied, decision stays HOLD")

    if MINI_GT.exists():
        gt = ["--track", "t07", "--gt", str(MINI_GT), "--split", "dev"]
        runs = [("baseline", OUT / "baseline" / "redactions.csv", "metrics_baseline.json"),
                ("baseline_blurall", OUT / "baseline_blurall" / "redactions.csv", "metrics_baseline_blurall.json"),
                *([("baseline_haar", OUT / "baseline_haar" / "redactions.csv", "metrics_baseline_haar.json")] if has_haar else []),
                ("poc_auto", poc / "redactions_before_review.csv", "metrics_poc_auto.json"),
                ("poc", poc / "redactions.csv", "metrics_poc.json")]
        for name, pred, out in runs:
            if evaluate.main(gt + ["--pred", str(pred), "--run-name", name, "--out", str(REPORTS / out)]) != 0:
                raise SystemExit(f"evaluate failed for {name}")
        compare.main([str(REPORTS / "metrics_baseline.json"), str(REPORTS / "metrics_poc.json"),
                      "--out", str(REPORTS / "table1_baseline_vs_poc.md")])
        compare.main([str(REPORTS / "metrics_baseline_blurall.json"), str(REPORTS / "metrics_poc.json"),
                      "--out", str(REPORTS / "table1b_blurall_vs_poc.md")])
        compare.main([str(REPORTS / "metrics_poc_auto.json"), str(REPORTS / "metrics_poc.json"),
                      "--out", str(REPORTS / "table1c_poc_auto_vs_reviewed.md")])
        from tools import t07_selfcheck
        t07_selfcheck.main(["--gt", str(MINI_GT),
                            "--run", f"baseline={OUT / 'baseline' / 'redactions.csv'}",
                            "--run", f"blur_all={OUT / 'baseline_blurall' / 'redactions.csv'}",
                            *(["--run", f"haar={OUT / 'baseline_haar' / 'redactions.csv'}"] if has_haar else []),
                            "--run", f"poc_auto={poc / 'redactions_before_review.csv'}",
                            "--run", f"poc={poc / 'redactions.csv'}",
                            "--out", str(REPORTS / "t07_selfcheck_slices.csv")])

    shutil.copyfile(poc / "decision_log.csv", REPORTS / "decision_log.csv")
    shutil.copyfile(poc / "audit_log.jsonl", REPORTS / "audit_log.jsonl")
    shutil.copyfile(poc / "run_info.json", REPORTS / "run_info_poc.json")
    print("[t07_run_all] done -> out/poc, reports/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
