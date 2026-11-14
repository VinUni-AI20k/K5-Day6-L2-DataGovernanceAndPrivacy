"""Test của nhóm cho T02: success + edge/failure. Không cần gt/, tự sinh ảnh trong tmp_path."""
import hashlib
import io

import numpy as np
import pandas as pd
import pytest
from PIL import Image, ImageFilter

from src import t02_qc as q

H, W = 180, 320


def _scene(seed: int, base: float = 120.0) -> np.ndarray:
    """Ảnh 'cảnh' có texture + cạnh, đủ nét để Laplacian có ý nghĩa."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W), float(base))
    for _ in range(25):
        y, x = rng.integers(0, H - 30), rng.integers(0, W - 40)
        img[y:y + rng.integers(10, 30), x:x + rng.integers(10, 40)] += rng.uniform(-60, 60)
    img += rng.normal(0, 4, img.shape)
    return np.clip(np.stack([img] * 3, -1), 0, 255).astype(np.uint8)


def _blur(a, r=3):
    return np.asarray(Image.fromarray(a).filter(ImageFilter.GaussianBlur(r)))


def _dark(a, k=0.25):
    return (a * k).astype(np.uint8)


def _glare_patch(a):
    b = a.copy()
    b[20:70, 30:100] = 255   # cháy sáng cục bộ, phần còn lại vẫn nét
    return b


def _jpeg(a, quality=4):
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "JPEG", quality=quality)
    return np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))


@pytest.fixture
def fixture_dir(tmp_path):
    """Dựng thư mục giống fixtures/t02_raw_qc: images/ + images.csv + manifest.csv."""
    (tmp_path / "images").mkdir()
    rows = []
    i = 0

    def add(arr, cam, light, split, tag):
        nonlocal i
        p = f"images/img_{i:03d}_{tag}.png"   # PNG để không dính JPEG artefact ngoài ý muốn
        Image.fromarray(arr).save(tmp_path / p)
        rows.append(dict(image_id=f"img_{i:03d}", path=p, camera_id=cam, light=light, split=split, tag=tag))
        i += 1

    for split, n in (("dev", 8), ("eval", 4)):
        for k in range(n):
            s = 1000 * (split == "eval") + k
            add(_scene(s), "cam_A", "day", split, "clean")
            add(_scene(s + 50, base=35), "cam_A", "night", split, "clean_night")      # đêm thật, không lỗi
            add(_blur(_scene(s + 100), r=1), "cam_B", "day", split, "clean_softcam")  # cam_B mềm, không lỗi
    add(_blur(_scene(2001)), "cam_A", "day", "eval", "blur")
    add(_dark(_scene(2002)), "cam_A", "day", "eval", "dark")
    add(_glare_patch(_scene(2003)), "cam_A", "day", "eval", "glare")
    add(_jpeg(_scene(2004)), "cam_A", "day", "eval", "compression")

    df = pd.DataFrame(rows)
    df.drop(columns="tag").to_csv(tmp_path / "images.csv", index=False)
    man = pd.DataFrame({
        "file_id": df["image_id"], "path": df["path"], "source": "synthetic", "license": "CC0",
        "split": df["split"], "group_id": "test",
        "sha256": [hashlib.sha256((tmp_path / p).read_bytes()).hexdigest() for p in df["path"]],
    })
    man.to_csv(tmp_path / "manifest.csv", index=False)
    return tmp_path, df


# ------------------------------------------------------------------------ success
def test_poc_ranks_all_injected_defects_into_top_and_types_them(fixture_dir):
    d, truth = fixture_dir
    ranked = q.run_poc(q.load_inputs(d), d)
    tags = dict(zip(truth["image_id"], truth["tag"]))
    ranked["tag"] = ranked["image_id"].map(tags)

    top4 = set(ranked.head(4)["tag"])
    assert top4 == {"blur", "dark", "glare", "compression"}
    for t in ("blur", "dark", "glare", "compression"):
        row = ranked[ranked["tag"] == t].iloc[0]
        assert row["pred_defect_type"] == t
        assert row["pred_action"] == "RECAPTURE"


def test_poc_keeps_night_and_soft_camera_images(fixture_dir):
    """Failure mode của đề: ảnh đêm hữu ích và cam_B mềm không được bị báo nhầm."""
    d, truth = fixture_dir
    ranked = q.run_poc(q.load_inputs(d), d)
    tags = dict(zip(truth["image_id"], truth["tag"]))
    benign = ranked[ranked["image_id"].map(tags).isin({"clean_night", "clean_softcam"})]
    assert (benign["pred_action"] == "KEEP").all()


def test_baseline_misses_non_blur_defects(fixture_dir):
    """Baseline 1 ngưỡng Laplacian không nhận ra dark/glare -> lý do cần PoC."""
    d, truth = fixture_dir
    base = q.run_baseline(q.load_inputs(d), d)
    assert set(base["pred_defect_type"]) <= {"blur", "none"}


def test_output_has_contract_columns_and_is_sorted(fixture_dir):
    d, _ = fixture_dir
    out = q.to_output(q.run_poc(q.load_inputs(d), d))
    assert {"image_id", "score"} <= set(out.columns)
    assert out["score"].is_monotonic_decreasing
    assert out["image_id"].is_unique


def test_deterministic(fixture_dir):
    d, _ = fixture_dir
    a = q.run_poc(q.load_inputs(d), d)
    b = q.run_poc(q.load_inputs(d), d)
    pd.testing.assert_frame_equal(a, b)


# -------------------------------------------------------------------- edge/failure
def test_hash_mismatch_fails_loudly(fixture_dir):
    d, truth = fixture_dir
    victim = d / truth["path"].iloc[0]
    Image.fromarray(_scene(999)).save(victim)        # sửa file sau khi manifest đã chốt
    with pytest.raises(ValueError, match="integrity"):
        q.load_inputs(d)


def test_missing_columns_fail(tmp_path):
    pd.DataFrame({"image_id": ["a"], "path": ["x.png"]}).to_csv(tmp_path / "images.csv", index=False)
    with pytest.raises(ValueError, match="thiếu cột"):
        q.load_inputs(tmp_path, verify_hash=False)


def test_degenerate_image_rejected():
    with pytest.raises(ValueError):
        q.image_features(np.zeros((0, 0, 3), dtype=np.uint8))


def test_flat_image_does_not_explode():
    """Ảnh phẳng -> MAD = 0; sàn min_scale phải giữ z hữu hạn."""
    f = q.image_features(np.full((H, W, 3), 128, np.uint8))
    assert all(np.isfinite(v) for v in f.values())


def test_no_dev_split_fails():
    feats = pd.DataFrame({"split": ["eval"], "camera_id": ["a"], "light": ["day"],
                          "f_blur": [1.0], "f_dark": [100.0], "f_glare": [0.0], "f_compression": [0.0]})
    with pytest.raises(ValueError, match="dev"):
        q.fit_reference(feats)
