# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 · Raw QC Triage |
| Primary metric (tên đúng như evaluator in ra) | `Defect Recall@B [PRIMARY]` |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image (96 ảnh synthetic 320×180, 24 scene × 4 ảnh) |
| Công thức + numerator / denominator | Recall@B = \|top-B ∩ GT defects\| / \|GT defects\| (num = 20, den = 23 tại B = 20, N = 40 eval) · Precision@B = \|top-B ∩ GT defects\| / B |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | exact `image_id` (string match, không tolerance) |
| Candidate pool cố định | 96 ảnh `fixtures/t02_raw_qc/images/` + `images.csv`; GT eval 40 ảnh (split=eval) |
| Review budget B / K | B = 20 (50% pool eval) |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | `lo` = midpoint clean↔defect gần nhất (bo về phía defect), `hi` = ranh giới severity-2 (bo về phía clean); freeze trên đủ 56 nhãn dev, trước khi nhận eval labels — provenance: `reports/t02_calibration.json` |
| Eval split (không dùng để tune) | `split=eval` — 40 nhãn từ `Downloads/Evalimg.txt`, chuẩn hoá vào `reports/eval_gt_from_Evalimg.txt.csv`; không dùng để tune |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | False alarm in top-B (ảnh clean lọt top-B) theo slice `light`; FN = defect ngoài top-B; bổ sung: Defect-type accuracy (GT defects) |
| Slices sẽ báo cáo (≥2) | `light=day/dusk/night` · `defect=blur/compression/dark/glare` (+ `blur glare` multi-label) |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | N=40 quá nhỏ để bootstrap đáng tin: báo luôn num/den (20/23), không làm tròn; nhắc rõ khi chênh lệch < 2 mẫu giữa baseline và PoC |
| Ngày giờ chốt + người chốt | 2026-11-14 · Nguyễn Thế Tùng (Lead/Integrator) — trước khi chạy eval trên 40 nhãn |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
