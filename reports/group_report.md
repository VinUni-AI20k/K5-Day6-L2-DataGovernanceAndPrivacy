# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Quy ước trong file này: `[CẦN ĐIỀN]` = thông tin chỉ bạn biết hoặc số liệu phải lấy từ file do script sinh ra.
> Không điền số khi chưa có file `reports/metrics_*.json` hoặc `reports/table1_baseline_vs_poc.md`.

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | Làm cá nhân |
| Challenge | T13 · Active Learning & Rare Case Miner |
| Thành viên (5–6) + vai trò | 1. Hoàng Gia Bảo (MSSV: 2A202603138 — kiểm tra lại) — làm một mình, đảm nhận toàn bộ vai trò: Lead/Integrator, Data & fixtures, Core algorithm, QA/metric, Review + report |
| Git URL | [CẦN ĐIỀN] |
| Tag `demo-180m` (commit) | [CẦN ĐIỀN] |
| Tag `final-24h` (commit) | [CẦN ĐIỀN] |
| Deadline (giờ VN) | [CẦN ĐIỀN] |

## 01 · Problem statement

- **Ai bị ảnh hưởng khi hệ thống sai?** Nhóm gán nhãn (tốn ngân sách vào ảnh trùng hoặc ảnh vô ích) và người huấn luyện model (model không thấy được các tình huống hiếm như ban đêm có mưa, xe máy bị che, công trường, động vật, nên yếu đúng ở những chỗ quan trọng).
- **Điểm nghẽn cụ thể:** ngân sách gán nhãn chỉ đủ cho K = 20 ảnh trong pool 200 ảnh chưa nhãn. Chọn ngẫu nhiên thì gần như không bắt được rare case (đề nêu baseline bằng 0 ở slice `night_rain` và `occluded`). Ngược lại, chọn theo "độ lạ" thuần túy dễ rơi vào ảnh nhiễu hoặc chỉ toàn ảnh tối.
- **Đầu vào → đầu ra:** `pool_features.csv` (đặc trưng rẻ + `emb_00..15`) và `images.csv` → `out/poc/selected.csv` (đúng 20 dòng, cột `image_id`, `rank`) kèm `review_queue.csv`, `contact_sheet.html`, `decision.json`.
- **Tiêu chí GO / HOLD / REWORK** (cài trong `decide()`):
  - `HOLD / EMPTY_POOL`: pool rỗng.
  - `REWORK / UNDERFILLED_SELECTION`: chọn chưa đủ K.
  - `REWORK / JUNK_IN_SELECTION`: có ảnh bị gắn junk trong K.
  - `REWORK / NEAR_DUPLICATE_IN_SELECTION`: có ảnh gần trùng nhau trong K.
  - `HOLD / PENDING_HUMAN_REVIEW`: tập chọn sạch nhưng chưa có review của người.
  - `GO / REVIEWED_OK`: đủ K, không junk, không near-duplicate, đã áp review.
- **Giả định cần domain owner xác nhận:** (1) "rare" được định nghĩa bằng 4 tag của đề; (2) embedding trong fixture là giả lập nên khoảng cách trong không gian đó chỉ xấp xỉ độ hiếm thật; (3) ngưỡng junk và dedupe là heuristic thống kê, chưa kiểm chứng bằng GT.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | không có tách riêng: pool 200 ảnh chưa nhãn, không dùng nhãn để tune | `fixtures/t13_rare_mining/` | [CẦN ĐIỀN từ `manifest.csv`] | [CẦN ĐIỀN từ `manifest.csv`]; embedding là giả lập (theo đề) |
| eval / heldout | cùng pool 200 ảnh, GT `gt/rare_labels.csv` do giảng viên giữ, nhóm không đọc | `fixtures/t13_rare_mining/gt/` (chỉ giảng viên) | [CẦN ĐIỀN] | [CẦN ĐIỀN] |

