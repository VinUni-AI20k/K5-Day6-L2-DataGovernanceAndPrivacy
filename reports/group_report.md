# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).
>
> Quy ước trong bản nháp này: `____` = chưa có, cần điền. `(TVx)` = thành viên chịu trách nhiệm cung cấp/xác nhận nội dung.

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G99 (theo `configs/lab.yaml`) |
| Challenge | T07 · Automatic Face/Plate Redaction + Review Queue |
| Thành viên (4) + vai trò | 1. Trương Thanh Đức (Lead / Integrator & Decision Gate) · 2. Võ Khắc Xuân Nguyên (Core Algorithm & Baselines) · 3. Nguyễn Xuân Khánh (Data, Mini-GT, Metrics & QA Tests) · 4. Huỳnh Nhật Quang (Human-in-the-loop, Compliance & Report/Slides) |
| Git URL | https://github.com/thanhduc270998/K5-L2A-DAY06-TruongThanhDuc-2A202603034-DataGovernanceAndPrivacy.git |
| Tag `demo-180m` (commit) | ____ |
| Tag `final-24h` (commit) | ____ |
| Deadline (giờ VN) | ____ |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? Người đi đường và chủ xe xuất hiện trong ảnh (lộ mặt/biển số nếu che sót); nhóm dùng dữ liệu phía sau (mất tín hiệu nếu che quá rộng); đơn vị phát hành dữ liệu (rủi ro pháp lý).
- Điểm nghẽn cụ thể: bộ dò bỏ sót vùng nhỏ, tối, mờ, bị che khuất; không thể duyệt tay toàn bộ nên cần xếp hàng ưu tiên vùng kém chắc chắn với budget B = 15.
- Đầu vào → đầu ra: 60 ảnh 640×360 + `images.csv` → `redactions.csv` (`image_id, x, y, w, h` — vùng đã che cuối cùng sau review) + ảnh đã che (`redacted/*.jpg`) + `review_queue.csv` + `contact_sheet.html` + `audit_log.jsonl` + `decision.json` / `decision_log.csv`.
- Tiêu chí GO / HOLD / REWORK (đã cài trong `decide()` của `src/pipeline.py`, chốt trước khi chạy eval):
  - **HOLD** · `REVIEW_PENDING`: hàng chờ chưa được người duyệt → không phát hành bộ ảnh đã che.
  - **REWORK** · `LOW_DETECTOR_CONFIDENCE`: đã duyệt nhưng độ tin cậy trung bình của bộ dò trên các vùng cuối cùng < `min_mean_conf` = 0,6.
  - **GO** · `REVIEWED_QUEUE_OK`: đã duyệt, có audit log, độ tin cậy trung bình ≥ 0,6.
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): (a) mặt và biển số là hai loại PII duy nhất cần che trong phạm vi bài; (b) đầu người nhìn từ phía sau không tính là PII theo định nghĩa GT của đề; (c) ngưỡng coverage ≥ 0,9 là đủ cho mục đích redaction. Cả ba là giả định của bài lab, chưa được DPO/legal xác nhận.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 36 ảnh | `fixtures/t07_redaction/` — `synthetic:tools/make_fixtures.py (seed 42)` | CC0-1.0 (synthetic, generated for AI20K Day06) | Có |
| eval / heldout | 24 ảnh | như trên | CC0-1.0 | Có |

- Schema & class mapping: `images.csv` = `image_id, path, width, height, split`; hai lớp PII `face`, `plate`; GT ẩn (`gt/gt_regions.csv`, chỉ giảng viên có) kèm `condition ∈ {normal, small, dark, blur, occluded}`.
- Seed: 42 · Cách chia split (theo scene/group/segment?): dùng cột `split` có sẵn trong `images.csv` (36 dev / 24 eval), nhóm không chia lại. Pipeline có tham số `run_split` để chỉ chạy trên `dev` khi tune.
- `manifest.csv` verified (sha256): bước `load()` gọi `verify_manifest` và dừng nếu sai hash (`strict_provenance: true`). Kết quả `python -m tools.verify_manifests`: ____
- Mini-GT nội bộ: ____ (TV3 — chưa có file mini-GT trong repo tại thời điểm viết)
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: không dùng.

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: xem mục 11. Fixture là ảnh vẽ (mặt hoạt hình, biển số trắng chữ đen), nên nhóm chọn bộ dò cổ điển theo hình dạng và màu, chạy CPU, không cần weights, thay cho mô hình học trên mặt người thật. Lý do chi tiết: ____ (TV2)
- Sơ đồ data flow:
  `load` (đọc `images.csv`, kiểm sha256 theo `manifest.csv`)
  → `process` (dò mặt + dò biển số → lọc `conf < min_conf` → nới khung theo `padding_ratio`)
  → `rank` (top-15 theo `score = 1 − conf`, ghi `review_queue.csv` + `contact_sheet.html`)
  → `review` (đọc `review_queue_reviewed.csv`, áp override, ghi `audit_log.jsonl`)
  → `decide` (GO/HOLD/REWORK)
  → xuất `redactions.csv` + `redacted/*.jpg` (Gaussian blur trong từng khung) + `decision.json`.
