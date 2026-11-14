# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 · Raw QC Triage (ảnh mờ, lóa và thiếu sáng) |
| Primary metric (tên đúng như evaluator in ra) | `Defect Recall@B` |
| Tăng tốt hay giảm tốt? | higher (càng cao càng tốt) |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image (ảnh lái xe synthetic 320×180) |
| Công thức + numerator / denominator | Recall@B = (GT defects in top-B) / (Total GT defects in eval split) = 17 / 20 = 0.8500 |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Khớp chính xác qua cột `image_id` |
| Candidate pool cố định | `fixtures/t02_raw_qc/images.csv` (96 ảnh tổng cộng, 24 cảnh x 4 biến thể) |
| Review budget B / K | B = 20 ảnh (xếp hạng score giảm dần từ cao nhất xuống) |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Chuẩn hóa theo quang học camera (`cam_A` baseline ~1000, `cam_B` baseline ~250) và ngưỡng sáng phân đoạn theo `light` (`day`, `dusk`, `night`). Chỉ hiệu chuẩn ngưỡng trên split `dev` (56 ảnh), không nhìn tập `eval`. |
| Eval split (không dùng để tune) | `split == 'eval'` (40 ảnh, 10 cảnh gốc, 20 ảnh lỗi thực tế) |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | `False alarm in top-B` (tỷ lệ ảnh sạch bị đưa nhầm vào top review gây lãng phí công sức chuyên gia) |
| Slices sẽ báo cáo (≥2) | 1. Điều kiện ánh sáng: `light=day`, `light=dusk`, `light=night`; 2. Nhóm camera: `cam_A` (thấu kính cứng) vs `cam_B` (thấu kính quang học mềm); 3. Loại lỗi: `blur`, `compression`, `dark`, `glare` |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson score interval 95% cho tỷ lệ nhị phân (với $N_{eval}=40$, $N_{pos}=20$, $B=20$) |
| Ngày giờ chốt + người chốt | 2026-11-14 14:00 (GMT+7) — Hoang Sy Khiem (Data Lead / Integrator) |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
