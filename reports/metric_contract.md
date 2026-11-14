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
| Candidate pool cố định | 60 ảnh fixtures/t07_redaction; chấm trên split eval (24 ảnh) |
| Review budget B / K | B = 15 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | padding_ratio=0.25, min_conf=0.25, min_mean_conf=0.6; chọn bằng quan sát overlay trên ảnh dev, đóng băng trước khi chạy eval |
| Eval split (không dùng để tune) | eval |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | miss (bỏ sót PII) là lỗi xấu nhất; false alarm đo bằng over-redaction |
| Slices sẽ báo cáo (≥2) | type (face/plate), condition (normal/small/dark/blur/occluded), kích thước vùng |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson CI 95% cho miss rate (số vùng eval nhỏ) |
| Ngày giờ chốt + người chốt | 2026-11-14 — Nguyen Xuan Khanh |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
