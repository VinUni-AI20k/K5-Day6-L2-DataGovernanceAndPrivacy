# Day 06 · Data Lab · Field-to-Release PoC (AI20K · Data Track)

Starter repo cho bài lab **Data Pipeline, Privacy & Production PoC**: 14 challenge (T01–T14), một contract chung.
Repo cung cấp **dữ liệu offline + hạ tầng dùng chung + metric chuẩn + template báo cáo** để nhóm tập trung vào phần quan trọng:
vấn đề, baseline, thuật toán, đánh giá trung thực, human-in-the-loop và quyết định GO/HOLD/REWORK.

> Repo **không** chứa lời giải. `src/pipeline.py` là file nhóm sở hữu; mọi thuật toán (kể cả baseline) do nhóm tự cài.
> Tài liệu học tập, không thay tư vấn pháp lý.

## 1. Quickstart (≤ 5 phút, chạy offline)

```bash
# Python 3.11–3.13 (đã test trên 3.13)
make setup                 # = python3 -m venv .venv && pip install -r requirements.txt
make preflight             # kiểm tra môi trường, fixtures, offline guard, không lộ token
make test                  # pytest -q  (phải 0 failed)

# Ví dụ wiring E2E (random baseline, có cho T01/T02/T11/T13):
make baseline TRACK=t11 && make eval-baseline TRACK=t11
```

Chọn challenge: sửa `configs/lab.yaml` (`track`, `track_config`, `owner`, `group_id`), đọc `docs/tracks/TXX.md`.

## 2. Contract lệnh (giảng viên sẽ chạy đúng các lệnh này)

| Lệnh | Điều kiện PASS |
|---|---|
| `python -m src.main --input fixtures/<track> --config configs/lab.yaml --output out/` | exit 0, sinh output + review log + decision |
| `python -m src.evaluate --gt fixtures/<track>/gt/<file> --pred out/<pred_file>` | in baseline/PoC và định nghĩa số mẫu, tính bằng script |
| `pytest -q` | ≥2 test của nhóm (success + failure/edge), 0 failed |
| `python -m src.main --offline --seed 42` | không network; thiếu model → fail rõ ràng, không tự download |
| `git shortlog -sne --all` | mỗi người có tên/email, khớp `reports/team_contributions.csv` |

Exit code của `src.main`: `0` OK · `2` input/output sai · `3` chưa implement · `4` gọi network khi `--offline` · `5` pipeline đọc ground truth.

`src.main` tự bật hai guard: **offline guard** (chặn socket ra ngoài) và **GT guard** (chặn đọc `fixtures/*/gt/`).
Ground truth chỉ dành cho `src.evaluate`; với T12, nhãn ẩn chỉ đọc được qua `AuditOracle` có budget.

## 3. Cấu trúc repo

```
README.md · requirements.txt · pyproject.toml · Makefile · run.sh
configs/lab.yaml               # config của nhóm (chọn track, owner, seed)
configs/tracks/tXX.yaml        # default params + eval params cho từng track
src/main.py                    # one-command runner (contract)  — KHÔNG cần sửa
src/pipeline.py                # ★ PIPELINE CỦA NHÓM: load → process → rank → review → decide
src/evaluate.py · src/compare.py
src/examples/random_baseline.py  # ví dụ nối dây E2E (random = baseline của T01/T02/T11/T13)
src/common/                    # hạ tầng dùng chung (xem bảng dưới)
src/metrics/                   # thư viện metric + evaluator chuẩn cho 14 track (tracks.py)
fixtures/<track>/              # dữ liệu synthetic offline, KHÔNG có PII thật; GT nằm trong gt/
data/real/                     # (gitignored) mẫu dữ liệu thật do giảng viên tải trước
docs/tracks/T01..T14.md        # đề bài chi tiết + data schema + metric + output contract
docs/INSTRUCTOR_SETUP.md       # chuẩn bị gói offline P0–P6, dữ liệu thật từ Hugging Face
reports/                       # group_report.md, metric_contract.md, team_contributions.csv, metrics_*.json
tests/                         # test hạ tầng + metric; nhóm thêm test của mình ở đây
tools/                         # make_fixtures, download_real_samples, verify_manifests, preflight
demo/                          # slides / ảnh chụp demo
```

### Hạ tầng dùng chung (`src/common/`)

