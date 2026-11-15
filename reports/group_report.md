# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Mọi con số trong báo cáo lấy từ file do script sinh ra (`reports/metrics_*.json`, `reports/table1*.md`,
> `reports/t07_selfcheck_slices.csv`, `reports/run_info_poc.json`). Tạo lại toàn bộ bằng một lệnh:
> `python -m tools.t07_run_all`. Chỗ còn `____` là thông tin chỉ nhóm biết, cần điền tay.
>
> **Lưu ý quan trọng về số liệu:** repo học viên không có ground truth. Các số dưới đây đo trên **mini-GT do nhóm tự gán nhãn
> (12 ảnh dev, 64 vùng)**, không phải điểm chính thức. Điểm chính thức do giảng viên chấm bằng GT ẩn trên split `eval`.

## 00 · Header

| Mục                      | Giá trị                                                                                                                                                                                                                                        |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Group ID                 | G99                                                                                                                                                                                                                                            |
| Challenge                | T07 · Automatic Face/Plate Redaction + Review Queue                                                                                                                                                                                            |
| Thành viên (4) + vai trò | 1. Trương Thành Đức (Lead / Integrator & Decision Gate) · 2. Võ Khắc Xuân Nguyên (Core Algorithm & Baselines) · 3. Nguyễn Xuân Khánh (Data, Mini-GT, Metrics & QA Tests) · 4. Huỳnh Nhật Quang (Human-in-the-loop, Compliance & Report/Slides) |
| Git URL                  | https://github.com/thanhduc270998/K5-L2A-DAY06-TruongThanhDuc-2A202603034-DataGovernanceAndPrivacy.git                                                                                                                                         |
| Tag `demo-180m` (commit) | \_\_\_\_                                                                                                                                                                                                                                       |
| Tag `final-24h` (commit) | \_\_\_\_                                                                                                                                                                                                                                       |
| Deadline (giờ VN)        | 12AM 15/11/2026                                                                                                                                                                                                                                |

## 01 · Problem statement

- **Ai chịu hậu quả khi hệ thống sai?** Người đi đường và chủ xe trong ảnh (lộ mặt/biển số nếu che sót); nhóm dùng dữ liệu phía sau (mất tín hiệu nếu che quá rộng); đơn vị phát hành dữ liệu (rủi ro pháp lý).
- **Điểm nghẽn:** bộ dò tổng quát bỏ sót vùng nhỏ, tối, mờ, bị che khuất; không thể duyệt tay 100% nên cần hàng chờ ưu tiên với budget B = 15 ảnh.
- **Đầu vào → đầu ra:** 60 ảnh 640×360 + `images.csv` → `out/poc/redactions.csv` (`image_id, x, y, w, h` — vùng đã che cuối cùng sau review) + `redacted/*.jpg` + `review_queue.csv` + `contact_sheet.html` + `audit_log.jsonl` + `decision.json` / `decision_log.csv`.
- **Tiêu chí GO / HOLD / REWORK** (cài trong `decide()` của `src/pipeline.py`, tham số chốt trong `configs/lab.yaml`):

| Trạng thái | `reason_code`                 | Điều kiện                                                             |
| ---------- | ----------------------------- | --------------------------------------------------------------------- |
| HOLD       | `EMPTY_INPUT`                 | không có ảnh đầu vào                                                  |
| HOLD       | `ESCALATED_BY_REVIEWER`       | reviewer chọn `escalate` cho ít nhất 1 ảnh                            |
| REWORK     | `OVER_REDACTION_RISK`         | diện tích che trung bình > 0,35 diện tích ảnh                         |
| REWORK     | `DETECTOR_STUB_NO_DETECTIONS` | bộ dò không trả vùng nào                                              |
| HOLD       | `NEEDS_HUMAN_REVIEW`          | còn ảnh rủi ro cao (score ≥ 0,55) chưa có người ký duyệt              |
| GO         | `REDACTION_QA_PASSED`         | mọi ảnh rủi ro cao đã được người duyệt, không có điều kiện nào ở trên |

- **Giả định cần DPO/legal/domain owner xác nhận:** (a) mặt và biển số là hai loại PII duy nhất cần che; (b) đầu người nhìn từ phía sau không phải PII (theo định nghĩa GT của đề); (c) coverage ≥ 0,9 là đủ cho mục đích redaction. Đây là giả định của bài lab, chưa được xác nhận.

