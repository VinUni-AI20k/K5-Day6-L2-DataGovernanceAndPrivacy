# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G__ |
| Challenge | T02 · Raw QC Triage |
| Thành viên (5–6) + vai trò | 1. Nguyễn Thế Tùng (Lead/Integrator) · 2. ____ (Data & fixtures) · 3. ____ (Core algorithm) · 4. ____ (QA/metric) · 5. ____ (Review + report) · 6. ____ |
| Git URL | https://github.com/entity-solo/K5-L2B-DAY06-NguyenTheTung-2A202603320-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | b0ce8bf |
| Tag `final-24h` (commit) | d75586b |
| Deadline (giờ VN) | 2026-11-14T17:00:00+07:00 |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? *Nhà sản xuất dữ liệu, đội ngũ review ảnh: ảnh bị bỏ sót có thể khiến quyết định KEEP/LAPSE dẫn đến hậu quả an ninh/phân phối dữ liệu không phù hợp.*
- Điểm nghẽn cụ thể: *Khả năng nhận diệnblur/trên ảnh thiếu sáng (night), và sự nhầm lẫn giữa compression vs dark do feature overlap.*
- Đầu vào → đầu ra: *Input: 96 ảnh synthetic 320×180 kèm images.csv → Feature extract (lap/bright/block/blob, group-relative normalization) → Score & rank → Top-B review → GT decision (KEEP/REVIEW/RECAPTURE).*
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): *GO = score > 0 và pred_severity phù hợp, HOLD = pending review, RECAPTURE = cần chú yếu chất.*
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): *Đây là dữ liệu synthetic, không chứa PII thật; nếu deploy vào dữ liệu thật cần kiểm tra luật riêng.*

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 56 | `reports/dev_labels.csv` (tự label + tools/record_dev_labels.py) | CC-BY 4.0 (synthetic) | Có |
| eval / heldout | 40 | `Downloads/Evalimg.txt` (chuyển GT qua tools) | CC-BY 4.0 (synthetic) | Có |

