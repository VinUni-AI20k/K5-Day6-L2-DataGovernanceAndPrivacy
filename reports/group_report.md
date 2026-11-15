# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G04 |
| Challenge | T02 · Raw QC Triage: blur, glare, dark, compression |
| Thành viên (5–6) + vai trò | 1. Hoàng Thu Hương (Lead/Integrator) · 2. ____ (Data & fixtures) · 3. ____ (Core algorithm) · 4. ____ (QA/metric) · 5. ____ (Review + report) · 6. ____ |
| Git URL | https://github.com/borisbrjch/K5-Day6-L2-HoangThuHuong-2A202603143-DataGovernanceAndPrivacy  |
| Tag `demo-180m` (commit) | ____ |
| Tag `final-24h` (commit) | ____ |
| Deadline (giờ VN) |  |

## 01 · Problem statement

- **Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai?**
  Batch ảnh camera hành trình (dashcam / field survey) được dùng để train perception model hoặc làm bằng chứng. Ảnh mờ, lóa, tối, hoặc nén quá mức làm giảm chất lượng dataset và có thể khiến downstream model học từ dữ liệu kém. Nếu QC bỏ sót (false negative), ảnh lỗi vào training set → giảm performance. Nếu QC báo nhầm (false positive), ảnh tốt bị loại → mất dữ liệu, tốn thời gian reviewer.
- **Điểm nghẽn cụ thể:**
  96 ảnh synthetic từ 24 cảnh gốc, review budget B=20 ảnh. Không thể review toàn bộ → cần ranking ưu tiên ảnh nghi lỗi. Baseline Laplacian variance toàn ảnh có 2 vấn đề: (1) không phát hiện glare/dark/compression, (2) camera cam_B có optical softness tự nhiên thấp hơn ~3-4x → bị báo nhầm blur.
- **Đầu vào → đầu ra:**
  Input: `fixtures/t02_raw_qc/images.csv` (96 rows: image_id, path, camera_id, light, split) + 96 JPEG 320×180.
  Output: `out/ranked_review.csv` (image_id, score; cao = review trước), `out/review_queue.csv` (top-20), `out/contact_sheet.html`, `out/decision.json`.
- **Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval):**
  - **KEEP (GO):** Top-20 reviewed, zero confirmed defects → batch sạch, release.
  - **HOLD:** Review chưa hoàn thành (<20/20) hoặc không có reviewer file → chờ review.
  - **RECAPTURE (REWORK):** ≥1 confirmed defect trong top-20 → batch bị contaminated, cần chụp lại toàn bộ (96 ảnh).
  - Decision policy áp dụng cho full batch (96 images), không chỉ top-20.
- **Giả định của nhóm (cần DPO/legal/domain owner xác nhận):**
  (1) Top-20 là risk-weighted sample đủ đại diện để suy luận về full batch — nếu top-20 sạch thì full batch coi như sạch (statistical assumption, không phải guarantee).
  (2) Ảnh synthetic representative cho ảnh camera thật về phân bố defect types và severities.
  (3) Các defect types (blur, glare, dark, compression) độc lập về mặt scoring (weighted-sum assumption).

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 40 | `fixtures/t02_raw_qc/images.csv` (split=dev) | Synthetic, generated in-repo | Yes |
| eval / heldout | 56 | `fixtures/t02_raw_qc/images.csv` (split=eval) | Synthetic, generated in-repo | Yes |

- **Schema & class mapping:**
  `images.csv`: `image_id` (str), `path` (str), `camera_id` (cam_A / cam_B), `light` (day / dusk / night), `split` (dev / eval).
  GT (không đọc trong pipeline): `defect_type` ∈ {none, blur, glare, dark, compression}, `severity` ∈ {0, 1, 2}, `is_defect` ∈ {0, 1}.
- **Seed:** 42 · **Cách chia split:** Scene-based split (24 cảnh gốc → 70% dev / 30% eval by scene), seed 42. Không chia ngẫu nhiên theo ảnh để tránh leakage giữa các ảnh cùng scene.
- **`manifest.csv` verified (sha256):** Có — pipeline gọi `verify_manifest()` trong `load()`, fail loudly nếu hash mismatch. Lệnh: `python -m tools.verify_manifests` (hoặc để pipeline tự verify khi chạy).
- **Dữ liệu thật dùng (nếu có) và cách xây GT cho nó:** Không dùng dữ liệu thật. Toàn bộ synthetic, GT do instructor repo tạo (private, không truy cập được từ pipeline).

