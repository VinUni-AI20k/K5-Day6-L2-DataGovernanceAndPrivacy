# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T__ |
| Primary metric (tên đúng như evaluator in ra) | |
| Tăng tốt hay giảm tốt? | higher / lower |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | |
| Công thức + numerator / denominator | |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | |
| Candidate pool cố định | |
| Review budget B / K | |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | |
| Eval split (không dùng để tune) | |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | |
| Slices sẽ báo cáo (≥2) | |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | |
| Ngày giờ chốt + người chốt | |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
