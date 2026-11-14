# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Mọi con số dưới đây lấy từ file do script sinh ra (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`,
> `reports/t02_calibration.json`) — không gõ tay. Lệnh reproduce ở mục 08 đã được chạy verify trên máy nộp bài.

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G00 (config `configs/lab.yaml`) |
| Challenge | T02 · Raw QC Triage |
| Thành viên + vai trò | 1. Nguyễn Thế Tùng, 2A202603320 (Lead/Integrator) · 2. ____ · 3. ____ · 4. ____ |
| Git URL | https://github.com/entity-solo/K5-L2B-DAY06-NguyenTheTung-2A202603320-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | `6d445f4` (freeze PoC + baseline + eval trước HITL) |
| Tag `final-24h` (commit) | tag `final-24h` trên repo = commit cuối cùng |
| Deadline (giờ VN) | 2026-11-14T17:00:00+07:00 |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? *Nhà sản xuất dữ liệu và đội review ảnh: ảnh lỗi bị bỏ sót khiến dữ liệu hỏng được phát hành (KEEP nhầm), còn ảnh sạch bị treo vào review thì đội review quá tải và chậm release.*
- Điểm nghẽn cụ thể: *Phân loại ảnh lỗi (blur/dark/glare/compression) trên ảnh nhóm theo scene — riêng lẻ từng ảnh, blur nhẹ và compression dễ nhầm nhau vì cùng giảm độ sắc nét (feature overlap).*
- Đầu vào → đầu ra: *Input: 96 ảnh synthetic 320×180 kèm `images.csv` → extract 4 feature nhóm (lap/bright/blob/block) + chuẩn hoá theo nhóm ảnh cùng scene → score & rank → Top-B=20 review → quyết định KEEP/REVIEW/RECAPTURE.*
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): *REWORK nếu có ảnh dự đoán severity 2 (chụp lại); HOLD nếu chỉ có severity 1 (chờ người review); GO nếu không ảnh nào vượt ngưỡng defect.*
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): *Dữ liệu synthetic CC0, không có người/biển số thật → không có PII; nếu deploy lên ảnh thật cần rà soát lại quyền sở hữu ảnh và luật bảo vệ dữ liệu trước.*

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 56 | `reports/dev_labels.csv` (tự label theo `tools/record_dev_labels.py`, batch 1–4 trong `reports/label_batches/`) | CC0 (synthetic fixture) | Có |
| eval / heldout | 40 | `Downloads/Evalimg.txt` (nhãn do đề cung cấp, chuẩn hoá vào `reports/eval_gt_from_Evalimg.txt.csv`) | CC0 (synthetic fixture) | Có |

- Schema & class mapping: *`defect_type ∈ {none, blur, glare, dark, compression, "blur glare"}`, severity 0–2, `is_defect = 1 ⇔ defect_type ≠ none` (multi-label "blur glare" giữ nguyên dạng chuỗi).*
- Seed: 42 · Cách chia split: *Theo scene gốc — 24 scene × 4 ảnh; mỗi scene chia 60% dev / 40% eval, không trộn ảnh cùng scene giữa 2 split để tránh leakage.*
- `manifest.csv` verified (sha256): *Đã verify — `src.main` chạy với `strict_provenance: true`, exit 0 trên toàn bộ run (không có provenance_problems trong `out/audit_log.jsonl`).*
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: *Không dùng dữ liệu thật. GT dev tự label từ 3 file nguồn (Folder1.txt, score_3.txt, duc.txt); GT eval lấy từ `Evalimg.txt` đề phát.*

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật:
  1. ISO/IEC TR 5259-6 (QC pipeline cho dữ liệu ảnh) — *chọn vì quy trình triage → review → decision khớp đúng khung bài T02.*
  2. ACDC (ETH Zürich) — *tham khảo cách benchmark phân loại ảnh lỗi trong điều kiện chụp thực tế để biết các failure mode cần phủ.*
  3. Laplacian variance (trích trong `src/common/image_ops.py`) — *chọn làm feature cơ sở vì là proxy độ sắc nét rẻ, chạy offline, không cần model.*
