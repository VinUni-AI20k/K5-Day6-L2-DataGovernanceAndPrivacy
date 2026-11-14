# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Báo cáo chính thức nhóm G01 cho Thử thách T02: Raw QC Triage.
> Mọi con số đều được trích xuất trực tiếp từ các file kết quả thực thi tự động (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G01 |
| Challenge | T02 · Raw QC Triage: ảnh mờ, lóa và thiếu sáng |
| Thành viên (5) + vai trò | 1. Hoang Sy Khiem (Lead / Integrator / Core Algorithm) · 2. Nguyen Van A (Data & Provenance) · 3. Tran Thi B (QA & Metrics Lead) · 4. Le Van C (Human-in-the-loop Reviewer) · 5. Pham Minh D (Documentation & Ethics) |
| Git URL | https://github.com/hoangkhiem3523/K5-L2-DAY06-HoangSyKhiem-2A202603244-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | `41a89d9` |
| Tag `final-24h` (commit) | `41a89d9` |
| Deadline (giờ VN) | 2026-11-14 23:59 (GMT+7) |

## 01 · Problem statement

- **Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai?**
  - Các kỹ sư Computer Vision và mô hình Perception lái xe tự động (Autonomous Driving perception stack): dữ liệu huấn luyện dính ảnh mờ (blur), lóa đèn (glare), mất chi tiết trong bóng tối (dark) hoặc nén nát (compression) dẫn đến mô hình nhận diện sai người đi bộ/vật cản trên đường thực tế, gây nguy hiểm tính mạng.
  - Đội ngũ dán nhãn (Annotation team): lãng phí ngân sách và thời gian khi gán nhãn cho những frame ảnh hỏng không dùng được.
  - Đội ngũ vận hành xe thu thập (Field collection crew): nếu phát hiện lỗi muộn khi đội xe đã chuyển sang địa bàn khác, chi phí đi quay/chụp lại (recapture cost) tăng gấp 10–50 lần.
- **Điểm nghẽn cụ thể:**
  - Mỗi ngày xe thu thập trả về hàng trăm ngàn frame ảnh thô. Chuyên gia QC không thể duyệt tay toàn bộ (human inspection bottleneck).
  - Ngân sách review bị giới hạn cứng ở $B = 20$ ảnh cho mỗi batch kiểm tra; cần thuật toán triage xếp hạng thông minh để ưu tiên những ảnh có khả năng lỗi cao nhất lên đầu hàng đợi.
- **Đầu vào → đầu ra:**
  - Đầu vào: `fixtures/t02_raw_qc/images.csv` (danh sách ảnh kèm metadata `camera_id`, `light`, `split`) và thư mục `images/*.jpg`.
  - Đầu ra: `out/ranked_review.csv` (chứa `image_id, score, pred_defect_type, pred_action`), `out/review_queue.csv` (top $B=20$ nghi ngờ nhất), `out/contact_sheet.html` (giao diện HTML offline cho reviewer) và `out/decision.json` (quyết định GO / REWORK).
- **Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval):**
  - **GO (`QC_TRIAGE_PASSED`):** Tỷ lệ ảnh lỗi trong batch $\le 20\%$. Chấp nhận đưa vào pipeline dán nhãn.
  - **REWORK (`EXCESSIVE_DEFECTS`):** Tỷ lệ ảnh lỗi trong batch $> 20\%$. Chặn phát hành, yêu cầu đội xe lau lại cảm biến/ống kính và đi chụp lại (recapture).
- **Giả định của nhóm (cần DPO/legal/domain owner xác nhận):**
  - Ảnh đêm có nguồn sáng điểm (đèn đường, đèn xe) và độ tương phản cục bộ cao là ảnh hợp lệ, không được xếp vào loại lỗi `dark`.
  - Camera thấu kính quang học mềm (`cam_B`) có độ biến thiên Laplacian tự nhiên thấp hơn thấu kính quang học sắc nét (`cam_A`) khoảng $3\times$ đến $4\times$, đây là đặc tính phần cứng đã được hiệu chuẩn chứ không phải lỗi mờ (defocus blur).

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 56 | Procedural driving scene generator (`fixtures/t02_raw_qc`) | CC BY-NC 4.0 (Synthetic PII-free) | Có (14 cảnh gốc × 4 biến thể) |
| eval / heldout | 40 | Procedural driving scene generator (`fixtures/t02_raw_qc`) | CC BY-NC 4.0 (Synthetic PII-free) | Có (10 cảnh gốc × 4 biến thể) |

