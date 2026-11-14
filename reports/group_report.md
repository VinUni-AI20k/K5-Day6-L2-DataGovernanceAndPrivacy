# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> **KHUNG NHÁP.** Phần đã điền lấy từ code/config/tài liệu trong repo. Mục `⟦TODO⟧` là chỗ nhóm phải điền sau khi chạy.
> Mọi con số phải lấy từ file do script sinh ra (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay.

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G⟦TODO: khớp `group_id` trong `configs/lab.yaml`⟧ · tên nhóm `sIx4nhd0cthAn` |
| Challenge | T14 · Auto-Annotation + Human QC |
| Thành viên + vai trò | 1. Trần Thành Hùng (2A202603247) · 2. Hoàng Quốc Chung (2A202604039) · 3. Nguyễn Xuân Việt (2A202604045) · 4. Trần Nguyễn Phi Long (2A202604058) · 5. Phạm Phú Nguyễn Hưng (2A202604062) · 6. ⟦TODO: chưa có thông tin⟧. Vai trò: ⟦TODO: phân vai, khớp `submission/README.md`⟧ |
| Git URL | https://github.com/phamphunguyenhung/K5-Day6-L2-sIx4nhd0cthAn-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | ⟦TODO⟧ |
| Tag `final-24h` (commit) | ⟦TODO⟧ |
| Deadline (giờ VN) | ⟦TODO⟧ |

## 01 · Problem statement

- Ai bị ảnh hưởng khi hệ thống sai? ⟦TODO: ví dụ team huấn luyện model downstream nhận nhãn sai; người đi bộ/xe máy bị nhận nhầm lớp⟧
- Điểm nghẽn: gán nhãn tay 100% tốn công; model có sẵn dùng label map COCO, **khác taxonomy dự án** (car, pedestrian, motorbike, sign), bỏ sót vật thể nhỏ, có false positive conf thấp.
- Đầu vào → đầu ra: `fixtures/t14_auto_annotation` (60 ảnh + prediction mô phỏng) → `predictions.csv` (`image_id, class, x, y, w, h, conf`) + YOLO + COCO + `decision.json`.
- Tiêu chí GO / HOLD / REWORK (policy trong `src/pipeline.py::decide`, chốt trước khi chạy eval):
  - **REWORK** `EXPORT_QA_FAILED`: có invalid label hoặc round-trip YOLO/COCO lệch.
  - **HOLD** `NOT_REVIEWED` (chưa review) / `REVIEW_INCOMPLETE` (review < `min_review_fraction` = 0.8 của queue).
  - **GO** `REVIEWED_AND_VALID`: đã review đủ và export hợp lệ. GO **không** khẳng định độ chính xác.
- Giả định cần domain owner xác nhận: ⟦TODO: ví dụ alias class `person→pedestrian`, `motorcycle→motorbike`, `stop sign→sign`; ngưỡng small = 150 px²⟧

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 40 ảnh ⟦TODO: xác nhận từ `images.csv`⟧ | `fixtures/t14_auto_annotation` | ⟦TODO: lấy từ `manifest.csv`⟧ | có |
| eval / heldout | 20 ảnh | như trên (GT chỉ có ở repo giảng viên) | ⟦TODO⟧ | có |

- Schema & class mapping: model `0 person, 2 car, 3 motorcycle, 11 stop sign` → taxonomy `1 pedestrian, 0 car, 2 motorbike, 3 sign` (`src/t14_tools.py::build_class_map`; class model không map được thì fail rõ ràng).
- Seed: 42 · Split: tách sẵn trong `images.csv` ⟦TODO: ghi cách chia theo scene/ngẫu nhiên nếu biết⟧.
- `manifest.csv` verified (sha256): ⟦TODO: có/không — chạy `python -m tools.preflight`⟧; `strict_provenance: true`.
- Dữ liệu thật: ⟦TODO: không dùng / mô tả `data/real/` nếu có⟧. Prediction là **mô phỏng** (`simulated-detector-fixture`, `fixture-1`), không báo là inference thật.

## 03 · Research & design

- References: ⟦TODO: 2–3 URL + ngày xem + vì sao chọn (CVAT QA, Ultralytics/RF-DETR, label-map validation)⟧ — xem mục 11.
- Data flow (`src/pipeline.py`): `load` (kiểm manifest) → `process` (map class, clip box, lọc conf, suspicion score) → `rank` (review queue top-B + `contact_sheet.html`) → `review` (áp `review_queue_reviewed.csv` + `review_additions.csv`, ghi audit) → `export` (validate, CSV/YOLO/COCO, round-trip) → `decide` (GO/HOLD/REWORK).
- Suspicion score = 0.5·uncertainty + 0.3·small + 0.2·clipped + 0.3·class_confusion (tham số ở `lab.yaml`, đóng băng trước eval). Chọn trên dev: ⟦TODO: bằng chứng `tools.t14_eval_dev --sweep`⟧.
- Thành phần offline: không có weights ngoài (prediction fixture). ⟦TODO: nếu dùng YOLO26/RF-DETR thì ghi checksum + license: YOLO26 là AGPL-3.0⟧.
- Trade-offs: ⟦TODO: B=30 so với tổng 227 box; recall vật thể nhỏ vs. công review; ngưỡng 0.25⟧.

## 04 · Baseline vs PoC

- Baseline (`src/baseline_t14.py`): map class, lọc conf ≥ 0.25, export **không clip, không rank, không review**. Decision luôn `HOLD / BASELINE_ONLY`. Commit: ⟦TODO⟧
- PoC (`src/pipeline.py`): thêm clip box, suspicion rank, review loop, validator, round-trip, decision. Commit: ⟦TODO⟧
- Cùng budget / heldout / seed 42 / config: ⟦TODO: xác nhận⟧

**Bảng 1 · Baseline vs PoC** — dán nguyên output `python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

⟦TODO: dán bảng do script sinh; không sửa tay. Nếu baseline = 0 hoặc Δ ≤ 0 thì ghi rõ.⟧

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: Detection F1@IoU0.5 (box, 20 ảnh eval) | ⟦⟧ | ⟦⟧ | higher is better |
| Hard-slice: recall small object (< 150 px²) | ⟦⟧ | ⟦⟧ | N=⟦⟧ |
| Review@B / miss / FP | ⟦⟧ | ⟦⟧ | B=30 |
| Invalid-label rate sau export | ⟦⟧ | ⟦⟧ | mục tiêu 0 |
| Runtime / 100 items | ⟦⟧ | ⟦⟧ | CPU=⟦⟧ |

## 05 · Evaluation protocol

- Primary: F1 = 2PR/(P+R), P = TP/(TP+FP), R = TP/(TP+FN); đơn vị box; ghép greedy IoU ≥ 0.5 và đúng class (`src/metrics/detection.py`). Chi tiết `reports/metric_contract.md`.
- Threshold 0.25, budget B = 30 (`configs/tracks/t14.yaml`); chốt lúc ⟦TODO: ngày giờ + người chốt, điền cả vào metric_contract⟧.
- Độ bất định: N = 20 ảnh eval, bootstrap theo ảnh ⟦TODO: kết quả CI⟧; N nhỏ nên không kết luận Δ nhỏ.
- Lệnh evaluate (giảng viên chạy, cần overlay `gt/`): `python -m src.evaluate --track t14 --pred out/poc/predictions.csv --run-name poc --out reports/metrics_poc.json`. Repo học viên không có GT nên exit 2; F1 nội bộ dev dùng `python -m tools.t14_eval_dev --gold gold/gold_dev.csv --pred out/poc/predictions.csv`.

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| class = car | ⟦⟧ | ⟦⟧ | ⟦⟧ | |
| class = pedestrian | ⟦⟧ | ⟦⟧ | ⟦⟧ | |
| class = motorbike | ⟦⟧ | ⟦⟧ | ⟦⟧ | |
| class = sign | ⟦⟧ | ⟦⟧ | ⟦⟧ | |
| small object | ⟦⟧ | ⟦⟧ | ⟦⟧ | |

- Failure case 1 — class ID sai vẫn export hợp lệ: ⟦TODO: ảnh/box_id, root cause, cách validator/alias bắt; xem `tools/t14_failure_evidence.py`⟧
- Failure case 2 — conf cao nhưng thiếu vật thể nhỏ: ⟦TODO: ảnh/metadata, vì sao rank theo conf không bắt được, cách `review_additions.csv` xử lý⟧
- Latency / compute: ⟦TODO: máy, CPU, ms/item từ `run_info.json`⟧

## 07 · Human & decision

- Review queue: `out/poc/review_queue.csv` (top B=30 theo suspicion score) + `contact_sheet.html` (offline). Reviewer: ⟦TODO: ai, bao nhiêu phút/ảnh⟧.
- Override: cột `reviewer`, `reviewer_decision` (approve/reject/edit/escalate/skip), `override_value` → `review_queue_reviewed.csv`; box thiếu thêm bằng `review_additions.csv` (cần reviewer). Audit: `out/poc/audit_log.jsonl`; diff: `correction_diff.csv`.
- Decision policy + `reason_code` + owner: xem mục 01. Owner (`configs/lab.yaml::owner`): ⟦TODO: chưa chốt⟧.
- Khi nào HOLD/REWORK: chưa review hoặc review < 80% queue → HOLD; invalid label / round-trip lệch → REWORK. Kết quả run thật: ⟦TODO: dán `decision.json`⟧.

## 08 · Reproduce & tests

```bash
make setup
python -m src.main --config configs/lab.yaml --track t14 --output out/poc --run-name poc --offline --seed 42
python -m src.main --config configs/lab.yaml --track t14 --pipeline src.baseline_t14 --output out/baseline --run-name baseline --offline --seed 42
pytest -q
```

- Test của nhóm (`tests/test_t14.py`): class map, unmapped class fail, alias sai, clip box, parse override, pipeline end-to-end tái lập, baseline vs PoC, review loop → GO, review dở → HOLD, file review hỏng → exit 2, thêm box thiếu.
- Output `pytest -q`: ⟦TODO: dán kết quả⟧
- Máy / CPU / OS / Python: ⟦TODO⟧ · git sha: ⟦TODO⟧

## 09 · Limitations & ethics

- Rủi ro PII / license: ⟦TODO: fixture synthetic; ảnh thật cần quyền; YOLO26 AGPL-3.0 nếu dùng⟧
- Điều chưa biết: prediction mô phỏng nên F1 không phản ánh model thật; N eval = 20; ⟦TODO: false alarms; nếu scale 10× thì sao⟧
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận: ⟦TODO⟧
- Kế hoạch cải tiến: ⟦TODO: threshold theo class, CVAT SDK, QA round-trip⟧

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Trần Thành Hùng | ⟦⟧ | ⟦⟧ | ⟦⟧ | ⟦⟧ |
| Hoàng Quốc Chung | ⟦⟧ | ⟦⟧ | ⟦⟧ | ⟦⟧ |
| Nguyễn Xuân Việt | ⟦⟧ | ⟦⟧ | ⟦⟧ | ⟦⟧ |
| Trần Nguyễn Phi Long | ⟦⟧ | ⟦⟧ | ⟦⟧ | ⟦⟧ |
| Phạm Phú Nguyễn Hưng | Phạm Phú Nguyễn Hưng | ⟦⟧ | ⟦⟧ | ⟦⟧ |
| Member 6 (nếu có) | ⟦⟧ | ⟦⟧ | ⟦⟧ | ⟦⟧ |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa |
|---|---|---|
| ⟦TODO⟧ | ⟦⟧ | ⟦⟧ |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
