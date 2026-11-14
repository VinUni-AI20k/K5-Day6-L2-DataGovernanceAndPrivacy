#!/usr/bin/env bash
# One-command reproduce T14: run PoC offline, evaluate (neu co gt/), run tests.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}
$PY -m src.main --config configs/lab.yaml --track t14 --output out/poc --run-name poc --offline --seed 42
# Ground truth chi co trong overlay giang vien; khong co thi bo qua buoc cham.
if [ -f fixtures/t14_auto_annotation/gt/gt_boxes.csv ]; then
  $PY -m src.evaluate --track t14 --pred out/poc/predictions.csv --run-name poc --out reports/metrics_poc.json
else
  echo "run.sh: fixtures/t14_auto_annotation/gt not found (overlay giang vien chua cai) - bo qua evaluate" >&2
fi
$PY -m pytest -q
