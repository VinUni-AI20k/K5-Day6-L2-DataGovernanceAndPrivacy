# T08 · Danh sách ngoại lệ trong dữ liệu (P2 · Data & fixtures)

> Phân tích tĩnh `fixtures/t08_deletion/data_graph.json` (212 artefact, version `mock-graph-1`) và
> `requests.json` (10 yêu cầu). Chỉ đọc input — **không đọc `gt/`**. Đây là bảng nhóm dùng để tự kiểm
> (đáp án nội bộ), không phải ground truth chính thức.

## 1. Tổng quan dữ liệu

| Loại artefact | Số lượng | Ghi chú |
|---|---|---|
| raw_video | 15 | mỗi subject `subj_00…subj_14` có đúng 1 raw, không có parent |
| backup | 15 | con trực tiếp của raw (`.bak`, lưu ở `mock://glacier/`) |
| frame | 45 | con của raw |
| face_crop | 45 | con của frame |
| embedding | 45 | con của face_crop — **định danh được người** |
| annotation | 45 | con của frame |
| training_export | 2 | `a0211` (12 parent, 10 subject), `a0212` (12 parent, 9 subject) |

- 10 yêu cầu xóa: `DR-001…DR-010`, subject `subj_01, 03, 04, 05, 07, 08, 09, 11, 12, 14`; tất cả `identity_verified = true`, deadline 30 ngày.
- Subject **không** yêu cầu xóa: `subj_00, 02, 06, 10, 13` → dữ liệu của họ không được đụng tới.

## 2. Các bẫy đã cài sẵn

| # | Loại ngoại lệ | Artefact | Request bị ảnh hưởng | Xử lý đề xuất |
|---|---|---|---|---|
| E1 | **Legal hold** | `a0043` raw (`LH-2026-03`) | DR-002 (subj_03) | `retain_legal_hold` |
| E2 | **Legal hold** | `a0099` raw (`LH-2026-07`) | DR-005 (subj_07) | `retain_legal_hold` |
| E3 | Bản sao/dẫn xuất của raw bị hold | 14 artefact của subj_03, 15 artefact của subj_07 (backup, frame, crop, embedding, annotation, export) | DR-002, DR-005 | `retain_legal_hold` nếu `legal_hold_inherit = true` |
| E4 | **Không có quyền xóa** (ACL `vendor-x`) | `a0156` backup | DR-008 (subj_11) | `escalate` → chủ dữ liệu vendor-x |
| E5 | **Không rõ nguồn gốc** (`origin_known = false`) | `a0075`, `a0079`, `a0083` embedding | DR-004 (subj_05) | `escalate` |
| E6 | **Frame/annotation chung 2 người** | `a0011`+`a0014` (subj_00, 01) · `a0067`+`a0070` (subj_04, 05) · `a0123`+`a0126` (subj_08, 09) · `a0179`+`a0182` (subj_12, 13) | DR-001, 003, 004, 006, 007, 009 | `escalate` (che/tách phần của subject, không xóa cả frame) |
| E7 | **Training export nhiều subject** | `a0211` (10 subject), `a0212` (9 subject) | mọi request có subject trong export | `escalate` (retrain / unlearning), hoặc `retain_legal_hold` nếu là bản dẫn xuất của raw bị hold |
| E8 | Lineage “lệch subject” | frame chung `a0011` có con `a0012` (face_crop) chỉ của subj_00 | DR-001 | **không** xóa `a0012` — không phải dữ liệu của subj_01 |

## 3. Bảng theo từng request

| Request | Subject | Artefact trong phạm vi | Ngoại lệ |
|---|---|---|---|
| DR-001 | subj_01 | 17 | `a0011`, `a0014` (E6) · `a0212` (E7) |
| DR-002 | subj_03 | 15 | `a0043` (E1) · 14 bản dẫn xuất (E3, gồm `a0211`) |
| DR-003 | subj_04 | 16 | `a0067`, `a0070` (E6) · `a0211`, `a0212` (E7) |
| DR-004 | subj_05 | 18 | `a0067`, `a0070` (E6) · `a0075`, `a0079`, `a0083` (E5) · `a0211`, `a0212` (E7) |
| DR-005 | subj_07 | 16 | `a0099` (E2) · 15 bản dẫn xuất (E3, gồm `a0211`, `a0212`) |
| DR-006 | subj_08 | 14 | `a0123`, `a0126` (E6) |
| DR-007 | subj_09 | 17 | `a0123`, `a0126` (E6) · `a0211` (E7) |
| DR-008 | subj_11 | 15 | `a0156` (E4) · `a0211` (E7) |
| DR-009 | subj_12 | 15 | `a0179`, `a0182` (E6) · `a0211` (E7) |
| DR-010 | subj_14 | 15 | `a0211` (E7) |
| **Tổng** | | **158 cặp (request, artefact)** | |

“Trong phạm vi” = artefact có `subject_id` của người yêu cầu trong `subject_ids`.

## 4. Hai failure mode bắt buộc (đề §5) — bằng chứng trong data

1. **Xóa nhầm dữ liệu thuộc ngoại lệ:** baseline “xóa raw theo tên file” sẽ xóa `a0043`
   (`drive_subj_03_…mp4`, đang `LH-2026-03`) và `a0099` (`LH-2026-07`). Root cause: không đọc trường `legal_hold`.
2. **Chỉ xóa raw, giữ bản sao + embedding:** mỗi subject có 1 raw nhưng ~14–18 artefact; baseline chỉ xóa 1/15.
   Còn sót backup (`mock://glacier/…`) và embedding định danh. Root cause: không duyệt lineage `parent_ids`.

## 5. Đáp án nội bộ để tự kiểm (3 request)

| Request | delete | retain_legal_hold | escalate |
|---|---|---|---|
| DR-002 | 0 | 15 (`a0043` + 14 dẫn xuất) | 0 |
| DR-004 | 11 | 0 | 7 |
| DR-008 | 13 | 0 | 2 (`a0156`, `a0211`) |

(Với `legal_hold_inherit = true`, đã chốt trong `reports/metric_contract.md`.) P2 so output PoC với bảng này ở bước kiểm tra.
