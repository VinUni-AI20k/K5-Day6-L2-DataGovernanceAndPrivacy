"""Test trên ẢNH THẬT trong fixtures/t02_raw_qc (không đọc gt/).

Không có đáp án nên chỉ kiểm những điều chắc chắn phải đúng: chạy hết 96 ảnh, không mất ảnh,
điểm hợp lệ, chạy lại ra y hệt, và nếu nhóm có data/gold_dev.csv thì PoC không thua baseline trên dev.
Repo thiếu fixtures -> tự skip.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import t02_qc as q

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures" / "t02_raw_qc"
GOLD = ROOT / "data" / "gold_dev.csv"

pytestmark = pytest.mark.skipif(not (FIX / "images.csv").exists(), reason="không có fixtures/t02_raw_qc")


@pytest.fixture(scope="module")
def images():
    return q.load_inputs(FIX)          # kiểm luôn sha256 theo manifest.csv


@pytest.fixture(scope="module")
def poc(images):
    return q.to_output(q.run_poc(images, FIX))


@pytest.fixture(scope="module")
def baseline(images):
    return q.to_output(q.run_baseline(images, FIX))


def test_all_real_images_load_and_hash_ok(images):
    assert len(images) > 0
    assert images["image_id"].is_unique
    for p in images["path"]:
        assert (FIX / p).exists(), p


def test_poc_scores_every_image_exactly_once(images, poc):
    assert sorted(poc["image_id"]) == sorted(images["image_id"])


def test_poc_scores_valid_and_sorted(poc):
    assert np.isfinite(poc["score"]).all()
    assert (poc["score"] >= 0).all()
    assert poc["score"].is_monotonic_decreasing
    assert set(poc["pred_action"]) <= {"KEEP", "RECAPTURE"}
    assert set(poc["pred_defect_type"]) <= {"none", *q.DEFECTS}


def test_poc_is_deterministic_on_real_images(images, poc):
    again = q.to_output(q.run_poc(images, FIX))
    pd.testing.assert_frame_equal(poc.reset_index(drop=True), again.reset_index(drop=True))


def test_poc_finds_more_than_one_defect_type(poc):
    """Baseline chỉ biết 'blur'; PoC trên ảnh thật phải báo được hơn 1 loại lỗi."""
    flagged = poc[poc["pred_action"] == "RECAPTURE"]["pred_defect_type"]
    assert flagged.nunique() >= 2, flagged.value_counts().to_dict()


def test_baseline_runs_on_real_images(images, baseline):
    assert len(baseline) == len(images)
    assert set(baseline["pred_defect_type"]) <= {"blur", "none"}


@pytest.mark.skipif(not GOLD.exists(), reason="chưa có data/gold_dev.csv")
def test_poc_not_worse_than_baseline_on_gold_dev(poc, baseline):
    gold = pd.read_csv(GOLD)
    bad = set(gold.loc[gold["defect_type"].astype(str).str.lower() != "none", "image_id"])
    if not bad:
        pytest.skip("gold dev chưa có ảnh lỗi nào")

    def recall(ranked):
        dev = ranked[ranked["image_id"].isin(gold["image_id"])]
        k = min(20, len(dev))
        return len(bad & set(dev.head(k)["image_id"])) / len(bad)

    r_poc, r_base = recall(poc), recall(baseline)
    print(f"Recall dev: PoC={r_poc:.2f} baseline={r_base:.2f}")
    assert r_poc >= r_base