## 03 · Research & design

- **2–3 references và vì sao chọn kỹ thuật:**
  1. **Pech-Pacheco et al. (2000), "Diatom autofocusing in brightfield microscopy: a comparative study"** — Laplacian variance là phương pháp cổ điển để đo sharpness, dùng cho blur detection. Ưu điểm: CPU-only, nhanh (~1ms/ảnh 320×180), không cần model. Nhược điểm: phụ thuộc texture và camera optics → cần camera-specific normalization.
  2. **"No-Reference Image Quality Assessment" survey (2010s)** — Các feature như luminance percentiles, saturated pixel fraction, blockiness ratio đều là các no-reference IQ metrics phổ biến. Chọn các feature này vì (a) giải thích được, (b) không cần training, (c) phù hợp với 96 ảnh (quá ít để train ML model).
  3. **JPEG blocking artifact theory (8×8 DCT grid)** — Compression artifacts xuất hiện theo lưới 8×8 do DCT block size. Blockiness ratio (boundary gradient / interior gradient) là feature trực tiếp phát hiện artifact này.

- **Sơ đồ data flow:**
  ```
  input/images.csv (96 rows)
      ↓
  [01 load] verify manifest SHA256 → load metadata
      ↓
  [02 process] for each image:
      ├─ load_rgb (fail → score=100, audit log)
      ├─ extract features:
      │   ├─ lap_var (blur)
      │   ├─ lum_p95 (dark)
      │   ├─ glare_blob_fraction (glare, 8-connected saturated region)
      │   └─ blockiness_ratio (JPEG 8×8)
      ├─ compute_badness: [0,1] per feature (camera-aware normalization for blur)
      ├─ aggregate_score: weighted sum → [0, 100]
      └─ infer_defect_type: argmax badness (epsilon filter)
      ↓
  [03 rank] sort by (score DESC, image_id ASC) → top-20 review queue
      ↓
  [04 review] render contact_sheet.html; optional reviewer overrides (review_queue_reviewed.csv)
      ↓
  [05 decide] batch policy: no review → HOLD (BASELINE_ONLY); 0 defects → KEEP; ≥1 defect → RECAPTURE
      ↓
  output: ranked_review.csv, review_queue.csv, contact_sheet.html, decision.json, audit_log.jsonl
  ```

- **Thành phần offline (model/weights + checksum + license nếu có):**
  Không có model weights. Chỉ dùng NumPy/SciPy/Pillow (đã có trong requirements.txt). Toàn bộ calibrated parameters nằm trong `params:` của `configs/tracks/t02.yaml` (nối qua `track_config:` trong `configs/lab.yaml`); pipeline đọc bằng `load_params(ctx.config)` và fail loudly nếu thiếu key. Derived from `/tmp/t02_probe3.py` GT-free calibration.

- **Trade-offs đã cân nhắc:**
  | Lựa chọn | Ưu điểm | Nhược điểm | Quyết định |
  |---|---|---|---|
  | Weighted-sum aggregation | Tích lũy multi-defect, giải thích được | Có thể bỏ sót single severe defect nếu weight thấp | **Chọn** — R@20=0.286 vs max-risk 0.250 trên validation pool |
  | Max-risk aggregation | Catch single severe defect | Không tích lũy multi-defect | Loại — P@20=0.700 vs 0.800 |
  | Camera-specific normalization | Fix cam_B false positive | Cần đủ dev data per camera | **Chọn** — dev có 40 ảnh, đủ để tính median per camera |
  | Global threshold | Đơn giản | cam_B bị báo nhầm (~3-4x lap_var thấp hơn) | Loại — root cause của failure mode C |
  | Absolute dark threshold (70) | Night ảnh thật vẫn >70 (dev p05=78) | Có thể miss extreme underexposure | **Chọn** — validate trên dev p05 |
  | Light-conditioned dark threshold | Chính xác hơn | Cần tune per-light, nguy cơ overfit | Loại — không đủ data, đơn giản hóa |

## 04 · Baseline vs PoC

