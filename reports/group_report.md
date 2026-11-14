# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).
>
> Quy ước trong bản nháp này: `____` = chưa có, cần điền. `(TVx)` = thành viên chịu trách nhiệm cung cấp/xác nhận nội dung.

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G__ (đang là `G00` trong `configs/lab.yaml` — TV1 sửa) |
| Challenge | T07 · Automatic Face/Plate Redaction + Review Queue |
| Thành viên (4) + vai trò | 1. Trương Thanh Đức (Lead / Integrator & Decision Gate) · 2. Võ Khắc Xuân Nguyên (Core Algorithm & Baselines) · 3. Nguyễn Xuân Khánh (Data, Mini-GT, Metrics & QA Tests) · 4. Huỳnh Nhật Quang (Human-in-the-loop, Compliance & Report/Slides) |
| Git URL | https://github.com/thanhduc270998/K5-L2A-DAY06-TruongThanhDuc-2A202603034-DataGovernanceAndPrivacy.git |
| Tag `demo-180m` (commit) | ____ |
| Tag `final-24h` (commit) | ____ |
| Deadline (giờ VN) | ____ |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? Người đi đường và chủ xe xuất hiện trong ảnh (lộ mặt/biển số nếu che sót); nhóm dùng dữ liệu phía sau (mất tín hiệu nếu che quá rộng); đơn vị phát hành dữ liệu (rủi ro pháp lý).
- Điểm nghẽn cụ thể: bộ dò tổng quát bỏ sót vùng nhỏ, tối, mờ, bị che khuất; không thể duyệt tay toàn bộ nên cần xếp hàng ưu tiên vùng kém chắc chắn với budget B = 15.
- Đầu vào → đầu ra: 60 ảnh 640×360 + `images.csv` → `redactions.csv` (`image_id, x, y, w, h` — vùng đã che cuối cùng sau review) + ảnh đã che + `review_queue.csv` + `audit_log.jsonl` + `decision.json`.
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): ____ (TV1 — policy `decide()`, kèm `reason_code` + `owner`)
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): (a) mặt và biển số là hai loại PII duy nhất cần che trong phạm vi bài; (b) đầu người nhìn từ phía sau không tính là PII theo định nghĩa GT của đề; (c) ngưỡng coverage ≥ 0,9 là đủ cho mục đích redaction. Cả ba là giả định của bài lab, chưa được DPO/legal xác nhận.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 36 ảnh | `fixtures/t07_redaction/` — `synthetic:tools/make_fixtures.py (seed 42)` | CC0-1.0 (synthetic, generated for AI20K Day06) | Có |
| eval / heldout | 24 ảnh | như trên | CC0-1.0 | Có |

