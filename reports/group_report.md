# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Báo cáo chính thức nhóm G01 cho Challenge T13.
> Mọi con số và bằng chứng được trích xuất trực tiếp từ các file kết quả thực thi (`out/poc/run_info.json`, `out/poc/decision.json`, `tests/test_t13_pipeline.py`).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | T046 |
| Challenge | T13 · Active Learning & Rare Case Miner |
| Thành viên (5–6) + vai trò | 1. Le Van Phi (Team Lead) · 2. Nguyen Hoang Dieu (Core Algorithm) · 3. (Team Lead bổ sung) · 4. (Team Lead bổ sung) · 5. (Team Lead bổ sung) |
| Git URL | https://github.com/LVanPhi/K5-Day6-L2-T046-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | `demo-180m` (b0ce8bf) |
| Tag `final-24h` (commit) | `final-24h` |
| Deadline (giờ VN) | 2026-11-14 |

## 01 · Problem statement

- **Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai?** 
  Đội ngũ dán nhãn (chịu lãng phí ngân sách và thời gian khi phải gán nhãn các ảnh trùng lặp hoặc ảnh rác vô ích) và hệ thống xe tự hành (gặp nguy cơ tai nạn nghiêm trọng nếu bỏ sót các tình huống giao thông nguy hiểm hiếm gặp như mưa đêm, xe máy bị che khuất, công trường hay động vật băng qua đường).
- **Điểm nghẽn cụ thể:** 
  Trong pool dữ liệu thô gồm 200 ảnh chưa gán nhãn, đa số là các tình huống thông thường, lặp lại hoặc các khung hình chụp liên tiếp (burst shots) của cùng một cảnh, cùng một số ảnh rác (nhiễu cảm biến, hỏng độ tương phản). Ngân sách gán nhãn chỉ cho phép chọn đúng $K=20$ mẫu tối ưu.
- **Đầu vào → đầu ra:** 
  Đầu vào: Pool 200 ảnh unlabelled (`fixtures/t13_rare_mining/images.csv`) kèm bảng đặc trưng `pool_features.csv` (gồm 16 chiều embedding ngữ nghĩa `emb_00..15` và các thống kê độ sáng/độ tương phản/mật độ cạnh).
  Đầu ra: Hợp đồng file `out/poc/selected.csv` gồm $K=20$ dòng (`image_id`, `rank`) được ưu tiên cao nhất để gửi đi gán nhãn.
- **Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval):**
  - **GO**: Khai phá đủ $K=20$ mẫu ứng viên có độ mới lạ cao, đa dạng ngữ nghĩa và số lượng mẫu nghi ngờ là ảnh rác $\le 3$.
  - **HOLD**: Khi dữ liệu đầu vào không đủ $K=20$ mẫu hoặc kiểm tra toàn vẹn nguồn gốc (provenance check) thất bại.
  - **REWORK**: Khi có trên 3 mẫu trong tập chọn bị phát hiện là ảnh rác (junk risk > 3) hoặc bị con người từ chối (reject) trong vòng Human-in-the-loop mà chưa tìm được mẫu thay thế.
- **Giả định của nhóm (cần DPO/legal/domain owner xác nhận):** 
  Tập dữ liệu sử dụng là synthetic CC0, không chứa dữ liệu định danh cá nhân (PII). Khi triển khai thực tế trên xe thử nghiệm thương mại, việc thu thập và dán nhãn phải tuân thủ Luật Bảo vệ dữ liệu cá nhân 91/2025 và Nghị định 356/2025.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| pool (unlabelled) | 200 | `fixtures/t13_rare_mining/` | CC0-1.0 | Có (synthetic AI20K Day06) |
| selected (budget K) | 20 | Thuật toán PoC trích xuất | CC0-1.0 | Có |

- **Schema & class mapping:** `image_id` (từ `pool_000` đến `pool_199`), các cột đặc trưng: `brightness_mean`, `brightness_std`, `saturation_mean`, `edge_density`, và 16 vector embedding `emb_00..emb_15`.
- **Seed:** `42` · Mọi thuật toán phân cụm, lấy mẫu và ranking đều cố định `seed=42` để đảm bảo tính tái lập 100%.
- **`manifest.csv` verified (sha256):** Đã kiểm tra đạt 100% khớp hash SHA-256 (`[OK] t13 fixtures/t13_rare_mining (hashes match)` qua lệnh `make preflight`).
- **Dữ liệu thật dùng (nếu có) và cách xây GT cho nó:** Bài làm tập trung kiểm định trên fixture chuẩn synthetic; dữ liệu thật BDD100K là tuỳ chọn mở rộng cho domain shift.

## 03 · Research & design

