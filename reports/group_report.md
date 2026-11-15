# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G__ |
| Challenge | T__ · ______________________ |
| Thành viên (5–6) + vai trò | 1. ____ (Lead/Integrator) · 2. ____ (Data & fixtures) · 3. ____ (Core algorithm) · 4. ____ (QA/metric) · 5. ____ (Review + report) · 6. ____ |
| Git URL | ____ |
| Tag `demo-180m` (commit) | ____ |
| Tag `final-24h` (commit) | ____ |
| Deadline (giờ VN) | ____ |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? ____
- Điểm nghẽn cụ thể: ____
- Đầu vào → đầu ra: ____
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): ____
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): ____

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | | | | |
| eval / heldout | | | | |

- **Schema & class mapping:** `images.csv` (`image_id`, `path`), `pool_features.csv` (`image_id`, `brightness_*`, `saturation_mean`, `edge_density`, `emb_00..15`). Rare tags dùng để đánh giá: `night_rain`, `occluded_motorbike`, `construction`, `animal`.
- **Seed:** 42. **Cách chia split:** không chia. Pool cố định cho cả baseline và PoC, GT chỉ dùng ở khâu đánh giá của giảng viên.
- **`manifest.csv` verified (sha256):** Có — lệnh: `python -m tools.verify_manifests`. Pipeline cũng tự kiểm hash ở bước `load` (`strict_provenance`).
- **Dữ liệu thật:** chỉ dùng tài liệu trong fixtures/t13


## 03 · Research & design

- **Tài liệu tham khảo và lý do chọn kỹ thuật** (URL và ngày xem điền ở mục 11):
  - FiftyOne Brain uniqueness: ý tưởng chấm độ "độc nhất" của ảnh bằng khoảng cách trong không gian embedding, nên dùng kNN novelty.
  - BDD100K: nguồn các tình huống hiếm thật (foggy, tunnel, gas stations, snowy+night) để định nghĩa rare.
  - Hướng gợi ý trong đề: density-weighted novelty (kNN distance), dedupe, loại junk, k-center greedy. PoC làm theo hướng này.
- **Sơ đồ data flow:**
  ```
  manifest.csv ──► 01 load (kiểm sha256) ─┐
  pool_features.csv + images.csv ─────────┤
                                          ▼
  02 process: chuẩn hoá emb_* → novelty (kNN, k=5) + rarity (KMeans, 10 cụm)
              → junk (robust z) → k-center greedy + dedupe cứng + giới hạn ảnh tối
                                          ▼
  03 rank: top-K review queue (K=20) → review_queue.csv + contact_sheet.html
                                          ▼
  04 review: reviewer approve/reject → audit_log.jsonl → chọn lại K (reject được thay thế)
                                          ▼
  05 decide: GO / HOLD / REWORK + reason_code + owner → decision.json, selected.csv
  ```
- **Thành phần offline (model/weights):** không có model hay weights tải về; chỉ dùng `scikit-learn` (StandardScaler, NearestNeighbors, KMeans) trên đặc trưng có sẵn. Không có checksum hay license model cần khai.
- **Trade-offs đã cân nhắc:**
  - Chỉ tính novelty/rarity/dedupe trên `emb_*` (không trộn `brightness_*`) để tránh thiên về ảnh tối; đổi lại bỏ qua tín hiệu độ sáng khi chấm rare. Độ sáng chỉ dùng để giới hạn tỉ lệ ảnh tối (`dark_cap = 0.6`).
  - Dedupe cứng (loại ảnh quá gần ảnh đã chọn) giảm trùng nhưng có thể loại nhầm ảnh rare nằm gần một ảnh đã chọn.
  - Loại junk theo robust z có nguy cơ coi ảnh rare thật (vốn là điểm ngoại lai) là junk.
  - `n_clusters = 10` là heuristic (`min(10, n // 5)`), chưa chọn bằng silhouette; ablation k = 5/10/20 có thể bổ sung.

## 04 · Baseline vs PoC

- **Baseline:** chọn ngẫu nhiên K = 20 (`src.examples.random_baseline`), seed 42.
- **PoC:** `src/pipeline.py` (file `pipeline_t13.py`), `mode = hybrid`, tham số mặc định như trong `reports/metric_contract.md`. 
- **Cùng budget / heldout / seed:** B = K = 20, cùng pool 200 ảnh, seed 42
**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:
| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: Rare-case Recall@K (image) | [chờ eval] | [chờ eval] | higher is better |
| Hard-slice: `night_rain` (image) | [chờ eval] | [chờ eval] | N=[chờ eval] |
| Hard-slice: `occluded_motorbike` (image) | [chờ eval] | [chờ eval] | N=[chờ eval] |
| Review@B / miss / FP | [chờ eval] | [chờ eval] | B=20 |
| Runtime (cả lần chạy, 200 ảnh) | 3,87 s | 13,05 s | từ log `run_info.json` ở lần chạy đầu; chạy lại bản code cuối để đo lại, CPU=[CẦN ĐIỀN] |
Chưa có số liệu: repo sinh viên không chứa GT nên `src.evaluate` không chạy được trên máy sinh viên (báo "ground truth file not found").
## 05 · Evaluation protocol

