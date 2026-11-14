# Chi tiết task từng thành viên — T14 Auto-Annotation + Human QC Exporter

Đọc cùng `docs/HUONG_DAN_LAM_BAI_NHOM.md` (quy tắc chung, cách review trên web). File này liệt kê **từng bước, lệnh và tiêu chí xong** cho từng người.

## Quy ước chung (áp dụng cho cả 6 người)

- Lệnh viết cho **PowerShell** (Windows). Nếu máy không có `make`, chạy trực tiếp `python -m ...` như trong từng bước.
- Cài môi trường một lần: `python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt`, rồi dùng `.venv\Scripts\python` thay cho `python`.
- Branch riêng `feat/t14-<ten-khong-dau>` từ `feat/t14-pipeline`. **1 người = 1 commit**, author đúng tên.
- `out/` bị `.gitignore`: file nào cần nộp phải copy sang `reports/` hoặc ghi rõ lệnh sinh lại trong báo cáo.
- Seed 42, `--offline`. Không đọc ground truth (`gt/`), không tune trên split `eval`.
- Báo cáo cá nhân: `reports/individual/<MSSV>_<HoTen>.md` gồm 4 mục: Việc đã làm · Lệnh đã chạy · Bằng chứng · Hạn chế. Không làm HTML.
- Xong việc = có bằng chứng (output lệnh hoặc file), không chỉ ghi "đã viết xong".

**Thứ tự phụ thuộc:** `B → C` · `D → E → F → G → I → J` · `H` sau khi có C và E · `K` song song.

---

## 1. Trần Thành Hùng — Task B, C (issue #1)

**Mục tiêu:** đóng băng luật chấm trước khi xem eval, rồi tạo baseline "auto-predict, không review".

### B. Metric contract → `reports/metric_contract.md`
1. Mở `reports/metric_contract.md`, đọc bảng đã điền sẵn (primary metric `Detection F1@IoU0.5`, B = 30, seed 42, split eval 20 ảnh).
2. Đối chiếu với `configs/tracks/t14.yaml` và `src/metrics/detection.py::match_detections`: `conf_threshold`, `budget`, IoU phải khớp đúng số trong bảng. Sai chỗ nào thì sửa file contract cho khớp config (không sửa config để khớp ý thích).
3. Điền dòng còn trống **"Ngày giờ chốt + người chốt"** (giờ thật lúc chốt, tên bạn).
4. Commit contract **trước** khi chạy bất kỳ eval nào. Sau đó không đổi `conf_threshold`, `budget`, seed.

### C. Baseline → `out/baseline/predictions.csv`
1. Chạy:
   ```powershell
   python -m src.main --config configs/lab.yaml --track t14 --pipeline src.baseline_t14 --output out/baseline --run-name baseline --offline --seed 42
   ```
2. Kiểm tra `out/baseline/` có `predictions.csv`, `qa_report.json`, `decision_log.csv`, `run_info.json`; mở `run_info.json` ghi lại git sha, config hash.
3. Mở `fixtures/t14_auto_annotation/model_card_fixture.yaml` và ghi vào báo cáo: **model, version, license**. Nêu rõ đây là **fixture dự đoán sẵn, không phải inference thật**.
4. Đếm số box và số box dưới threshold trong `predictions.csv` (dùng pandas) để ghi vào báo cáo.

**Xong khi:** contract có giờ chốt, commit trước baseline; `out/baseline/predictions.csv` sinh được bằng đúng lệnh trên; báo cáo ghi model/version/license; điền mục 04 và 05 của `group_report.md`.

---

## 2. Hoàng Quốc Chung — Task D (issue #2)

**Mục tiêu:** chặn failure mode 1: class ID của model (COCO-style) map sai sang taxonomy nhưng export vẫn "hợp lệ".

Code liên quan đã có trong `src/t14_tools.py`: `build_class_map`, `map_classes`, `validate_predictions`. Thư mục `tests/` hiện chỉ có `__init__.py`, bạn tạo test mới.

1. Đọc `fixtures/t14_auto_annotation/taxonomy.yaml` và `model_predictions_fixture.csv`; liệt kê class ID COCO của fixture so với ID taxonomy (car, pedestrian, motorbike, sign).
2. Đọc `build_class_map` và `validate_predictions` để hiểu hành vi hiện tại: map thiếu thì báo lỗi hay bỏ qua im lặng?
3. Viết `tests/test_t14_label_map.py` với ít nhất:
   - **Test thất bại có chủ đích (red):** map ID sai (ví dụ COCO `2 = car` bị map thành `pedestrian`) mà `validate_predictions` vẫn trả "hợp lệ" → test phải **fail** trước khi sửa. Chụp output fail.
   - Test class ID không có trong taxonomy phải bị bắt.
   - Test map đúng cho cả 4 class của fixture phải pass.