## 02 · Data & provenance

| Split            | N                                       | Nguồn / link                                                             | License     | Synthetic?                  |
| ---------------- | --------------------------------------- | ------------------------------------------------------------------------ | ----------- | --------------------------- |
| dev              | 36 ảnh                                  | `fixtures/t07_redaction/` — `synthetic:tools/make_fixtures.py (seed 42)` | CC0-1.0     | Có                          |
| eval / heldout   | 24 ảnh                                  | như trên                                                                 | CC0-1.0     | Có                          |
| mini-GT của nhóm | 12 ảnh dev, 64 vùng (35 face, 29 plate) | `reports/mini_gt/gt_regions.csv`                                         | do nhóm tạo | nhãn tay trên ảnh synthetic |

- **Schema:** `images.csv` = `image_id, path, width, height, split`; hai lớp PII `face`, `plate`.
- **Seed:** 42. **Split:** dùng cột `split` có sẵn (36 dev / 24 eval), nhóm không chia lại. Mọi tinh chỉnh bộ dò chỉ dựa trên ảnh dev.
- **Provenance:** `load()` gọi `verify_manifest` và dừng nếu sai sha256 (`strict_provenance: true`). `python -m tools.verify_manifests` → `14 manifests, 0 failing`.
- **Mini-GT** (`reports/mini_gt/README.md`): phủ ảnh thường, hoàng hôn, đêm, mờ, bị che khuất. Phân bố `condition`: normal 24, dark 16, occluded 10, blur 10, small 4. Cách gán: khung do bộ dò đề xuất được kiểm bằng mắt trên ảnh phóng 2× có lưới tọa độ (43 vùng), sửa tay (11 vùng), và thêm tay các vùng bị sót (10 vùng). Không có ảnh eval; pipeline không đọc thư mục này.
- **Hạn chế của mini-GT:** vì khung xuất phát từ chính bộ dò, số đo lạc quan cho PoC (mọi vùng PoC bỏ sót trên mini-GT đều là vùng thêm tay). Dùng để so sánh tương đối với baseline và tìm failure case, không thay cho GT chính thức.
- **Dữ liệu thật:** không dùng.

## 03 · Research & design