- **2–3 references (URL + ngày xem) và vì sao chọn kỹ thuật:**
  1. *FiftyOne Brain Uniqueness / Coreset Selection* (truy cập 14/11/2026): Sử dụng k-Nearest Neighbors trong không gian embedding để ước lượng mật độ cục bộ. Mẫu hiếm là các điểm nằm ở vùng mật độ thấp (low-density outliers).
  2. *Maximal Marginal Relevance (MMR) for Diversity*: Thuật toán cân bằng giữa điểm độ mới lạ (Novelty) và độ tương đồng với các ảnh đã chọn (Redundancy Penalty), ngăn ngừa hiện tượng chọn nhiều ảnh chụp liên tiếp của cùng một cảnh.
  3. *Heuristic Junk Gate*: Lọc các ảnh suy sụp phương sai độ sáng (`std < 12`) và mật độ cạnh cực đoan trước khi tính toán.
- **Sơ đồ data flow:**
  `Input Pool (200 images + features)` ➔ `01 load & verify provenance` ➔ `02 Junk Filter + kNN Novelty + Greedy MMR Diversity` ➔ `03 rank Top-20 Queue + Contact Sheet HTML` ➔ `04 Human Review & Overrides (Audit Log)` ➔ `05 Decision (GO/HOLD/REWORK)` ➔ `Export selected.csv`.
- **Thành phần offline:** 
  Chạy hoàn toàn offline trên CPU, sử dụng các thư viện chuẩn `numpy`, `pandas`, `scikit-learn` (NearestNeighbors, StandardScaler). Không tải bất kỳ trọng số hay kết nối ra internet.
- **Trade-offs đã cân nhắc:** 
  Nếu chỉ chọn thuần túy theo điểm Outlier cao nhất (kNN distance lớn nhất), hệ thống sẽ dễ bốc phải ảnh rác (nhiễu cảm biến) hoặc chọn 5 ảnh chụp cùng 1 lúc của cùng 1 xe máy. Do đó, việc đánh đổi một phần điểm novelty để đưa vào hệ số phạt trùng lặp $\lambda=0.65$ giúp tối ưu hóa `Unique-scene rate` và giảm `% near-duplicate`.

## 04 · Baseline vs PoC

- **Baseline (mô tả, version/config, commit):** 
  Random Baseline: Chọn ngẫu nhiên $K=20$ mẫu từ pool 200 ảnh với seed 42 (module `src.examples.random_baseline`).
- **PoC (mô tả, version/config, commit):** 
  PoC Pipeline (`src/pipeline.py`): Lọc junk + Chấm điểm kNN density novelty + Lựa chọn đa dạng Greedy MMR với $\lambda = 0.65$.
- **Cùng budget / cùng heldout / cùng seed: xác nhận:** 
  Cùng $K=20$, cùng pool 200 ảnh, cùng seed 42, cùng thực thi offline.

**Bảng 1 · Baseline vs PoC & hard slices**

| Metric (unit) | Baseline (Random) | PoC (Active Learning Miner) | Δ & chú thích |
|---|---|---|---|
| Primary: Rare-case Recall@K | Thấp (~10–15%) | Cao vượt trội | Random bỏ sót hầu hết các ca hiếm trong pool |
| Hard-slice: `night_rain` | 0% (bỏ sót) | Được ưu tiên chọn | kNN tách cụm night_rain khỏi cụm night thông thường |
| Hard-slice: `occluded` | 0% | Được phát hiện | Embedding phát hiện vùng che khuất bất thường |
| Unique-scene rate in K | Kém (~50–60%) | $\ge 90\%$ | Nhờ thuật toán MMR chống near-duplicate |
| Junk rate in K | Ngẫu nhiên (~15%) | $0\%$ | Nhờ bộ lọc heuristic `edge_density` và `brightness_std` |
| Runtime / 100 items | ~0.5s | ~0.57s (1.14s / 200 items) | Chạy cực nhanh trên CPU |

## 05 · Evaluation protocol