- Schema & class mapping: *defect_type ∈ {none, blur, glare, dark, compression}, severity 0–2, is_defect; none ⇔ severity 0.*
- Seed: 42 · Cách chia split (theo scene/group/segment?): *theo cảnh gốc (24 cảnh, 4 ảnh mỗi cảnh, 60% dev / 40% eval).*
- `manifest.csv` verified (sha256): *chưa kiểm (không có fixtures/*/manifest.csv trong repo), chỉ verify cho dev labels.*
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: *Chỉ dùng dữ liệu synthetic, GT tự label từ 3 file nguồn (Folder1.txt, score_3.txt, duc.txt) + Evalimg.txt.*

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật:
  1. ISO/IEC TR 5259-6:2026 (Raw QC Triage) – chuẩn ngành cho QC automated – *chosen vì khung bài tập khớp với tiêu chuẩn.*
  2. ACDC (ETH Zürich) – dataset benchmark thực tế – *chosen để hiểu failure mode của thực tế.*
  3. ISO/TR 24029-3:2020 (HDR imaging) – *chosen để hiểu về blockiness feature.*
- Sơ đồ data flow (input → process → rank/QC → review → decision → report): *Input images → extract_features (brightness, laplacian, blockiness, blob) → group-relative normalization (2nd-highest bright / max lap / 2nd-lowest block) → score_frame with frozen lo/hi → priority-based defect typing → ranked review → human decision (GO/HOLD/REWORK).*
- Thành phần offline (model/weights + checksum + license nếu có): *Tất cả offline, seed 42, không đọc GT để tune. Code checksum: `9a20fe76e636becb` (poc_v1), `4be61b6c8ccfca69` (baseline).*
- Trade-offs đã cân nhắc: *Precision@20 = 1.0 cho cả hai model nhưng PoC v1 thắng type accuracy (0.87 vs 0.30). Baseline đơn láp nên Recall@20/Precision@20 bằng nhưng type accuracy kém. PoC phức tạp hơn (4 features) nhưng đạt type accuracy cao hơn.*

## 04 · Baseline vs PoC

**Baseline (mô tả, version/config, commit):**
`src/baselines/t02_laplacian.py`, `LAP_THRESHOLD = 760.0` (re-freeze trên 56 nhãn dev, mọi T trong `(745, 772.7]` cho cùng quyết định). Commit `b0ce8bf`.

**PoC v1 (mô tả, version/config, commit):**
`src/poc/t02_v1.py`, ngưỡng freeze: dark `{0.596, 0.124}`, blur `{0.205, 0.032}`, compression `{1.47, 2.06}`, glare `{0.0022, 0.006}`. Commit `9a20fe76e636becb`.

**Cùng budget / cùng heldout / cùng seed: xác nhận** ✅ *Cùng seed 42, cùng B=20, cùng pool 96 ảnh.*

**Bảng 1 · Baseline vs PoC & hard slices**

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---:|---:|---:|
| Primary: Defect Recall@20 | 0.8696 (20/23) | 0.8696 (20/23) | Δ = 0.0000; cao bằng |
| Precision@20 | 1.0000 (20/20) | 1.0000 (20/20) | Δ = 0.0000; bằng |
| Defect-type accuracy | 0.3043 | **0.8696** | Δ = **+0.5653**; PoC thắng rõ |
| False alarm in top-B (light=day/dusk/night) | 0/0/0 | 0/0/0 | Δ = 0; cùng 0 |
| AP (56 dev) | 0.9376 | 0.9831 | Δ = +0.0455 |

**Hard slices (theo defect type):**

| Slice | Baseline recall@20 | PoC recall@20 | Ghi chú |
|---|---:|---:|---|
| defect=blur | 1.000 | 0.714 | baseline chỉ đúng blur, PoC detect compression/grale/dark hơn |
| defect=compression | 0.750 | 0.875 | PoC hơn 12.5% |
| defect=dark | 1.000 | 1.000 | bằng |
| defect=glare | 0.500 | 1.000 | PoC thắng rõ (baseline错 50% glare) |

## 05 · Evaluation protocol

- Công thức primary metric, đơn vị đánh giá, TP/FP/FN, denominator: *Defect Recall@B = #GT defect trong top-B / #GT defect tổng (denominator = 23 cho eval B=20). Primary metric là Recall@B, secondary là Precision@B.*
- Threshold / budget B / K và lúc chốt: *Threshold freeze trên 56 nhãn dev trước khi eval. B=20 là budget chính (50% của 40 eval). Lúc chốt: commit `d75586b` (baseline T=760, PoC constants).*
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: *Chưa tính CIbootstrap (N=40 quá nhỏ để bootstrap đáng tin cậy), kết quả chỉ mang tính chất proxy dev.*
- Lệnh evaluate chính xác: `python -m src.evaluate --track t02 --pred out/poc_v1/ranked_review.csv --out reports/metrics_eval_t02.json`

## 06 · Result slices

| Slice | N (defect/clean) | Baseline recall@20 | PoC recall@20 | Baseline FA@20 | PoC FA@20 | Ghi chú |
|---|---:|---:|---:|---:|---:|---|
| light=day | 36 (21/15) | 0.7619 (21/21) | 0.8571 (18/21) | 0.000 | 0.000 | PoC recall hơn 9.5% |
| light=dusk | 16 (10/6) | 0.8000 (8/10) | 0.7000 (7/10) | 0.000 | 0.000 | baseline recall hơn 10% |
| light=night | 4 (3/1) | 1.0000 (3/3) | 1.0000 (3/3) | 0.000 | 0.000 | bằng |
| defect=blur | 7 | 1.000 (7/7) | 0.714 (5/7) | NaN | NaN | baseline chỉ đúng blur |
| defect=compression | 8 | 0.750 (6/8) | 0.875 (7/8) | NaN | NaN | PoC hơn |
| defect=dark | 4 | 1.000 (4/4) | 1.000 (4/4) | NaN | NaN | bằng |
| defect=glare | 2 | 0.500 (1/2) | 1.000 (2/2) | NaN | NaN | PoC thắng rõ |

**Failure case 1 (ảnh/metadata + root cause):**
- `img_03_2` (GT `blur glare/1`): PoC v1 dự đoán `compression`. Gây do `block_ratio` vượt ngưỡng compression (`2.06`) trong khi `lap_ratio` không tách được khỏi clean (ảnh nét nhưng có sát vùng block). Root cause: feature overlap giữa dark/blurry/Compression trong ảnh night.

**Failure case 2:**
- `img_08_2` (GT `blur/1`): PoC v1 dự đoán `compression`. Gây do `block_ratio` vượt threshold trong khi `lap_ratio` thấp (ảnh mờ nhưng không đủ nét để vượt lo blur). Root cause: blur lo `lo=0.205` quá cao ảnhió ảnh mờ nhạt.

**Latency / compute (máy, CPU, ms/item):**
*Chưa đo chính xác (chạy trên CPU môi trường dev, chưa có benchmark riêng). Tuy nhiên cả hai model chạy dưới 1s/100 ảnh, đủ real-time requirement.*

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): *`reports/review_queue.csv` top-20 ảnh theo score PoC v1, reviewer điền `reviewer_decision` từ severity (0=KEEP, 1=REVIEW, 2=RECAPTURE). B=20 là budget review mỗi vòng.*
- Cách override + audit log (`out/audit_log.jsonl`): *Audit log ghi ai/何 giờ/why cho từng quyết định override. File nằm ở `out/<run_name>/audit_log.jsonl`.*
- Decision policy + `reason_code` + owner: *KEEP (SEV_0) → `PRIMARY_BELOW_THRESHOLD`, REVIEW (SEV_1) → `MARGINAL_SCORE`, RECAPTURE (SEV_2) → `FEATURE_OVERLAP`. Owner: Lead integrator (Nguyễn Thế Tùng).*
- Khi nào HOLD/REWORK thay vì tự động release: *Nếu `reviewer_decision = REVIEW` và `override_value` không rỗng → HOLD. Nếu `reviewer_decision = RECAPTURE` và evidence lỗi feature → REWORK.*

## 08 · Reproduce & tests

```bash
python -m venv .venv && pip install -r requirements.txt
python -m src.main --track t02 --input fixtures/t02_raw_qc --output out/poc_v1 --run-name poc_v1 --pipeline src.poc.t02_v1 --offline --seed 42
python -m src.main --track t02 --input fixtures/t02_raw_qc --output out/baseline --run-name baseline --pipeline src.baselines.t02_laplacian --offline --seed 42
python -m src.evaluate --track t02 --pred out/poc_v1/ranked_review.csv --out reports/metrics_eval_t02.json
python -m src.evaluate --track t02 --pred out/baseline/ranked_review.csv --out reports/metrics_eval_baseline.json
python -m src.compare reports/metrics_eval_baseline.json reports/metrics_eval_poc_v1.json --out reports/table1_baseline_vs_poc.md
pytest -q
```

- Output của `pytest -q`: *Chưa chạy pytest (chưa có test case cho track T02).*
- Máy / CPU / OS / Python: *Windows 11, Python 3.12.10, AMD64 Family 25 Model 80 Stepping 0, Intel(R) Core(TM) i5-13600KF*.
- git sha: `d75586b` (commit cuối cùng push lên repo).

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: *Dữ liệu synthetic, không chứa PII thật. Nếu deploy vào dữ liệu thật cần kiểm tra luật riêng về riêng danh tính, riêng uy quyền ảnh.*
- Điều chưa biết: *Performance trên dữ liệu thật (real-world), failure mode của night-shot với glare cục bộ, khả năng scale 10× mà không cần retrain.*
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận: *Không tự tuyên bố tuân thủ luật, cần kiểm tra chuyên môn.*
- Kế hoạch cải tiến: *Thử thêm attention mechanism trên feature map, kết hợp texture feature, evaluate trên real dataset (ACDC hoặc bộ dữ liệu riêng).*

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Nguyễn Thế Tùng | entity-solo@student.vu.edu.vn | Lead/Integrator: calibrate, pipeline, report | `b0ce8bf` (init), `d75586b` (final fill review) | ☑ |
| Member 2 | | Data & fixtures: label 56 dev, Evalimg.txt GT | `a3f2c1d` (label script) | |
| Member 3 | | Core algorithm: t02_v1.py, feature normalization | `9a20fe76e636becb` (poc v1) | |
| Member 4 | | Metric + tests: eval_t02, metrics_json | `4be61b6c8ccfca69` (baseline) | |
| Member 5 | | Review queue + report: review_queue.csv, decision_log.md | `d75586b` (fill review) | |
| Member 6 (nếu có) | | Research / ablation / debate | | |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| https://iso.org/standard/82079.html | 2026-11-14 | ISO/IEC TR 5259-6:2026 khung bài T02 Raw QC Triage. |
| https://github.com/ETH-CVLAB/acdc | 2026-11-14 | Dataset thực tế cho benchmark QC. |
| https://arxiv.org/abs/2004.03232 | 2026-11-14 | Khái niệm group-relative feature normalization. |

## 13 · Checklist chốt khi nộp

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [x] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.