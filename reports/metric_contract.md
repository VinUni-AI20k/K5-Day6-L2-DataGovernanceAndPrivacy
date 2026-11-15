# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 (Raw QC Triage) |
| Primary metric (tên đúng như evaluator in ra) | Defect Recall@20 |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image |
| Công thức + numerator / denominator | (# defects in top-20) / (# total defects in eval pool) |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | exact image_id match; evaluator filters predictions to GT image_id set |
| Candidate pool cố định | 96 images (eval split), fixed by manifest SHA256 |
| Review budget B / K | B=20 (top-20 review queue from 96-image batch) |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | GT-free calibration: synthetic corruption injection on dev split (n=40); threshold sweep based on dev originals vs sev1/sev2 corrupted; badness normalization to [0,1]; weights frozen from validation pool (56 clean + 56 corrupted, round-robin defect types); no tuning on eval |
| Eval split (không dùng để tune) | eval split (n=56) untouched until final evaluation; scene-based split (seed 42) prevents leakage |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Miss = defect not in top-20 (1 - Recall@20); False alarm = clean image in top-20 (1 - Precision@20); batch decision policy: ≥1 confirmed defect → RECAPTURE full batch (96 images) |
| Slices sẽ báo cáo (≥2) | 1) light condition (day/dusk/night); 2) camera_id (cam_A/cam_B); 3) defect_type (blur/dark/glare/compression) if evaluator provides |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson score interval for proportions (Recall@20, Precision@20); report exact counts alongside rates due to small N (eval n=56, budget B=20) |
| Ngày giờ chốt + người chốt | 2026-11-15 00:26 UTC+7, JullyWang (pipeline implementation); parameters frozen from /tmp/t02_probe3.py GT-free calibration |

## Frozen parameters (configs/tracks/t02.yaml::params — merged into the run config via configs/lab.yaml)

**Nguồn duy nhất (single source of truth):** `configs/tracks/t02.yaml`, mục `params:`. `configs/lab.yaml` nối tới file đó bằng `track_config: tracks/t02.yaml`; `src/common/io.py::load_config` deep-merge track file rồi tới `lab.yaml`, nên `ctx.config["params"]` đã chứa đủ mọi giá trị đã đóng băng. `src/pipeline.py::load_params()` chỉ đọc từ đó và **fail loudly** nếu thiếu key hoặc nếu `weights` không cộng lại bằng 1.0 — không còn hằng số nào hard-code trong pipeline (chuyển từ `src/pipeline.py::FROZEN_PARAMS` ngày 2026-11-15, giá trị giữ nguyên; ranking trước/sau refactor giống hệt, max |Δscore| = 0.0).

**Calibration source:** `/tmp/t02_probe3.py` — GT-free synthetic corruption stress test on dev split (n=40), seed 42, 2026-11-15.

**Camera normalization (blur):**
- cam_A median Laplacian variance: 870.7
- cam_B median Laplacian variance: 235.8
- global median (fallback): 710.7
- Normalization: `lap_var / camera_median` → camera-aware sharpness ratio

**Badness thresholds (calibrated on dev originals vs synthetic sev1/sev2):**
- blur_threshold: 0.15 (lap_ratio < 0.15 flags; catches 100% sev1/2, 14% dev flagged)
- blur_range: 0.10 (ramp width [0.15, 0.05] → badness [0, 1])
- dark_threshold: 70.0 (lum_p95 < 70 flags; catches 98% sev1, 11% dev flagged)
- glare_threshold: 0.010 (glare_blob > 0.01 flags; catches 82% sev1/100% sev2, 0% dev flagged)
- glare_range: 0.030 (ramp width [0.01, 0.04] → badness [0, 1])
- jpeg_threshold: 2.20 (blockiness > 2.20 flags; catches 48% sev1/98% sev2, 16% dev flagged)
- jpeg_range: 0.60 (ramp width [2.20, 2.80] → badness [0, 1])

**Aggregation (weighted sum, chosen over max-risk on synthetic validation pool):**
- weights: {blur: 0.35, dark: 0.30, glare: 0.25, jpeg: 0.10}
- Weighted-sum performance on validation pool (112 items: 56 clean + 56 sev1): R@20=0.286, P@20=0.800
- Max-risk performance (same pool): R@20=0.250, P@20=0.700
- Score range: [0, 100]; higher = review first

**Decision policy:**
- pred_action_threshold: 10.0 (score > 10 → pred_action="REVIEW")
- pred_defect_epsilon: 0.05 (max(badness) < 0.05 → pred_defect_type="none", noise filter)

**Decode failures:** score=100.0 (within [0,100] range), pred_defect_type="multiple"

## Baseline comparison

**Baseline (required by T02 spec):** Single-feature Laplacian variance, global threshold, score = -lap_var (higher lap_var → lower score → lower priority). Not implemented separately; PoC multi-defect replaces it.

**PoC multi-defect:** 4 features (blur + dark + glare + compression), camera-aware normalization, badness [0,1] per feature, weighted-sum aggregation, batch decision policy.

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