- Bộ dò mặt (`detect_faces`): biến đổi black-hat tìm đốm tối nhỏ (mắt) → ghép cặp đốm gần ngang hàng → flood-fill từ điểm giữa hai mắt để lấy vùng mặt → lọc theo kích thước, tỉ lệ rộng/cao 0,6–1,3 → NMS (IoU 0,4). `conf` tính từ độ đầy của vùng so với hình ô-van, giảm 30% nếu cạnh < 10 px.
- Bộ dò biển số (`detect_plates`): mặt nạ pixel trắng (V > 170, S < 70) hợp với pixel tối (gray < 90) → thành phần liên thông → lọc kích thước 10–90 × 4–30 px, tỉ lệ rộng/cao 1,8–7, tỉ lệ trắng ≥ 0,35 và có chữ tối ≥ 0,05.
- Thành phần offline (model/weights + checksum + license nếu có): không dùng model hay weights; chỉ dùng hàm xử lý ảnh của OpenCV (`opencv-python-headless`, Apache-2.0). Version OpenCV trên máy chạy: ____
- Trade-offs đã cân nhắc: `padding_ratio` = 0,25 nới mỗi cạnh thêm 25% để đạt coverage ≥ 0,9, đổi lại tăng pixel che thừa; `min_conf` = 0,25 thấp để giữ vùng nhỏ, đổi lại dễ che nhầm (bánh xe máy, đầu người đi bộ). Số liệu trade-off: ____ (TV2/TV3)

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): ____ (TV2 — tại thời điểm viết, module baseline chưa có trên nhánh `main`. Kế hoạch: (1) `blur-all`, baseline tầm thường, miss rate 0 nhưng dự kiến FAIL guardrail; (2) bộ dò mặc định + blur cố định, không queue/human audit.)
- PoC (mô tả, version/config, commit): pipeline 5 bước trong `src/pipeline.py`, bộ dò cổ điển như mục 03, `padding_ratio=0.25`, `min_conf=0.25`, `min_mean_conf=0.6`, B = 15, có review queue và audit log. Commit ____
- Cùng budget / cùng heldout / cùng seed: xác nhận ____ (B = 15, seed 42, split eval)

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: PII Miss Rate (tỉ lệ vùng GT) | ____ | ____ | ____; lower = tốt, chỉ hợp lệ khi guardrail PASS |
| Guardrail: over-redaction rate (≤ 0,3) | ____ | ____ | ____; PASS/FAIL |
| Hard-slice: ______ (blur / dark / small) | ____ | ____ | ____; N=__ |
| Review Recall@B | ____ | ____ | ____; B=15 |
| Runtime / 100 items | ____ | ____ | ____; CPU=__ |

## 05 · Evaluation protocol

- Công thức primary metric: PII Miss Rate = số vùng GT có pixel coverage < 0,9 / tổng số vùng GT. Đơn vị đánh giá: vùng (region) `face`/`plate`. Ghép prediction ↔ GT theo `image_id`; coverage tính theo pixel của vùng GT được các hộp che phủ, không dùng IoU (xem `reports/metric_contract.md`).
- Guardrail: over-redaction rate = pixel che ngoài GT / pixel che, phải ≤ 0,3.
- Chỉ số lỗi xấu nhất: miss (bỏ sót PII); false alarm đo bằng over-redaction.
- Threshold / budget B / K và lúc chốt: B = 15; `padding_ratio=0.25`, `min_conf=0.25`, `min_mean_conf=0.6`, chọn bằng quan sát overlay trên ảnh dev, đóng băng trước khi chạy eval. Chốt ngày 2026-11-14 bởi Nguyễn Xuân Khánh.
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: Wilson CI 95% cho miss rate.
- Lệnh evaluate chính xác: `python -m src.evaluate --track t07 --pred out/poc/redactions.csv --run-name poc --out reports/metrics_poc.json`
- Lưu ý: repo học viên không có `gt/`, lệnh trên chỉ chạy được với overlay của giảng viên. Số nội bộ của nhóm (nếu có) đo trên mini-GT dev và được ghi rõ là số tự đo.

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| type = face / plate | | | | |
| condition = small / dark / blur / occluded | | | | |
| kích thước vùng nhỏ / vừa / lớn | | | | |

