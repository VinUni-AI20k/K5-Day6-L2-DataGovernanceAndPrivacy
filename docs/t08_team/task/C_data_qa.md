# Người C — Data & fixtures + QA / metric

**Sở hữu:** `tools/t08_profile.py` · `tools/t08_selfcheck_template.py` · `reports/t08_data_profile.md` · `reports/selfcheck/` · `tests/test_t08_pipeline.py` · `reports/metric_contract.md` · report 02, 04, 05, 06
**Code mẫu:** [code_mau/tools/](code_mau/tools/) · [code_mau/tests/test_t08_pipeline.py](code_mau/tests/test_t08_pipeline.py)

> Vì sao C giữ cả Data lẫn QA: người **gán nhãn tự kiểm** phải khác người **viết luật** (B),
> nếu không bộ tự kiểm chỉ chép lại output của code → luôn đúng 100%, vô nghĩa.

---

## C1 · Phút 0–10 — Setup
```powershell
git pull
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tools.preflight
.\.venv\Scripts\python.exe -m pytest -q
git checkout -b c/data-qa
```

## C2 · Phút 10–30 — Data & fixtures: hồ sơ dữ liệu + case catalog

1. Kiểm provenance:
   ```powershell
   .\.venv\Scripts\python.exe -m tools.verify_manifests
   ```
   Nếu t08 báo `hash_mismatch` → lỗi CRLF, báo A (A1).
2. Chép [code_mau/tools/t08_profile.py](code_mau/tools/t08_profile.py) vào `tools/`, chạy:
   ```powershell
   .\.venv\Scripts\python.exe -m tools.t08_profile          # tự ghi reports/t08_data_profile.md (UTF-8)
   ```
   Kết quả: số artefact theo type, **bảng case catalog** (16 artefact ngoại lệ), cây con của 2 raw bị hold, số artefact trong phạm vi mỗi request.
3. Mở `data_graph.json`, nhìn tận mắt 3 case và ghi chú vào profile:
   - `a0011` (frame chung subj_00 + subj_01) — con `a0012` chỉ có subj_00.
   - `a0156` backup ACL `vendor-x`.
   - `a0211` export 10 người, có cha là `a0046` (crop của subj_03 bị hold).
4. Gửi case catalog cho cả nhóm (B dùng để viết luật, D dùng để tra luật).
5. Commit `docs(t08): data profile + case catalog`.

## C3 · Phút 30–50 — Metric contract + khung bộ tự kiểm