4. Sửa `src/t14_tools.py` tối thiểu để test xanh (ví dụ buộc map đầy đủ và báo lỗi khi ID ngoài taxonomy). Chạy `python -m pytest -q tests/test_t14_label_map.py`.
5. Chạy toàn bộ `python -m pytest -q` và `python -m tools.preflight` để chắc không vỡ chỗ khác.

**Xong khi:** có output test red rồi green trong báo cáo; diff `src/t14_tools.py` nhỏ gọn; điền mục 02 và 08 của `group_report.md`.

---

## 3. Nguyễn Xuân Việt — Task E (issue #3)

**Mục tiêu:** chọn đúng 30 box bất định nhất để người review, tạo `review_queue.csv`.

1. Đọc `src/pipeline.py` (các hàm `load`, `process`, `rank`, `review`, `export`, `decide`, `run`) và `add_suspicion` trong `src/t14_tools.py`.
2. Hiểu cách tính điểm nghi ngờ: box nhỏ (< 150 px²), conf trung bình (gần threshold), threshold theo class, chồng lấn class (`flag_class_confusion`). Ghi công thức vào báo cáo.
3. Chạy PoC:
   ```powershell
   python -m src.main --config configs/lab.yaml --track t14 --output out/poc --run-name poc --offline --seed 42
   ```
4. Kiểm tra `out/poc/review_queue.csv`: **đúng 30 dòng** (`budget=30`), có cột `rank`, `item_id`, `score`, `reason`, `suggested_action`, xếp hạng giảm dần theo score, không trùng `item_id`.
5. Tính tỉ lệ box nhỏ và box conf trung bình trong 30 box được chọn, so với toàn bộ 227 box. Đây là bằng chứng queue ưu tiên đúng loại box khó.
6. Tạo lại web queue sau khi queue đổi: `python tools/t14_build_web.py` (xem `--help` để chọn `--run`), rồi kiểm tra `web/public/queue.json` có 30 item.
7. Không chỉnh threshold sau khi nhìn eval. Chỉ tune trên split dev.

**Xong khi:** `review_queue.csv` đúng 30 dòng, sinh lại được bằng lệnh trên; báo cáo có công thức chấm điểm và bảng so sánh; điền mục 03 và phần PoC của mục 04.

---

## 4. Trần Nguyễn Phi Long — Task F (issue #4)

**Mục tiêu:** duyệt thủ công 30 box bằng web, ghi quyết định có tên và lý do.

1. Đọc `docs/HUONG_DAN_GAN_NHAN_CVAT.md` trước (tiêu chí thế nào là box đúng, khi nào xóa, khi nào sửa).
2. Mở link web do Hưng gửi (cần Hưng deploy trước; nếu chưa có link thì chờ, không tự deploy). Nhập tên thật và passcode.
3. Duyệt **đủ 30 box, độc lập**, không hỏi Hùng/Chung trước. Dùng zoom: bấm vào ảnh, nhấn giữ Ctrl hoặc Shift và lăn chuột (hoặc nút +/−) để nhìn box nhỏ.
4. Mỗi box chọn Giữ / Xóa / Sửa / Cần admin xem. Với Xóa và Sửa luôn ghi `ghi chú` một câu giải thích.
5. Kiểm tra thanh tiến độ hiện "Đã duyệt 30/30".
6. Báo "đã xong" trong issue #4 để Hưng chốt ở `admin.html` và tải CSV.
7. Khi có `review_queue_reviewed.csv`: kiểm tra 30 dòng, đủ `reviewer` và `decision`; tính **tỉ lệ đồng thuận** giữa 3 reviewer (số box cả 3 cùng quyết định / 30) và liệt kê các box lệch phiếu.
8. Ghi vào báo cáo: số box giữ / xóa / sửa của bạn, thời gian duyệt khoảng bao lâu, 2-3 box khó nhất kèm lý do.

**Xong khi:** CSV có đủ cột; bảng đồng thuận trong báo cáo; điền mục 07 `group_report.md`.

> Hùng và Chung làm đúng các bước 2-6 như Long (mỗi người một phiếu). Phần tính đồng thuận ở bước 7 chỉ Long làm.

---

## 5. Phạm Phú Nguyễn Hưng — Task G, I, J, K (issue #5)

### Hạ tầng web (làm trước, vì 3 người review cần)
1. Tạo D1 và điền `database_id` thật vào `web/wrangler.toml`; áp dụng `web/schema.sql`; đặt passcode và admin passcode theo `web/.dev.vars` (file này bị ignore, không commit).
2. Chạy thử local với đúng 1 URL (`index.html`), thử bấm zoom ảnh. Chỉ deploy khi bạn quyết định, rồi gửi link và passcode cho nhóm.

