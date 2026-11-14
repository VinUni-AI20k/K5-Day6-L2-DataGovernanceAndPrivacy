# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T08 |
| Primary metric (tên đúng như evaluator in ra) |Deletion Completeness |
| Tăng tốt hay giảm tốt? | higher|
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | Cặp (request_id, artefact_id)|
| Công thức + numerator / denominator | Completeness = #cặp GT `delete` mà nhóm `delete` / #cặp GT `delete`. False-delete = #cặp GT `retain_legal_hold`/`escalate` bị nhóm `delete` + #lệnh `delete` cho cặp không có trong GT. Exception handling accuracy = #cặp ngoại lệ xử lý đúng action / #cặp ngoại lệ. Audit trace completeness = #hành động có `item_id` trong `audit_log.jsonl` / #hành động|
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) |Khớp chính xác theo khóa `(request_id, artefact_id)`; cặp GT không có trong `actions.csv` = không xóa; trùng khóa = lỗi |
| Candidate pool cố định |212 artefact `fixtures/t08_deletion/data_graph.json` + 10 yêu cầu `DR-001…DR-010` (`requests.json`), sha256 theo `manifest.csv` |
| Review budget B / K |**Không cắt budget**: mọi cặp `retain_legal_hold` / `escalate` vào `review_queue.csv` (xóa nhầm không phục hồi được) |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) |Không có threshold số. Luật ưu tiên chốt trước: legal hold > danh tính chưa xác minh > không có quyền (`acl` ∉ `[data-platform]`) > không rõ nguồn gốc > nhiều subject > `delete`. **`legal_hold_inherit = true`**: bản sao/dẫn xuất của dữ liệu *của chính subject* đang bị hold cũng `retain_legal_hold`. Tham số ghi trong `configs/tracks/t08.yaml` |
| Eval split (không dùng để tune) |Không có split dev/eval: chấm cả 10 yêu cầu bằng GT ẩn `gt/gt_actions.csv` (chỉ giảng viên). Nhóm tự kiểm bằng đáp án nội bộ 3 request (DR-002, DR-004, DR-008) trong `reports/t08_exceptions.md`; không chỉnh policy sau khi có điểm chính thức |
| Chỉ số lỗi xấu (miss / false alarm / false reject) |**False delete** (xóa dữ liệu đang bị legal hold / ngoài quyền / có người khác) — lỗi nặng nhất, mục tiêu 0. Thứ hai: **miss** = bỏ sót bản sao/embedding (Completeness thấp) |
| Slices sẽ báo cáo (≥2) |(1) theo `expected_action` (evaluator in sẵn); (2) theo loại artefact (raw_video, backup, frame, face_crop, embedding, annotation, training_export); (3) theo từng request DR-001…DR-010 |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) |N nhỏ (10 request, 158 cặp) → **Wilson 95% CI** cho Completeness và Exception handling accuracy + bảng từng request; False-delete báo số đếm tuyệt đối |
| Ngày giờ chốt + người chốt |2026-11-14 · Bui Thanh Tan - reviewer (P1) · soạn bởi P5  |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