- **Baseline (mô tả, version/config, commit):**
  Single-feature Laplacian variance: `score = -laplacian_variance(img)`. Không camera normalization, không multi-defect. Ưu điểm: đơn giản, deterministic. Nhược điểm: (1) không phát hiện glare/dark/compression, (2) cam_B bị báo nhầm blur do optical softness tự nhiên (lap_var median cam_B=235.8 vs cam_A=870.7).
  Test baseline: `tests/test_t02_pipeline.py::test_t02_baseline_sharp_image_low_score` và `test_t02_baseline_blurry_image_high_score`.

- **PoC (mô tả, version/config, commit):**
  Multi-defect scoring: 4 features (blur + dark + glare + compression) → badness [0,1] per feature → weighted sum → score [0, 100].
  - Blur: camera-normalized Laplacian variance (`lap_var / camera_median`)
  - Dark: luminance p95 (absolute threshold 70; dev night p05=78, an toàn)
  - Glare: largest connected saturated blob (8-connected, ≥250 threshold)
  - Compression: JPEG 8×8 blockiness ratio
  Parameters frozen in `configs/tracks/t02.yaml` (`params:`), read by `src/pipeline.py::load_params(ctx.config)`. GT-free calibration source: `/tmp/t02_probe3.py`.

- **Cùng budget / cùng heldout / cùng seed:** Xác nhận — B=20, eval split (n=56), seed 42, same manifest SHA256.

**Bảng 1 · Baseline vs PoC & hard slices** — PoC metrics từ synthetic validation pool (112 items: 56 clean + 56 corrupted sev1, round-robin defect types), KHÔNG phải T02 GT. Eval metrics chưa có (hidden GT).

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: Defect Recall@20 (image) | *Not measured* | 0.286 | PoC validation pool; higher is better; oracle ceiling=0.357 (20/56) |
| Hard-slice: Precision@20 | *Not measured* | 0.800 | 16/20 top-20 are true defects; 4 clean false alarms |
| Hard-slice: max-risk R@20 (comparison) | — | 0.250 | Weighted-sum outperforms max-risk by 0.036 |
| Review@B / miss / FP | — | Miss=0.714 (40/56 defects not in top-20), FP=0.200 (4/20) | B=20, N=112 validation pool |
| Runtime / 100 items | ~100ms | ~150ms | CPU only, ~1.5ms/image (320×180) |

**Ghi chú quan trọng:** Defect Recall@20 trên eval split (n=56) **chưa thể tính** vì GT nằm trong `fixtures/t02_raw_qc/gt/` (guard chặn). Con số 0.286 ở trên là từ synthetic validation pool (oracle ceiling=0.357 do pool có 56 defects, budget=20). Khi có hidden evaluator: `python -m src.evaluate --track t02 --pred out/ranked_review.csv --out reports/metrics_poc.json`.

## 05 · Evaluation protocol

- **Công thức primary metric, đơn vị đánh giá, TP/FP/FN, denominator:**
  `Defect Recall@20 = |{defects in top-20}| / |{total defects in eval pool}|`
  - Unit: image (exact image_id match)
  - TP: defect image in top-20; FN: defect image not in top-20; FP: clean image in top-20
  - Denominator: total defects in eval split
  - Evaluator filter: chỉ giữ predictions có `image_id ∈ GT.image_id`, sort by score DESC (mergesort), take top-20.
  - Xem chi tiết: `reports/metric_contract.md`
- **Threshold / budget B / K và lúc chốt:**
  B=20 (fixed by T02 spec). Thresholds calibrated GT-free on dev split (n=40) via synthetic corruption injection, frozen 2026-11-15 00:26 UTC+7 in `configs/tracks/t02.yaml` (`params:`). Weights frozen from validation pool (56 clean + 56 sev1 corrupted, round-robin defect types).
- **Độ bất định (CI/bootstrap/variance) khi N nhỏ:**
  Wilson score interval cho proportions (Recall@20, Precision@20). Eval n=56, budget B=20 → CI width ~±0.15 at p=0.5. Report exact counts alongside rates. Không dùng bootstrap vì (a) deterministic ranking, (b) N quá nhỏ để bootstrap stable.