- Sơ đồ data flow: *load (`manifest.csv` verify) → extract features (laplacian variance, brightness, saturation blob, blockiness 8×8) → chuẩn hoá theo nhóm scene (lap ÷ max nhóm, bright ÷ 2nd-highest, block ÷ 2nd-lowest) → score_frame với ngưỡng lo/hi frozen → priority typing (dark > glare > compression > blur) → rank top-B → review queue → decide (GO/HOLD/REWORK).*
- Thành phần offline: *Không model, không weights — chỉ 4 feature + 8 hằng số frozen. Code checksum (sha256 file): `src/poc/t02_v1.py` = `9a20fe76e636becb…`, `src/baselines/t02_laplacian.py` = `4be61b6c8ccfca69…`. `--offline` chặn socket, GT-guard chặn đọc `fixtures/*/gt/`.*
- Trade-offs đã cân nhắc: *Baseline Laplacian đơn giản, rẻ (3.4 ms/ảnh) nhưng chỉ bắt được blur — type accuracy chỉ 0.30. PoC 4 feature (7.7 ms/ảnh) nâng type accuracy lên 0.87 với Recall/Precision không đổi. Đánh đổi phức tạp vs độ chính xác phân loại được coi là đáng vì hành động sau review (KEEP vs RECAPTURE) phụ thuộc đúng loại lỗi.*

## 04 · Baseline vs PoC

**Baseline (mô tả, version/config, commit):**
`src/baselines/t02_laplacian.py` — ảnh có `laplacian_variance < 760` bị flag. T = 760 re-freeze trên 56 nhãn dev (mọi T ∈ (745, 772.7] cho cùng tập quyết định). Commit `6d445f4`.

**PoC v1 (mô tả, version/config, commit):**
`src/poc/t02_v1.py` — 4 feature nhóm + ngưỡng frozen: dark `{0.596, 0.124}`, blur `{0.205, 0.032}`, compression `{1.47, 2.06}`, glare `{0.0022, 0.006}` (lo, hi). Calibrate trên đủ 56 nhãn dev (`tools/_t02_calibrate.py`, LOSO: FP 1/22, FN 3/34). Commit `6d445f4`.

**Cùng budget / cùng heldout / cùng seed: xác nhận** ✅ *Cùng seed 42, cùng B=20, cùng pool 96 ảnh, cùng GT eval 40 nhãn (`reports/eval_gt_from_Evalimg.txt.csv`); run_info ghi git sha như nhau cho 2 run.*

**Bảng 1 · Baseline vs PoC** (sinh bằng `python -m src.compare`)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Better | N |
|---|---|---:|---:|---:|---|---:|
| Defect Recall@B (PRIMARY) | all | 0.8696 | 0.8696 | 0.0000 | — | 40 |
| Precision@B | all | 1.0000 | 1.0000 | 0.0000 | — | 40 |
| Defect-type accuracy (GT defects) | all | 0.3043 | **0.8696** | **+0.5652** | PoC | 23 |
| False alarm in top-B | light=day/dusk/night | 0/0/0 | 0/0/0 | 0 | — | 20/4/16 |
| Runtime / 100 items (s) | all | 0.339 | 0.766 | — | baseline | — |
| AP (56 dev, proxy) | all | 0.9376 | **0.9831** | +0.0455 | PoC | 56 |

Ghi chú trung thực: *Recall@20 và Precision@20 bằng nhau cho cả hai model — cả hai cùng bỏ sót 3/23 defect trong top-20 và không treo ảnh clean nào. Lợi thế thực sự của PoC nằm ở **type accuracy** (0.87 vs 0.30) và **severity**, tức đúng hành động KEEP/REVIEW/RECAPTURE. 2 ảnh multi-label `blur glare` bị evaluator đếm sai theo so sánh chuỗi — ảnh hưởng 2/23 cho cả hai model như nhau.*

## 05 · Evaluation protocol

- Công thức primary metric, đơn vị, TP/FP/FN, denominator: *Defect Recall@B = #GT defect trong top-B / #GT defect tổng (denominator = 23 trên eval N=40, B=20). TP = defect nằm trong top-20; FP = ảnh clean nằm trong top-20; FN = defect nằm ngoài top-20.*
- Threshold / budget B / K và lúc chốt: *Ngưỡng lo/hi và baseline T=760 freeze trên 56 nhãn dev TRƯỚC khi nhận 40 eval labels; B=20 chốt từ đề. Lúc chốt: commit `6d445f4` (tag `demo-180m`).*
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: *N=40 (23 defect) quá nhỏ để bootstrap đáng tin → báo đầy đủ num/den (20/23) thay vì số làm tròn; mọi chênh lệch < 2 mẫu giữa 2 model được coi là không có ý nghĩa.*
- Lệnh evaluate chính xác:
  `python -m src.evaluate --track t02 --gt reports/eval_gt_from_Evalimg.txt.csv --pred out/poc_v1/ranked_review.csv --run-name poc_v1 --out reports/metrics_poc.json`

## 06 · Result slices

Bảng sinh từ `reports/metrics_poc.json` / `reports/metrics_baseline.json` (`--slices-out`):

