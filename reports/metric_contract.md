# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T13 · Active Learning & Rare Case Miner |
| Primary metric (tên đúng như evaluator in ra) | Rare-case Recall@K |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image (tập K ảnh được chọn đưa vào gán nhãn) |
| Công thức + numerator / denominator | rare images selected / rare images in pool (Tử số: số ca hiếm thật trong K; Mẫu số: tổng ca hiếm trong pool 200 ảnh) |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Khớp chính xác theo `image_id` trong `selected.csv` |
| Candidate pool cố định | 200 ảnh unlabelled (`fixtures/t13_rare_mining/images.csv`) |
| Review budget B / K | K = 20 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Đa tiêu chí: Novelty (khoảng cách outlier/kNN trong feature + embedding), Diversity (k-center greedy/phash chống near-duplicate), và Lọc junk/dark-common; đóng băng trọng số trước khi eval |
| Eval split (không dùng để tune) | Toàn bộ pool 200 ảnh (đánh giá mù trên nhãn ẩn GT) |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Junk rate in K (chọn phải ảnh rác), % near-duplicate in K (chọn nhiều ảnh cùng cảnh), Dark-but-common rate in K (ảnh tối bình thường bị chọn) |
| Slices sẽ báo cáo (≥2) | 4 nhóm rare tag: `night_rain`, `occluded_motorbike`, `construction`, `animal` |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson score 95% CI cho tỷ lệ Rare Recall@K |
| Ngày giờ chốt + người chốt | 2026-11-14 07:55 UTC · Nguyen Hoang Dieu |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