- **Lệnh evaluate chính xác:**
  `python -m src.evaluate --track t02 --pred out/ranked_review.csv --out reports/metrics_poc.json`

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| light=day | 28 | — | — | Chưa đo (cần GT) |
| light=dusk | 8 | — | — | Chưa đo (cần GT) |
| light=night | 4 | — | — | **Failure mode A:** night images có thể bị dark score cao dù hợp lệ; dev night p05=78 > threshold 70 → PoC không flag night nhầm |
| camera=cam_A | 32 | — | — | lap_var median=870.7; normalized ratio ổn định |
| camera=cam_B | 24 | — | — | **Failure mode C:** lap_var median=235.8 (3.7x thấp hơn cam_A); camera normalization fix |

- **Failure case 1 (ảnh/metadata + root cause):**
  **Night image bị flag dark (Failure mode A).** Dev image `img_XX` (light=night): lum_p95 có thể thấp hơn threshold 70 nếu scene cực tối. Root cause: dark threshold tuyệt đối không phân biệt "night hợp lệ" vs "underexposure". Mitigation: dev night p05=78 > 70, nên PoC hiện tại không flag night nhầm. Nếu cần xử lý extreme night: light-conditioned threshold (night → 55-60) thay vì 70.
- **Failure case 2 (Failure mode B — local glare):**
  **Ảnh nét nhưng biển số/vùng cục bộ bị cháy sáng.** Global Laplacian vẫn cao (blur badness=0), global mean brightness không nhạy với vùng nhỏ. Root cause: chỉ dùng global brightness bỏ sót local saturation. Mitigation: PoC dùng `glare_blob_fraction` (largest connected saturated region ≥250, 8-connected) → phát hiện local glare. Calibration: catches 82% sev1/100% sev2, 0% dev flagged.
- **Failure case 3 (Failure mode C — cam_B false positive):**
  **cam_B bị báo nhầm blur.** lap_var median cam_B=235.8 vs cam_A=870.7 (3.7x). Global threshold (e.g., lap_var<300) sẽ flag toàn bộ cam_B. Root cause: optical softness tự nhiên khác camera. Mitigation: camera-specific normalization `lap_var / camera_median` → ratio ổn định across cameras. Calibration: blur_threshold=0.15 on ratio catches 100% sev1/2, 14% dev flagged.
- **Latency / compute (máy, CPU, ms/item):**
  CPU-only (no GPU). ~1.5ms/image (320×180, 4 features). Full 96-image batch: ~150ms. MacOS Darwin 23.6.0, Python 3.12.4.

## 07 · Human & decision

- **Review queue (file, B, cách ưu tiên):**
  `out/review_queue.csv`, B=20. Sorting: `ranked_review.csv` sorted by (score DESC, image_id ASC) — deterministic tie-break. Queue columns: `item_id`, `score`, `reason` (feature breakdown), `slice` (light condition), `evidence_path` (for contact sheet).
- **Cách override + audit log (`out/audit_log.jsonl`):**
  Reviewer tạo `out/review_queue_reviewed.csv` với columns: `item_id`, `reviewer`, `reviewer_decision` ∈ {approve, reject, edit}, `override_value` (score for edit), `review_note`.
  - `reject` (no value): ảnh OK → score=-1e9 (drop out of top-B)
  - `edit` (score): replace model score
  - `approve`: confirm defect, keep score
  Mọi thay đổi ghi vào `audit_log.jsonl` (append-only, không xóa history).
- **Decision policy + `reason_code` + owner:**
  - No reviewer file → `HOLD`, reason_code=`BASELINE_ONLY`, metrics: n_images=96, budget=20, n_reviewed=0
  - Review incomplete (<20/20) → `HOLD`, reason_code=`REVIEW_INCOMPLETE`
  - 20/20 reviewed, 0 defects → `KEEP` (GO), reason_code=`REVIEW_COMPLETE_BATCH_CLEAN`
  - ≥1 defect confirmed → `RECAPTURE` (REWORK), reason_code=`DEFECT_CONFIRMED_IN_BATCH`, metrics: defect_image_ids (first 10)
  Owner: `configs/lab.yaml::owner` (phải ≠ "TODO-owner" khi submit).