- **Lý do chọn kỹ thuật:** fixture là ảnh vẽ, quy tắc vẽ công khai trong `tools/synth/scene.py` (mặt = ô-van màu da có viền, hai mắt, miệng; biển số = chữ nhật trắng viền đen có chữ). Mô hình học trên mặt thật không hợp: Haar cascade mặc định của OpenCV bỏ sót 75% vùng trên mini-GT và không dò biển số (`reports/metrics_baseline_haar.json`). Nhóm chọn bộ dò cổ điển theo màu và hình, chạy CPU, không weights, tất định.
- **Data flow:** `load` (đọc `images.csv`, kiểm sha256) → `process` (`detect_image` cho từng ảnh → khung + conf; đo độ sáng và độ nét ảnh; xuất ảnh đã blur) → `rank` (top-15 **ảnh** theo điểm rủi ro; `review_queue.csv` + `contact_sheet.html` có ảnh trước/sau và khung) → `review` (đọc `review_queue_reviewed.csv`, áp approve/reject/edit/escalate/skip, ghi `audit_log.jsonl`) → `decide` (GO/HOLD/REWORK) → `redactions.csv`.
- **Bộ dò mặt** (`src/t07_detector.py::detect_faces`): mặt nạ theo 5 tông da của renderer (khoảng cách màu Chebyshev ≤ 24; ảnh đêm thêm tông ×0,35) → thành phần liên thông từng tông → lọc hình ô-van (tỉ lệ rộng/cao 0,64–0,97, độ đầy ≥ 0,58) → kiểm "có mắt" bằng độ tối tương đối trong dải mắt. Xử lý riêng: mặt bị che nửa dưới (cạnh dưới phẳng + có mắt → kéo khung xuống hết chiều cao mặt); ảnh mờ (nới dung sai màu, nới khung 12%).
- **Hard negative:** đầu người đi bộ (ô-van rộng hơn cao, không có mắt, nằm trên thân chữ nhật) và biển báo tròn đỏ bị loại bằng tỉ lệ, phép thử mắt và phép thử "thân bên dưới".
- **Bộ dò biển số** (`detect_plates`): pixel trắng (V ≥ 185, S ≤ 45) → đóng hình thái theo chiều ngang để nối các khe do chữ → lọc kích thước, tỉ lệ rộng/cao 1,25–6,5, tỉ lệ trắng ≥ 0,30 và có chữ tối ≥ 0,04. Biển bị che một phần (tỉ lệ < 2,6) được nới ngang. Ảnh mờ dùng mặt nạ "nhạt màu, kém bão hòa" kèm phép thử vành xung quanh.
- **Padding:** mặt 3% + 1 px, biển số 2% + 1 px mỗi cạnh (bù viền 1 px của hình vẽ).
- **Điểm rủi ro của ảnh (cao = duyệt trước):** +0,30 nếu ảnh tối, +0,30 nếu ảnh mờ, +0,40 nếu không dò được vùng nào; nếu có vùng: +0,5·(1 − conf nhỏ nhất), +0,25 nếu diện tích che > 25%, +0,15 nếu có vùng cạnh < 14 px.
- **Thành phần offline:** PoC và baseline chính không dùng model. Chỉ baseline tham khảo Haar (tùy chọn) dùng `models_optional/haarcascade_frontalface_default.xml` (lấy từ wheel OpenCV 4.10.0, license kiểu BSD của Intel, sha256 trong `models_optional/README.md`). Thư viện lúc tạo báo cáo (cài sạch từ `requirements.txt`): opencv-python-headless 5.0.0.93, NumPy 2.5.4, pandas 3.1.1, Pillow 13.0.0.
- **Trade-off đã đo (mini-GT dev):** padding ban đầu 18–30% cho over-redaction 0,535 → FAIL guardrail 0,3; padding 2–3% + 1 px cho 0,204 → PASS, miss rate không đổi (0,156).

## 04 · Baseline vs PoC

- **Baseline `baseline`** (`src/t07_baseline.py`, "bộ dò mặc định + blur cố định"): một ngưỡng màu da chung (H ≤ 25, S 40–200, V ≥ 60) và một ngưỡng trắng (V ≥ 200, S ≤ 40), lấy thành phần liên thông; không kiểm hình dạng, không kiểm mắt, không padding, không xử lý ảnh tối/mờ, không queue, không người duyệt. Quyết định luôn là HOLD.
- **Baseline tham khảo `baseline_haar`** (`src/t07_baseline_haar.py`, tùy chọn): Haar cascade mặt mặc định của OpenCV. `cv2.CascadeClassifier` không còn trong OpenCV 5.x bản thường, nên baseline này chỉ chạy được với OpenCV 4.x hoặc opencv-contrib; kết quả đo trong môi trường có contrib: miss 0,750, over-redaction 0,430 → FAIL (`reports/metrics_baseline_haar.json`). Không dùng làm baseline chính vì không tái lập được trên mọi máy.
- **Baseline tầm thường `baseline_blurall`** (`src/t07_baseline_blurall.py`): một khung phủ toàn ảnh. Miss rate = 0 nhưng over-redaction = 0,988 → **FAIL guardrail**, nên chỉ số chính không hợp lệ (`reports/table1b_blurall_vs_poc.md`).
- **PoC `poc`** (`src/pipeline.py` + `src/t07_detector.py` v1.0.0, tham số trong `configs/lab.yaml`): bộ dò cổ điển, hàng chờ 15 ảnh, người duyệt, audit log, decision gate. `poc_auto` = cùng pipeline **trước** khi người duyệt (`redactions_before_review.csv`).
- **Cùng điều kiện:** cùng 60 ảnh, cùng seed 42, cùng mini-GT, cùng `--split dev`, cùng lệnh evaluate. Commit của bản nộp: \_\_\_\_

**Bảng 1 · Baseline vs PoC** — output nguyên văn của `python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json` (mini-GT dev, không phải điểm chính thức):

Baseline: `baseline` (git 3919d8c, seed 42) · PoC: `poc` (git 3919d8c, seed 42)

