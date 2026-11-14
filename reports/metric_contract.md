# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T14 |
| Primary metric (tên đúng như evaluator in ra) | `Detection F1@IoU0.5` |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | box (trên 20 ảnh eval) |
| Công thức + numerator / denominator | F1 = 2PR/(P+R); P = TP/(TP+FP), R = TP/(TP+FN); TP tính trên box đúng class |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | IoU ≥ 0.5, greedy, phải đúng class (`src/metrics/detection.py::match_detections`) |
| Candidate pool cố định | 60 ảnh `fixtures/t14_auto_annotation` (dev/eval tách sẵn trong `images.csv`), 227 box ≥ threshold |
| Review budget B / K | B = 30 box (`configs/tracks/t14.yaml`) |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | `conf_threshold` = 0.25 theo config; chỉ chỉnh trên split dev, không nhìn eval |
| Eval split (không dùng để tune) | `split=eval` (20 ảnh) |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Invalid-label rate sau export (↓, mục tiêu 0); miss box nhỏ (recall slice small) |
| Slices sẽ báo cáo (≥2) | recall theo class (car / pedestrian / motorbike / sign); small objects < 150 px² |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | bootstrap theo ảnh (20 ảnh eval); ghi rõ N nhỏ, không kết luận Δ nhỏ |
| Ngày giờ chốt + người chốt | |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