- Schema & class mapping: `images.csv` = `image_id, path, width, height, split`; hai lớp PII `face`, `plate`; GT ẩn (`gt/gt_regions.csv`, chỉ giảng viên có) kèm `condition ∈ {normal, small, dark, blur, occluded}`.
- Seed: 42 · Cách chia split (theo scene/group/segment?): dùng cột `split` có sẵn trong `images.csv` (36 dev / 24 eval), nhóm không chia lại.
- `manifest.csv` verified (sha256): ____ (có / không) — lệnh: `python -m tools.verify_manifests`
- Mini-GT nội bộ: ~10–12 ảnh `dev` do TV3 tự gán nhãn (`scratch/dev_mini_gt.csv`), đủ các nhóm normal/small/dark/blur/occluded/pedestrian, không đụng `eval`. N vùng: ____ (TV3)
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: không dùng.

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: xem mục 11. Lý do chọn kỹ thuật: ____ (TV2)
- Sơ đồ data flow: `load` (đọc `images.csv` + kiểm sha256) → `process` (tiền xử lý CLAHE/tăng sáng → nhánh face + lọc hard-negative, nhánh plate → padding) → `rank` (top-15 theo `score`) → `review` (contact sheet → `review_queue_reviewed.csv` → override + audit log) → `decide` (GO/HOLD/REWORK) → xuất `redactions.csv` + ảnh đã che + report.
- Thành phần offline (model/weights + checksum + license nếu có): OpenCV Haar Cascade đi kèm gói `opencv` (`cv2.data.haarcascades`), không tải gì từ mạng. Tên file cascade + version OpenCV + license: ____ (TV2)
- Trade-offs đã cân nhắc: padding rộng hơn làm tăng coverage (giảm miss) nhưng tăng over-redaction; ngưỡng dò thấp hơn bắt được vùng nhỏ/tối nhưng dễ che nhầm đầu người đi bộ. Số liệu cụ thể: ____ (TV2/TV3)

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): (1) `blur-all` — làm mờ toàn ảnh, baseline tầm thường: miss rate 0 nhưng dự kiến FAIL guardrail over-redaction; (2) OpenCV Haar Cascade mặc định + blur cố định, không queue/human audit. File `src/t07_baseline.py`, commit ____ (TV2)
- PoC (mô tả, version/config, commit): detector offline trong `src/t07_detector.py` — CLAHE/tăng sáng cho ảnh tối, nhánh face + lọc hard-negative đầu người đi bộ, nhánh plate, padding cân bằng coverage ≥ 0,9 và over-redaction ≤ 0,3; có review queue top-15 và audit log. Commit ____ (TV2)
- Cùng budget / cùng heldout / cùng seed: xác nhận ____ (B = 15, seed 42, split eval)

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: PII Miss Rate (tỉ lệ vùng GT) | ____ | ____ | ____; lower = tốt, chỉ hợp lệ khi guardrail PASS |
| Guardrail: over-redaction rate (≤ 0,3) | ____ | ____ | ____; PASS/FAIL |
| Hard-slice: ______ (small / dark / …) | ____ | ____ | ____; N=__ |
| Review Recall@B | ____ | ____ | ____; B=15 |
| Runtime / 100 items | ____ | ____ | ____; CPU=__ |

## 05 · Evaluation protocol

- Công thức primary metric: PII Miss Rate = số vùng GT có pixel coverage < 0,9 / tổng số vùng GT. Đơn vị đánh giá: vùng (region) `face`/`plate`. Chi tiết TP/FP/FN: xem `reports/metric_contract.md` (TV3).
- Guardrail: over-redaction rate = pixel che ngoài GT / pixel che, phải ≤ 0,3.
- Threshold / budget B / K và lúc chốt: B = 15; threshold chọn trên dev, chốt lúc ____ bởi ____ (TV3)
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: ____ (TV3)
- Lệnh evaluate chính xác: `python -m src.evaluate --track t07 --pred out/poc/redactions.csv --run-name poc --out reports/metrics_poc.json`
- Lưu ý: repo học viên không có `gt/`, lệnh trên chỉ chạy được với overlay của giảng viên. Số nội bộ của nhóm đo trên mini-GT dev và được ghi rõ là số tự đo.

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| type = face / plate | | | | |
| condition = small / dark / blur / occluded | | | | |
| kích thước vùng nhỏ / vừa / lớn | | | | |