| Metric (unit)                                                                    | Slice              | Baseline | PoC    | Δ abs   | Δ rel      | Better | N    |
| -------------------------------------------------------------------------------- | ------------------ | -------- | ------ | ------- | ---------- | ------ | ---- |
| **PII Miss Rate** (GT regions with coverage < 0.9 / GT regions)                  | all                | 0.5781   | 0.1094 | -0.4688 | -81.1%     | lower  | 64   |
| Region recall (1 - miss rate)                                                    | all                | 0.4219   | 0.8906 | 0.4688  | +111.1%    | higher | 64   |
| Over-redaction rate (redacted px outside GT / redacted px)                       | all                | 0.7165   | 0.1978 | -0.5188 | -72.4%     | lower  | None |
| Guardrail: Over-redaction rate <= 0.3 (1 = pass, 0 = fail (constrained primary)) | all                | 0.0000   | 1.0000 | 1.0000  | baseline=0 | higher | None |
| PII Miss Rate (fraction)                                                         | type=face          | 0.2571   | 0.0857 | -0.1714 | -66.7%     | lower  | 35   |
| PII Miss Rate (fraction)                                                         | type=plate         | 0.9655   | 0.1379 | -0.8276 | -85.7%     | lower  | 29   |
| PII Miss Rate (fraction)                                                         | condition=blur     | 0.5000   | 0.3000 | -0.2000 | -40.0%     | lower  | 10   |
| PII Miss Rate (fraction)                                                         | condition=dark     | 0.8125   | 0.0000 | -0.8125 | -100.0%    | lower  | 16   |
| PII Miss Rate (fraction)                                                         | condition=normal   | 0.3750   | 0.0417 | -0.3333 | -88.9%     | lower  | 24   |
| PII Miss Rate (fraction)                                                         | condition=occluded | 0.7000   | 0.3000 | -0.4000 | -57.1%     | lower  | 10   |
| PII Miss Rate (fraction)                                                         | condition=small    | 0.7500   | 0.0000 | -0.7500 | -100.0%    | lower  | 4    |
| Runtime / 100 items (s)                                                          | all                | 0.4438   | 7.7597 |         |            | lower  |      |

Đọc bảng: PoC giảm miss rate từ 0,578 xuống 0,109 và là phương án duy nhất PASS guardrail. Baseline ngưỡng màu FAIL guardrail (0,717) vì nó che cả xe, tòa nhà và bầu trời hoàng hôn có màu giống da, đồng thời vẫn sót 97% biển số (khung trắng bị chữ cắt vụn). Review Recall@B không được evaluator in ra cho T07; nhóm báo số tự tính ở mục 07.

## 05 · Evaluation protocol

- **Primary:** PII Miss Rate = số vùng GT có pixel coverage < 0,9 / tổng số vùng GT (giảm = tốt). Đơn vị: vùng `face`/`plate`. Ghép theo `image_id`, coverage theo pixel, không dùng IoU.
- **Guardrail:** over-redaction = pixel che ngoài GT / pixel che ≤ 0,3; primary chỉ hợp lệ khi PASS.
- **Lỗi xấu nhất:** miss. False alarm đo bằng over-redaction.
- **Tham số và thời điểm chốt:** xem `reports/metric_contract.md`. B = 15; tham số bộ dò chốt lại 2026-11-15 16:20 trên dev, trước khi có bất kỳ kết quả GT eval nào (nhóm không có GT eval).
- **Độ bất định:** Wilson CI 95% (`python -m tools.t07_selfcheck`). N = 64 nên khoảng tin cậy rộng: miss rate PoC 0,109 có CI 0,05–0,21.
- **Lệnh evaluate:**
  - Tự kiểm: `python -m src.evaluate --track t07 --gt reports/mini_gt/gt_regions.csv --split dev --pred out/poc/redactions.csv --run-name poc --out reports/metrics_poc.json`
  - Chính thức (cần overlay GT của giảng viên): `python -m src.evaluate --track t07 --pred out/poc/redactions.csv --run-name poc --out reports/metrics_poc.json`
- **Trung thực về eval:** 8 ảnh eval nằm trong hàng chờ và đã được người duyệt xem, sửa (đó là một phần của pipeline). Tham số bộ dò không bị chỉnh lại sau khi xem các ảnh này, dù chúng lộ ra lỗi che nhầm trên ảnh đêm (mục 06).