### G. Export và QA → `out/poc/predictions.csv`
1. Sau khi có quyết định review, chạy lại `python -m src.main ... --run-name poc` (xem Việt, bước 3) để ra `predictions.csv`, `yolo/`, `coco.json`.
2. Mở `out/poc/qa_report.json`: ghi **invalid-label rate** (mục tiêu 0) và kết quả **round-trip COCO↔YOLO** (`roundtrip_check`, sai số ≤ 0.05 px).
3. Nếu round-trip lệch hoặc có box ngoài ảnh, ghi nguyên nhân, không sửa số cho đẹp.

### I. Eval → `reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`
1. Dev eval trên gold set của nhóm: `python -m tools.t14_eval_dev --gold gold/gold_dev.csv --pred out/poc/predictions.csv`.
2. Eval chính thức **chỉ chạy được khi có overlay `gt/` của giảng viên**. Khi có:
   ```powershell
   python -m src.evaluate --track t14 --pred out/baseline/predictions.csv --run-name baseline --out reports/metrics_baseline.json
   python -m src.evaluate --track t14 --pred out/poc/predictions.csv --run-name poc --out reports/metrics_poc.json
   python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
   ```
3. Chưa có `gt/` thì ghi rõ trong báo cáo "chưa có số chính thức", không điền số ước đoán. Nếu baseline = 0, ghi "baseline = 0" thay vì phần trăm cải thiện.

### J. Decision → `reports/decision_log.csv`
1. Xem `out/poc/decision.json` và `decision_log.csv`. Chọn **GO / HOLD / REWORK** dựa trên metric, invalid rate và failure case của Thịnh.
2. Điền `reason_code` và `owner` (tên người ký duyệt, sửa `owner` trong `configs/lab.yaml`).
3. Ghi rõ **license AGPL-3.0 của YOLO26** và hệ quả với việc phát hành.

### K. Hồ sơ nhóm
1. Hoàn thiện `submission/README.md` (vai trò từng người ở cột cuối, người ký duyệt).
2. Gom `commit_shas` của 6 người vào `reports/team_contributions.csv`; kiểm tra khớp `git shortlog -sne --all`.
3. Chạy `python -m pytest -q` và `python -m tools.preflight` lần cuối.

**Xong khi:** web chạy và đã gửi link; số QA, metric, decision đều có file chứng minh; điền mục 00, 06, 10 `group_report.md`.

---

## 6. Bùi Văn Thịnh — Task H (issue #6)

**Mục tiêu:** tìm và minh họa 2 loại lỗi trong fixture, nêu root cause.

Phụ thuộc: cần baseline (Hùng, task C) và queue (Việt, task E).

1. Chạy công cụ có sẵn để xem cách nó xuất bằng chứng: `python -m tools.t14_failure_evidence --help`.
2. **Case 1, "map ID sai":** tìm box có class sai do map COCO→taxonomy (ví dụ nhầm car/motorbike/pedestrian). Lấy `item_id`, ảnh, class dự đoán và class đúng (nhìn ảnh để xác định).
3. **Case 2, "conf cao nhưng thiếu object nhỏ":** tìm ảnh mà model tự tin ở vài box lớn nhưng bỏ sót vật nhỏ (sign, pedestrian xa < 150 px²). Ghi số object bị sót.
4. Với mỗi case: lưu ảnh minh họa (box dự đoán + vị trí bị sót) vào `reports/figures/` hoặc thư mục tương đương, kèm `item_id` và đường dẫn ảnh gốc `fixtures/t14_auto_annotation/images/`.
5. Viết root cause từng case (1 đoạn ngắn): vì sao baseline không bắt được, queue của Việt có bắt được không, hướng sửa.
6. Ghi các giới hạn và rủi ro đạo đức (ảnh có người/biển số?), điền mục 06 (failure cases) và 09 của `group_report.md`.

**Xong khi:** có ít nhất 1 case mỗi loại, mỗi case có ảnh + item_id + root cause; báo cáo cá nhân đủ 4 mục.

---

## Checklist trước khi mở PR (mỗi người)

- [ ] `python -m pytest -q` xanh
- [ ] `python -m tools.preflight` xanh
- [ ] Báo cáo `.md` đủ 4 mục, mọi số liệu có bằng chứng
- [ ] Đã điền mục của mình trong `reports/group_report.md` và dòng của mình trong `reports/team_contributions.csv`
- [ ] Chỉ **1 commit**, author đúng tên, không commit `.env`, `.dev.vars`, `out/`
