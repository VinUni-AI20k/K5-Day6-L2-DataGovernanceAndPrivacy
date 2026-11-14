# T08 · Delete Request Simulator — Phân công nhóm 4 người (PHẦN CHUNG — ai cũng đọc)

File theo người: [A_integrator.md](A_integrator.md) · [B_algorithm.md](B_algorithm.md) · [C_data_qa.md](C_data_qa.md) · [D_review_report.md](D_review_report.md)
Code mẫu ĐÃ CHẠY THỬ (pytest 0 failed, `src.main` exit 0): [code_mau/](code_mau/) — cấu trúc giống hệt repo, ai phụ trách file nào thì chép file đó.

---

## 0. Ai giữ vai nào (khớp `reports/team_contributions.csv`)

Template có 5 vai, nhóm có 4 người → **gộp "Data & fixtures" với "QA / metric" cho C**
(dữ liệu, nhãn tự kiểm và test đều là "bằng chứng đúng/sai"; người gán nhãn ≠ người viết luật (B) → tự kiểm không bị vòng tròn).

| Người | role (ghi vào CSV) | modules_files |
|---|---|---|
| **A** | Lead / Integrator | `configs/lab.yaml; src/pipeline.py; src/t08/store.py` |
| **B** | Core algorithm | `src/t08/graph.py; src/t08/policy.py; src/t08/baseline.py; configs/t08_policy.yaml; tests/test_t08_policy.py` |
| **C** | Data & fixtures + QA / metric | `tools/t08_profile.py; tools/t08_selfcheck_template.py; reports/t08_data_profile.md; reports/selfcheck/; tests/test_t08_pipeline.py; reports/metric_contract.md` |
| **D** | Human review + report | `src/t08/review.py; out/poc/review_queue_reviewed.csv; reports/group_report.md; demo/` |

Xoá dòng "Member 5" trong CSV, ghi chú ở report mục 10: "nhóm 4 người, C kiêm Data & fixtures + QA".

---

## 1. Đề T08 trong 4 ý

### ① Input — `fixtures/t08_deletion/`
| File | Nội dung |
|---|---|
| `requests.json` | 10 yêu cầu xoá DR-001…DR-010: `subject_id`, `deadline` (+30 ngày), `identity_verified` (cả 10 = true) |
| `data_graph.json` | 212 artefact dạng cây: `raw_video` → `backup`, `frame` → `face_crop`, `embedding`, `annotation`; + 2 `training_export`. Trường quyết định: `subject_ids`, `parent_ids`, `legal_hold`, `acl`, `origin_known` |
| `manifest.csv` | sha256 của 2 file trên — sai → exit 2 |
| `gt/` | **CẤM đọc** (exit 5). Repo học viên không có. |

### ② Output — `out/poc/`
| File | Bắt buộc |
|---|---|
| **`actions.csv`** (được chấm) | `request_id, artefact_id, action ∈ {delete, retain_legal_hold, escalate}`, mỗi cặp đúng 1 dòng (158 dòng) |
| `audit_log.jsonl` | mỗi action có dòng log với **`item_id = artefact_id`** (được chấm) |
| `review_queue.csv` → `review_queue_reviewed.csv` | hàng chờ ngoại lệ (56 dòng) + quyết định DPO |
| `decision.json`, `decision_log.csv`, `decisions/<request>.json` | GO/HOLD/REWORK + `reason_code` + `owner` |
| `deletion_plan.csv`, `mock_store_state.json`, `run_info.json` | dry-run, trạng thái kho mock, thông tin chạy |

### ③ Metric
| Metric | Công thức | Ý nghĩa |
|---|---|---|
| **Deletion Completeness** (chính) | đã xoá / phải xoá | xoá đủ |
| **False-delete** (mục tiêu 0) | xoá nhầm ngoại lệ + xoá ngoài phạm vi | không xoá nhầm |
| Exception accuracy | hold/escalate đúng / số ngoại lệ | nhận đúng ngoại lệ |
| Audit completeness | action có log / tổng action | có dấu vết |

### ④ GO / HOLD / REWORK (theo từng request)
| | Nghĩa | reason_code |
|---|---|---|
| **GO** | đóng request: đã xoá mock phần được xoá, mọi ngoại lệ đã được DPO ký | `ERASURE_COMPLETE` / `ERASURE_DONE_EXCEPTIONS_SIGNED` |
| **HOLD** | chưa đóng: còn ngoại lệ chưa ký, hoặc có dữ liệu đang legal hold | `PENDING_DPO_REVIEW` / `LEGAL_HOLD_ACTIVE` |
| **REWORK** | catalog lineage mâu thuẫn (con có subject mà cha không có) | `LINEAGE_INCONSISTENT` (scope `data-catalog`) |