## 06 · Result slices

Miss rate theo slice trên mini-GT dev (`reports/t07_selfcheck_slices.csv`; dạng `tỉ lệ (sót/tổng; CI95)`):

| Slice              | N   | Baseline (ngưỡng màu)         | PoC trước review              | PoC sau review               |
| ------------------ | --- | ----------------------------- | ----------------------------- | ---------------------------- |
| all=all            | 64  | 0.578 (37/64; CI95 0.46–0.69) | 0.156 (10/64; CI95 0.09–0.26) | 0.109 (7/64; CI95 0.05–0.21) |
| type=face          | 35  | 0.257 (9/35; CI95 0.14–0.42)  | 0.114 (4/35; CI95 0.05–0.26)  | 0.086 (3/35; CI95 0.03–0.22) |
| type=plate         | 29  | 0.966 (28/29; CI95 0.83–0.99) | 0.207 (6/29; CI95 0.10–0.38)  | 0.138 (4/29; CI95 0.06–0.31) |
| condition=normal   | 24  | 0.375 (9/24; CI95 0.21–0.57)  | 0.042 (1/24; CI95 0.01–0.20)  | 0.042 (1/24; CI95 0.01–0.20) |
| condition=small    | 4   | 0.750 (3/4; CI95 0.30–0.95)   | 0.000 (0/4; CI95 0.00–0.49)   | 0.000 (0/4; CI95 0.00–0.49)  |
| condition=dark     | 16  | 0.812 (13/16; CI95 0.57–0.93) | 0.062 (1/16; CI95 0.01–0.28)  | 0.000 (0/16; CI95 0.00–0.19) |
| condition=blur     | 10  | 0.500 (5/10; CI95 0.24–0.76)  | 0.500 (5/10; CI95 0.24–0.76)  | 0.300 (3/10; CI95 0.11–0.60) |
| condition=occluded | 10  | 0.700 (7/10; CI95 0.40–0.89)  | 0.300 (3/10; CI95 0.11–0.60)  | 0.300 (3/10; CI95 0.11–0.60) |
| size=small         | 15  | 0.800 (12/15; CI95 0.55–0.93) | 0.267 (4/15; CI95 0.11–0.52)  | 0.133 (2/15; CI95 0.04–0.38) |
| size=medium        | 39  | 0.615 (24/39; CI95 0.46–0.75) | 0.103 (4/39; CI95 0.04–0.24)  | 0.103 (4/39; CI95 0.04–0.24) |
| size=large         | 10  | 0.100 (1/10; CI95 0.02–0.40)  | 0.200 (2/10; CI95 0.06–0.51)  | 0.100 (1/10; CI95 0.02–0.40) |

Số liệu mô tả output: PoC che 281 vùng (150 face, 131 plate) trên 60 ảnh trước review, 282 vùng sau review; không ảnh nào có 0 vùng. Diện tích che trung bình 1,3% ảnh.

