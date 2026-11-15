"""Test T02: đặc trưng, chấm điểm theo nhóm, ảnh hỏng, nhóm nhỏ, tái lập, chạy end-to-end.

Không đọc gt/. Ảnh dùng để thử lấy từ split=dev; lỗi nhân tạo tạo bằng src.common.corruptions.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import main as runner
from src.common import corruptions
from src.common.image_ops import load_rgb
from src.t02_features import features_from_array
from src.t02_scoring import DEFECT_NAMES, build_feature_table, score_images, score_table

FIX = Path("fixtures/t02_raw_qc")


@pytest.fixture(scope="module")
def images():
    return pd.read_csv(FIX / "images.csv")


@pytest.fixture(scope="module")
def dev_imgs(images):
    dev = images[images["split"] == "dev"].head(8)
    return [load_rgb(FIX / p) for p in dev["path"]]


# --------------------------------------------------------------- 1) mỗi bộ phát hiện đổi đúng chiều khi tiêm lỗi
@pytest.mark.parametrize("kind,col,sign", [("blur", "blur_pct", -1), ("dark", "p95", -1),
                                           ("glare", "glare_max_cell", +1), ("jpeg", "blockiness", +1)])
def test_detector_moves_with_injected_defect(dev_imgs, kind, col, sign):
    for im in dev_imgs:
        clean = features_from_array(im)[col]
        bad = features_from_array(corruptions.apply(kind, im, severity=2))[col]
        assert sign * (bad - clean) > 0, f"{kind}: {col} clean={clean:.3f} bad={bad:.3f}"


# --------------------------------------------------------------- 2) ảnh tiêm lỗi có điểm cao hơn bản gốc trong cùng nhóm
def _table_with_injection(images, tmp_path, kind):
    dev = images[images["split"] == "dev"].head(10).copy()
    dev["camera_id"], dev["light"] = "cam_T", "day"           # ép cùng một nhóm
    base = build_feature_table(dev.assign(path=dev["path"].map(lambda p: str((FIX / p).resolve()))), "/", None)
    victim = dev.iloc[0]
    bad_path = tmp_path / f"bad_{kind}.png"
    from PIL import Image
    Image.fromarray(corruptions.apply(kind, load_rgb(FIX / victim["path"]), severity=2)).save(bad_path)
    row = victim.copy()
    row["image_id"], row["path"] = "BAD", str(bad_path)
    bad = build_feature_table(pd.DataFrame([row]), "/", None)
    return pd.concat([base, bad], ignore_index=True)


@pytest.mark.parametrize("kind,expected", [("blur", "blur"), ("dark", "dark"), ("glare", "glare")])
def test_injected_image_scores_higher_and_type_matches(images, tmp_path, kind, expected):
    scored = score_table(_table_with_injection(images, tmp_path, kind))
    bad = scored[scored["image_id"] == "BAD"].iloc[0]
    clean0 = scored[scored["image_id"] == images[images["split"] == "dev"].iloc[0]["image_id"]].iloc[0]
    assert bad["score"] > clean0["score"]
    assert bad["pred_defect_type"] == expected
    assert bad["pred_action"] == "RECAPTURE"


# --------------------------------------------------------------- 3) biên: ảnh hỏng/thiếu không làm sập pipeline
def test_unreadable_image_is_flagged_not_crashing(images):
    sub = images.head(8).copy()
    sub.loc[sub.index[0], "path"] = "images/does_not_exist.jpg"
    scored = score_images(sub, FIX, {})
    bad = scored[scored["image_id"] == sub.iloc[0]["image_id"]].iloc[0]
    assert np.isinf(bad["score"]) and bad["pred_defect_type"] == "unreadable"
    assert scored.loc[scored["image_id"] != bad["image_id"], "score"].notna().all()


# --------------------------------------------------------------- 4) biên: nhóm quá nhỏ -> lùi nhóm, không NaN
def test_tiny_groups_fall_back_without_nan(images):
    sub = images.head(5).copy()
    sub["camera_id"] = ["a", "b", "c", "d", "e"]               # mỗi ảnh một nhóm riêng
    sub["light"] = ["day", "night", "dusk", "day", "night"]
    scored = score_images(sub, FIX, {})
    assert scored["score"].notna().all() and np.isfinite(scored["score"]).all()
    assert (scored["group_used"] == "ALL=ALL").all()           # <6 ảnh mỗi nhóm -> dùng toàn bộ


# --------------------------------------------------------------- 5) tái lập
def test_scoring_is_deterministic(images):
    a = score_images(images, FIX, {})
    b = score_images(images, FIX, {})
    pd.testing.assert_frame_equal(a, b)


# --------------------------------------------------------------- 6) toàn lô: đủ dòng, đủ cột, không NaN
def test_full_batch_invariants(images):
    s = score_images(images, FIX, {})
    assert len(s) == len(images) and s["image_id"].is_unique
    for c in ["score", "pred_defect_type", "pred_action"] + [f"z_{n}" for n in DEFECT_NAMES]:
        assert c in s and s[c].notna().all()
    assert set(s["pred_action"]) <= {"KEEP", "RECAPTURE"}
    assert (s["score"] >= 0).all()


# --------------------------------------------------------------- 7) end-to-end qua src.main (PoC và baseline)
@pytest.mark.parametrize("pipeline", ["src.t02_poc", "src.t02_baseline"])
def test_cli_pipeline_writes_contract_files(tmp_path, pipeline):
    rc = runner.main(["--track", "t02", "--pipeline", pipeline, "--output", str(tmp_path), "--offline", "--seed", "42"])
    assert rc == 0
    pred = pd.read_csv(tmp_path / "ranked_review.csv")
    assert {"image_id", "score"} <= set(pred.columns) and len(pred) == 96 and pred["score"].notna().all()
    q = pd.read_csv(tmp_path / "review_queue.csv")
    assert len(q) == 20
    for f in ["contact_sheet.html", "decision.json", "decision_log.csv"]:
        assert (tmp_path / f).exists()


# --------------------------------------------------------------- 8) sheet gán nhãn dev tuyệt đối không có ảnh eval
def test_dev_sheet_contains_no_eval_images(tmp_path, images):
    from tools import t02_make_dev_sheet
    html = tmp_path / "dev.html"
    assert t02_make_dev_sheet.main(["--out-html", str(html), "--labels", str(tmp_path / "l.csv")]) == 0
    text = html.read_text(encoding="utf-8")
    for iid in images.loc[images["split"] == "eval", "image_id"]:
        assert f'data-item="{iid}"' not in text
    labels = pd.read_csv(tmp_path / "l.csv")
    assert set(labels["image_id"]) == set(images.loc[images["split"] == "dev", "image_id"])


# --------------------------------------------------------------- 9) self-test có nhãn chắc chắn: PoC phải thắng baseline và không bỏ sót loại lỗi nào
def test_selftest_poc_beats_baseline_and_covers_all_defect_types(tmp_path):
    from tools import t02_selftest as st
    from src.t02_baseline import baseline_scores
    df = st.make_set(tmp_path, seed=201, n=120)            # seed 201: chưa dùng khi chọn tham số
    images = pd.read_csv(tmp_path / "images.csv")
    labels = df[["image_id", "is_defect", "defect_type", "severity"]]
    poc = st.evaluate(score_images(images, tmp_path, {}), labels, budget=60)
    base = st.evaluate(baseline_scores(images, tmp_path), labels, budget=60)
    assert poc["recall@B"] > base["recall@B"]
    assert poc["recall@B"] >= 0.9
    for t in st.DEFECTS:
        assert poc[f"recall[{t}]"] >= 0.8, t