Số liệu mô tả output của PoC (đếm từ `out/poc/redactions.csv`, chưa phải metric vì chưa có GT — **chạy lại `make run TRACK=t07` trên máy nhóm để xác nhận trước khi nộp**): 222 vùng được che trên 60 ảnh, gồm 164 `face` và 58 `plate`; dev 98 face + 33 plate, eval 66 face + 25 plate; 6/60 ảnh không có vùng nào được che.

- **Failure case 1 — ảnh mờ (blur) bị bỏ sót hoàn toàn.** Ảnh `pii_15`, `pii_19`, `pii_24`, `pii_38`, `pii_59` (cả ảnh bị làm mờ) có mặt và biển số nhìn thấy rõ bằng mắt nhưng pipeline không che vùng nào. Root cause: bộ dò mặt dựa vào đốm mắt sắc nét (ngưỡng black-hat > 18) và bộ dò biển số dựa vào ranh giới trắng/tối sắc nét; khi ảnh mờ, các tín hiệu này bị nhòe dưới ngưỡng. Hệ quả: các ảnh này không sinh vùng nào nên cũng không vào hàng chờ, người duyệt không có cơ hội bắt lỗi. Ảnh `pii_27` (ảnh nét, mặt bị che khuất một phần, biển số nhỏ) cũng không có vùng nào được che.
- **Failure case 2 — ảnh đêm (dark): sót mặt tối và sót biển số.** Ảnh `pii_56`: các mặt tối màu trên nền tối không được dò; chỉ 1 trong 3 biển số nhìn thấy được che (`pii_56#2`). Root cause: ngưỡng độ sáng tuyệt đối (gray < 90, V > 170) không thích nghi với ảnh tối; không có bước tăng sáng/CLAHE.
- **Failure case 3 — che thừa (over-redaction) do nhầm vật không phải PII.** Bánh xe máy bị dò thành `face` ở `pii_35#5` (conf 0,353) và `pii_00#5` (conf 0,498); đầu người đi bộ nhìn từ sau (hard negative, không có nét mặt) bị che ở `pii_05#0` (conf 0,902), `pii_35#4` (conf 0,8), `pii_56#1` (conf 0,468); biển báo tròn đỏ bị che ở `pii_56#0` (conf 0,958). Root cause: điều kiện "cặp đốm tối + vùng tô đầy gần ô-van" cũng đúng với hai bánh xe hoặc một hình tròn đơn sắc. Các ca conf thấp lọt vào top-15 để người duyệt bác bỏ, nhưng các ca conf cao (0,8–0,96) thì **không** vào hàng chờ, nên `score = 1 − conf` chưa phải thước đo rủi ro đáng tin.
- Failure mode thứ ba theo đề (upload raw PII lên cloud): rủi ro quy trình, xem mục 09.
- Ảnh minh họa cho các failure case: ____ (đặt trong `demo/`)
- Latency / compute (máy, CPU, ms/item): ____ (lấy từ `out/poc/run_info.json`)

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): `out/poc/review_queue.csv`, B = 15, ưu tiên theo `score = 1 − conf` giảm dần (cao = kém chắc chắn, cần duyệt trước). Mỗi dòng là một vùng, mã `item_id` dạng `pii_35#5`. Bản đã duyệt lưu tại `reports/review_queue.csv`.
- Giao diện duyệt: `out/poc/contact_sheet.html`, chạy offline, có ô tên reviewer (bắt buộc) và nút "Export decisions CSV". Hạn chế hiện tại: trang chỉ hiện ảnh gốc thu nhỏ, chưa vẽ khung vùng đang xét và chưa có ảnh trước/sau, nên reviewer phải đối chiếu tọa độ trong `redactions.csv`.
- Ý nghĩa quyết định (theo `review()`): `approve` / `skip` giữ nguyên khung; `reject` xóa khung khỏi `redactions.csv`; `edit` thay khung bằng `override_value` dạng `x,y,w,h`; `escalate` giữ khung và chỉ ghi log.
- Cách override + audit log: reviewer Export thành `out/poc/review_queue_reviewed.csv` → chạy lại pipeline → mỗi quyết định được ghi vào `out/poc/audit_log.jsonl` (actor = tên reviewer, action, item_id, before/after, reason). Dòng có quyết định mà thiếu `reviewer` thì pipeline dừng.
- Kết quả vòng duyệt: reviewer ____ ; approve __ / reject __ / edit __ / escalate __ / skip __ (trên 15 ca)
- Decision policy + `reason_code` + owner: xem mục 01. Owner theo `configs/lab.yaml`: ____ (giá trị hiện tại còn tiền tố "TODO:" — TV1 sửa). Quyết định cuối: ____ · `reason_code` ____ . Bản ghi: `reports/decision_log.csv`.
- Khi nào HOLD/REWORK thay vì tự động release: luôn HOLD khi chưa có người duyệt; REWORK khi độ tin cậy trung bình < 0,6. Hạn chế: policy chưa xét các ảnh không có vùng nào được dò (failure case 1), nên GO không đảm bảo các ảnh đó an toàn.

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --config configs/lab.yaml --track t07 --output out/poc --run-name poc --offline --seed 42
python -m src.evaluate --track t07 --pred out/poc/redactions.csv --run-name poc --out reports/metrics_poc.json
pytest -q
```

- Output của `pytest -q`: ____ (TV3 — tại thời điểm viết chưa có test riêng cho T07 trong `tests/`; cần ≥ 2 test: success + failure/edge)
- Máy / CPU / OS / Python: ____ (lấy từ `out/poc/run_info.json`) · git sha: `main` = `c4a80ba` lúc viết; sha của bản nộp: ____

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: fixture là dữ liệu synthetic CC0, không có người hay biển số thật. Nếu áp dụng lên dữ liệu thật thì ảnh gốc chưa che là dữ liệu cá nhân: chỉ xử lý local, không commit, không đưa lên cloud hay repo công khai. Pipeline chạy `--offline`, không gọi mạng.
- **Blur ≠ ẩn danh hóa.** Output của nhóm được gọi là *redacted/pseudonymised*, không gọi là *anonymised* (lý do GO trong `decide()` cũng ghi rõ điều này). Theo EDPB Guidelines 02/2026 on Anonymisation (bản dự thảo v1.0, thông qua 07/07/2026 để lấy ý kiến công chúng), việc đánh giá dữ liệu có ẩn danh hay không dựa trên ba tiêu chí: không tách riêng được bản ghi, không liên kết được, không suy luận được. Che mặt và biển số không tự chứng minh được cả ba, vì ảnh vẫn còn vị trí, thời gian, ngữ cảnh, dáng người, quần áo, màu và kiểu xe.
- Điều chưa biết; false alarms; nếu scale 10× thì sao:
  - Bộ dò được thiết kế theo hình vẽ của fixture (mặt ô-van có hai chấm mắt, biển trắng chữ đen); chưa thử trên ảnh thật và nhiều khả năng không dùng được nguyên trạng.
  - Ảnh mờ và ảnh đêm là điểm yếu đã quan sát được (mục 06).
  - Hàng chờ chỉ chứa vùng **đã dò được**, nên người duyệt không thấy các vùng bị sót; cần thêm cơ chế đưa ảnh "không có vùng nào" hoặc ảnh mờ/tối vào hàng chờ.
  - Budget B = 15 không tăng theo dữ liệu: khi scale 10×, tỉ lệ vùng được người duyệt giảm tương ứng.
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động. Các giả định ở mục 01 cần DPO/legal xác nhận trước khi dùng cho dữ liệu thật.
- Kế hoạch cải tiến: (1) tiền xử lý tăng sáng/CLAHE cho ảnh tối và phát hiện ảnh mờ để hạ ngưỡng hoặc đưa thẳng vào hàng chờ; (2) lọc bánh xe và đầu người đi bộ; (3) vẽ khung và ảnh trước/sau trên contact sheet; (4) policy `decide()` xét thêm ảnh không có vùng nào.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Thành viên 1: Trương Thanh Đức | thanhduc0998 / truongthanhduc270998@gmail.com | Lead / Integrator & Decision Gate — `configs/lab.yaml`, `src/pipeline.py` (`load`, `rank`, `review`, `decide`), merge + tag Git | | |
| Thành viên 2: Võ Khắc Xuân Nguyên | Nguyenvkx / vokhacxuannguyen165@gmail.com | Core Algorithm & Baselines — bộ dò mặt/biển số, baseline | | |
| Thành viên 3: Nguyễn Xuân Khánh | Khanh-AI-ML-DL / khanhblackjaky@gmail.com | Data, Mini-GT, Metrics & QA Tests — `reports/metric_contract.md`, test T07, mini-GT | `c4a80ba` (main) — điền `reports/metric_contract.md` | |
| Thành viên 4: Huỳnh Nhật Quang | quanghunh / nhatquangh72@gmail.com | Human-in-the-loop, Compliance & Report/Slides — `reports/group_report.md`, `reports/team_contributions.csv`, `reports/review_queue.csv`, `reports/decision_log.csv`, `demo/` | `5218064` (nhánh `quang_2A2603113`) — `group_report.md`, `team_contributions.csv` | |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| https://www.edpb.europa.eu/public-consultations/guidelines-022026-on-anonymisation | 2026-11-14 | EDPB Guidelines 02/2026 (bản dự thảo v1.0): khung ba tiêu chí đánh giá ẩn danh; cơ sở để gọi output là pseudonymised thay vì anonymised. |
| ____ (tài liệu OpenCV về morphological transforms / connected components — TV2) | | Kỹ thuật nền của bộ dò cổ điển. |
| ____ (TV2/TV3) | | |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
