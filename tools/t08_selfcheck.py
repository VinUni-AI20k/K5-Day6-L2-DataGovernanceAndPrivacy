"""T08 self-check against the group's INTERNAL answer key (not the official GT).   [P2]

    python -m tools.t08_selfcheck --pred out/poc/actions.csv
    python -m tools.t08_selfcheck --pred out/baseline/actions.csv

The key (reports/t08_internal_key.csv) was checked against the input metadata and the group's policy
for DR-002, DR-004, DR-008 only (see reports/t08_exceptions.md). Same formulas as
src/metrics/tracks.py::eval_t08, restricted to those requests. Official scores come only from the
instructor's hidden GT.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd


def selfcheck(pred_path: str, key_path: str) -> dict:
    key = pd.read_csv(key_path)
    pred = pd.read_csv(pred_path, dtype=str)
    ids = ["request_id", "artefact_id"]
    required = ids + ["action"]
    missing = [column for column in required if column not in pred.columns]
    if missing:
        raise ValueError(f"actions.csv missing columns: {missing}")
    for column in required:
        pred[column] = pred[column].fillna("").str.strip()
    if pred[required].eq("").any().any():
        raise ValueError("actions.csv contains blank request_id, artefact_id, or action")
    if pred.duplicated(ids).any():
        raise ValueError("actions.csv contains duplicate (request_id, artefact_id) pairs")
    pred["action"] = pred["action"].str.lower()
    pred = pred[pred.request_id.isin(key.request_id.unique())]
    m = key.merge(pred[["request_id", "artefact_id", "action"]], on=["request_id", "artefact_id"], how="left")
    must = m[m.expected_action == "delete"]
    exc = m[m.expected_action != "delete"]
    keys = set(zip(key.request_id, key.artefact_id))
    outside = pd.Series([k not in keys for k in zip(pred.request_id, pred.artefact_id)], index=pred.index, dtype=bool)
    stray = pred[(pred.action == "delete") & outside]
    res = {
        "requests": sorted(key.request_id.unique()),
        "completeness": f"{int((must.action == 'delete').sum())}/{len(must)}",
        "false_delete": int((exc.action == "delete").sum()) + len(stray),
        "exception_accuracy": f"{int((exc.action == exc.expected_action).sum())}/{len(exc)}",
        "exact_match": f"{int((m.action == m.expected_action).sum())}/{len(m)}",
    }
    wrong = m[m.action != m.expected_action]
    return res | {"mismatches": wrong[["request_id", "artefact_id", "type", "expected_action", "action", "why"]]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="T08 self-check vs internal key")
    ap.add_argument("--pred", required=True)
    ap.add_argument("--key", default="reports/t08_internal_key.csv")
    a = ap.parse_args(argv)
    try:
        r = selfcheck(a.pred, a.key)
    except ValueError as exc:
        ap.error(str(exc))
    mism = r.pop("mismatches")
    for k, v in r.items():
        print(f"{k:20s} {v}")
    if len(mism):
        print(f"\n{len(mism)} mismatch(es):")
        print(mism.fillna("(missing)").to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