| Slice | N (defect/clean) | Recall@20 (cả 2 model) | FA@20 | Ghi chú |
|---|---|---:|---:|---|
| light=day | 20 (10/10) | 0.900 (9/10) | 0.000 | 1 defect day bị bỏ sót |
| light=dusk | 4 (3/1) | 1.000 (3/3) | 0.000 | phủ đủ |
| light=night | 16 (10/6) | 0.800 (8/10) | 0.000 | yếu nhất: 2 defect night bị sót |
| defect=blur | 7 | baseline 1.000 / PoC 0.714 | — | PoC sót 2 blur (nhầm qua compression) |
| defect=blur glare (multi-label) | 2 | baseline 1.000 / PoC 1.000 | — | được đếm trong top-B nhưng type accuracy trừ điểm chuỗi |
| defect=compression | 8 | baseline 0.750 / PoC 0.875 | — | PoC bắt thêm 1 |
| defect=dark | 4 | baseline 1.000 / PoC 1.000 | — | phủ đủ |
| defect=glare | 2 | baseline 0.500 / PoC 1.000 | — | baseline không có feature glare |

**Failure case 1 (ảnh/metadata + root cause):**
- `img_03_2` (GT `blur glare`/1, scene img_03, night, cam_B): PoC v1 dự đoán `compression`. `block_ratio` vượt ngưỡng compression lo (1.47) trong khi `lap_ratio` không tách được khỏi ảnh clean cùng scene. Root cause: glare cục bộ + JPEG artefact trong ảnh night làm 2 feature chồng nhau — typing ưu tiên compression trước blur theo `TYPE_PRIORITY`.

**Failure case 2:**
- `img_08_2` (GT `blur`/1, scene img_08): PoC v1 dự đoán `compression`, tương tự case 1 — `block_ratio` vượt lo nhưng `lap_ratio` không xuống dưới blur lo (0.205) vì ảnh chỉ mờ nhẹ. Root cause: blur lo=0.205 vẫn quá cao cho blur mức severity-1; cần thêm feature texture tần số trung bình để tách blur vs compression.

**Latency / compute (máy, CPU, ms/item):**
*Đo bằng `run_info.json` trên máy nộp bài: PoC v1 = 0.766 s/100 ảnh (≈7.7 ms/ảnh), baseline = 0.339 s/100 ảnh (≈3.4 ms/ảnh); CPU Intel i5-13600KF, Windows 11, Python 3.12.10, chỉ CPU, single process — đủ cho triage hàng loạt offline.*

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): *`reports/review_queue.csv` — top-20 ảnh theo score PoC v1 (cao = nghi nhất), có `reason` (pred_defect_type), `suggested_action`, `slice` (scene), `evidence_path` tới ảnh. B=20/lượt review.*
- Reviewer evidence + audit log: *Reviewer = Nguyễn Thế Tùng, `reviewer_decision` điền theo severity (0=KEEP, 1=REVIEW, 2=RECAPTURE), `review_note` ghi GT severity, `reviewed_at` ghi timestamp. Pipeline 5 bước sinh thêm `out/audit_log.jsonl` (append-only, ai/khi nào/làm gì) cho mọi run.*
- Decision policy + `reason_code` + owner:
  *Cổng tự động (pipeline, frozen): severity 2 → REWORK `SEV2_PREDICTED`; chỉ severity 1 → HOLD `SEV1_REVIEW`; không flag → GO `NO_DEFECT_FLAGGED`. Owner: `Nguyễn Thế Tùng (Lead/Integrator)` trong `configs/lab.yaml`.*
  *Quyết định review trong `reports/decision_log.csv`: `HUMAN_SEV_0/1/2` theo severity-based policy, owner = Nguyễn Thế Tùng, evidence = ảnh gốc.*
- Khi nào HOLD/REWORK thay vì tự động release: *REWORK ngay khi có ảnh dự đoán severity 2 (chụp lại); HOLD khi có ảnh severity 1 cần người quyết; chỉ GO khi pool không vượt ngưỡng nào. Baseline không bao giờ tự GO (`BASELINE_ONLY`).*

## 08 · Reproduce & tests

Đã chạy verify trên máy nộp bài (Windows 11, Python 3.12.10, i5-13600KF):