- Failure case 1 (ảnh/metadata + root cause): ____ (TV3 tìm, TV4 minh họa — ưu tiên: sót mặt nhỏ trong bóng tối)
- Failure case 2: ____ (ưu tiên: che quá rộng làm mất tín hiệu task)
- Failure mode thứ ba theo đề (upload raw PII lên cloud): rủi ro quy trình, xem mục 09.
- Latency / compute (máy, CPU, ms/item): ____

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): `out/poc/review_queue.csv`, B = 15, ưu tiên theo `score` giảm dần (cao = kém chắc chắn, cần duyệt trước). Bản đã duyệt lưu tại `reports/review_queue.csv`.
- Giao diện duyệt: `out/poc/contact_sheet.html` (ảnh trước/sau + bbox, chạy offline, nút Export CSV).
- Cách override + audit log: reviewer chọn `approve / reject / edit / escalate / skip` cho từng vùng → Export thành `out/poc/review_queue_reviewed.csv` → chạy lại pipeline, bước `review()` áp override và ghi `out/poc/audit_log.jsonl` (append-only). Dòng có quyết định mà thiếu `reviewer` thì pipeline dừng.
- Kết quả vòng duyệt: reviewer ____ ; approve __ / reject __ / edit __ / escalate __ / skip __ (trên 15 ca)
- Decision policy + `reason_code` + owner: ____ (TV1); owner = Huynh Nhat Quang (theo `configs/lab.yaml`). Bản ghi: `reports/decision_log.csv`.
- Khi nào HOLD/REWORK thay vì tự động release: ____ (TV1)

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/t07_redaction --config configs/lab.yaml --output out/ --offline --seed 42
python -m src.evaluate --track t07 --pred out/redactions.csv --out reports/metrics_poc.json
pytest -q
```

- Output của `pytest -q`: ____ (TV3 — gồm `tests/test_t07.py`, ≥ 2 test: success + failure/edge)
- Máy / CPU / OS / Python: ____ · git sha: ____

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: fixture là dữ liệu synthetic CC0, không có người hay biển số thật. Nếu áp dụng lên dữ liệu thật thì ảnh gốc chưa che là dữ liệu cá nhân: chỉ xử lý local, không commit, không đưa lên cloud hay repo công khai.
- **Blur ≠ ẩn danh hóa.** Output của nhóm được gọi là *redacted/pseudonymised*, không gọi là *anonymised*. Theo EDPB Guidelines 02/2026 on Anonymisation (bản dự thảo v1.0, thông qua 07/07/2026 để lấy ý kiến công chúng), việc đánh giá dữ liệu có ẩn danh hay không dựa trên ba tiêu chí: không tách riêng được bản ghi, không liên kết được, không suy luận được. Che mặt và biển số không tự chứng minh được cả ba, vì ảnh vẫn còn vị trí, thời gian, ngữ cảnh, dáng người, quần áo, màu và kiểu xe.
- Điều chưa biết; false alarms; nếu scale 10× thì sao: chưa đo trên ảnh thật; số nội bộ chỉ dựa trên mini-GT ~10–12 ảnh dev nên độ bất định lớn; budget review B = 15 không tăng theo dữ liệu, nên khi scale 10× tỉ lệ vùng được người duyệt giảm tương ứng. Chi tiết: ____
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động. Các giả định ở mục 01 cần DPO/legal xác nhận trước khi dùng cho dữ liệu thật.
- Kế hoạch cải tiến: ____

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Thành viên 1: ____ | | Lead / Integrator & Decision Gate — `configs/lab.yaml`, `src/pipeline.py` (`load`, `rank`, `review`, `decide`), merge + tag Git | | |
| Thành viên 2: ____ | | Core Algorithm & Baselines — `src/t07_baseline.py`, `src/t07_detector.py` | | |
| Thành viên 3: ____ | | Data, Mini-GT, Metrics & QA Tests — `reports/metric_contract.md`, `tests/test_t07.py`, `scratch/dev_mini_gt.csv` | | |
| Thành viên 4: Huynh Nhat Quang | | Human-in-the-loop, Compliance & Report/Slides — `reports/group_report.md`, `reports/team_contributions.csv`, `reports/review_queue.csv`, `reports/decision_log.csv`, `demo/` | | |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| https://www.edpb.europa.eu/public-consultations/guidelines-022026-on-anonymisation | 2026-11-14 | EDPB Guidelines 02/2026 (bản dự thảo v1.0): khung ba tiêu chí đánh giá ẩn danh; cơ sở để gọi output là pseudonymised thay vì anonymised. |
| ____ (tài liệu OpenCV Haar Cascade — TV2) | | Bộ dò dùng cho baseline, có sẵn offline. |
| ____ (TV2/TV3) | | |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
