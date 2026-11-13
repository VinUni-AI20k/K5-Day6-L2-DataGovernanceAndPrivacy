"""One evaluator per track = the shared *metric contract*.

Each evaluator reads ground truth (fixtures/<track>/gt/...) and the group's
prediction file (out/<file>.csv), and returns MetricResult rows + a slice table.
Prediction schemas are documented in docs/tracks/TXX.md and in TRACKS below.

Do NOT change these definitions to make your numbers look better. If you think a
metric is wrong, argue it in the report and add an *extra* metric in your code.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import yaml

from ..common.decision import canonical_status
from ..common.report import MetricResult, safe_div
from . import classification as CL
from . import correlation as CO
from . import detection as DE
from . import pairs as PA
from . import ranking as RK
from . import timing as TI

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@dataclass
class EvalOutput:
    metrics: list[MetricResult]
    slices: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: list[str] = field(default_factory=list)


@dataclass
class TrackSpec:
    track: str
    title: str
    fixture_dir: str
    default_gt: str            # relative to fixture dir
    pred_file: str             # default prediction file name inside --output
    pred_columns: list[str]    # required columns
    evaluator: Callable[[Path, Path, dict], EvalOutput]
    params: dict = field(default_factory=dict)


def _m(name, value, direction, unit="", num=None, den=None, n=None, primary=False, slice="all", notes="") -> MetricResult:
    if isinstance(value, float) and math.isnan(value):
        value = None
    return MetricResult(name=name, value=None if value is None else float(value), direction=direction, unit=unit,
                        numerator=num, denominator=den, n=n, slice=slice, primary=primary, notes=notes)


def _guardrail(name: str, value, limit: float) -> tuple[MetricResult, str]:
    """Constrained primary: the primary metric only counts when this side metric stays within its limit.

    Without it, a trivial policy (blur everything, HOLD everything) can reach a perfect primary score.
    """
    ok = value is not None and float(value) <= limit
    note = (f"guardrail {name} <= {limit}: {'PASS' if ok else 'FAIL — primary metric is not valid on its own'}"
            f" (value={'n/a' if value is None else round(float(value), 4)})")
    return _m(f"Guardrail: {name} <= {limit}", 1.0 if ok else 0.0, "higher", "1 = pass, 0 = fail (constrained primary)"), note


def _need(df: pd.DataFrame, cols: list[str], what: str) -> None:
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise ValueError(f"{what} is missing required columns {miss}; has {list(df.columns)}")


def _fixture_dir_of(gt_path: Path) -> Path:
    return gt_path.parent.parent if gt_path.parent.name == "gt" else gt_path.parent


def _split(df: pd.DataFrame, cfg: dict, default: str) -> pd.DataFrame:
    s = cfg.get("split", default)
    if s in (None, "all") or "split" not in df.columns:
        return df
    return df[df["split"] == s]


# ----------------------------------------------------------------------------- T01
def eval_t01(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    fx = _fixture_dir_of(gt_path)
    targets = pd.read_csv(fx / "targets.csv")
    gt = pd.read_csv(gt_path).set_index("clip_id")
    cand_file = "holdout_candidates.csv" if "holdout" in gt_path.name else "candidates.csv"
    cand = pd.read_csv(fx / cand_file).set_index("clip_id")
    k = int(cfg.get("k", 6 if "holdout" in gt_path.name else 30))
    pred = pd.read_csv(pred_path, dtype={"clip_id": str})
    _need(pred, ["clip_id"], "pick.csv")
    if "rank" in pred.columns:
        pred = pred.sort_values("rank")
    picks = [c for c in pred["clip_id"].astype(str) if c in gt.index]
    notes = []
    if len(pred) != k:
        notes.append(f"pick.csv has {len(pred)} rows but K={k}; using first {k}")
    unknown = len(pred) - len(picks)
    if unknown:
        notes.append(f"{unknown} picked clip_ids not in candidate pool (ignored)")
    picks = list(dict.fromkeys(picks))[:k]
    dims = ["route", "weather", "light", "object"]

    def matches(row, cell):
        return all(cell[d] == "*" or cell[d] == row[d] for d in dims)

    covered = set()
    for c in picks:
        row = gt.loc[c]
        for _, cell in targets.iterrows():
            if matches(row, cell):
                covered.add(cell["cell_id"])
    w = dict(zip(targets.cell_id, targets.weight.astype(float)))
    wc = RK.weighted_coverage(covered, w)
    hard = set(targets.loc[targets.is_hard == 1, "cell_id"])
    combos = [tuple(gt.loc[c, dims]) for c in picks]
    dup = len(combos) - len(set(combos))
    cost = float(cand.loc[picks, "cost_min"].sum()) if picks else 0.0
    ms = [
        _m("Weighted Coverage@K", wc["value"], "higher", "Σw covered / Σw targets", wc["numerator"], wc["denominator"], len(picks), True),
        _m("Rare-scenario Recall@K", safe_div(len(covered & hard), len(hard)), "higher", "hard cells covered / hard cells", len(covered & hard), len(hard)),
        _m("Duplicate clips in K", dup, "lower", "count (same verified scenario)", n=len(picks)),
        _m("Cost per covered cell", safe_div(cost, len(covered)), "lower", "capture minutes / covered cell", cost, len(covered)),
    ]
    sl = targets.assign(covered=targets.cell_id.isin(covered).astype(int))[["cell_id", "weight", "is_hard", "covered"]]
    notes.append(f"missing cells: {wc['missing']}")
    return EvalOutput(ms, sl, notes)


# ----------------------------------------------------------------------------- T02
def eval_t02(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    gt = _split(pd.read_csv(gt_path), cfg, "eval")
    pred = pd.read_csv(pred_path)
    _need(pred, ["image_id", "score"], "ranked_review.csv")
    pred = pred[pred.image_id.isin(gt.image_id)].sort_values("score", ascending=False, kind="mergesort")
    B = int(cfg.get("budget", 20))
    pos = gt.loc[gt.is_defect == 1, "image_id"]
    r = RK.recall_at_k(pred.image_id, pos, B)
    p = RK.precision_at_k(pred.image_id, pos, B)
    top = set(pred.image_id.head(B))
    ms = [
        _m("Defect Recall@B", r["value"], "higher", "GT defects in top-B / GT defects", r["numerator"], r["denominator"], len(gt), True),
        _m("Precision@B", p["value"], "higher", "GT defects in top-B / B", p["numerator"], p["denominator"], len(gt)),
    ]
    if "pred_defect_type" in pred.columns:
        m = gt[gt.is_defect == 1].merge(pred[["image_id", "pred_defect_type"]], on="image_id", how="left")
        acc = (m.defect_type == m.pred_defect_type).mean() if len(m) else None
        ms.append(_m("Defect-type accuracy (GT defects)", acc, "higher", "fraction", n=len(m)))
    rows = []
    for s, sub in gt.groupby("light"):
        neg = sub[sub.is_defect == 0]
        posn = sub[sub.is_defect == 1]
        fa = safe_div(neg.image_id.isin(top).sum(), len(neg))
        rec = safe_div(posn.image_id.isin(top).sum(), len(posn))
        rows.append({"slice": f"light={s}", "n": len(sub), "recall_in_topB": rec, "false_alarm_in_topB": fa})
        ms.append(_m("False alarm in top-B", fa, "lower", "clean images in top-B / clean images", int(neg.image_id.isin(top).sum()), len(neg), len(sub), slice=f"light={s}"))
    for s, sub in gt[gt.is_defect == 1].groupby("defect_type"):
        rows.append({"slice": f"defect={s}", "n": len(sub), "recall_in_topB": safe_div(sub.image_id.isin(top).sum(), len(sub)), "false_alarm_in_topB": None})
    return EvalOutput(ms, pd.DataFrame(rows), [f"B={B}, eval N={len(gt)}"])


# ----------------------------------------------------------------------------- T03
def eval_t03(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    gt = pd.read_csv(gt_path)
    pred = pd.read_csv(pred_path)
    _need(pred, ["image_id", "pred_unusable"], "qc.csv")
    m = gt.merge(pred[["image_id", "pred_unusable"]], on="image_id", how="left")
    missing = int(m.pred_unusable.isna().sum())
    m["pred_unusable"] = m.pred_unusable.fillna(0).astype(int)  # no prediction = treated as 'usable' (worst case)
    r = CL.prf(m.unusable, m.pred_unusable)
    ms = [
        _m("Transform QC F1", r["f1"], "higher", "F1, positive = unusable", n=len(m), primary=True),
        _m("Precision (unusable)", r["precision"], "higher", "TP/(TP+FP)", r["tp"], r["tp"] + r["fp"], len(m)),
        _m("Recall (unusable)", r["recall"], "higher", "TP/(TP+FN)", r["tp"], r["tp"] + r["fn"], len(m)),
        _m("Missed label-invalidating edits", int(((m.note == "object_removed_label_kept") & (m.pred_unusable == 0)).sum()), "lower", "count"),
    ]
    man = pred_path.parent / "transform_manifest.csv"
    if man.exists():
        mf = pd.read_csv(man)
        req = ["image_id", "parent_image", "transform", "severity", "seed"]
        ok = mf[[c for c in req if c in mf.columns]].notna().all(axis=1) if all(c in mf.columns for c in req) else pd.Series([False] * len(mf))
        ms.append(_m("Provenance completeness", ok.mean() if len(mf) else None, "higher", "manifest rows with all required fields", int(ok.sum()), len(mf)))
    sl = CL.per_slice(m, "transform", lambda s: {k: v for k, v in CL.prf(s.unusable, s.pred_unusable).items() if k in ("f1", "recall", "precision")})
    return EvalOutput(ms, sl, [f"{missing} holdout images had no prediction (counted as usable)"] if missing else [])


# ----------------------------------------------------------------------------- T04
def eval_t04(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    gt = _split(pd.read_csv(gt_path), cfg, "eval")
    pred = pd.read_csv(pred_path)
    _need(pred, ["frame_id", "imu_t_ms"], "pairs.csv")
    m = gt.merge(pred[["frame_id", "imu_t_ms"]], on="frame_id", how="left")
    tol = float(cfg.get("tol_ms", 50))
    valid = m.gt_imu_t_ms.notna()
    acc = TI.pair_accuracy_at_tol(m.imu_t_ms, m.gt_imu_t_ms, tol)
    med = TI.median_abs_residual(m.imu_t_ms, m.gt_imu_t_ms)
    drop = m[~valid]
    held_drop = int(drop.imu_t_ms.isna().sum())
    ms = [
        _m(f"Pair Accuracy@{int(tol)}ms", acc["value"], "higher", "frames within tol / frames with GT partner", acc["numerator"], acc["denominator"], len(m), True),
        _m("Median |time residual|", med, "lower", "ms"),
        _m("Bad-pair recall (dropout held)", safe_div(held_drop, len(drop)), "higher", "dropout frames put on HOLD / dropout frames", held_drop, len(drop)),
        _m("% frames HOLD (valid frames)", safe_div(int(m.loc[valid, "imu_t_ms"].isna().sum()), int(valid.sum())), "lower", "fraction", n=int(valid.sum())),
    ]
    rows = []
    for (seg, dr), sub in m.groupby(["segment", "drift_ms_per_s"]):
        a = TI.pair_accuracy_at_tol(sub.imu_t_ms, sub.gt_imu_t_ms, tol)
        rows.append({"slice": f"segment={seg},drift={dr}", "n": len(sub), "pair_accuracy": a["value"], "median_abs_residual_ms": TI.median_abs_residual(sub.imu_t_ms, sub.gt_imu_t_ms)})
    return EvalOutput(ms, pd.DataFrame(rows))


# ----------------------------------------------------------------------------- T05
def eval_t05(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    gt = pd.read_csv(gt_path)
    pred = pd.read_csv(pred_path, dtype={"img_a": str, "img_b": str})
    _need(pred, ["img_a", "img_b"], "suspect_pairs.csv")
    if "pred_dup" in pred.columns:
        pred = pred[pred.pred_dup.astype(int) == 1]
    gt_dup = PA.pairs_from_groups(dict(zip(gt.image_id, gt.dup_group_id)))
    gt_scene = PA.pairs_from_groups(dict(zip(gt.image_id, gt.scene_id)))
    r = PA.pair_prf(zip(pred.img_a, pred.img_b), gt_dup)
    scene_of = dict(zip(gt.image_id, gt.scene_id))
    cross = sum(1 for a, b in zip(pred.img_a, pred.img_b) if scene_of.get(a) != scene_of.get(b))
    ms = [
        _m("Leakage Detection F1 (pair)", r["f1"], "higher", "unit = unordered image pair in same near-dup group", n=len(gt_dup), primary=True),
        _m("Pair precision", r["precision"], "higher", "TP/(TP+FP)", r["tp"], r["tp"] + r["fp"]),
        _m("Pair recall", r["recall"], "higher", "TP/(TP+FN)", r["tp"], r["tp"] + r["fn"]),
        _m("False merge rate", safe_div(cross, len(pred)), "lower", "predicted pairs across different scenes / predicted pairs", cross, len(pred)),
    ]
    sp = pred_path.parent / "split_manifest.csv"
    notes = []
    if sp.exists():
        s = pd.read_csv(sp, dtype=str)
        split_of = dict(zip(s.image_id, s.split))
        leak_d = PA.residual_cross_split_leak(split_of, gt_dup)
        leak_s = PA.residual_cross_split_leak(split_of, gt_scene)
        kept = sum(1 for i in gt.image_id if split_of.get(i) not in (None, "drop", ""))
        ms += [
            _m("Residual cross-split leak (near-dup)", leak_d["value"], "lower", "GT dup pairs split across train/test / kept GT dup pairs", leak_d["numerator"], leak_d["denominator"]),
            _m("Residual cross-split leak (scene)", leak_s["value"], "lower", "same-scene pairs split across train/test / kept pairs", leak_s["numerator"], leak_s["denominator"]),
            _m("% data kept", kept / len(gt), "higher", "images not dropped / all images", kept, len(gt)),
        ]
    else:
        notes.append("split_manifest.csv not found next to predictions — leakage-after-split metrics skipped")
    sl = gt.assign(found=[any(i in (a, b) for a, b in zip(pred.img_a, pred.img_b)) for i in gt.image_id]).groupby("transform").found.mean().reset_index()
    return EvalOutput(ms, sl.rename(columns={"transform": "slice", "found": "share_in_any_pred_pair"}), notes)


# ----------------------------------------------------------------------------- T06
def eval_t06(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    gt = _split(pd.read_csv(gt_path), cfg, "all")
    pred = pd.read_csv(pred_path)
    _need(pred, ["release_id", "decision"], "release_decisions.csv")
    m = gt.merge(pred, on="release_id", how="left")
    m["blocked"] = m.decision.fillna("GO").map(lambda s: int(canonical_status(str(s)) != "GO"))
    r = CL.prf(m.is_defective, m.blocked)
    clean = m[m.is_defective == 0]
    ms = [
        _m("Silent-defect Detection F1", r["f1"], "higher", "F1, unit = release, positive = defective & blocked", n=len(m), primary=True),
        _m("Defect recall", r["recall"], "higher", "defective releases blocked / defective", r["tp"], r["tp"] + r["fn"]),
        _m("False-block rate", safe_div(int(clean.blocked.sum()), len(clean)), "lower", "clean releases blocked / clean", int(clean.blocked.sum()), len(clean)),
    ]
    if "root_cause" in m.columns:
        d = m[(m.is_defective == 1) & (m.blocked == 1)]
        ms.append(_m("Root-cause accuracy", safe_div(int((d.root_cause == d.corruption_type).sum()), len(d)), "higher", "correct root cause / defective blocked", int((d.root_cause == d.corruption_type).sum()), len(d)))
    sl = m.groupby("corruption_type").blocked.mean().reset_index().rename(columns={"corruption_type": "slice", "blocked": "block_rate"})
    return EvalOutput(ms, sl)


# ----------------------------------------------------------------------------- T07
def eval_t07(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    fx = _fixture_dir_of(gt_path)
    imgs = pd.read_csv(fx / "images.csv")
    sizes = {r.image_id: (int(r.height), int(r.width)) for r in imgs.itertuples()}
    gt = _split(pd.read_csv(gt_path), cfg, "eval")
    red = pd.read_csv(pred_path)
    _need(red, ["image_id", "x", "y", "w", "h"], "redactions.csv")
    split = cfg.get("split", "eval")
    pool = set(imgs.image_id) if split in (None, "all") else set(imgs.loc[imgs.split == split, "image_id"])
    red = red[red.image_id.isin(pool)]
    cov = float(cfg.get("min_coverage", 0.9))
    r = DE.pii_miss_rate(gt, red, sizes, cov)
    reg = r["regions"]
    over = DE.over_redaction_rate(gt, red, sizes)
    ms = [
        _m("PII Miss Rate", r["value"], "lower", f"GT regions with coverage < {cov} / GT regions", r["numerator"], r["denominator"], len(gt), True),
        _m("Region recall", 1 - r["value"] if r["value"] is not None else None, "higher", "1 - miss rate", n=len(gt)),
        _m("Over-redaction rate", over["value"], "lower", "redacted px outside GT / redacted px", over["numerator"], over["denominator"]),
    ]
    rows = []
    for col in ("type", "condition"):
        for s, sub in reg.groupby(col):
            ms.append(_m("PII Miss Rate", sub.missed.mean(), "lower", "fraction", int(sub.missed.sum()), len(sub), len(sub), slice=f"{col}={s}"))
            rows.append({"slice": f"{col}={s}", "n": len(sub), "miss_rate": sub.missed.mean(), "mean_coverage": sub.coverage.mean()})
    g, note = _guardrail("Over-redaction rate", over["value"], float(cfg.get("max_over_redaction", 0.3)))
    ms.insert(3, g)
    return EvalOutput(ms, pd.DataFrame(rows), [f"min_coverage={cov}", note,
                                               "report the trivial blur-all baseline next to your PoC"])


# ----------------------------------------------------------------------------- T08
def eval_t08(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    gt = pd.read_csv(gt_path)
    pred = pd.read_csv(pred_path)
    _need(pred, ["request_id", "artefact_id", "action"], "actions.csv")
    pred["action"] = pred.action.str.strip().str.lower()
    m = gt.merge(pred, on=["request_id", "artefact_id"], how="left")
    must = m[m.expected_action == "delete"]
    done = int((must.action == "delete").sum())
    exc = m[m.expected_action != "delete"]
    key_gt = set(zip(gt.request_id, gt.artefact_id))
    stray = pred[(pred.action == "delete") & ~pd.Series([k in key_gt for k in zip(pred.request_id, pred.artefact_id)], index=pred.index)]
    false_del = int((exc.action == "delete").sum()) + len(stray)
    ms = [
        _m("Deletion Completeness", safe_div(done, len(must)), "higher", "must-delete artefacts deleted / must-delete artefacts", done, len(must), len(m), True),
        _m("False-delete count", false_del, "lower", "count (target 0): exceptions deleted + deletes outside request scope"),
        _m("Exception handling accuracy", safe_div(int((exc.action == exc.expected_action).sum()), len(exc)), "higher", "legal-hold/escalate rows handled as expected / such rows", int((exc.action == exc.expected_action).sum()), len(exc)),
    ]
    audit = pred_path.parent / "audit_log.jsonl"
    if audit.exists():
        logged = {json.loads(l).get("item_id") for l in audit.read_text().splitlines() if l.strip()}
        acted = pred[pred.action.isin(["delete", "retain_legal_hold", "escalate"])]
        ms.append(_m("Audit trace completeness", safe_div(int(acted.artefact_id.isin(logged).sum()), len(acted)), "higher", "actions with an audit entry / actions", int(acted.artefact_id.isin(logged).sum()), len(acted)))
    sl = m.assign(correct=(m.action == m.expected_action).astype(int)).groupby("expected_action").correct.agg(["mean", "count"]).reset_index().rename(columns={"expected_action": "slice", "mean": "accuracy", "count": "n"})
    return EvalOutput(ms, sl)


# ----------------------------------------------------------------------------- T09
def eval_t09(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    gt = _split(pd.read_csv(gt_path), cfg, "eval")
    pred = pd.read_csv(pred_path)
    _need(pred, ["case_id", "decision"], "decisions.csv")
    m = gt.merge(pred, on="case_id", how="left")
    m["pred"] = m.decision.fillna("GO").map(lambda s: canonical_status(str(s)))  # missing decision counts as GO (worst case)
    risky = m[m.gold_decision != "GO"]
    safe = m[m.gold_decision == "GO"]
    crit = int((risky.pred == "GO").sum())
    ms = [
        _m("Critical-miss Rate", safe_div(crit, len(risky)), "lower", "risky cases given GO / risky cases", crit, len(risky), len(m), True),
        _m("High-risk HOLD Recall", safe_div(len(risky) - crit, len(risky)), "higher", "risky cases not GO / risky cases", len(risky) - crit, len(risky)),
        _m("False HOLD rate", safe_div(int((safe.pred != "GO").sum()), len(safe)), "lower", "GO cases blocked / GO cases", int((safe.pred != "GO").sum()), len(safe)),
        _m("Exact decision accuracy", (m.pred == m.gold_decision).mean(), "higher", "fraction", n=len(m)),
    ]
    false_hold = safe_div(int((safe.pred != "GO").sum()), len(safe))
    g, gnote = _guardrail("False HOLD rate", false_hold, float(cfg.get("max_false_hold", 0.5)))
    ms.append(g)
    if "reason_codes" in m.columns:
        def hit(r):
            g = {x for x in str(r.gold_reason_codes).split(";") if x and x != "nan"}
            p = {x.strip() for x in str(r.reason_codes).replace(",", ";").split(";") if x.strip() and x != "nan"}
            return int(bool(g & p))
        h = risky.apply(hit, axis=1) if len(risky) else pd.Series(dtype=int)
        ms.append(_m("Reason-code match (risky)", h.mean() if len(h) else None, "higher", "risky cases with ≥1 correct reason code", int(h.sum()), len(h)))
    sl = m.assign(ok=(m.pred == m.gold_decision).astype(int)).groupby("gold_decision").ok.agg(["count", "mean"]).reset_index().rename(columns={"gold_decision": "slice", "count": "n", "mean": "accuracy"})
    split = cfg.get("split", "eval")
    return EvalOutput(ms, sl, [f"split={split} (N={len(m)}); official score uses split=eval, split=all is self-check only",
                               "N is tiny: report results case by case, not only as rates", gnote,
                               "report the trivial all-HOLD baseline next to your PoC"])


# ----------------------------------------------------------------------------- T10
def eval_t10(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    gt = pd.read_csv(gt_path)
    pred = pd.read_csv(pred_path)
    _need(pred, ["batch_id", "shift_score"], "shift_scores.csv")
    m = gt.merge(pred, on="batch_id", how="left")
    if m.shift_score.isna().any():
        raise ValueError(f"missing shift_score for batches {m.loc[m.shift_score.isna(), 'batch_id'].tolist()}")
    rho = CO.spearman(m.shift_score, m.perf_drop)
    lo, hi = CO.bootstrap_ci(lambda a, b: CO.spearman(a, b)["value"] if len(set(a)) > 1 and len(set(b)) > 1 else np.nan, m.shift_score.values, m.perf_drop.values, n_boot=int(cfg.get("n_boot", 2000)))
    ms = [
        _m("Spearman ρ(ShiftScore, PerformanceDrop)", rho["value"], "higher", f"rank correlation over {len(m)} batches; 95% bootstrap CI [{lo:.2f}, {hi:.2f}]", n=len(m), primary=True, notes=f"p={rho['p_value']:.3f}"),
        _m("AUROC high-risk", CO.auroc(m.high_risk, m.shift_score), "higher", "AUROC of shift_score vs high_risk (drop ≥ 0.10)", n=len(m)),
    ]
    if "pred_high_risk" in m.columns:
        neg = m[m.high_risk == 0]
        pos = m[m.high_risk == 1]
        ms.append(_m("False-alarm rate", safe_div(int(neg.pred_high_risk.sum()), len(neg)), "lower", "non-risky batches flagged / non-risky", int(neg.pred_high_risk.sum()), len(neg)))
        ms.append(_m("High-risk recall", safe_div(int(pos.pred_high_risk.sum()), len(pos)), "higher", "risky batches flagged / risky", int(pos.pred_high_risk.sum()), len(pos)))
    return EvalOutput(ms, m[["batch_id", "shift_score", "perf_drop", "high_risk"]].rename(columns={"batch_id": "slice"}), ["Only 6 batches: always show the CI and the per-batch table"])


# ----------------------------------------------------------------------------- T11
def eval_t11(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    fx = _fixture_dir_of(gt_path)
    imgs = pd.read_csv(fx / "images.csv")
    ann = pd.read_csv(fx / "annotations.csv")
    split = cfg.get("split", "heldout")
    pool_imgs = set(imgs.image_id if split == "all" else imgs.loc[imgs.split == split, "image_id"])
    gt = pd.read_csv(gt_path)
    gt = gt[gt.image_id.isin(pool_imgs)]
    pool_items = set(ann.loc[ann.image_id.isin(pool_imgs), "ann_id"]) | {f"img:{i}" for i in pool_imgs}
    n_ann = int(ann.image_id.isin(pool_imgs).sum())
    B = int(cfg.get("budget", RK.budget_b(n_ann)))
    pred = pd.read_csv(pred_path)
    _need(pred, ["item_id", "score"], "ranking.csv")
    pred = pred[pred.item_id.isin(pool_items)].sort_values("score", ascending=False, kind="mergesort")
    r = RK.recall_at_k(pred.item_id, gt.item_id, B)
    p = RK.precision_at_k(pred.item_id, gt.item_id, B)
    top = set(pred.item_id.head(B))
    found_types = set(gt.loc[gt.item_id.isin(top), "error_type"])
    ms = [
        _m("Error Recall@B", r["value"], "higher", "true errors in top-B / true errors in pool", r["numerator"], r["denominator"], n_ann, True, notes=f"B={B}"),
        _m("Precision@B", p["value"], "higher", "true errors in top-B / B", p["numerator"], p["denominator"]),
        _m("Error-type coverage", safe_div(len(found_types), gt.error_type.nunique()), "higher", "types with ≥1 error found / types present", len(found_types), gt.error_type.nunique()),
    ]
    sl = gt.assign(found=gt.item_id.isin(top).astype(int)).groupby("error_type").found.agg(["mean", "count"]).reset_index().rename(columns={"error_type": "slice", "mean": "recall_at_B", "count": "n"})
    ceiling = min(1.0, B / len(gt)) if len(gt) else None
    return EvalOutput(ms, sl, [f"pool split={split}, annotations N={n_ann}, B={B}; items = ann_id or img:<image_id> (missing boxes)",
                               f"oracle ceiling of Error Recall@B = min(1, B/#errors) = {ceiling:.3f}"])


# ----------------------------------------------------------------------------- T12
def eval_t12(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    fx = _fixture_dir_of(gt_path)
    gt = pd.read_csv(gt_path)
    pred = pd.read_csv(pred_path)
    _need(pred, ["batch_id", "est_error_rate", "decision", "n_audited"], "batch_decisions.csv")
    m = gt.merge(pred, on="batch_id", how="left")
    m["dec"] = m.decision.fillna("ACCEPT").str.upper()  # missing decision counts as ACCEPT (worst case for recall)
    bad, good = m[m.is_bad == 1], m[m.is_bad == 0]
    caught = int((bad.dec != "ACCEPT").sum())
    ms = [
        _m("MAE error-rate estimate", float(np.mean(np.abs(m.est_error_rate - m.true_error_rate))), "lower", "mean |est - true| over batches (fraction)", n=len(m), primary=True),
        _m("Bad-batch Recall", safe_div(caught, len(bad)), "higher", "bad batches not ACCEPTed / bad batches (reported separately from MAE)", caught, len(bad), primary=True),
        _m("False reject rate", safe_div(int((good.dec == "REWORK").sum()), len(good)), "lower", "good batches sent to REWORK / good batches", int((good.dec == "REWORK").sum()), len(good)),
        _m("HOLD rate", (m.dec == "HOLD").mean(), "lower", "batches on HOLD / batches", int((m.dec == "HOLD").sum()), len(m)),
    ]
    if {"ci_low", "ci_high"} <= set(m.columns):
        cov = ((m.ci_low <= m.true_error_rate) & (m.true_error_rate <= m.ci_high)).mean()
        ms.append(_m("CI coverage", cov, "higher", "batches whose CI contains true rate / batches (nominal 0.95)", n=len(m)))
    if (fx / "acceptance_policy.yaml").exists():
        budget = yaml.safe_load((fx / "acceptance_policy.yaml").read_text())["audit_budget_per_batch"]
        over = int((m.n_audited > budget).sum())
        ms.append(_m("Budget violations", over, "lower", f"batches audited above budget {budget}", n=len(m)))
    g, note = _guardrail("HOLD rate", float((m.dec == "HOLD").mean()), float(cfg.get("max_hold_rate", 0.4)))
    ms.append(g)
    notes = [note, "missing decision = ACCEPT; report the trivial all-HOLD / all-REWORK baselines next to your PoC"]
    return EvalOutput(ms, m[["batch_id", "true_error_rate", "est_error_rate", "dec", "is_bad"]].rename(columns={"batch_id": "slice"}), notes)


# ----------------------------------------------------------------------------- T13
def eval_t13(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    gt = pd.read_csv(gt_path)
    pred = pd.read_csv(pred_path)
    _need(pred, ["image_id"], "selected.csv")
    if "rank" in pred.columns:
        pred = pred.sort_values("rank")
    K = int(cfg.get("k", 20))
    sel = list(dict.fromkeys(pred.image_id.astype(str)))[:K]
    s = gt.set_index("image_id").loc[[i for i in sel if i in set(gt.image_id)]]
    rare = gt[gt.is_rare == 1]
    hit = int(s.is_rare.sum())
    uniq = s.scene_group.nunique()
    ms = [
        _m("Rare-case Recall@K", safe_div(hit, len(rare)), "higher", "rare images selected / rare images in pool", hit, len(rare), len(gt), True, notes=f"K={K}"),
        _m("Unique-scene rate in K", safe_div(uniq, len(s)), "higher", "distinct scene groups / selected", uniq, len(s)),
        _m("% near-duplicate in K", safe_div(len(s) - uniq, len(s)), "lower", "selected - distinct scenes / selected", len(s) - uniq, len(s)),
        _m("Junk rate in K", safe_div(int(s.is_junk.sum()), len(s)), "lower", "junk frames / selected", int(s.is_junk.sum()), len(s)),
        _m("Dark-but-common rate in K", safe_div(int(((s.difficulty == "hard") & (s.is_rare == 0) & (s.is_junk == 0)).sum()), len(s)), "lower", "hard-not-rare / selected"),
    ]
    sl = rare.assign(sel=rare.image_id.isin(sel).astype(int)).groupby("rare_tag").sel.agg(["mean", "count"]).reset_index().rename(columns={"rare_tag": "slice", "mean": "recall", "count": "n"})
    return EvalOutput(ms, sl)


# ----------------------------------------------------------------------------- T14
def eval_t14(gt_path: Path, pred_path: Path, cfg: dict) -> EvalOutput:
    fx = _fixture_dir_of(gt_path)
    tax = set(yaml.safe_load((fx / "taxonomy.yaml").read_text())["classes"].values())
    imgs = pd.read_csv(fx / "images.csv").set_index("image_id")
    gt = _split(pd.read_csv(gt_path), cfg, "eval")
    pred = pd.read_csv(pred_path)
    _need(pred, ["image_id", "class", "x", "y", "w", "h"], "predictions.csv (export)")
    split = cfg.get("split", "eval")
    pool = set(imgs.index) if split in (None, "all") else set(imgs.index[imgs.split == split])
    pred = pred[pred.image_id.isin(pool)].reset_index(drop=True)
    iou = float(cfg.get("iou", 0.5))
    r = DE.detection_prf(gt.reset_index(drop=True), pred, iou, True)
    W = pred.image_id.map(imgs.width)
    H = pred.image_id.map(imgs.height)
    invalid = (~pred["class"].astype(str).isin(tax)) | (pred.w <= 0) | (pred.h <= 0) | (pred.x < 0) | (pred.y < 0) | (pred.x + pred.w > W + 0.5) | (pred.y + pred.h > H + 0.5)
    ms = [
        _m(f"Detection F1@IoU{iou}", r["f1"], "higher", "class-aware greedy match", n=len(gt), primary=True),
        _m("Precision", r["precision"], "higher", "TP/(TP+FP)", r["tp"], r["tp"] + r["fp"]),
        _m("Recall", r["recall"], "higher", "TP/(TP+FN)", r["tp"], r["tp"] + r["fn"]),
        _m("Invalid-label rate", safe_div(int(invalid.sum()), len(pred)), "lower", "exported boxes with unknown class or out-of-bounds / exported boxes", int(invalid.sum()), len(pred)),
    ]
    rows = []
    for c, sub in gt.groupby("class"):
        rr = DE.detection_prf(sub.reset_index(drop=True), pred[pred["class"] == c].reset_index(drop=True), iou, True)
        rows.append({"slice": f"class={c}", "n": len(sub), "recall": rr["recall"], "precision": rr["precision"], "f1": rr["f1"]})
    small = gt[(gt.w * gt.h) < 150]
    if len(small):
        rr = DE.detection_prf(small.reset_index(drop=True), pred, iou, True)
        rows.append({"slice": "small_objects(<150px²)", "n": len(small), "recall": rr["recall"], "precision": None, "f1": None})
    return EvalOutput(ms, pd.DataFrame(rows))


TRACKS: dict[str, TrackSpec] = {
    "t01": TrackSpec("t01", "Coverage Planner", "t01_coverage", "gt/verified_tags.csv", "pick.csv", ["clip_id"], eval_t01, {"k": 30}),
    "t02": TrackSpec("t02", "Raw QC Triage", "t02_raw_qc", "gt/labels.csv", "ranked_review.csv", ["image_id", "score"], eval_t02, {"budget": 20, "split": "eval"}),
    "t03": TrackSpec("t03", "Synthetic-vs-Real", "t03_synthetic", "gt/holdout_gt.csv", "qc.csv", ["image_id", "pred_unusable"], eval_t03),
    "t04": TrackSpec("t04", "Sensor Sync Guard", "t04_sensor_sync", "gt/gt_pairs.csv", "pairs.csv", ["frame_id", "imu_t_ms"], eval_t04, {"tol_ms": 50, "split": "eval"}),
    "t05": TrackSpec("t05", "Leakage & Near-Duplicate Guardian", "t05_near_duplicate", "gt/gt_groups.csv", "suspect_pairs.csv", ["img_a", "img_b"], eval_t05),
    "t06": TrackSpec("t06", "Semantic Integrity & Provenance Gate", "t06_release_gate", "gt/gt_releases.csv", "release_decisions.csv", ["release_id", "decision"], eval_t06, {"split": "eval"}),
    "t07": TrackSpec("t07", "Face/Plate Redaction + Review Queue", "t07_redaction", "gt/gt_regions.csv", "redactions.csv", ["image_id", "x", "y", "w", "h"], eval_t07, {"min_coverage": 0.9, "split": "eval", "max_over_redaction": 0.3}),
    "t08": TrackSpec("t08", "Retention & Delete Request Simulator", "t08_deletion", "gt/gt_actions.csv", "actions.csv", ["request_id", "artefact_id", "action"], eval_t08),
    "t09": TrackSpec("t09", "Multi-Market Privacy Decision Gate", "t09_privacy_gate", "gt/gold_decisions.csv", "decisions.csv", ["case_id", "decision"], eval_t09, {"split": "eval", "max_false_hold": 0.5}),
    "t10": TrackSpec("t10", "Domain Shift Radar", "t10_domain_shift", "gt/batch_perf.csv", "shift_scores.csv", ["batch_id", "shift_score"], eval_t10),
    "t11": TrackSpec("t11", "Post-label Error Review Prioritizer", "t11_label_errors", "gt/gt_errors.csv", "ranking.csv", ["item_id", "score"], eval_t11, {"split": "heldout"}),
    "t12": TrackSpec("t12", "Vendor Batch Acceptance", "t12_vendor_batches", "gt/batch_truth.csv", "batch_decisions.csv", ["batch_id", "est_error_rate", "decision", "n_audited"], eval_t12, {"max_hold_rate": 0.4}),
    "t13": TrackSpec("t13", "Active Learning & Rare Case Miner", "t13_rare_mining", "gt/rare_labels.csv", "selected.csv", ["image_id"], eval_t13, {"k": 20}),
    "t14": TrackSpec("t14", "Auto-Annotation + Human QC Exporter", "t14_auto_annotation", "gt/gt_boxes.csv", "predictions.csv", ["image_id", "class", "x", "y", "w", "h"], eval_t14, {"iou": 0.5, "split": "eval"}),
}


def get_track(track: str) -> TrackSpec:
    t = track.lower()[:3]
    if t not in TRACKS:
        raise KeyError(f"unknown track {track!r}; choose one of {sorted(TRACKS)}")
    return TRACKS[t]


def default_gt_path(track: str) -> Path:
    spec = get_track(track)
    return FIXTURES / spec.fixture_dir / spec.default_gt


def infer_track_from_path(path: str | Path | None) -> str | None:
    """'fixtures/t07_redaction/...' -> 't07' (lets the contract commands omit --track)."""
    if not path:
        return None
    parts = Path(path).resolve().parts
    for spec in TRACKS.values():
        if spec.fixture_dir in parts:
            return spec.track
    return None
