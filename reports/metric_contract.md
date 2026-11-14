# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

**Team 6 · bản nháp protocol:** track, pool, budget và seed đã xác định theo đề T02.
Ngưỡng, trọng số, cách báo CI và thời điểm freeze còn chờ nhóm chốt; đây chưa phải cam kết freeze thuật toán.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 · Raw QC Triage · G06 |
| Primary metric (tên đúng như evaluator in ra) | Defect Recall@B; báo kèm Precision@B |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image |
| Công thức + numerator / denominator | Recall: ảnh lỗi thật trong top-B / tổng ảnh lỗi thật trên eval; Precision: ảnh lỗi thật trong top-B / số ảnh được chọn (20 nếu đủ) |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | image_id; evaluator lọc eval rồi sort score giảm dần |
| Candidate pool cố định | fixtures/t02_raw_qc: 96 ảnh; 56 dev / 40 eval; giữ split gốc |
| Review budget B / K | B=20; pool queue review thực tế cần khai báo riêng |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Chỉ chọn trên dev; phương pháp và giá trị ngưỡng/trọng số chưa chốt |
| Eval split (không dùng để tune) | eval; GT chính thức do giảng viên giữ |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Lỗi bị bỏ sót; false alarm trên ảnh sạch, nhất là ảnh đêm |
| Slices sẽ báo cáo (≥2) | light và camera_id; bổ sung defect_type nếu có nhãn |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Chưa chốt — QA đề xuất, lead xác nhận trước eval |
| Ngày giờ chốt + người chốt | Chưa freeze; người phụ trách: Hoàng Trọng Trà – 2A202603342 |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
