# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T13 — Active Learning & Rare Case Miner |
| Primary metric (tên đúng như evaluator in ra) | Rare-case Recall@K (`eval_t13`) |
| Tăng tốt hay giảm tốt? | **higher** |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image (mỗi ảnh trong pool 256×144) |
| Công thức + numerator / denominator | Recall@K = (số ảnh rare thật nằm trong K ảnh được chọn) / (tổng số ảnh rare thật trong pool 200 ảnh). Numerator: \|selected ∩ rare\|. Denominator: \|rare trong pool\|. Rare = 1 trong 4 tag `night_rain`, `occluded_motorbike`, `construction`, `animal` |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Khớp chính xác theo `image_id` (không IoU, không tolerance). `out/selected.csv` có đúng K dòng, cột `image_id` (+ `rank`) |
| Candidate pool cố định | Pool 200 ảnh chưa nhãn, `fixtures/t13_rare_mining/images.csv` + `pool_features.csv` (`brightness_*`, `saturation_mean`, `edge_density`, `emb_00..15`). Pool không đổi giữa baseline và PoC |
| Review budget B / K | B = K = 20 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Không có GT ở phía sinh viên nên **không tune theo nhãn**. Ngưỡng cố định trước khi chạy, dựa trên thống kê robust của pool: `junk_z = 3.0` (robust z của novelty), `noise_z = 3.5` (robust z của `edge_density`), `dedupe_tau` = phân vị 10% khoảng cách tới láng giềng gần nhất, `dark_quantile = 0.25`, `dark_cap = 0.6`, `lambda = 0.5`, `knn = 5`, `n_clusters = 10`, `mode = hybrid` (trọng số novelty:rarity = 0.5:0.5). Các giá trị này không đổi sau khi thấy kết quả eval; ablation `novelty` / `diversity` / `hybrid` được báo cáo đầy đủ, không chọn lại theo kết quả |
| Eval split (không dùng để tune) | Toàn bộ pool 200 ảnh được chấm bằng `gt/rare_labels.csv` do giảng viên giữ (held-out, nhóm không đọc `gt/`). Nhãn tự gán (nếu có) chỉ dùng để ước lượng, không đưa vào bước rank |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | **Miss**: ảnh rare thật không lọt vào K (đặc biệt slice bằng 0). **False alarm**: ảnh trong K không phải rare — gồm junk rate, dark-but-common rate. **Redundancy**: % near-duplicate trong K (duplicate đội lốt rare) |
| Slices sẽ báo cáo (≥2) | `night_rain`, `occluded_motorbike` (target chính, baseline đang bằng 0); thêm `construction`, `animal`; báo riêng từng slice, kể cả khi bằng 0 |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Số rare trong pool nhỏ nên báo **Wilson 95% CI** cho Recall@K và cho từng slice. Baseline random chạy nhiều seed (42..51), báo trung bình ± độ lệch chuẩn và bootstrap CI; PoC chạy seed 42 (xác định) |
| Ngày giờ chốt + người chốt | 15/11/2026 — Hoàng Gia Bảo |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.

**Ghi chú:** các slice mà baseline = 0 (`night_rain`, `occluded_motorbike`) được báo cáo nguyên giá trị tuyệt đối (ví dụ "baseline = 0, PoC = x/y"), không dùng phần trăm cải thiện. Kết quả bằng 0 hoặc âm vẫn được báo cáo.
