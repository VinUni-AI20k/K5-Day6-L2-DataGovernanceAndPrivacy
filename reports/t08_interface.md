# T08 · Hợp đồng dữ liệu giữa P3 và P4 (chốt phút 10–30)


## 1. Output của `process()` → input của `rank()` / `review()`

Một dòng = một cặp (request, artefact) **có chứa dữ liệu của subject** (artefact có subject trong `subject_ids`).

| Cột | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `request_id` | str | ✔ (contract) | `DR-001…` |
| `artefact_id` | str | ✔ (contract) | `a0001…` |
| `action` | str | ✔ (contract) | `delete` / `retain_legal_hold` / `escalate` |
| `key` | str | ✔ | `"<request_id>:<artefact_id>"` — khóa duy nhất, dùng làm `item_id` trong review queue |
| `subject_id` | str | ✔ | subject của request |
| `type` | str | ✔ | raw_video, backup, frame, face_crop, embedding, annotation, training_export |
| `reason_code` | str | ✔ | xem mục 2 |
| `reason` | str | ✔ | 1 câu cho người đọc |
| `uri` | str | ✔ | `mock://…` — bằng chứng cho reviewer |
| `lineage_depth` | int | | khoảng cách BFS từ artefact gắn subject |
| `lineage_via` | str | | artefact cha trên đường BFS, hoặc `subject_tag` |
| `n_subjects` | int | | số subject trong artefact |
| `held_ancestors` | str | | `"a0043:LH-2026-03;…"`, rỗng nếu không có |
| `deadline` | str (ISO) | ✔ | deadline của request, để xếp ưu tiên |
| `source` | str | ✔ | `pipeline` / `human` (sau review) |

Không trùng `(request_id, artefact_id)` — evaluator sẽ báo lỗi nếu trùng.

## 2. `reason_code` (thứ tự ưu tiên, dừng ở luật đầu tiên khớp)

| Ưu tiên | reason_code | Điều kiện | action |
|---|---|---|---|
| 1 | `LEGAL_HOLD` | artefact có `legal_hold` | `retain_legal_hold` |
| 2 | `LEGAL_HOLD_INHERITED` | `legal_hold_inherit = true` và có tổ tiên **của chính subject** đang bị hold | `retain_legal_hold` |
| 3 | `IDENTITY_NOT_VERIFIED` | request `identity_verified = false` | `escalate` |
| 4 | `NO_DELETE_PERMISSION` | `acl` không giao với `permitted_acl` | `escalate` |
| 5 | `UNKNOWN_ORIGIN` | `origin_known = false` | `escalate` |
| 6 | `MULTI_SUBJECT` | artefact chứa subject khác | `escalate` |
| 7 | `SUBJECT_DATA` | còn lại | `delete` |

## 3. File P4 ghi ra (`out/poc/`)

| File | Nội dung |
|---|---|
| `actions.csv` | contract: `request_id, artefact_id, action` + cột giải thích |
| `review_queue.csv` | mọi dòng `action ≠ delete`, theo `REVIEW_COLUMNS` của `src/common/review.py` |
| `review_queue_reviewed.csv` | do **người thật** (P6) điền, P4 đọc lại |
| `audit_log.jsonl` | mỗi hành động 1 dòng, `item_id = artefact_id` |
| `dry_run_diff.csv` | `would_delete` / `deleted_mock` / `already_deleted` / `kept` |
| `request_summary.csv` | SLA theo request: số artefact, pending review, ngày tới deadline |
| `decision.json` + `decision_log.csv` | GO/HOLD + `reason_code` + `owner` |

## 4. Reviewer decision → action (P4)

| `reviewer_decision` | Kết quả |
|---|---|
| `approve` | giữ action đề xuất |
| `edit` + `override_value ∈ {delete, retain_legal_hold, escalate}` | đổi action; giá trị khác → lỗi (exit 2) |
| `escalate` / `reject` | `escalate` (reject không bao giờ biến thành delete) |
| `skip` | không đổi, vẫn tính là chưa duyệt |
