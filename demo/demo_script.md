# T08 · Kịch bản demo (5 slide, khoảng 5 phút)

Toàn bộ dữ liệu là MOCK. Số liệu lấy từ `reports/t08_selfcheck.md` (gold do nhóm tự gán nhãn, không phải GT của giảng viên).

## Slide 1 — Bài toán

10 yêu cầu xóa trên 212 artefact. Dữ liệu của một người nằm ở 7 loại artefact trên 6 kho. Hai cách sai:
xóa thiếu (còn backup, embedding) và xóa nhầm (legal hold, người khác, bản ở vendor).

## Slide 2 — Baseline thất bại ở cả hai cách

```bash
python -m src.main --track t08 --pipeline src.baseline_t08 --output out/baseline --run-name baseline --offline --seed 42
```

Xóa 1 raw theo filename: Completeness 8/110 = 0.073, **xóa nhầm 2 raw đang bị legal hold** (`a0043`, `a0099`),
để lại 30/30 embedding của người yêu cầu.

## Slide 3 — PoC: một lệnh, 5 bước

```bash
python -m src.main --config configs/lab.yaml --track t08 --output out/poc --run-name poc --offline --seed 42
```

Mở `out/poc/dry_run_plan.csv` (kế hoạch), `review_queue.csv` hoặc `contact_sheet.html` (62 ngoại lệ),
`decision.json` (`HOLD / EXCEPTIONS_PENDING_REVIEW`). Kết quả máy tự chạy: Completeness 102/110 = 0.927, False-delete 0.
Chạy lại lệnh trên lần nữa: `deletion_evidence.json` báo `newly_deleted: 0` (idempotent).

## Slide 4 — Người duyệt và audit

```bash
mkdir -p out/poc_reviewed && cp reports/review_queue.csv out/poc_reviewed/review_queue_reviewed.csv
python -m src.main --config configs/lab.yaml --track t08 --output out/poc_reviewed --run-name poc_reviewed --offline --seed 42
```

8 override (`a0067/a0070`, `a0123/a0126`: cả hai chủ thể đều yêu cầu) → `GO`. Tìm `override:edit` trong `audit_log.jsonl`.
Chốt chặn đáng demo: sửa một dòng legal hold thành `delete` trong file review → pipeline dừng, exit 2.

## Slide 5 — Điều chưa chắc và câu hỏi cho phần debate

- Legal hold có kế thừa xuống bản sao và embedding không? Nếu không: PoC còn nợ 26 lệnh xóa (Completeness 0.750) nhưng
  vẫn không xóa nhầm. Nếu chọn ngược lại mà sai: 26 lần xóa nhầm, không hoàn tác được.
- Artefact chung khi cả hai người đều yêu cầu: máy không tự xóa; người duyệt quyết.
- Lỗi tìm được ở hạ tầng chấm: `eval_t08` đọc audit log bằng encoding mặc định, ghi chú tiếng Việt làm evaluator crash trên Windows.
