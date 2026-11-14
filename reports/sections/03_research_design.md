# 03 · Research & design  *(người B — D gộp vào `group_report.md`)*

## References (xem ngày 2026-11-14) và vì sao chọn kỹ thuật

| Nguồn | Dùng để |
|---|---|
| GDPR Art.17 — Right to erasure: https://gdpr-info.eu/art-17-gdpr/ | Quyền xoá (17(1)), nghĩa vụ báo bên nhận dữ liệu (17(2)), ngoại lệ yêu cầu pháp lý (17(3)(e)) → luật R2/R3/R6/R8 |
| Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15 + Nghị định 356/2025/NĐ-CP | Quyền xoá và các trường hợp không được xoá ngay theo pháp luật Việt Nam → luật R2/R3/R8 (cần DPO/pháp chế xác nhận cách áp dụng) |
| California DROP (Delete Request and Opt-out Platform), CPPA | So sánh: một yêu cầu xoá phát tới mọi data broker — tương ứng việc phải lan yêu cầu tới backup/export/vendor (R4, R6) |
| Data Cards Playbook (Google PAIR) | Ghi nguồn gốc, phạm vi dữ liệu → trường `origin_known`, case catalog |

**Kỹ thuật chọn:**
1. **Duyệt đồ thị lineage (BFS theo `parent_ids`)** — dữ liệu của một người nằm rải từ `raw_video` xuống `backup`, `frame`, `face_crop`, `embedding`, `annotation`, `training_export`. Baseline chỉ xoá theo filename nên bỏ sót toàn bộ phần dẫn xuất.
2. **"Lineage để TÌM, `subject_ids` để QUYẾT"** — chỉ đưa vào phạm vi artefact có `subject_id` của request. Duyệt mù cây con sẽ xoá nhầm: `a0011` (frame chung subj_00 + subj_01) có con `a0012` là crop **chỉ của subj_00**.
3. **Bộ luật khai báo (YAML), luật đầu tiên khớp thắng** — tách chính sách khỏi code: DPO/pháp chế đọc và duyệt được `configs/t08_policy.yaml` (mỗi luật có `source`), đổi thứ tự/luật không phải sửa code; `load_policy` báo lỗi ngay nếu `when`/`action` sai.

## Thứ tự ưu tiên luật (`configs/t08_policy.yaml`, chốt trước khi đánh giá)

| # | Điều kiện | Action | reason_code | Vì sao đứng ở vị trí này |
|---|---|---|---|---|
| R1 | `identity_verified = false` | escalate | IDENTITY_NOT_VERIFIED | Chưa xác minh người yêu cầu thì không được động vào dữ liệu nào |
| R2 | artefact có `legal_hold` | retain_legal_hold | LEGAL_HOLD_ACTIVE | Nghĩa vụ pháp lý thắng mọi xử lý vận hành |
| R3 | tổ tiên có `legal_hold` | retain_legal_hold | LEGAL_HOLD_INHERITED | Hold giữ cả bản sao và dữ liệu dẫn xuất (bằng chứng) |
| R4 | ACL không có `data-platform` | escalate | NO_PERMISSION_ACL | Không có quyền thì không xoá được; phải yêu cầu bên giữ (vendor) |
| R5 | `origin_known = false` | escalate | ORIGIN_UNKNOWN | Không chứng minh được nguồn gốc → cần người xác minh |
| R6 | `training_export` | escalate | SHARED_EXPORT_REBUILD | Export chứa 9–10 người; phải rebuild, không xoá cả file |
| R7 | `len(subject_ids) > 1` | escalate | MULTI_SUBJECT_SHARED | Dữ liệu chung với người khác → redact, không xoá |
| R8 | còn lại | delete | ERASURE_REQUEST | Trường hợp thường |

## Data flow

```
requests.json ─┐
data_graph.json┼─► load (kiểm sha256 manifest) ─► scope (BFS + lọc subject_ids)
manifest.csv ──┘                                     │
                                                      ▼
                         policy.decide (R1→R8, first match) ─► deletion_plan.csv (dry-run)
                                                      │
                     ngoại lệ (≠ delete) ─► review_queue (DPO duyệt) ─► apply_review + audit
                                                      │
                     actions.csv ─► MockStore (xoá giả, idempotent) ─► GO / HOLD / REWORK từng request
                                                      │
                     lineage_warnings ─► REWORK scope data-catalog
```

## Thành phần offline
Không dùng model/weights. Chỉ Python + pandas + PyYAML, chạy `--offline --seed 42`; kết quả tất định (không có ngẫu nhiên).

## Trade-offs đã cân nhắc

| Lựa chọn | Được | Mất |
|---|---|---|
| **Hold thừa kế cả cây con** (chọn) vs chỉ backup (ablation) | Không huỷ bằng chứng dẫn xuất khi đang tranh chấp; false-delete = 0 dù GT chọn cách nào | Ít dòng `delete` hơn: **102 / 40 / 16** (delete / retain / escalate) so với **126 / 4 / 28** của ablation → Completeness thấp hơn nếu GT chỉ giữ raw |
| Artefact chung 2 người đều yêu cầu xoá (`a0067`, `a0123`) → vẫn escalate | Mỗi request xử lý độc lập, không phụ thuộc request khác đến hay không; chạy lại ra cùng kết quả | Cần DPO ký thêm 4 dòng |
| Phạm vi theo `subject_ids` vs mọi hậu duệ | Không xoá dữ liệu người khác (dòng ngoài phạm vi bị evaluator tính false-delete) | Phụ thuộc catalog đúng: catalog thiếu subject ở cha (4 cảnh báo `a0011, a0067, a0123, a0179`) → báo REWORK `data-catalog` |
| Khi phân vân → không xoá | Xoá không hoàn tác được; giữ/escalate thì sửa được sau | Completeness có thể thấp hơn lý thuyết |

Số liệu trên tính bằng `tests/test_t08_policy.py::test_action_counts_main_vs_ablation` (158 dòng, 10 request).