| Module | Dùng để |
|---|---|
| `io.py` | config YAML, `set_seed`, sha256, JSON, git sha |
| `manifest.py` | `manifest.csv` (file_id, path, source, license, split, group_id, sha256): build + verify |
| `offline.py` / `gt_guard.py` | chặn network / chặn đọc ground truth |
| `review.py` | review queue top-B, đọc quyết định reviewer, `apply_overrides`, `AuditLog` (JSONL append-only) |
| `contact_sheet.py` | contact sheet HTML offline (ảnh trước/sau, bbox, dropdown quyết định, nút **Export CSV**) |
| `decision.py` | `Decision` GO/HOLD/REWORK (+ alias PASS/ACCEPT/KEEP/RECAPTURE…) bắt buộc `reason_code` + `owner` |
| `report.py` | ghi `metrics_*.json` (seed, git sha, runtime/100 items, máy) + bảng Baseline vs PoC |
| `corruptions.py` | blur / dark / glare / jpeg / fog / rain / night / tint với severity 0–2 (deterministic) |
| `image_ops.py` | Laplacian variance, brightness stats, histogram, aHash/dHash/pHash + Hamming |
| `audit_oracle.py` | "người kiểm" mô phỏng: chỉ lộ nhãn ẩn cho mẫu được chọn, dừng khi hết budget |
| `timer.py` | đo thời gian, ms/item, thông tin máy |

### Metric chuẩn (`src/metrics/`)

Mỗi track có evaluator riêng trong `src/metrics/tracks.py`, cài đúng primary metric trong handout:

| Track | Primary metric | Output nhóm phải ghi |
|---|---|---|
| T01 Coverage Planner | Weighted Coverage@K (K=30) | `pick.csv` |
| T02 Raw QC Triage | Defect Recall@B + Precision@B (B=20) | `ranked_review.csv` |
| T03 Synthetic-vs-Real | Transform QC F1 | `qc.csv` (+ `transform_manifest.csv`) |
| T04 Sensor Sync Guard | Pair Accuracy@50ms | `pairs.csv` |
| T05 Leakage & Near-Dup | Leakage Detection F1 (pair) | `suspect_pairs.csv` (+ `split_manifest.csv`) |
| T06 Integrity & Provenance Gate | Silent-defect Detection F1 (release) | `release_decisions.csv` |
| T07 Face/Plate Redaction | PII Miss Rate (coverage ≥ 0.9) + guardrail over-redaction ≤ 0.3 | `redactions.csv` |
| T08 Delete Request Simulator | Deletion Completeness (+ false-delete = 0) | `actions.csv` (+ `audit_log.jsonl`) |
| T09 Privacy Decision Gate | Critical-miss Rate (split eval) + guardrail false HOLD ≤ 0.5 | `decisions.csv` |
| T10 Domain Shift Radar | Spearman ρ(ShiftScore, PerfDrop) + bootstrap CI | `shift_scores.csv` |
| T11 Label Error Prioritizer | Error Recall@B, B=max(10, 10%N) | `ranking.csv` |
| T12 Vendor Batch Acceptance | MAE + Bad-batch Recall (báo riêng) + guardrail HOLD rate ≤ 0.4 | `batch_decisions.csv` |
| T13 Rare Case Miner | Rare-case Recall@K (K=20) | `selected.csv` |
| T14 Auto-Annotation + QC | Detection F1@IoU0.5 | `predictions.csv` |

Thư viện chung (`classification`, `ranking`, `detection`, `pairs`, `timing`, `estimation`, `correlation`) có docstring ghi rõ numerator/denominator.
**Không sửa định nghĩa metric để đẹp số.** Nếu thấy metric chưa hợp lý, hãy lập luận trong report và thêm metric phụ.

## 4. Quy trình làm bài (240 phút)

| Phút | Việc | Checkpoint |
|---|---|---|
| 00–10 | Chọn challenge, lập repo/nhóm, chia module | mỗi người 1 commit đầu |
| 10–30 | Đọc `docs/tracks/TXX.md`, chốt GT + metric | điền `reports/metric_contract.md` |
| 30–50 | Baseline + 2–3 fixture lỗi đầu tiên | `reports/metrics_baseline.json` |
| 50–145 | Pipeline xử lý → review → report | one-command PoC + `review_queue.csv` / contact sheet |
| 145–170 | Heldout, ablation nhanh, sửa bug | `reports/metrics_poc.json` + 2 failure cases |
| 170–180 | Freeze demo | `make tag-demo` (tag `demo-180m`), 3–5 slides |
| 180–240 | Showcase + adversarial debate | |
| +24h | Repo tái lập, report, contributions | `make tag-final` (tag `final-24h`) |

Lệnh nộp số liệu (không gõ tay):

```bash
python -m src.main --track tXX --output out/baseline --run-name baseline --pipeline <module baseline của nhóm> --offline
python -m src.main --track tXX --output out/poc --run-name poc --offline
make eval-baseline eval-poc compare TRACK=tXX      # -> reports/metrics_*.json + reports/table1_baseline_vs_poc.md
```