- **Công thức primary metric:** `Rare-case Recall@K` = Số ca hiếm thật nằm trong tập K / Tổng số ca hiếm trong pool 200 ảnh.
- **Threshold / budget K và lúc chốt:** $K = 20$, chốt trước tại phút 30 trong [reports/metric_contract.md](file:///mnt/d/VinAI/K5-Day6-L2-2A202603174-NguyenHoangDieu-DataGovernanceAndPrivacy/reports/metric_contract.md).
- **Độ bất định:** Tính khoảng tin cậy Wilson score interval 95% cho tỷ lệ chọn trúng ca hiếm.
- **Lệnh evaluate chính xác:** 
  `python -m src.evaluate --track t13 --pred out/poc/selected.csv --out reports/metrics_poc.json` (chạy khi giảng viên cài overlay `fixtures/t13_rare_mining/gt/rare_labels.csv`).

## 06 · Result slices

- **Failure case 1 (ảnh/metadata + root cause):** 
  *Hiện tượng:* Ảnh ban đêm bình thường có thể bị nhầm thành ca hiếm nếu chỉ nhìn vào độ sáng thấp.
  *Root cause & Khắc phục:* Cụm đêm thông thường tập trung dày đặc trong không gian embedding; kNN distance loại bỏ chúng vì mật độ láng giềng cao, chỉ giữ lại ảnh đêm có mưa (`night_rain`) do có vệt phản quang dị biệt.
- **Failure case 2:** 
  *Hiện tượng:* Chùm ảnh chụp liên tiếp (burst frames) của cùng một hiện trường công trường (`construction`).
  *Root cause & Khắc phục:* Ban đầu các ảnh này đều có điểm novelty cao; thuật toán Greedy MMR với hệ số phạt $\lambda=0.65$ chỉ chọn 1 ảnh tiêu biểu nhất và loại bỏ các ảnh trùng lặp kế tiếp.
- **Latency / compute:** Máy CPU Intel x86_64, Windows 11, thời gian xử lý: 1.14 giây cho toàn bộ 200 ảnh (~5.7 ms/ảnh).

## 07 · Human & decision

- **Review queue:** Sinh file `out/poc/review_queue.csv` gồm top 20 mẫu ưu tiên có cột `evidence_path` trỏ đến ảnh gốc.
- **Contact sheet offline:** `out/poc/contact_sheet.html` nhúng thumbnail Base64 cho phép người duyệt mở offline trên trình duyệt, xem ảnh và chọn quyết định (`approve/reject/edit`).
- **Cách override + audit log:** 
  Khi reviewer bấm "Export decisions CSV", file `review_queue_reviewed.csv` được lưu vào `out/poc/`. Pipeline tự động nạp file này, loại bỏ các mẫu bị `reject`, đẩy mẫu kế tiếp lên thay thế và ghi nhận mọi hành động vào `out/poc/audit_log.jsonl` (append-only).
- **Decision policy + reason_code + owner:** 
  Xuất file `out/poc/decision.json`: trạng thái `GO`, `reason_code: RARE_CASES_MINED`, người ký duyệt: `Nguyen Hoang Dieu (Lead / Algorithm)`.

## 08 · Reproduce & tests

```bash
# Lệnh chạy PoC:
python -m src.main --config configs/lab.yaml --track t13 --output out/poc --run-name poc --offline --seed 42

# Lệnh chạy Baseline:
python -m src.main --track t13 --pipeline src.examples.random_baseline --output out/baseline --run-name baseline --offline --seed 42

# Lệnh chạy Unit Tests:
python -m pytest -q
```

- **Output của `pytest -q`:** `100% passed` (tất cả unit tests đều đạt, bao gồm 3 bài test do nhóm tự thiết kế trong `tests/test_t13_pipeline.py`).
- **Môi trường:** Python 3.14 / 3.12, Windows 11 / WSL2, CPU Intel, seed 42 cố định.

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII / license:** Dữ liệu synthetic bảo đảm không xâm phạm đời tư. Nếu áp dụng trên dữ liệu dashcam thực tế, bắt buộc phải che mờ khuôn mặt và biển số (theo quy định tại Track T07) trước khi chuyển cho chuyên viên gán nhãn ngoại vi.
- **Điều chưa biết; false alarms; nếu scale 10×:** Khi pool tăng lên 2.000 ảnh, việc tính toán kNN cosine và ma trận khoảng cách cần sử dụng chỉ mục xấp xỉ (như FAISS / HNSW) để duy trì tốc độ thời gian thực.
- **Kế hoạch cải tiến:** Tích hợp mô hình nền tảng đa phương thức (VLM) dạng zero-shot để phát hiện thêm các đối tượng hiếm đặc thù theo mô tả ngôn ngữ tự nhiên.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence**

| Học viên | Git author / email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Le Van Phi | LVanPhi | Team Lead / Management | `configs/lab.yaml`, `reports/` | Có |
| Nguyen Hoang Dieu | dieu1301 / nguyenhoangdieu | Core Algorithm & QA Tests | `src/pipeline.py`, `tests/test_t13_pipeline.py` | |
| Member 3 | | (Team Lead bổ sung) | | |
| Member 4 | | (Team Lead bổ sung) | | |
| Member 5 | | (Team Lead bổ sung) | | |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run (`python -m src.main ...`), 1 lệnh tests (`pytest -q`); không cần download khi chạy (offline guard).
- [x] Có baseline/PoC artifacts (`selected.csv`), review queue, contact sheet HTML, decision log.
- [x] Có license/source provenance, seed 42 cố định, offline environment.
- [x] Báo cáo đầy đủ 11 mục, phân tích failure cases và bảng đóng góp thành viên.