1. Điền `reports/metric_contract.md`:
   - Primary: Deletion Completeness = must-delete deleted / must-delete.
   - Secondary: False-delete (mục tiêu 0, tính cả xoá ngoài phạm vi), Exception accuracy, Audit completeness, latency (`run_info.json`).
   - Chính sách R1–R8 đã chốt (copy từ `00_CHUNG.md` §2), seed 42, N = 158 dòng / 10 request.
   - Ghi rõ: **repo học viên không có gt/** → báo số trên bộ self-check, nói rõ giới hạn.
   - **Commit trước khi chạy bất kỳ đánh giá nào** (`docs: t08 metric contract (frozen)`).
2. Chép [code_mau/tools/t08_selfcheck_template.py](code_mau/tools/t08_selfcheck_template.py), chạy:
   ```powershell
   .\.venv\Scripts\python.exe -m tools.t08_selfcheck_template
   ```
   → `reports/selfcheck/t08_expected_TODO.csv` (158 dòng, cột `expected_action` trống, có sẵn type/legal_hold/acl/origin/parent để dễ gán).

> ⚠ **Không** đặt file vào `fixtures/t08_deletion/gt/`: GT guard chặn đọc, và `tests/conftest.py`
> thấy có gt/ ở 1 track mà không có ở 13 track khác → pytest dừng với "instructor overlay is incomplete".

## C4 · Phút 50–90 — Gán nhãn bằng tay (KHÔNG nhìn output của pipeline)

1. Mở `t08_expected_TODO.csv` bằng Excel. Điền `expected_action` theo chính sách đã chốt + case catalog:
   - Dòng của DR-002 (subj_03) và DR-005 (subj_07): toàn bộ `retain_legal_hold` (raw bị hold + cả cây con).
   - `a0211`, `a0212` ở mọi request: `retain_legal_hold` (hậu duệ của crop bị hold).
   - `a0156` → `escalate`; `a0075/a0079/a0083` → `escalate`.
   - Mọi artefact `n_subjects > 1` còn lại → `escalate`.
   - Còn lại → `delete`.
   - Cột `label_note`: ghi lý do ngắn cho các dòng ngoại lệ.
2. Lưu thành `reports/selfcheck/t08_expected.csv` (giữ 3 cột bắt buộc `request_id, artefact_id, expected_action`; các cột khác để nguyên cũng được).
3. Đếm lại: kỳ vọng 102 / 40 / 16. Lệch → xem lại nhãn **trước khi** chạy PoC lên nó.
4. Commit `data(t08): hand-labelled self-check set (frozen)`.

## C5 · Phút 50–145 — Test end-to-end + edge case

Chép [code_mau/tests/test_t08_pipeline.py](code_mau/tests/test_t08_pipeline.py). 9 test:
| Test | Loại | Kiểm |
|---|---|---|
| `test_poc_contract` | success | exit 0, đủ cột, không trùng cặp, action hợp lệ, đủ file output |
| `test_every_action_has_audit_entry` | success | mọi `artefact_id` có trong audit log |
| `test_idempotent_two_runs` | protocol | chạy 2 lần → `actions.csv` giống hệt |
| `test_legal_hold_never_deleted` | failure mode 1 | a0043/a0099 và cả DR-002 không có `delete` |
| `test_other_persons_data_not_deleted` | failure mode 1 | a0011 escalate; không dòng nào ngoài phạm vi subject |
| `test_baseline_only_raw` | baseline | 10 dòng, toàn raw |
| `test_tampered_input_fails` | edge | sửa `requests.json` mà không sửa manifest → exit 2 |
| `test_unverified_identity_escalates_everything` | edge (mini fixture) | `identity_verified=false` → cả request escalate |
| `test_store_resume_after_crash` | reliability | crash sau 5 lần xoá → chạy lại skip 5, tổng đúng |

Mini fixture: hàm `_copy_fixture()` chép fixture vào thư mục tạm, sửa request, **tạo manifest mới** bằng `build_manifest` — không đụng fixture gốc.
```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_t08_pipeline.py
.\.venv\Scripts\python.exe -m pytest -q                      # toàn bộ, 0 failed
```
Commit `test(t08): e2e, idempotency, edge cases, resume`.

## C6 · Phút 90–145 — Tự chấm bằng evaluator chính thức trên bộ self-check

```powershell
$GT = "reports/selfcheck/t08_expected.csv"
.\.venv\Scripts\python.exe -m src.evaluate --track t08 --gt $GT --pred out/baseline/actions.csv --run-name baseline --out reports/selfcheck/metrics_baseline_selfcheck.json
.\.venv\Scripts\python.exe -m src.evaluate --track t08 --gt $GT --pred out/poc/actions.csv --run-name poc --out reports/selfcheck/metrics_poc_selfcheck.json
.\.venv\Scripts\python.exe -m src.compare reports/selfcheck/metrics_baseline_selfcheck.json reports/selfcheck/metrics_poc_selfcheck.json --out reports/selfcheck/table1_selfcheck.md
```
Số baseline đã đo thử: Completeness **0.078** (8/102) · False-delete **2** (a0043, a0099) · Exception acc **0**.
PoC phải: Completeness cao, False-delete **0**. Nếu PoC = 1.0 tuyệt đối → ghi rõ "self-check theo đúng chính sách nhóm, không phải GT giảng viên".

Ablation (B làm file policy biến thể): chạy PoC với `configs/t08_policy_backup_only.yaml` vào `out/ablation/`, chấm cùng self-check → ghi số delete/retain/escalate và metric.

Lệnh chính thức (`reports/metrics_baseline.json`, `metrics_poc.json`) chỉ chạy được khi giảng viên chép gt/ — để nguyên lệnh trong report.

## C7 · Phút 145–170 — Bảng 1, slice, 2 failure case
1. `table1_selfcheck.md` → report mục 04 (Baseline vs PoC), kèm câu "cùng data, seed 42, 158 dòng".
2. Slice: accuracy theo `expected_action` (evaluator in sẵn) + theo `artefact_type` (tự groupby) → mục 06.
3. **Failure case 1 — xoá nhầm ngoại lệ:** baseline xoá `a0043` (raw subj_03, `LH-2026-03`). Bằng chứng: dòng trong `out/baseline/actions.csv` + bản ghi trong `data_graph.json`. Root cause: không đọc `legal_hold`.
4. **Failure case 2 — chỉ xoá raw:** DR-001 baseline xoá 1/17 artefact; còn backup `a0016`, embedding của subj_01. Root cause: không duyệt lineage.
5. Latency: `runtime_seconds` trong `out/*/run_info.json` (ms / 158 dòng).
6. 1 slide số liệu.

## +24h
- Test thêm: GO sau khi ký (dùng file reviewed mẫu), REWORK data-catalog.
- Report mục 02 (Data & provenance: nguồn synthetic CC0, manifest sha256, vì sao không chia dev/eval — 10 request, mọi luật đã chốt trước), 04, 05 (protocol: seed, chạy 2 lần, self-check độc lập), 06.

**Commit gợi ý:** `docs(t08): data profile` · `docs: metric contract` · `data(t08): self-check labels` · `test(t08): e2e + edge` · `docs: table1 + failure cases`