- **Schema & class mapping:** `images.csv` (`image_id`, `path`), `pool_features.csv` (`image_id`, `brightness_*`, `saturation_mean`, `edge_density`, `emb_00..15`). Rare tags dùng để đánh giá: `night_rain`, `occluded_motorbike`, `construction`, `animal`.
- **Seed:** 42. **Cách chia split:** không chia. Pool cố định cho cả baseline và PoC, GT chỉ dùng ở khâu đánh giá của giảng viên.
- **`manifest.csv` verified (sha256):** [CẦN ĐIỀN: có / không] — lệnh: `python -m tools.verify_manifests`. Pipeline cũng tự kiểm hash ở bước `load` (`strict_provenance`).
- **Dữ liệu thật:** [CẦN ĐIỀN: có dùng `data/real/bdd/` không; nếu có, ghi cách xây GT từ metadata BDD. Nếu không, ghi "không dùng"].

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

- **Baseline:** chọn ngẫu nhiên K = 20 (`src.examples.random_baseline`), seed 42. Commit: [CẦN ĐIỀN].
- **PoC:** `src/pipeline.py` (file `pipeline_t13.py`), `mode = hybrid`, tham số mặc định như trong `reports/metric_contract.md`. Commit: [CẦN ĐIỀN].
- **Cùng budget / heldout / seed:** B = K = 20, cùng pool 200 ảnh, seed 42 — [CẦN XÁC NHẬN].

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của `python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`.

> Chưa có số liệu: repo sinh viên không chứa GT nên `src.evaluate` không chạy được trên máy sinh viên (báo "ground truth file not found"). Giảng viên chạy chấm chính thức. Khi có file `reports/table1_baseline_vs_poc.md`, dán nguyên bảng vào đây, không gõ tay. Nếu baseline = 0 thì ghi "baseline = 0" thay vì phần trăm cải thiện.

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: Rare-case Recall@K (image) | [chờ eval] | [chờ eval] | higher is better |
| Hard-slice: `night_rain` (image) | [chờ eval] | [chờ eval] | N=[chờ eval] |
| Hard-slice: `occluded_motorbike` (image) | [chờ eval] | [chờ eval] | N=[chờ eval] |
| Review@B / miss / FP | [chờ eval] | [chờ eval] | B=20 |
| Runtime (cả lần chạy, 200 ảnh) | 3,87 s | 13,05 s | từ log `run_info.json` ở lần chạy đầu; chạy lại bản code cuối để đo lại, CPU=[CẦN ĐIỀN] |

## 05 · Evaluation protocol

- **Công thức:** Recall@K = (số ảnh rare thật trong K) / (tổng số ảnh rare thật trong pool); đơn vị là ảnh; ghép theo `image_id`. Chi tiết trong `reports/metric_contract.md`.
- **Threshold / budget:** B = K = 20; các ngưỡng cố định trước khi chạy (`junk_z = 3.0`, `noise_z = 3.5`, `dedupe_q = 0.10`, `dark_cap = 0.6`, `lambda = 0.5`, `knn = 5`, `n_clusters = 10`). Giờ chốt: [CẦN ĐIỀN].
- **Độ bất định khi N nhỏ:** Wilson 95% CI cho Recall@K và từng slice; baseline random chạy nhiều seed — [CẦN ĐIỀN: ghi rõ đã chạy bao nhiêu seed, nếu chỉ seed 42 thì nói rõ].
- **Lệnh evaluate:**
  `python -m src.evaluate --track t13 --pred out/poc/selected.csv --run-name poc --out reports/metrics_poc.json`
- **Lưu ý:** nhóm không có GT nên chưa tự chấm được; các số trên chỉ có sau khi giảng viên chạy hoặc cấp file chấm. Nhãn tự gán, nếu dùng, chỉ là ước lượng và phải ghi rõ như vậy.

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| `night_rain` | [chờ eval] | [chờ eval] | [chờ eval] | target chính; báo cả khi bằng 0 |
| `occluded_motorbike` | [chờ eval] | [chờ eval] | [chờ eval] | target chính; báo cả khi bằng 0 |
| `construction` | [chờ eval] | [chờ eval] | [chờ eval] | |
| `animal` | [chờ eval] | [chờ eval] | [chờ eval] | |

