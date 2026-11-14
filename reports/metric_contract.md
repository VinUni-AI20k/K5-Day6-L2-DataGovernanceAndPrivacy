# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T08 · Retention & Delete Request Simulator (`fixtures/t08_deletion`) |
| Primary metric (tên đúng như evaluator in ra) | `Deletion Completeness` |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | cặp `(request_id, artefact_id)` — N = 158 cặp trên 10 request (DR-001…DR-010) |
| Công thức + numerator / denominator | số cặp có `expected_action = delete` mà pred `action = delete` / số cặp có `expected_action = delete` |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | khớp chính xác theo khoá `(request_id, artefact_id)`; cặp thiếu trong pred tính là sai; pred `delete` cho cặp không có trong GT tính là **xoá ngoài phạm vi** (cộng vào False-delete) |
| Candidate pool cố định | mọi artefact có `subject_id` của request trong `subject_ids` (lineage chỉ để TÌM, `subject_ids` để QUYẾT) → 158 cặp; không thêm/bớt sau khi chốt |
| Review budget B / K | không giới hạn: mọi dòng `retain_legal_hold` / `escalate` đều vào `review_queue.csv` để DPO ký |
| Seed | 42 (`--offline --seed 42`) |
| Threshold policy (chọn trên dev như thế nào) | không có ngưỡng số; dùng chính sách luật R1–R8 (bảng dưới), luật đầu tiên khớp thắng, chốt phút 30 và đóng băng trong `configs/t08_policy.yaml` |
| Eval split (không dùng để tune) | không chia dev/eval: chỉ 10 request, không có tham số để tune; luật chốt trước khi nhìn bất kỳ kết quả chấm nào |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | **`False-delete count`** (mục tiêu = 0; = ngoại lệ bị xoá + xoá ngoài phạm vi) — xoá không hoàn tác được nên lỗi này nặng nhất. Phụ: `Exception handling accuracy`, `Audit trace completeness`, latency (`runtime_seconds` trong `run_info.json`) |
| Slices sẽ báo cáo (≥2) | (1) theo `expected_action` (delete / retain_legal_hold / escalate); (2) theo `artefact_type` (raw_video, backup, frame, face_crop, embedding, annotation, training_export) |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson 95% CI cho Deletion Completeness và Exception accuracy (N = 102 và 56) |
| Ngày giờ chốt + người chốt | 2026-11-14 · C (Data & fixtures + QA / metric) — chốt trước khi chạy `src.evaluate` lần nào |

## Chính sách đã chốt (copy `00_CHUNG.md` §2)

Phạm vi: artefact có `subject_id` của request trong `subject_ids`. Luật đầu tiên khớp thắng.

| # | Điều kiện | Action | reason_code |
|---|---|---|---|
| R1 | `identity_verified = false` | escalate | IDENTITY_NOT_VERIFIED |
| R2 | artefact có `legal_hold` | retain_legal_hold | LEGAL_HOLD_ACTIVE |
| R3 | tổ tiên có `legal_hold` (cả cây con) | retain_legal_hold | LEGAL_HOLD_INHERITED |
| R4 | ACL không có `data-platform` | escalate | NO_PERMISSION_ACL |
| R5 | `origin_known = false` | escalate | ORIGIN_UNKNOWN |
| R6 | `training_export` | escalate | SHARED_EXPORT_REBUILD |
| R7 | `len(subject_ids) > 1` | escalate | MULTI_SUBJECT_SHARED |
| R8 | còn lại | delete | ERASURE_REQUEST |

Kỳ vọng (theo chính sách, trước khi chạy): 158 dòng = 102 delete · 40 retain_legal_hold · 16 escalate.

## Giới hạn

- **Repo học viên không có `fixtures/t08_deletion/gt/`** → mọi số nhóm báo cáo được chấm trên **bộ self-check**
  `reports/selfcheck/t08_expected.csv` do C gán tay, độc lập với người viết luật (B). Self-check phản ánh
  *chính sách của nhóm*, **không phải GT của giảng viên**; đạt 1.0 trên self-check không chứng minh đúng luật thật.
- Lệnh chính thức (chạy khi giảng viên chép `gt/` vào):
  `python -m src.evaluate --track t08 --pred out/poc/actions.csv --out reports/metrics_poc.json`
- Mô phỏng giáo dục; không tuyên bố "đạt GDPR / luật VN" — cần DPO/pháp chế xác nhận.