- **Công thức:** Recall@K = (số ảnh rare thật trong K) / (tổng số ảnh rare thật trong pool); đơn vị là ảnh; ghép theo `image_id`. Chi tiết trong `reports/metric_contract.md`.
- **Threshold / budget:** B = K = 20; các ngưỡng cố định trước khi chạy (`junk_z = 3.0`, `noise_z = 3.5`, `dedupe_q = 0.10`, `dark_cap = 0.6`, `lambda = 0.5`, `knn = 5`, `n_clusters = 10`). Giờ chốt: [CẦN ĐIỀN].
- **Độ bất định khi N nhỏ:** Wilson 95% CI cho Recall@K và từng slice; baseline random chạy nhiều seed — [CẦN ĐIỀN: ghi rõ đã chạy bao nhiêu seed, nếu chỉ seed 42 thì nói rõ].
- **Lệnh evaluate:**
  `python -m src.evaluate --track t13 --pred out/poc/selected.csv --run-name poc --out reports/metrics_poc.json`
- **Lưu ý:** nhóm không có GT nên chưa tự chấm được; các số trên chỉ có sau khi giảng viên chạy hoặc cấp file chấm.

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| | | | | |
| | | | | |

- Failure case 1 (ảnh/metadata + root cause): ____
- Failure case 2: ____
- Latency / compute (máy, CPU, ms/item): ____

## 07 · Human & decision

- **Review queue:** `out/poc/review_queue.csv`, B = 20, xếp theo `score` giảm dần (ảnh do greedy chọn đứng đầu); contact sheet `out/poc/contact_sheet.html`.
- **Override + audit log:** reviewer chọn `approve` / `reject` / `skip` trên contact sheet, Export CSV, lưu thành `out/poc/review_queue_reviewed.csv` rồi chạy lại `make run`. `reject` loại ảnh khỏi K và thay bằng ảnh sạch tốt nhất tiếp theo; `approve` giữ ảnh. Mỗi quyết định ghi vào audit log (`out/poc/audit_log.jsonl`) kèm tên reviewer và ghi chú. Ảnh thay thế chưa được review.
- **Decision policy + `reason_code` + owner:** xem mục 01; owner mặc định `T13-ActiveLearningTeam` (đổi qua `ctx.config["owner"]`). [CẦN ĐIỀN: ghi tên owner thật nếu có].
- **Khi nào HOLD/REWORK thay vì tự động release:** HOLD khi pool rỗng hoặc chưa có review; REWORK khi chọn thiếu, có junk hoặc có near-duplicate trong K.
- **Kết quả review thực tế:** [CẦN ĐIỀN: số approve / reject / skip, và `decision.json` cuối cùng].

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/<track> --config configs/lab.yaml --output out/ --offline --seed 42
python -m src.evaluate --track t__ --pred out/<file> --out reports/metrics_poc.json
pytest -q
```

- Output của `pytest -q`: ____
- Máy / CPU / OS / Python: ____ · git sha: ____

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII / license:** ảnh trong fixture là dữ liệu của lab; license và nguồn xem `manifest.csv` [CẦN ĐIỀN]. Nếu dùng ảnh thật (BDD100K), cần kiểm tra điều khoản sử dụng và khả năng có mặt người hoặc biển số.
- **Điều chưa biết / false alarms / scale 10×:**
  - Chưa có Recall thật vì không có GT.
  - Junk detector có thể loại nhầm rare thật; near-duplicate threshold chọn theo phân vị, chưa kiểm chứng.
  - Embedding là giả lập nên kết luận về độ hiếm chưa chắc áp dụng cho embedding thật.
  - Nếu pool lớn 10×: kNN và greedy dạng hiện tại tính ma trận khoảng cách theo từng bước, tốn bộ nhớ; cần dùng ANN và tính khoảng cách tăng dần.
- **Không tuyên bố "đạt GDPR / luật Việt Nam"** từ checklist tự động; mọi giả định pháp lý cần DPO/legal xác nhận: [CẦN ĐIỀN nếu có].
- **Kế hoạch cải tiến:** chọn `n_clusters` bằng silhouette, so ablation `novelty` / `diversity` / `hybrid`, thêm uncertainty nếu có model, review cả ảnh thay thế, đo Recall khi có GT.

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
| | | |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