- **Failure case 1 — ảnh mờ, biển số nhỏ và mặt nhỏ bị sót, và ảnh không vào hàng chờ** (`demo/failure_case_1_blur_pii_19.png`). Ảnh `pii_19` (dev, blur): sót 2 biển số (25×7 px) và 1 mặt nhỏ (14×17 px). Root cause: khi mờ, biển trắng trộn với chữ đen và màu xe nên không còn "trắng, kém bão hòa"; mặt nhỏ trộn màu nền nên lệch khỏi tông da. Điểm rủi ro của ảnh chỉ 0,50 (xếp ngoài top-15, ngưỡng rủi ro cao 0,55), nên người duyệt không thấy. Slice blur: miss 0,50 trước review, 0,30 sau review.
- **Failure case 2 — mặt tối trên nền cùng màu** (`demo/failure_case_2_dark_pii_08.png`). Ảnh đêm `pii_08`: mặt 26×33 px có màu gần trùng tòa nhà phía sau nên mặt nạ màu nối liền với nền, không tách được hình ô-van. Đây là failure mode "mặt trong bóng tối" của đề. Ảnh có trong hàng chờ; reviewer đã thêm khung.
- **Failure case 3 — che thừa trên ảnh đêm** (`demo/failure_case_3_over_redaction_pii_56.png`). Bộ dò che nhầm đèn cửa sổ (màu vàng gần tông da) và đầu người đi bộ ở 5 ảnh đêm/mờ trong hàng chờ (`pii_56, 33, 20, 52, 24`: 7 khung). Root cause: phép thử mắt dựa trên một pixel tối, nhiễu JPEG trên đốm nhỏ đủ để vượt ngưỡng. Reviewer đã bỏ cả 7 khung. Lỗi này lộ ra trên ảnh eval nên nhóm **không** chỉnh bộ dò, chỉ ghi nhận.
- **Failure case 4 — vùng bị che khuất không nhìn thấy.** Biển số bị xe/xe máy che gần hết (`pii_00`, `pii_21`), mặt bị che bởi mặt khác hoặc trùng màu đầu người đi bộ (`pii_21`, `pii_25`): bộ dò không có tín hiệu, điểm rủi ro của ảnh thấp, ảnh không vào hàng chờ. Slice occluded: miss 0,30.
- **Failure mode "upload raw PII lên cloud":** rủi ro quy trình, xem mục 09.
- **Latency / compute:** PoC 5.78 s / 100 ảnh, baseline 0.40 s / 100 ảnh (cùng máy: Python 3.13.17, Windows; `reports/run_info_poc.json`). Chạy lại trên máy khác sẽ cho số khác.

## 07 · Human & decision

- **Hàng chờ:** `out/poc/review_queue.csv`, B = 15 **ảnh**, xếp theo điểm rủi ro giảm dần. 14 ảnh có điểm ≥ 0,55 (rủi ro cao), tất cả nằm trong top-15. Thành phần hàng chờ: 10 ảnh đêm, 5 ảnh mờ.
- **Giao diện duyệt:** `out/poc/contact_sheet.html` (offline; mỗi ảnh có ảnh gốc và ảnh đã che, khung mặt đỏ / biển số xanh kèm conf; ô nhập tên reviewer bắt buộc; nút "Export decisions CSV").
- **Ý nghĩa quyết định:** `approve` giữ nguyên; `reject` xóa mọi khung của ảnh (hoặc thay bằng `override_value`); `edit` thay danh sách khung, hoặc thêm khung nếu `override_value` bắt đầu bằng `add:`; `escalate` giữ khung và buộc quyết định HOLD; `skip` không tính là đã duyệt. Định dạng khung: `x,y,w,h; x,y,w,h` hoặc JSON.
- **Kết quả vòng duyệt** (`reports/review_queue.csv`): reviewer **Huynh Nhat Quang**, 2026-11-15 16:23 (giờ VN); approve 6 / edit 9 / reject 0 / escalate 0 / skip 0. Các lần `edit` thêm 8 vùng bị sót (2 mặt, 6 biển số) và bỏ 7 vùng che nhầm. Minh họa: `demo/review_edits_top15.png`.
- **Audit log** (`reports/audit_log.jsonl`, append-only): 17 dòng — 1 quyết định HOLD trước review, 15 dòng review (actor = tên reviewer, action, item_id, before/after, lý do), 1 quyết định GO. Dòng có quyết định mà thiếu tên reviewer làm pipeline dừng với exit code 2 (có test).
- **Quyết định:** lần chạy chưa review → **HOLD** · `NEEDS_HUMAN_REVIEW` (14/14 ảnh rủi ro cao chưa ký). Sau review → **GO** · `REDACTION_QA_PASSED`. Owner: Huynh Nhat Quang (reviewer, HITL & compliance). Bản ghi: `reports/decision_log.csv`.
- **Hiệu quả của hàng chờ (tự tính):** 9/15 ảnh trong hàng chờ có lỗi thật (60%). Trên mini-GT, 6 ảnh có vùng bị PoC bỏ sót, chỉ 2 ảnh trong số đó nằm trong hàng chờ (recall theo ảnh 2/6): điểm rủi ro bắt tốt ảnh tối và mờ, nhưng không thấy các vùng bị che khuất.
- **Giới hạn của GO:** GO nghĩa là mọi ảnh rủi ro cao đã có người xem, không có nghĩa bộ ảnh hết PII. 45 ảnh ngoài hàng chờ chưa ai kiểm; trên mini-GT vẫn còn 7/64 vùng sót sau review.

