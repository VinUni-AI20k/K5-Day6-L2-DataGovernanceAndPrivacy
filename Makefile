# Day06 Data Lab — common commands.  Usage: make <target> TRACK=t02
PY ?= .venv/bin/python
TRACK ?= t02
OUT ?= out
PRED = $(shell $(PY) -c "from src.metrics.tracks import get_track;print(get_track('$(TRACK)').pred_file)")

.PHONY: help setup preflight test fixtures verify baseline run eval-baseline eval-poc compare real-data tag-demo tag-final

help:
	@echo "make setup | preflight | test | verify | baseline TRACK=t11 | run TRACK=t02 | eval-baseline | eval-poc | compare"

setup:
	python3 -m venv .venv && $(PY) -m pip install -q --upgrade pip && $(PY) -m pip install -q -r requirements.txt

preflight:
	$(PY) -m tools.preflight

test:
	$(PY) -m pytest -q

verify:
	$(PY) -m tools.verify_manifests

fixtures:            ## instructor only: regenerate fixtures (needs the private instructor overlay)
	@test -f tools/make_fixtures.py || { echo "tools/make_fixtures.py is instructor-only (private overlay not installed)"; exit 1; }
	$(PY) -m tools.make_fixtures

baseline:            ## random baseline wiring example (t01, t02, t11, t13)
	$(PY) -m src.main --track $(TRACK) --pipeline src.examples.random_baseline --output $(OUT)/baseline --run-name baseline --offline --seed 42

run:                 ## your PoC (src/pipeline.py)
	$(PY) -m src.main --config configs/lab.yaml --track $(TRACK) --output $(OUT)/poc --run-name poc --offline --seed 42

eval-baseline:
	$(PY) -m src.evaluate --track $(TRACK) --pred $(OUT)/baseline/$(PRED) --run-name baseline --out reports/metrics_baseline.json

eval-poc:
	$(PY) -m src.evaluate --track $(TRACK) --pred $(OUT)/poc/$(PRED) --run-name poc --out reports/metrics_poc.json

compare:
	$(PY) -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md

real-data:           ## instructor only: needs HF_TOKEN in .env, run BEFORE class
	$(PY) -m tools.download_real_samples

tag-demo:
	git tag -a demo-180m -m "Demo freeze at minute 180"

tag-final:
	git tag -a final-24h -m "Final submission"
