# Metric contract

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 · Raw QC Triage |
| Primary metric (tên đúng như evaluator in ra) | `Defect Recall@B` với `B=20`. Metric phụ là `Precision@B`. |
| Tăng tốt hay giảm tốt? | Recall và precision càng cao càng tốt. Miss và false alarm càng thấp càng tốt. |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | Một ảnh. Ảnh lỗi có nhãn `is_defect=1`. |
| Công thức + numerator / denominator | Tử số chung là số ảnh lỗi thật trong top 20. Mẫu số của recall là tổng số ảnh lỗi thật trong tập `eval`. Mẫu số của precision là số ảnh thực tế trong top 20 (20 khi đủ dự đoán). Ghi N/A nếu mẫu số bằng 0. |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Ghép chính xác bằng `image_id`. Mỗi ảnh có một dòng dự đoán trong `ranked_review.csv`, với `score` càng cao càng ưu tiên. Evaluator lọc ảnh thuộc tập `eval` rồi sắp điểm giảm dần. Khi đồng điểm, giữ thứ tự trong CSV. |
| Candidate pool cố định | Cùng 40 ảnh `eval` của `fixtures/t02_raw_qc/images.csv` cho baseline và PoC. Mỗi lần chạy xuất điểm cho đủ 96 ảnh fixture để evaluator lọc theo split. |
| Review budget B / K | `B=20` cho cả hai phương pháp. Tính metric trên điểm xếp hạng do thuật toán tạo trước khi reviewer can thiệp. |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Baseline dùng phương sai Laplacian toàn ảnh `L`, với `score = 1 / (1 + L)`. Dùng một ngưỡng chung bằng phân vị 20% của `L` trên 56 ảnh `dev` (lần chạy hiện tại: 186,9666). Nếu `L` bằng hoặc thấp hơn ngưỡng thì đề xuất `RECAPTURE`, còn lại đề xuất `KEEP`. Top 20 được chọn theo `score`. Ngưỡng và trọng số của PoC, nếu có, được chọn trên `dev` và chốt trước khi đánh giá. |
| Eval split (không dùng để tune) | `eval` là tập giữ lại, tách khỏi `dev` theo cảnh gốc. Điểm chính thức dùng nhãn của giảng viên qua `src.evaluate`. |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Miss rate = số ảnh lỗi thật nằm ngoài top 20 / tổng số ảnh lỗi thật. False alarm rate = số ảnh tốt lọt vào top 20 / tổng số ảnh tốt. |
| Slices sẽ báo cáo (≥2) | Theo ánh sáng `day`, `dusk`, `night`: recall và false alarm của từng nhóm, dựa trên cùng top 20 toàn tập `eval`. Báo thêm recall theo loại lỗi nếu có mẫu. |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Báo tử số, mẫu số và khoảng Wilson 95% cho các tỷ lệ, ghi rõ đây là khoảng tham khảo vì các ảnh cùng cảnh có thể tương quan. Với nhóm ít mẫu, hiển thị số đếm cùng tỷ lệ. Mẫu số bằng 0 thì ghi N/A. |
| Ngày giờ chốt + người chốt | 15:30+PhạmTrầnAnh     |

Kiểm tra nội bộ trên khoảng 20 ảnh được chọn trước từ `dev` và gán nhãn thủ công trong `reports/mini_gold_dev.csv`. Với phép thử xếp hạng nội bộ, dùng top 5 trên cùng danh sách đã gán nhãn cho baseline và PoC. Báo kết quả này riêng với kết quả chính thức trên `eval`.

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
