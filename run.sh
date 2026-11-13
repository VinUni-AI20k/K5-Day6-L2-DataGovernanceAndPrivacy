#!/usr/bin/env bash
# One-command reproduce: run PoC offline, evaluate, run tests.
#   ./run.sh            (track from configs/lab.yaml)
#   ./run.sh t11
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}
TRACK=${1:-$($PY -c "from src.common.io import load_config;print(load_config('configs/lab.yaml')['track'])")}
PRED=$($PY -c "from src.metrics.tracks import get_track;print(get_track('$TRACK').pred_file)")
$PY -m src.main --config configs/lab.yaml --track "$TRACK" --output out/poc --run-name poc --offline --seed 42
$PY -m src.evaluate --track "$TRACK" --pred "out/poc/$PRED" --run-name poc --out reports/metrics_poc.json
$PY -m pytest -q