```bash
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
# 1 lệnh run theo hợp đồng (pipeline mặc định = PoC v1 frozen, exit 0, 0.91s):
python -m src.main --input fixtures/t02_raw_qc --config configs/lab.yaml --output out/ --offline --seed 42
# Chạy trực tiếp từng model:
python -m src.main --track t02 --output out/poc_v1 --run-name poc_v1 --pipeline src.poc.t02_v1 --offline --seed 42
python -m src.main --track t02 --output out/baseline --run-name baseline --pipeline src.baselines.t02_laplacian --offline --seed 42
# Evaluate (GT do đề phát, chuẩn hoá; KHÔNG đọc fixtures/*/gt/):
python -m src.evaluate --track t02 --gt reports/eval_gt_from_Evalimg.txt.csv --pred out/poc_v1/ranked_review.csv --run-name poc_v1 --out reports/metrics_poc.json
python -m src.evaluate --track t02 --gt reports/eval_gt_from_Evalimg.txt.csv --pred out/baseline/ranked_review.csv --run-name baseline --out reports/metrics_baseline.json
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
pytest -q
```

- Output của `pytest -q`: *exit 0, **0 failed**; test của nhóm `tests/test_t02_poc.py` = **4 passed** (success: flag ảnh dark + severity 2, policy REWORK/HOLD/GO; edge: nhóm 1 ảnh không crash, blockiness = 0 trên ảnh phẳng). Các test hạ tầng thiếu GT overlay giảng viên tự skip.*
- Máy / CPU / OS / Python: *Windows 11, Python 3.12.10, Intel i5-13600KF (AMD64, Family 25 Model 80).*
- git sha: *xem tag `final-24h` trên repo (commit cuối cùng); freeze nguồn = `6d445f4` (tag `demo-180m`).*

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: *Dữ liệu synthetic CC0, không người/biển số thật → không PII. Trên dữ liệu thật: quyền sở hữu ảnh, quyền riêng tư người trong ảnh và luật bảo vệ dữ liệu phải được rà soát trước khi review/luư trữ — review queue chứa path ảnh, không chứa dữ liệu nhạy cảm.*
- Điều chưa biết: *Chưa đo trên ảnh thật (real-world); chưa biết failure mode của glare cục bộ trong scene lớn; chưa chắc scale 10× giữ nguyên calibration (group-relative normalization có thể méo nếu nhóm ảnh quá nhỏ/lớn).*
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận: *Không tuyên bố tuân thủ; các giả định ở mục 01 cần DPO/legal/domain owner xác nhận trước khi deploy.*
- Kế hoạch cải tiến: *Thêm feature texture tần số trung bình để tách blur vs compression (fix 2 failure cases); Wilson CI khi N đủ lớn; thử calibration theo severity thay vì binary; chạy trên bộ ảnh thật có GT tự gán.*

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Nguyễn Thế Tùng (2A202603320) | 26ai.tungnt4@vinuni.edu.vn (commit: entity-solo@users.noreply.github.com) | Lead/Integrator: labels + calibration + PoC v1 + baseline re-freeze + eval + report | `6d445f4` (PoC + eval hoàn chỉnh), `2bf7a89` (review queue + decision log) | ☑ |
| Member 2 | ____ | Data & fixtures | — | |
| Member 3 | ____ | Core algorithm | — | |
| Member 4 | ____ | QA/metric | — | |

Ghi chú minh bạch: *Làm việc 1 người, slot 2–4 để trống cho thành viên tham gia sau. Các commit khởi tạo hạ tầng lab (docs/fixtures/tests) thuộc repo starter, tác giả gốc được giữ nguyên lịch sử.*

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| https://www.iso.org/standard/82079.html | 2026-11-14 | Khung QC pipeline cho dữ liệu ảnh — tham chiếu quy trình triage/review/decision của T02. |
| https://github.com/ETH-CVLAB/acdc | 2026-11-14 | Benchmark phân loại ảnh lỗi điều kiện thực — danh sách failure mode cần phủ trong thiết kế slice. |
| https://doi.org/10.5201/ipol.2013.45 (Laplacian variance) | 2026-11-14 | Nguồn feature độ sắc nét dùng cho baseline và blur feature của PoC. |

## 12 · Checklist chốt khi nộp

- [x] Link repo và tag (`demo-180m`, `final-24h`) trong report; input mẫu không chứa PII thật (synthetic CC0).
- [x] Đúng 1 lệnh run (`python -m src.main --input fixtures/t02_raw_qc --config configs/lab.yaml --output out/`), 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics (`metrics_baseline.json`, `metrics_poc.json`), ≥1 failure case (mục 06 có 2), reviewer evidence, decision log.
- [x] Có license/source provenance, data splits (dev 56 / eval 40, chia theo scene), seed 42, offline environment, GT/eval N (23 defect / 17 clean).
- [x] `pytest -q` exit 0, ≥2 test của nhóm (`tests/test_t02_poc.py`: 4 passed — success + edge).
- [x] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