- **Khi nào HOLD/REWORK thay vì tự động release:**
  - **HOLD:** Chưa có human review (PoC default) hoặc review chưa đủ 20/20. Không tự động release dựa trên heuristic.
  - **REWORK:** ≥1 defect confirmed trong top-20 → batch bị contaminated, cần chụp lại. Không tự động recapture chỉ vì heuristic score cao — cần human confirm.
  - **GO:** Top-20 reviewed sạch → full batch release. Assumption: top-20 là risk-weighted sample đủ đại diện.

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/t02_raw_qc --config configs/lab.yaml --output out/ --offline --seed 42
python -m src.evaluate --track t02 --pred out/ranked_review.csv --out reports/metrics_poc.json
pytest -q
```

- **Output của `pytest -q`:** `tests/test_t02_pipeline.py`: **9 passed** (4 baseline + 5 validation tests). Full suite: **1 failed, 55 passed, 39 skipped** — failure duy nhất là `test_cli.py::test_template_pipeline_fails_clearly_not_silently`, test template giả định pipeline T02 *chưa* implement (expect `rc==3`); sau khi implement, pipeline trả `rc==0` đúng hành vi mới. File `test_cli.py` là shared infrastructure, giữ nguyên vẹn so với HEAD (`git diff` rỗng); premise test đã hết hiệu lực, nhóm quyết định không sửa file này.
- **Máy / CPU / OS / Python:** Darwin 23.6.0 (macOS), Python 3.12.4 · git sha: `b0ce8bf` (trước Phase 3); commit PoC: TBD.

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII / license:**
  Toàn bộ synthetic data, không chứa PII thật. License: in-repo synthetic generation (xem `fixtures/t02_raw_qc/manifest.csv`). Không dùng ảnh thật → không có rủi ro privacy.
- **Điều chưa biết; false alarms; nếu scale 10× thì sao:**
  - **False alarms:** Validation pool FP rate 20% (4/20). Trên eval split chưa biết vì không có GT. False alarms = ảnh sạch vào top-20 → tốn reviewer time, không gây hại downstream.
  - **Nếu scale 10× (960 ảnh):** (1) Camera medians có thể lệch nếu phân bố camera thay đổi → cần recalibrate on larger dev set. (2) Threshold absolute (dark=70, glare=0.01) có thể cần scale theo lighting conditions. (3) Review budget B=20 sẽ không đủ → cần scale B proportionally hoặc stratified sampling by camera/light.
  - **Điều chưa biết:** (1) Performance trên eval split chưa đo (hidden GT). (2) Severity calibration: threshold tuned cho sev1/sev2; severity 0.5 (borderline) chưa test.
- **Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận:**
  Synthetic data, không có PII. Nếu dùng ảnh camera thật sau này: cần DPO review về (a) consent, (b) retention policy, (c) face/plate blurring nếu cần.
- **Kế hoạch cải tiến:**
  1. **Eval split measurement:** Khi có hidden evaluator, chạy `python -m src.evaluate --track t02 --pred out/ranked_review.csv` → report Recall@20, Precision@20, slices.
  2. **Failure mode A (night):** Implement light-conditioned dark threshold (day=70, dusk=55, night=40) nếu eval cho thấy night false positives.
  3. **Failure mode B (local glare):** Tile-based analysis (e.g., 4×4 grid) để phát hiện glare nhỏ hơn nếu recall thấp.
  4. **Compression:** Blockiness recall 48% sev1 → có thể cải thiện với DCT-domain features hoặc multiple thresholds.
  5. **Calibration:** Tăng dev split size (hiện 40) để thresholds ổn định hơn; cross-validation cho threshold sweep.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Member 1 | | Integration / CLI | | |
| Member 2 | | Data + GT | | |
| Member 3 | | Core algorithm | | |
| Member 4 | | Metric + tests | | |
| Member 5 | | Review queue + report | | |
| Member 6 (nếu có) | | Research / ablation / debate | | |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| Pech-Pacheco et al. (2000), Diatom autofocusing | 2026-11-14 | Laplacian variance as sharpness metric; foundation for blur baseline |
| JPEG blocking artifacts (8×8 DCT grid theory) | 2026-11-14 | Block boundary discontinuity → blockiness ratio feature |
| No-reference IQA survey (luminance percentiles, saturated fraction) | 2026-11-14 | Dark/glare feature design rationale |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