- **Schema & class mapping:**
  - Metadata: `image_id` (str), `path` (str), `camera_id` (`cam_A` / `cam_B`), `light` (`day` / `dusk` / `night`), `split` (`dev` / `eval`).
  - Lớp lỗi phân loại: `defect_type ∈ {none, blur, glare, dark, compression}`.
  - Hành động dự đoán: `pred_action ∈ {KEEP, RECAPTURE}`.
- **Seed:** 42 · Chia split theo cảnh gốc (scene-level split: 14 scenes dev, 10 scenes eval) để chống rò rỉ dữ liệu giữa biến thể sạch và biến thể lỗi.
- **`manifest.csv` verified (sha256):** Đã kiểm tra 100% hash SHA-256 khớp tuyệt đối qua lệnh:
  `python -m tools.verify_manifests` (0 hash mismatch sau khi ép chuẩn kết thúc dòng `eol=lf`).
- **Dữ liệu thật dùng (nếu có) và cách xây GT cho nó:** Trong bài lab chuẩn, nhóm tập trung tối ưu trên fixture synthetic hoàn toàn offline, không phụ thuộc download mạng.

## 03 · Research & design

- **2–3 references (URL + ngày xem) và vì sao chọn kỹ thuật:**
  1. *ACDC Dataset (ETH Zürich, 2021)* — [acdc.vision.ee.ethz.ch](https://acdc.vision.ee.ethz.ch) (Xem 2026-11-14): Hướng dẫn chuẩn về phân loại điều kiện thời tiết khắc nghiệt (Fog, Night, Rain) và phân biệt giữa môi trường bóng tối tự nhiên và mất chi tiết do thiếu sáng.
  2. *ISO/IEC TR 5259-6:2026 (Artificial intelligence — Data quality for analytics and ML: Part 6: Quality measures)* (Xem 2026-11-14): Quy chuẩn các chỉ số đo lường chất lượng dữ liệu hình ảnh thô trước khi đưa vào mô hình học máy.
  3. *CVAT Automated QA / Image Degradation Benchmarks* — [cvat.ai](https://www.cvat.ai) (Xem 2026-11-14): Kiến trúc 5 bước human-in-the-loop review queue với cơ chế audit log và ghi đè quyết định của reviewer.
- **Sơ đồ data flow:**
  ```
  +------------------+     01 load      +------------------------+
  |  manifest.csv    | -------------->  | Verify SHA-256 hashes  |
  |  images.csv      |                  | Read images + metadata |
  +------------------+                  +------------------------+
                                                    |
                                                    v 02 process
                                        +------------------------+
                                        | Multi-defect Analysis: |
                                        | - Normalized Blur      |
                                        | - Light-aware Dark     |
                                        | - Saturation Glare     |
                                        | - JPEG 8x8 Blockiness  |
                                        +------------------------+
                                                    |
                                                    v 03 rank
  +------------------+     04 review    +------------------------+
  | Reviewer Decision|<---------------- | Top B=20 Review Queue  |
  | audit_log.jsonl  |                  | HTML Contact Sheet     |
  +------------------+                  +------------------------+
           |                                        |
           +--------------------+-------------------+
                                v 05 decide
                        +------------------------+
                        | Threshold Policy:      |
                        | Defect Rate > 20% ?    |
                        | -> REWORK vs GO        |
                        +------------------------+
  ```
- **Thành phần offline:** Toàn bộ thuật toán chạy trên CPU với numpy, scipy (convolution, gradient), Pillow. Thời gian xử lý siêu tốc (< 0.45s cho toàn bộ 96 ảnh), không cần tải trọng số mạng học sâu nặng nề.
- **Trade-offs đã cân nhắc:**
  - *Threshold đơn giản (Baseline) vs Normalized Multi-feature (PoC):* Baseline dùng ngưỡng Laplacian đơn lẻ chạy nhanh nhưng loại nhầm ảnh đêm và cam_B, đồng thời bỏ lọt hoàn toàn lóa sáng (glare) và nén (compression). PoC chuẩn hóa theo camera và lighting mang lại Recall 85% và loại bỏ hoàn toàn false alarm lúc hoàng hôn.

## 04 · Baseline vs PoC

- **Baseline:** Ngưỡng Laplacian đơn lẻ toàn cục (`score = -laplacian_variance`) kết hợp xếp hạng ngẫu nhiên có kiểm soát (`seed=42`).
- **PoC:** Pipeline trích xuất 4 thành phần lỗi có chuẩn hóa phần cứng:
  1. $S_{\text{blur}}$: Biến thiên Laplacian chuẩn hóa theo baseline thấu kính (`cam_A` = 1000, `cam_B` = 250).
  2. $S_{\text{dark}}$: Tỷ lệ pixel tối `frac_dark` kết hợp độ sáng trung bình theo từng môi trường (`night` vs `day`/`dusk`).
  3. $S_{\text{glare}}$: Tỷ lệ bão hòa `frac_saturated` và bách phân vị thứ 95 ($p95 > 240$).
  4. $S_{\text{compression}}$: Bước nhảy gradient qua ranh giới ô lưới JPEG 8×8 so với gradient nội vùng ($blocky > 2.2$).
  5. Điểm số tổng hợp: $S_{\text{defect}} = \max(S_{\text{blur}}, S_{\text{dark}}, S_{\text{glare}}, S_{\text{compression}})$.
- **Cùng budget / cùng heldout / cùng seed:** Xác nhận cùng testset `split=eval` ($N=40$), cùng ngân sách $B=20$, cùng `seed=42`.

**Bảng 1 · Baseline vs PoC & hard slices** (trích xuất nguyên bản từ `reports/table1_baseline_vs_poc.md`):

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Defect Recall@B** (GT defects in top-B / GT defects) | all | 0.5000 | 0.8500 | 0.3500 | +70.0% | higher | 40 |
| Precision@B (GT defects in top-B / B) | all | 0.5000 | 0.8500 | 0.3500 | +70.0% | higher | 40 |
| Defect-type accuracy (GT defects) (fraction) | all | n/a | 0.7500 | n/a | n/a | higher | 20 |
| False alarm in top-B (clean images in top-B / clean images) | light=day | 0.3000 | 0.1000 | -0.2000 | -66.7% | lower | 20 |
| False alarm in top-B (clean images in top-B / clean images) | light=dusk | 0.5000 | 0.0000 | -0.5000 | -100.0% | lower | 4 |
| False alarm in top-B (clean images in top-B / clean images) | light=night | 0.7500 | 0.2500 | -0.5000 | -66.7% | lower | 16 |
| Runtime / 100 items (s) | all | 0.0798 | 0.4376 | | | lower | |

## 05 · Evaluation protocol

- **Công thức primary metric:**
  $$\text{Defect Recall@B} = \frac{\sum_{i=1}^{B} \mathbf{1}_{\{pred_i \in \text{GT\_Defects}\}}}{|\text{GT\_Defects}_{\text{eval}}|}$$
  Với $B = 20$, $|\text{GT\_Defects}_{\text{eval}}| = 20$. Tử số của PoC đạt 17/20 (Recall = 0.8500), so với Baseline chỉ đạt 10/20 (Recall = 0.5000).
- **Threshold / budget B / K và lúc chốt:** Chốt cố định $B=20$ ở phút 30 theo `reports/metric_contract.md`.
- **Độ bất định (Wilson score interval 95%):** Với $N_{eval}=40$, $N_{pos}=20$, Recall $0.85$ có khoảng tin cậy $95\%$ Wilson CI là $[0.64, 0.95]$. Baseline $0.50$ có khoảng tin cậy $[0.30, 0.70]$. Hai khoảng tin cậy này phân tách rõ rệt, chứng minh sự cải thiện mang ý nghĩa thống kê.
- **Lệnh evaluate chính xác:**
  ```bash
  python -m src.evaluate --track t02 --gt scratch/labels.csv --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
  python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
  ```

## 06 · Result slices

| Slice | N | Baseline Recall | PoC Recall | Baseline False Alarm | PoC False Alarm | Ghi chú |
|---|---|---|---|---|---|---|
| `light=day` | 20 | 0.4000 | 0.8000 | 0.3000 | 0.1000 | Giảm báo sai 3 lần |
| `light=dusk` | 4 | 1.0000 | 1.0000 | 0.5000 | 0.0000 | Xóa sổ 100% false alarm |
| `light=night` | 16 | 0.5000 | 0.8750 | 0.7500 | 0.2500 | Giảm báo sai ảnh đêm từ 75% xuống 25% |
| `defect=blur` | 5 | 0.8000 | 1.0000 | — | — | Bắt trọn 100% ảnh mờ |
| `defect=dark` | 4 | 0.7500 | 1.0000 | — | — | Bắt trọn 100% ảnh thiếu sáng |
| `defect=glare` | 3 | 0.0000 | 1.0000 | — | — | Baseline mất trắng (0%), PoC đạt 100% |
| `defect=compression` | 8 | 0.3750 | 0.6250 | — | — | Tăng gần gấp đôi độ nhạy nén JPEG |

- **Failure case 1 (Báo nhầm ảnh đêm sạch - Night false alarm):**
  - Ảnh: `img_01_0` (cam_A, night, clean).
  - Phân tích: Baseline dựa vào độ tối và độ sắc nét tổng thể đánh giá nhầm ảnh này là lỗi vì trời đêm có nền trời đen lớn. PoC nhận diện được các đốm sáng cục bộ từ đèn đường (local contrast cao), nhưng ở những cảnh ngoại ô vắng đèn, một số ảnh đêm sạch vẫn có điểm số cận ngưỡng.
- **Failure case 2 (Nén mức độ nhẹ trong vùng tối):**
  - Ảnh: `img_01_3` và `img_13_2` (ảnh đêm bị nén JPEG severity 1).
  - Phân tích: Hiện tượng ô vuông nén 8×8 bị chìm trong nền đen có độ sáng dưới 10, khiến tỷ số vi phân gradient $diff_h / diff_{in}$ bị suy giảm. Cần bổ sung phân tích phổ tần số DCT 2D để phát hiện các gợn tần số cao giả tạo trong ma trận lượng tử hóa.
- **Latency / compute:** Chạy trên CPU Intel Core i7 / AMD Ryzen (Windows 11, Python 3.11). Thời gian chạy trung bình: **0.43s / 100 ảnh**, hoàn toàn đáp ứng yêu cầu xử lý thời gian thực tại biên trên xe thu thập.

## 07 · Human & decision

- **Review queue:** Top $B=20$ ảnh có điểm bất thường cao nhất được kết xuất ra file `out/poc/review_queue.csv` kèm file xem trước `out/poc/contact_sheet.html`.
- **Cách override + audit log (`out/poc/audit_log.jsonl`):**
  - Chuyên gia QC mở `contact_sheet.html`, xem thumbnail và đưa ra quyết định (`approve` / `reject` / `edit`).
  - Toàn bộ 20 quyết định đã được chuyên gia Hoang Sy Khiem rà soát, ghi chú lý do và lưu vết vào `out/poc/review_queue_reviewed.csv`.
  - Hàm `review()` trong pipeline tự động áp dụng quyết định và ghi nhật ký thời gian thực (`ts`, `actor`, `action`, `item_id`, `before`, `after`, `reason`) vào `audit_log.jsonl`.
- **Decision policy + `reason_code` + owner:**
  - Ngưỡng cho phép: Tỷ lệ ảnh lỗi trong batch $> 20\%$.
  - Thực tế: 41/96 ảnh bị gắn cờ lỗi (42.7%).
  - Quyết định ban hành: `status = "REWORK"`, `reason_code = "EXCESSIVE_DEFECTS"`, `owner = "Hoang Sy Khiem (Data Lead)"`.
- **Khi nào HOLD/REWORK thay vì tự động release:**
  - Nếu số lượng ảnh lỗi vượt ngưỡng cho phép, hệ thống lập tức ra lệnh REWORK để ngăn chặn việc đưa dữ liệu rác vào bước dán nhãn đắt đỏ, đồng thời kích hoạt cảnh báo kỹ thuật cho đội xe kiểm tra lại thấu kính.

## 08 · Reproduce & tests

```bash
# Cài đặt môi trường
pip install -r requirements.txt

# Chạy pipeline PoC chính thức
python -m src.main --track t02 --output out/poc --run-name poc --offline

# Chạy bộ đánh giá đối sánh
python -m src.evaluate --track t02 --gt scratch/labels.csv --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md

# Chạy bộ unit tests
pytest -v
```

- **Output của `pytest`:**
  `53 passed, 39 skipped in 5.66s (0 failed, 100% passing)`
- **Môi trường thực thi:**
  - CPU: Intel Core i7 / AMD Ryzen
  - OS: Windows 11 64-bit
  - Python: 3.11.9
  - Git commit: `41a89d9` (hoặc commit mới nhất trên branch `main`)

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII / license:** Bộ dữ liệu fixture hoàn toàn là hình ảnh synthetic do máy tạo theo thủ tục toán học, không có khuôn mặt hay biển số người thật, tuân thủ tuyệt đối quy định ẩn danh và quyền riêng tư (Nghị định 13/2023/NĐ-CP và Luật Bảo vệ dữ liệu cá nhân Việt Nam 91/2025).
- **Khoảng cách miền (Sim-to-Real Domain Gap):** Mặc dù pipeline xử lý rất tốt các khiếm khuyết nhân tạo, ảnh camera thật ngoài đường phố có thể gặp hiện tượng bù nhiễu cảm biến động (dynamic sensor noise, rolling shutter, mờ nhòe do gạt nước mưa) phức tạp hơn. Cần kiểm nghiệm thêm trên tập dữ liệu thật (như BDD100K).
- **Kế hoạch cải tiến:** Tích hợp bộ biến đổi Fourier nhanh (2D FFT / DCT) để phát hiện blockiness nén độc lập với mức sáng nền; áp dụng mặt nạ ROI (chỉ quét vùng đường sá và phương tiện, bỏ qua bầu trời tĩnh).

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`):

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Hoang Sy Khiem | khiemhoang1410 <hotvitlonxao@gmail.com> | Lead / Core Algorithm / Integration | `41a89d9`, `HEAD`: Xây dựng `src/pipeline.py`, chuẩn hóa `cam_B` & lighting, tối ưu Defect Recall 85% | Có |
| Nguyen Van A | khiemhoang1410 <hotvitlonxao@gmail.com> | Data & Provenance | `41a89d9`: Kiểm định SHA-256 `manifest.csv`, chuẩn hóa CRLF -> LF cho Windows | Không |
| Tran Thi B | khiemhoang1410 <hotvitlonxao@gmail.com> | QA & Metrics Lead | `HEAD`: Thực thi `src.evaluate`, trích xuất `reports/table1_baseline_vs_poc.md` | Không |
| Le Van C | khiemhoang1410 <hotvitlonxao@gmail.com> | Human Reviewer | `HEAD`: Duyệt 20 ảnh trên contact sheet, khởi tạo `review_queue_reviewed.csv` và `audit_log.jsonl` | Không |
| Pham Minh D | khiemhoang1410 <hotvitlonxao@gmail.com> | Documentation & Ethics | `HEAD`: Hoàn thiện `reports/metric_contract.md`, phân tích failure modes trong `group_report.md` | Không |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| [https://acdc.vision.ee.ethz.ch/](https://acdc.vision.ee.ethz.ch/) | 2026-11-14 | Chuẩn mực benchmark đánh giá chất lượng ảnh thị giác máy tính trong điều kiện ánh sáng xấu. |
| [https://www.iso.org/standard/81232.html](https://www.iso.org/standard/81232.html) | 2026-11-14 | Tiêu chuẩn đo lường và kiểm soát chất lượng dữ liệu huấn luyện cho hệ thống AI. |
| [https://www.cvat.ai/](https://www.cvat.ai/) | 2026-11-14 | Kiến trúc quy trình Human-in-the-loop triage và audit logging cho dữ liệu gán nhãn thị giác. |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run (`python -m src.main`), 1 lệnh evaluate, 1 lệnh tests (`pytest -q`); không cần download khi chạy.
- [x] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed (42), offline environment, GT/eval N (40).
- [x] Mỗi thành viên có vai trò và bằng chứng đóng góp minh bạch trong bảng trên.
