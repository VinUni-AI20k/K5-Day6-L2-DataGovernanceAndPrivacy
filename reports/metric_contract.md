# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 · Raw QC Triage |
| Primary metric (tên đúng như evaluator in ra) | Defect Recall@B |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image |
| Công thức + numerator / denominator | GT defects in top-B / GT defects (tính trên split `eval`) |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Khớp theo `image_id`, sắp xếp giảm dần theo `score` (`mergesort`), lấy top-`B` |
| Candidate pool cố định | `fixtures/t02_raw_qc/images.csv` (96 ảnh từ 24 cảnh gốc; `dev`: 56 ảnh, `eval`: 40 ảnh) |
| Review budget B / K | B = 20 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Baseline: 1 ngưỡng `laplacian_variance` (quantile 0.25 trên `dev`). PoC: chuẩn hoá `ref_var` theo `camera_id` (`cam_A`=800, `cam_B`=400) & `light` (`night` ×1.5), ngưỡng `light` (`day`/`dusk`/`night`), glare 4×4 patch (`max_patch_sat > 0.04`), JPEG 8×8 blockiness (`> 1.4`), ngưỡng flag `max_score >= 0.45` — đóng băng trước khi chạy `eval`. |
| Eval split (không dùng để tune) | `eval` (40 ảnh, chia theo cảnh gốc) |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | `False alarm in top-B` (ảnh sạch lọt top-20 / tổng ảnh sạch) và tỷ lệ bỏ sót lỗi (`1 - Defect Recall@B`) |
| Slices sẽ báo cáo (≥2) | `light` (`day`, `dusk`, `night`), `defect_type` (`blur`, `glare`, `dark`, `compression`), và `camera_id` (`cam_A`, `cam_B`) |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson 95% CI cho tỷ lệ (`Defect Recall@B`, `Precision@B`) trên `eval` (N = 40) |
| Ngày giờ chốt + người chốt | 2026-11-14 21:05 (giờ VN) — huudang-de (Role 4 · QA / Metric) |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
