# Day 06 · Data Lab · T14 Auto-Annotation + Human QC (AI20K · Data Track)

Repo cho bài lab **T14 - Auto-Annotation + Human QC Exporter**: tự gán nhãn bounding box, xếp hạng box đáng ngờ,
người review (CVAT / contact sheet), xuất `predictions.csv` và ra quyết định GO/HOLD/REWORK.
Đề bài chi tiết: `docs/tracks/T14.md`. Hướng dẫn CVAT: `docs/HUONG_DAN_GAN_NHAN_CVAT.md`.

> Repo **không** chứa ground truth. Tài liệu học tập, không thay tư vấn pháp lý.

## 1. Quickstart (offline)

```bash
# Python 3.11-3.13 (đã test trên 3.13)
make setup        # venv + pip install -r requirements.txt
make preflight    # kiểm tra môi trường, fixture, offline guard, không lộ token
make test         # pytest -q (0 failed)
make baseline     # baseline: ngưỡng mặc định, không review  -> out/baseline/
make run          # PoC (src/pipeline.py)                    -> out/poc/
```

Config nhóm: `configs/lab.yaml` (`group_id`, `owner`, `seed`); default T14: `configs/tracks/t14.yaml`.

## 2. Contract lệnh

| Lệnh | Điều kiện PASS |
|---|---|
| `python -m src.main --track t14 --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42` | exit 0, sinh `predictions.csv` + review log + decision |
| `python -m src.main --track t14 --pipeline src.baseline_t14 --output out/baseline --run-name baseline --offline` | baseline |
| `python -m src.evaluate --track t14 --pred out/poc/predictions.csv --run-name poc --out reports/metrics_poc.json` | giảng viên chạy (cần `gt/`); repo học viên exit 2 |
| `python -m tools.t14_eval_dev --gold gold/gold_dev.csv --pred out/poc/predictions.csv` | F1 nội bộ trên gold set tự vẽ (dev) |
| `pytest -q` | ≥2 test của nhóm (success + failure/edge), 0 failed |

Exit code của `src.main`: `0` OK · `2` input/output sai · `3` chưa implement · `4` gọi network khi `--offline` · `5` pipeline đọc ground truth.

Primary metric: **Detection F1@IoU0.5** (`src/metrics/tracks.py`, `eval_t14`). Không sửa định nghĩa metric.

## 3. Cấu trúc repo

```
configs/lab.yaml · configs/tracks/t14.yaml
src/main.py                  # one-command runner
src/pipeline.py              # PoC của nhóm: load -> predict -> rank -> review -> export
src/baseline_t14.py          # baseline T14
src/t14_tools.py             # class adapter, chuẩn hoá box, suspicion score, validator export
src/evaluate.py · compare.py
src/common/                  # io, manifest, offline/gt guard, review, contact_sheet, decision, report, timer
src/metrics/                 # detection.py + evaluator
fixtures/t14_auto_annotation/  # input synthetic offline (gt/ chỉ có ở repo giảng viên)
docs/tracks/T14.md · docs/HUONG_DAN_GAN_NHAN_CVAT.md · docs/INSTRUCTOR_SETUP.md
reports/                     # group_report, metric_contract, team_contributions, metrics_*.json
tools/preflight.py · tools/t14_eval_dev.py
submission/                  # bài nộp
```

## 4. Vòng human-in-the-loop (review -> override -> audit)

1. `make run` sinh `out/poc/review_queue.csv` (top-B) và `contact_sheet.html` (mở offline bằng trình duyệt).
2. Reviewer chọn quyết định (`approve/reject/edit/escalate/skip`), bấm **Export CSV**, hoặc điền trực tiếp
   `reviewer`, `reviewer_decision`, `override_value`, `review_note`; hoặc sửa nhãn trên CVAT.
3. Chép file vào `out/poc/review_queue_reviewed.csv`, chạy lại `make run`: pipeline áp override và ghi `out/poc/audit_log.jsonl`.

## 5. Quy tắc

1. Không đọc `gt/` trong pipeline; không tune trên split eval; chọn ngưỡng trên dev (`tools.t14_eval_dev --sweep`).
2. Mọi run dùng `--seed 42`, ghi N và tốc độ (`run_info.json` / `metrics_*.json`).
3. Không gọi API ngoài khi demo; model pretrained phải tải trước, ghi tên/checksum/license.
4. Không commit token (`.env`, `CVAT_PAT`).
5. Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; nêu giả định cần DPO/legal xác nhận.
6. Mỗi thành viên ≥1 commit thực chất; khớp `reports/team_contributions.csv` với `git shortlog -sne --all`.
7. Tag: `make tag-demo` (`demo-180m`), `make tag-final` (`final-24h`).