### Bắt đầu viết pipeline (15 phút đầu)

1. Sửa `configs/lab.yaml`: `group_id`, `owner`, `track: tXX`, `track_config: tracks/tXX.yaml`.
2. Đọc `docs/tracks/TXX.md`, mở `fixtures/<track>/` xem input; xem `src/examples/random_baseline.py` để biết cách nối dây.
3. Trong `src/pipeline.py`, viết `load()` + `process()`; `process()` trả DataFrame có **các cột bắt buộc** của track
   (bảng trên) **và** cột `score` (số, cao = cần review trước) để `rank()` lập queue top-B.
4. `make run TRACK=tXX` (exit 0) → `make eval-poc TRACK=tXX`. Exit 3 nghĩa là `process()` chưa được cài.

### Vòng human-in-the-loop (review → override → audit)

1. `make run` sinh `out/poc/review_queue.csv` (top-B). Muốn có giao diện: gọi
   `render_contact_sheet(queue, ctx.out("contact_sheet.html"), image_root=ctx.input_dir)` (xem `random_baseline.py`), mở file HTML bằng trình duyệt (offline).
2. Reviewer nhập tên, chọn quyết định (`approve/reject/edit/escalate/skip`), bấm **Export CSV**
   → trình duyệt tải về `review_queue_reviewed.csv`. Hoặc điền thẳng các cột `reviewer`, `reviewer_decision`, `override_value`, `review_note` trong CSV.
3. Chép file vào **`out/poc/review_queue_reviewed.csv`** rồi chạy lại `make run`: bước `review()` đọc file
   (dòng có quyết định mà thiếu `reviewer` → fail rõ), nhóm tự áp override (`common.review.apply_overrides`) và ghi `out/poc/audit_log.jsonl`.

## 5. Dữ liệu

- `fixtures/`: **synthetic, sinh deterministic** bởi `python -m tools.make_fixtures` (seed 42), CC0, không có người/biển số thật.
  Mỗi track có `manifest.csv` (input) và `gt/manifest.csv` (ground truth) kèm sha256. Kiểm tra: `make verify`.
  **Không cần chạy `make fixtures`**: dữ liệu đã commit sẵn. Sinh lại với phiên bản Pillow/OpenCV khác sẽ ra byte JPEG khác (GT giữ nguyên) và làm lệch hash so với bản chấm.
- `data/real/` (gitignored, tuỳ chọn): mẫu nhỏ dữ liệu thật từ Hugging Face (BDD100K val, COCO val2017, license plates).
  Giảng viên chuẩn bị trước lớp bằng `make real-data` — xem `docs/INSTRUCTOR_SETUP.md`.
  **Có người và biển số thật → không commit, không đưa lên cloud/public repo.**
- Dữ liệu thật **không có GT ẩn** do giảng viên giữ: nếu dùng, nhóm tự khai báo protocol GT trong report.
  Điểm chính vẫn tính trên fixtures (có hidden eval tương đương).

## 6. Quy tắc

1. Không đọc `gt/` trong pipeline; không tune trên split eval/heldout; chốt threshold/trọng số trước.
2. Mọi run dùng `--seed 42`, ghi N và tốc độ (đã có trong `run_info.json` / `metrics_*.json`).
3. Không gọi API ngoài khi demo; model pretrained phải tải trước, ghi tên/checksum/version/license.
4. Không đưa ảnh người thật/biển số thật chưa có quyền lên repo công khai hoặc cloud.
5. Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; nêu giả định cần DPO/legal xác nhận.
6. Mỗi thành viên ≥1 commit thực chất (khuyến nghị 2); commit chỉ đổi khoảng trắng không tính.
7. Không đổi testset hoặc chèn kết quả không tái lập sau khi chốt protocol.

## 7. Rubric (100 điểm + bonus ≤ 15)

| Tiêu chí | Điểm |
|---|---|
| End-to-end & đúng yêu cầu (1 lệnh, 5 bước, demo thật) | 22 |
| Gold set + metric rõ | 18 |
| Baseline + kết quả so sánh (cùng budget/heldout/seed, trung thực khi 0/âm) | 18 |
| Human-in-loop & risk gate (queue, override, audit log, reason/owner) | 12 |
| Reliability & reproducibility (offline, clean start, ≥2 tests, 1 failure mode) | 12 |
| Report + team Git evidence | 10 |
| Showcase & debate | 8 |

Bonus: +5 verified E2E trước phút 180 (tag) · +5 ablation/hidden test thật · +5 debate tìm bug thật bằng test.
