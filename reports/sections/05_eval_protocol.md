# 05 · Evaluation protocol (phần C — QA / metric)

Chi tiết cam kết: `reports/metric_contract.md` (commit `docs: t08 metric contract (frozen)` — trước mọi lần chạy `src.evaluate`).

- **Đơn vị:** cặp `(request_id, artefact_id)`, N = 158 / 10 request; ghép pred ↔ self-check theo khoá chính xác.
- **Primary:** `Deletion Completeness` = số cặp `expected=delete` mà pred `delete` / số cặp `expected=delete` (102). Higher is better.
- **Lỗi nặng nhất:** `False-delete count` = ngoại lệ (expected ≠ delete) bị pred `delete` + pred `delete` ngoài phạm vi; mục tiêu 0 vì xoá không hoàn tác được.
- **Phụ:** `Exception handling accuracy` (/56), `Audit trace completeness` (action có `item_id` trong `audit_log.jsonl` / action), latency (`runtime_seconds` trong `run_info.json`).
- **Threshold / budget:** không có ngưỡng; chính sách R1–R8 chốt phút 30 (`configs/t08_policy.yaml` v1.0). Review budget không giới hạn — mọi ngoại lệ (56) vào `review_queue.csv`.
- **Độ bất định:** Wilson 95% CI (N nhỏ) — xem `reports/selfcheck/t08_slices.md`.
- **Độc lập của bộ chấm:** C gán `t08_expected.csv` bằng tay từ chính sách + case catalog, không đọc output pipeline / code của B; đếm kiểm 102/40/16 trước khi chấm. Không sửa nhãn sau khi thấy kết quả.
- **Tái lập:** seed 42, `--offline`; chạy PoC 2 lần → `actions.csv` giống hệt byte (`test_idempotent_two_runs`); crash giữa chừng → resume bỏ qua 5 artefact đã xoá (`test_store_resume_after_crash`).
- **Test (`tests/test_t08_pipeline.py`, 11 test):** contract output, audit đủ, idempotent, legal hold không bị xoá, không xoá dữ liệu người khác, baseline chỉ raw, input bị sửa → exit 2, `identity_verified=false` → escalate cả request, resume sau crash, `data-catalog` REWORK với 4 cảnh báo, DR-006 GO sau khi DPO ký (DR-002/DR-005 vẫn HOLD).

Lệnh chấm self-check:
```powershell
$GT = "reports/selfcheck/t08_expected.csv"
.\.venv\Scripts\python.exe -m src.evaluate --track t08 --gt $GT --pred out/baseline/actions.csv --run-name baseline --out reports/selfcheck/metrics_baseline_selfcheck.json
.\.venv\Scripts\python.exe -m src.evaluate --track t08 --gt $GT --pred out/poc/actions.csv --run-name poc --out reports/selfcheck/metrics_poc_selfcheck.json
.\.venv\Scripts\python.exe -m src.compare reports/selfcheck/metrics_baseline_selfcheck.json reports/selfcheck/metrics_poc_selfcheck.json --out reports/selfcheck/table1_selfcheck.md
.\.venv\Scripts\python.exe -m tools.t08_slices
```
