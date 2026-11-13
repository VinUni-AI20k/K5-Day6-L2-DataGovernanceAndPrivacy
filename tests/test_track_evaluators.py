"""Every track evaluator: perfect predictions -> best score; empty/naive -> worse; bad schema -> clear error."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.metrics.tracks import TRACKS, default_gt_path

FX = Path("fixtures")
pytestmark = pytest.mark.requires_gt


def primary(res):
    return [m for m in res.metrics if m.primary][0].value


def _perfect(track: str, out: Path) -> Path:
    spec = TRACKS[track]
    gt_path = default_gt_path(track)
    gt = pd.read_csv(gt_path)
    p = out / spec.pred_file
    if track == "t01":
        t = pd.read_csv(FX / "t01_coverage/targets.csv")
        picks = []
        for _, c in t.iterrows():
            m = gt[np.logical_and.reduce([(c[d] == "*") | (gt[d] == c[d]) for d in ["route", "weather", "light", "object"]])]
            if len(m):
                picks.append(m.clip_id.iloc[0])
        pd.DataFrame({"clip_id": list(dict.fromkeys(picks))}).to_csv(p, index=False)
    elif track == "t02":
        gt.assign(score=gt.is_defect + 0.0)[["image_id", "score"]].to_csv(p, index=False)
    elif track == "t03":
        gt.rename(columns={"unusable": "pred_unusable"})[["image_id", "pred_unusable"]].to_csv(p, index=False)
    elif track == "t04":
        gt.rename(columns={"gt_imu_t_ms": "imu_t_ms"})[["frame_id", "imu_t_ms"]].to_csv(p, index=False)
    elif track == "t05":
        from src.metrics.pairs import pairs_from_groups
        prs = sorted(pairs_from_groups(dict(zip(gt.image_id, gt.dup_group_id))))
        pd.DataFrame(prs, columns=["img_a", "img_b"]).to_csv(p, index=False)
        scene = dict(zip(gt.image_id, gt.scene_id))
        scenes = sorted(set(scene.values()))
        test = set(scenes[::3])
        pd.DataFrame({"image_id": gt.image_id, "split": ["test" if scene[i] in test else "train" for i in gt.image_id]}).to_csv(out / "split_manifest.csv", index=False)
    elif track == "t06":
        gt.assign(decision=np.where(gt.is_defective == 1, "HOLD", "PASS"), root_cause=gt.corruption_type)[["release_id", "decision", "root_cause"]].to_csv(p, index=False)
    elif track == "t07":
        gt[["image_id", "x", "y", "w", "h"]].to_csv(p, index=False)
    elif track == "t08":
        gt.rename(columns={"expected_action": "action"})[["request_id", "artefact_id", "action"]].to_csv(p, index=False)
    elif track == "t09":
        gt.rename(columns={"gold_decision": "decision", "gold_reason_codes": "reason_codes"})[["case_id", "decision", "reason_codes"]].to_csv(p, index=False)
    elif track == "t10":
        gt.assign(shift_score=gt.perf_drop, pred_high_risk=gt.high_risk)[["batch_id", "shift_score", "pred_high_risk"]].to_csv(p, index=False)
    elif track == "t11":
        imgs = pd.read_csv(FX / "t11_label_errors/images.csv")
        held = set(imgs.loc[imgs.split == "heldout", "image_id"])
        g = gt[gt.image_id.isin(held)]
        pd.DataFrame({"item_id": g.item_id, "score": 1.0}).to_csv(p, index=False)
    elif track == "t12":
        gt.assign(est_error_rate=gt.true_error_rate, ci_low=gt.true_error_rate - 0.01, ci_high=gt.true_error_rate + 0.01,
                  decision=np.where(gt.is_bad == 1, "REWORK", "ACCEPT"), n_audited=20)[["batch_id", "est_error_rate", "ci_low", "ci_high", "decision", "n_audited"]].to_csv(p, index=False)
    elif track == "t13":
        r = gt.sort_values("is_rare", ascending=False).drop_duplicates("scene_group")
        r[r.is_rare == 1].head(20)[["image_id"]].to_csv(p, index=False)
    elif track == "t14":
        gt[["image_id", "class", "x", "y", "w", "h"]].assign(conf=1.0).to_csv(p, index=False)
    return p


BEST = {"t01": None, "t02": 1.0, "t03": 1.0, "t04": 1.0, "t05": 1.0, "t06": 1.0, "t07": 0.0, "t08": 1.0, "t09": 0.0,
        "t10": 1.0, "t11": 10 / 11, "t12": 0.0, "t13": None, "t14": 1.0}


@pytest.mark.parametrize("track", sorted(TRACKS))
def test_perfect_predictions_score_best(track, tmp_path):
    spec = TRACKS[track]
    p = _perfect(track, tmp_path)
    res = spec.evaluator(default_gt_path(track), p, dict(spec.params))
    v = primary(res)
    assert v is not None
    if BEST[track] is not None:
        assert v == pytest.approx(BEST[track], abs=1e-9), (track, v, res.notes)


def test_t01_missing_cell_caps_coverage(tmp_path):
    # C15 is deliberately absent from the pool: even a perfect planner cannot reach 1.0
    p = _perfect("t01", tmp_path)
    res = TRACKS["t01"].evaluator(default_gt_path("t01"), p, {"k": 30})
    assert 0.85 < primary(res) < 1.0


def test_t13_dup_aware_perfect_selection(tmp_path):
    p = _perfect("t13", tmp_path)
    res = TRACKS["t13"].evaluator(default_gt_path("t13"), p, {"k": 20})
    dup = [m for m in res.metrics if m.name == "% near-duplicate in K"][0].value
    assert dup == 0.0 and primary(res) > 0.5


def test_missing_columns_raise_clear_error(tmp_path):
    bad = tmp_path / "ranked_review.csv"
    pd.DataFrame({"image_id": ["x"]}).to_csv(bad, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        TRACKS["t02"].evaluator(default_gt_path("t02"), bad, {"budget": 20, "split": "eval"})


def test_t09_consent_only_baseline_has_critical_misses(tmp_path):
    cases = sorted((FX / "t09_privacy_gate/cases").glob("*.json"))
    rows = []
    for c in cases:
        d = json.loads(c.read_text())
        rows.append({"case_id": d["case_id"], "decision": "GO" if d["consent"]["obtained"] or d["lawful_basis"] != "unknown" else "HOLD"})
    p = tmp_path / "decisions.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    res = TRACKS["t09"].evaluator(default_gt_path("t09"), p, {"split": "all"})
    assert primary(res) > 0.5   # naive rule lets most risky cases through


def _t12_eval(df, tmp_path):
    p = tmp_path / TRACKS["t12"].pred_file
    df.to_csv(p, index=False)
    spec = TRACKS["t12"]
    return spec.evaluator(default_gt_path("t12"), p, dict(spec.params))


def test_t12_rejects_unknown_decision(tmp_path):
    df = pd.read_csv(_perfect("t12", tmp_path)).assign(decision="MAYBE")
    with pytest.raises(ValueError, match="decision must be one of"):
        _t12_eval(df, tmp_path)


def test_t12_rejects_duplicate_batches(tmp_path):
    df = pd.read_csv(_perfect("t12", tmp_path))
    with pytest.raises(ValueError, match="duplicate"):
        _t12_eval(pd.concat([df, df.head(1)]), tmp_path)


def test_t12_rejects_blank_estimate(tmp_path):
    df = pd.read_csv(_perfect("t12", tmp_path))
    df.loc[1:, "est_error_rate"] = np.nan
    with pytest.raises(ValueError, match="est_error_rate"):
        _t12_eval(df, tmp_path)


def test_t12_missing_batches_cannot_lower_mae(tmp_path):
    df = pd.read_csv(_perfect("t12", tmp_path))
    res = _t12_eval(df.head(1), tmp_path)
    assert primary(res) > 0.0