## 08 · Reproduce & tests

```bash
make setup                                   # Windows: python -m venv .venv ; .venv\Scripts\python -m pip install -r requirements.txt
python -m tools.t07_run_all                  # baselines + PoC + áp review đã ký + tự đánh giá + chép bằng chứng vào reports/
                                             # Windows: .venv\Scripts\python -m tools.t07_run_all (cần Python 3.11–3.13)
python -m pytest -q
```

Từng bước (tương đương):

```bash
python -m src.main --track t07 --pipeline src.t07_baseline --output out/baseline --run-name baseline --offline --seed 42
python -m src.main --config configs/lab.yaml --track t07 --output out/poc --run-name poc --offline --seed 42
cp reports/review_queue.csv out/poc/review_queue_reviewed.csv      # file review đã ký
python -m src.main --config configs/lab.yaml --track t07 --output out/poc --run-name poc --offline --seed 42
python -m src.evaluate --track t07 --pred out/poc/redactions.csv --run-name poc --out reports/metrics_poc.json   # cần GT của giảng viên
```

- **`pytest -q`:** `64 passed, 39 skipped` (39 test bị skip cần GT của giảng viên), chạy trong môi trường cài sạch từ `requirements.txt`. `tests/test_t07.py` có 17 test của nhóm: bộ dò phủ ≥ 0,9 các mặt trên cảnh tự render; không che đầu người đi bộ và biển báo; tất định; ảnh trống → 0 vùng; đầu vào sai định dạng → `ValueError`; parser override (hợp lệ và sai định dạng); baseline chạy offline, baseline Haar tùy chọn báo lỗi rõ ràng khi OpenCV không hỗ trợ; pipeline end-to-end HOLD → review → GO kèm audit log; tái lập cùng seed; review thiếu tên reviewer → exit 2.
- **Không cần mạng:** `--offline` bật network guard; không tải model.
- **Lưu ý Windows:** đặt `git config core.autocrlf false` trước khi checkout, nếu không Git đổi ký tự xuống dòng của CSV trong `fixtures/` và bước kiểm sha256 sẽ dừng pipeline (exit 2).
- **Máy / Python:** Python 3.13.17, Windows; thời gian chạy PoC 3.47 s cho 60 ảnh. Git sha lúc tạo số liệu: `3919d8c` + thay đổi chưa commit; sha của bản nộp: \_\_\_

## 09 · Limitations & ethics

- **PII / license:** fixture là dữ liệu synthetic CC0, không có người hay biển số thật. Với dữ liệu thật, ảnh gốc chưa che là dữ liệu cá nhân: chỉ xử lý local, không commit, không đưa lên cloud hay repo công khai. Pipeline chạy offline. `demo/` chỉ chứa ảnh synthetic.
- **Blur ≠ ẩn danh hóa.** Output được gọi là _redacted/pseudonymised_, không gọi là _anonymised_. EDPB Guidelines 02/2026 on Anonymisation (bản dự thảo v1.0, thông qua 07/07/2026 để lấy ý kiến công chúng) đánh giá ẩn danh theo ba tiêu chí: không tách riêng được bản ghi, không liên kết được, không suy luận được. Che mặt và biển số không tự chứng minh được cả ba, vì ảnh vẫn còn vị trí, thời gian, ngữ cảnh, dáng người, quần áo, màu và kiểu xe.
- **Bộ dò quá khớp với fixture.** Nó dựa vào đúng bảng màu da và cách vẽ của `tools/synth/scene.py`; trên ảnh thật gần như chắc chắn không dùng được. Giá trị của PoC nằm ở quy trình (queue, review, audit, gate), không ở bộ dò.
- **Chữ biển số tràn ra ngoài khung.** Renderer vẽ chữ dài hơn hình chữ nhật trắng, nên vài ký tự cuối nằm ngoài vùng GT và vẫn đọc được sau khi che (thấy trong `demo/before_after_pii_30.png`). Metric không phạt điều này; với dữ liệu thật đây là rò rỉ.
- **Gaussian blur có thể chưa đủ mạnh** với vùng lớn; chưa đo khả năng khôi phục. Phương án an toàn hơn là tô đặc.
- **Hàng chờ chỉ thấy rủi ro mà máy thấy.** Vùng bị che khuất hoàn toàn không tạo tín hiệu nên không được ưu tiên (mục 07).
- **Số liệu:** mini-GT nhỏ (N = 64), do chính nhóm gán và lạc quan cho PoC; CI rộng. Budget B = 15 cố định: scale 10× thì tỉ lệ ảnh được người xem giảm còn 2,5%.
- **Không tuyên bố "đạt GDPR / luật Việt Nam".** Các giả định ở mục 01 cần DPO/legal xác nhận trước khi dùng cho dữ liệu thật.
- **Kế hoạch cải tiến:** (1) đưa mọi ảnh mờ vào hàng chờ bất kể conf; (2) phép thử mắt dùng 2 đốm đối xứng để bớt che nhầm đèn cửa sổ; (3) suy vị trí biển số từ thân xe khi bị che; (4) che cả phần chữ tràn; (5) lấy mẫu ngẫu nhiên ảnh ngoài hàng chờ để ước lượng miss rate còn lại.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** — cột "Commit" chỉ ghi commit có thật trong `git log --all` tại thời điểm viết; đối chiếu bằng `git shortlog -sne --all`.

