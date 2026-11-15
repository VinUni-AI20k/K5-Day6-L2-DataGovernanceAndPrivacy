# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T07 Face/Plate Redaction + Review Queue |
| Primary metric (tên đúng như evaluator in ra) | PII Miss Rate (guardrail: Over-redaction rate ≤ 0.3) |
| Tăng tốt hay giảm tốt? | lower |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | region (face/plate) |
| Công thức + numerator / denominator | #vùng GT có pixel coverage < 0.9 / #vùng GT; over-redaction = pixel che ngoài GT / pixel che |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Theo image_id; coverage tính theo pixel của vùng GT được các hộp che phủ, không dùng IoU |
| Candidate pool cố định | 60 ảnh fixtures/t07_redaction; chấm chính thức trên split eval (24 ảnh, GT của giảng viên). Tự kiểm của nhóm: 12 ảnh dev có nhãn trong `reports/mini_gt/` (64 vùng), chạy với `--split dev` |
| Review budget B / K | B = 15 ảnh (hàng chờ xếp theo ảnh; mỗi ảnh hiện toàn bộ khung trước/sau) |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Bản chốt 2026-11-14 (bộ dò cũ): padding_ratio=0.25, min_conf=0.25, min_mean_conf=0.6. **Bản chốt lại 2026-11-15 16:20 (bộ dò `src/t07_detector.py` v1.0.0)**, ghi trong `configs/lab.yaml`: face_pad=0.03 + 1 px, plate_pad=0.02 + 1 px, blur_grow=0.12, min_conf=0.30, blur_laplacian_threshold=60, dark_mean_threshold=55, high_risk_score_threshold=0.55, max_redacted_area_frac=0.35. Chọn bằng quan sát overlay và mini-GT trên **dev**; đóng băng trước khi có bất kỳ kết quả nào trên GT eval (nhóm không có GT eval). Lý do chốt lại: bộ dò được thay, và padding 0.18–0.30 ban đầu cho over-redaction 0,535 trên mini-GT dev (FAIL guardrail) |
| Eval split (không dùng để tune) | eval |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | miss (bỏ sót PII) là lỗi xấu nhất; false alarm đo bằng over-redaction |
| Slices sẽ báo cáo (≥2) | type (face/plate), condition (normal/small/dark/blur/occluded), kích thước vùng (small < 200 px², medium < 700 px², large) |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson CI 95% cho miss rate (`python -m tools.t07_selfcheck`, ghi ra `reports/t07_selfcheck_slices.csv`) |
| Ngày giờ chốt + người chốt | 2026-11-14 — Nguyen Xuan Khanh (bản đầu) · 2026-11-15 16:20 (giờ VN) — Huynh Nhat Quang (chốt lại tham số theo bộ dò mới, không đổi metric, split hay budget) |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.

**Baseline đã khai báo:** (1) `baseline` = bộ dò ngưỡng màu chung + blur cố định, không queue, không người duyệt (`src/t07_baseline.py`); tham khảo thêm `baseline_haar` = Haar cascade mặc định của OpenCV, chỉ chạy được khi OpenCV có `CascadeClassifier` (`src/t07_baseline_haar.py`); (2) `baseline_blurall` = che toàn ảnh (`src/t07_baseline_blurall.py`), baseline tầm thường bắt buộc báo kèm.

**Giới hạn của mini-GT:** 64 vùng trên 12 ảnh dev, gán nhãn theo cách "pre-annotation bằng bộ dò + người kiểm tra từng ảnh trên lưới tọa độ, thêm tay các vùng bị sót" (cột `label_source`). Cách này lạc quan cho PoC (vùng PoC đã dò đúng thì coverage gần như chắc chắn đạt), nên chỉ dùng để tự kiểm và so sánh tương đối với baseline; điểm chính thức là GT ẩn của giảng viên.