- **Failure case 1 (ảnh/metadata + root cause):** [CẦN ĐIỀN: ví dụ ảnh junk hoặc dark-but-common trong K. Tìm bằng `out/poc/scored_all.csv`: lọc `is_junk`, `is_dark`, cột `reason`; chèn ảnh từ contact sheet và nêu nguyên nhân].
- **Failure case 2:** [CẦN ĐIỀN: ví dụ near-duplicate đội lốt rare hoặc rare bị loại nhầm là junk].
- **Latency / compute:** [CẦN ĐIỀN: máy, CPU, ms/item. Số tham khảo: một lần `make run` mất 13,05 s cho 200 ảnh trên WSL; đo lại bằng bản code cuối].

## 07 · Human & decision

- **Review queue:** `out/poc/review_queue.csv`, B = 20, xếp theo `score` giảm dần (ảnh do greedy chọn đứng đầu); contact sheet `out/poc/contact_sheet.html`.
- **Override + audit log:** reviewer chọn `approve` / `reject` / `skip` trên contact sheet, Export CSV, lưu thành `out/poc/review_queue_reviewed.csv` rồi chạy lại `make run`. `reject` loại ảnh khỏi K và thay bằng ảnh sạch tốt nhất tiếp theo; `approve` giữ ảnh. Mỗi quyết định ghi vào audit log (`out/poc/audit_log.jsonl`) kèm tên reviewer và ghi chú. Ảnh thay thế chưa được review.
- **Decision policy + `reason_code` + owner:** xem mục 01; owner mặc định `T13-ActiveLearningTeam` (đổi qua `ctx.config["owner"]`). [CẦN ĐIỀN: ghi tên owner thật nếu có].
- **Khi nào HOLD/REWORK thay vì tự động release:** HOLD khi pool rỗng hoặc chưa có review; REWORK khi chọn thiếu, có junk hoặc có near-duplicate trong K.
- **Kết quả review thực tế:** [CẦN ĐIỀN: số approve / reject / skip, và `decision.json` cuối cùng].

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/t13_rare_mining --config configs/lab.yaml --output out/ --offline --seed 42
python -m src.evaluate --track t13 --pred out/poc/selected.csv --out reports/metrics_poc.json
pytest -q
```

Lệnh thực tế đã dùng: `make baseline TRACK=T13` và `make run TRACK=T13`.

- **Output của `pytest -q`:** [CẦN ĐIỀN: chạy `pytest -q` và dán kết quả]
- **Máy / CPU / OS / Python:** [CẦN ĐIỀN] (WSL trên Windows) · git sha: [CẦN ĐIỀN]

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

Dự án do một người thực hiện toàn bộ.

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Hoàng Gia Bảo | [CẦN ĐIỀN] | Toàn bộ: pipeline 5 bước, review queue, decision, metric contract, report | [CẦN ĐIỀN] | [CẦN ĐIỀN] |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| [CẦN ĐIỀN: FiftyOne Brain uniqueness] | [CẦN ĐIỀN] | Cách đo độ độc nhất của mẫu trong không gian embedding; làm cơ sở cho novelty bằng kNN. |
| [CẦN ĐIỀN: BDD100K] | [CẦN ĐIỀN] | Bộ dữ liệu lái xe có metadata thời tiết/cảnh; nguồn định nghĩa rare case thật. |
| [CẦN ĐIỀN: Ultralytics YOLO26 (theo Research Shelf trong handout)] | [CẦN ĐIỀN] | Tham chiếu mà đề nêu trong Research Shelf; ghi lại ý nghĩa nếu bạn thực sự đã đọc. |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics (cần số từ giảng viên), ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