| Học viên               | Git author / email                                                                                           | Vai trò được phân công                        | Commit SHA / file chứng minh                                                                                                                                                                                                             | Trình bày? |
| ---------------------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| 1. Trương Thành Đức    | `thanhduc270998` (GitHub noreply); `sbgroup` / foundersbgroup@gmail.com — cần nhóm xác nhận `sbgroup` là Đức | Lead / Integrator & Decision Gate             | `5f6bca6` (`group_report.md`). Tác giả `sbgroup`: `5b0530c`, `e288e44`, `a93726a` (`configs/lab.yaml`), `b8923c5`, `de67a78` (`src/pipeline.py`: khung 5 bước, `review()`, `decide()`; giao diện `src/t07_detector.py`)                  | \_\_\_\_   |
| 2. Võ Khắc Xuân Nguyên | `Võ Khắc Xuân Nguyên` (GitHub noreply)                                                                       | Core Algorithm & Baselines                    | `d3e4468`, `f66836e`, `3919d8c` (`reports/group_report.md`: failure case, latency)                                                                                                                                                       | \_\_\_\_   |
| 3. Nguyễn Xuân Khánh   | `Khanh-AI-ML-DL` / khanhblackjaky@gmail.com                                                                  | Data, Mini-GT, Metrics & QA Tests             | `c4a80ba` (`reports/metric_contract.md`)                                                                                                                                                                                                 | \_\_\_\_   |
| 4. Huỳnh Nhật Quang    | `quanghunh` / nhatquangh72@gmail.com                                                                         | Human-in-the-loop, Compliance & Report/Slides | `5218064`, `563effe`, `0679fce`, `825bb61` (`group_report.md`, `team_contributions.csv`); commit bản nộp \_\_\_\_ : bộ dò `src/t07_detector.py`, baseline, `tests/test_t07.py`, mini-GT, metrics, vòng review + audit log, report, slide | \_\_\_\_   |

## 11 · References

| URL                                                                                | Ngày xem   | 1–2 dòng ý nghĩa (không chép nguyên văn)                                                                                           |
| ---------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| https://www.edpb.europa.eu/public-consultations/guidelines-022026-on-anonymisation | 2026-11-14 | EDPB Guidelines 02/2026 (bản dự thảo v1.0): ba tiêu chí đánh giá ẩn danh; cơ sở để gọi output là pseudonymised thay vì anonymised. |
| `tools/synth/scene.py` (trong repo)                                                | 2026-11-15 | Quy tắc vẽ mặt, biển số, người đi bộ của fixture; cơ sở thiết kế bộ dò theo màu và hình, và của các hard negative.                 |
| `docs/tracks/T07.md` (trong repo)                                                  | 2026-11-14 | Định nghĩa metric, guardrail over-redaction, failure mode bắt buộc và gợi ý Haar cascade làm bộ dò mặc định.                       |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật. _(README đã có mục nhóm; tag chưa gắn)_
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics (mini-GT dev), ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên. _(cần xác nhận danh tính `sbgroup`)_
