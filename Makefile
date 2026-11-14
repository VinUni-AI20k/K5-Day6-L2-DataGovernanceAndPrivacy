# Day06 Data Lab - T14 Auto-Annotation + Human QC.  Usage: make <target>
PY ?= .venv/bin/python
OUT ?= out
GOLD ?= gold/gold_dev.csv

.PHONY: help setup preflight test baseline run eval-baseline eval-poc compare dev-eval tag-demo tag-final

help:
	@echo "make setup | preflight | test | baseline | run | eval-baseline | eval-poc | compare | dev-eval"

setup:
	python3 -m venv .venv && $(PY) -m pip install -q --upgrade pip && $(PY) -m pip install -q -r requirements.txt

preflight:
	$(PY) -m tools.preflight

test:
	$(PY) -m pytest -q

baseline:            ## baseline T14: default threshold, no review
	$(PY) -m src.main --config configs/lab.yaml --track t14 --pipeline src.baseline_t14 --output $(OUT)/baseline --run-name baseline --offline --seed 42

run:                 ## PoC T14 (src/pipeline.py)
	$(PY) -m src.main --config configs/lab.yaml --track t14 --output $(OUT)/poc --run-name poc --offline --seed 42

eval-baseline:       ## can overlay giang vien (gt/); khong co thi exit 2
	$(PY) -m src.evaluate --track t14 --pred $(OUT)/baseline/predictions.csv --run-name baseline --out reports/metrics_baseline.json

eval-poc:
	$(PY) -m src.evaluate --track t14 --pred $(OUT)/poc/predictions.csv --run-name poc --out reports/metrics_poc.json

compare:
	$(PY) -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md

dev-eval:            ## F1 noi bo tren gold set tu ve cua nhom (dev)
	$(PY) -m tools.t14_eval_dev --gold $(GOLD) --pred $(OUT)/poc/predictions.csv

tag-demo:
	git tag -a demo-180m -m "Demo freeze at minute 180"

tag-final:
	git tag -a final-24h -m "Final submission"