Kết quả code mẫu: trước duyệt 10/10 HOLD; DPO ký 2 ngoại lệ của DR-006 → **DR-006 GO** (request duy nhất không dính legal hold; 9 request còn lại có artefact bị giữ vì training export là hậu duệ của crop bị hold). `data-catalog` REWORK với 4 cảnh báo: `a0011, a0067, a0123, a0179`.

---

## 2. Chính sách — chốt phút 10–30 rồi ĐÓNG BĂNG

Phạm vi: artefact có `subject_id` của request trong `subject_ids` (**lineage để TÌM, `subject_ids` để QUYẾT**). Luật đầu tiên khớp thắng:

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

Kết quả: 158 dòng = 102 delete · 40 retain_legal_hold · 16 escalate. Nguyên tắc: xoá không hoàn tác được; giữ/escalate thì sửa được.

---

## 3. Lịch 240 phút (chi tiết từng bước trong file mỗi người)

| Phút | A · Integrator | B · Algorithm | C · Data + QA | D · Review + Report |
|---|---|---|---|---|
| 0–10 | A1 repo + config | B1 setup | C1 setup | D1 setup |
| 10–30 | A2 chủ trì họp chốt §2 | B2 YAML luật | C2 profile dữ liệu + case catalog | D2 nguồn luật |
| 30–50 | A3 khung pipeline → exit 0 | B3 `graph.py` + B4 baseline | C3 metric contract + khung self-check | D3 report 01 |
| 50–90 | A4 nối B + D, audit plan | B5 `policy.py` | C4 gán nhãn self-check (độc lập với B) | D4 `review.py` |
| 90–145 | A5 MockStore + A6 decide | B6 lineage_warnings + test | C5 test E2E/edge + C6 tự chấm | D5 vòng duyệt DPO |
| 145–170 | A7 clean start | B7 report 02(phần thuật toán)/03 | C7 bảng 1, slice, failure case | D6 report 07/09 |
| 170–180 | **A8 tag `demo-180m`** | slide thuật toán | slide số liệu | D7 gộp slide |
| 180–240 | demo | debate thuật toán | debate metric | pitch |
| +24h | A9 resume demo, report 00/08, **tag `final-24h`** | report 03 | report 02/04/05/06 | D8 SLA + report 01/07/09/11 |

**Mốc:** phút 90 E2E chạy · phút 120 ≥1 ngoại lệ đúng · phút 180 đủ baseline + metric + hàng chờ + failure log.

---

## 4. Lệnh chung (Windows PowerShell)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# PoC
.\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t08 --output out/poc --run-name poc --offline --seed 42
# Baseline
.\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t08 --pipeline src.t08.baseline --output out/baseline --run-name baseline --offline --seed 42
```
Exit code: 0 OK · 2 input/output sai · 3 chưa cài · 4 gọi mạng · 5 đọc gt.

## 5. Quy tắc
1. Không đọc `gt/`, không gọi mạng, luôn `--seed 42 --offline`.
2. Không đổi chính sách / nhãn self-check sau khi nhìn kết quả (buộc đổi → ghi lý do vào report).
3. Không tuyên bố "đạt GDPR / luật VN" — mô phỏng, cần DPO/pháp chế xác nhận.
4. Số trong report lấy từ file script sinh ra.
5. Mỗi người ≥ 1 commit thực chất (khuyến nghị 2); làm trên branch riêng → PR/merge vào `main`.

## 6. Checklist nộp
- [ ] `.gitattributes` + `docs/t08_team/` (hoặc thư mục phân công) đã commit (A)
- [ ] Xoá `out/` → `src.main --offline --seed 42` exit 0 (A)
- [ ] Chạy 2 lần cùng `actions.csv`; resume sau khi ngắt (A + C)
- [ ] DR-006 GO sau khi DPO ký; DR-002/DR-005 HOLD; `data-catalog` REWORK (A + D)
- [ ] `reports/t08_data_profile.md` + `reports/selfcheck/t08_expected.csv` (C)
- [ ] Bảng Baseline vs PoC (self-check, ghi rõ) (C)
- [ ] `pytest -q` 0 failed, có `test_t08_policy.py` (B) + `test_t08_pipeline.py` (C)
- [ ] `review_queue_reviewed.csv` + audit có dòng `review:*` (D)
- [ ] `configs/t08_policy.yaml` có `source` từng luật (B + D)
- [ ] `group_report.md` đủ 00–11 (D chủ trì) · `team_contributions.csv` 4 dòng có SHA
- [ ] Tag `demo-180m`, `final-24h` (A) · 3–5 slide trong `demo/` (D)
