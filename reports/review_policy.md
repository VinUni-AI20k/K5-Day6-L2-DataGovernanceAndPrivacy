# Review policy — T02 · Raw QC Triage

| Mục | Giá trị |
|---|---|
| Phiên bản | 1.1 · 2026-11-14 |
| Soạn bởi | Duong Manh Huy — Human review + Report |
| Người ký quyết định (owner) | theo trường `owner` trong `configs/lab.yaml` |
| Áp dụng cho | `out/poc/review_queue.csv`, `out/poc/review_queue_reviewed.csv`, `review()` và `decide()` trong `src/pipeline.py` |
| Căn cứ | `reports/metric_contract.md` (chốt 2026-11-14 21:05) |

Policy được chốt **trước** khi chạy đánh giá và không thay đổi theo kết quả đánh giá.

## 1. Phạm vi review

| Mục | Giá trị |
|---|---|
| Đối tượng | top-**B = 20** ảnh theo `score` giảm dần, lấy trên toàn bộ 96 ảnh (dev + eval) |
| Thông tin trên mỗi thẻ | `reason` = `pred_defect_type` (blur / dark / glare / compression / none) · `suggested_action` = `pred_action` (RECAPTURE / KEEP) · `slice` = `light` (day / dusk / night) · ảnh |
| Công cụ | `out/poc/contact_sheet.html` (offline) → *Export decisions CSV* → `out/poc/review_queue_reviewed.csv` |
| Thời điểm | sau khi tham số pipeline đã đóng băng theo metric contract |
| Reviewer | thành viên phụ trách Human review, dùng tên thật trùng với Git author |
| Owner | người ghi trong `configs/lab.yaml`; tách biệt với reviewer để phân định người kiểm và người chịu trách nhiệm |
| Ngân sách thời gian | ≤ 60 giây/ảnh, tương đương khoảng 20 phút cho 20 ảnh |

Queue là top-20 trên 96 ảnh, trong khi metric chính (Defect Recall@B) tính trên top-20 của 40 ảnh **eval**.
Review không làm thay đổi `score`, nên không làm thay đổi metric.

## 2. Quyết định cho từng ảnh

### 2.1 Năm loại quyết định

Override tác động lên cột **`pred_action`**. Giá trị hợp lệ của `override_value`: **`KEEP`** hoặc **`RECAPTURE`**.

| Decision | Dùng khi | `override_value` | Tác động trong pipeline | Audit log |
|---|---|---|---|---|
| `approve` | hành động máy đề xuất là đúng | để trống | giữ `pred_action` | — |
| `reject` | máy đề xuất RECAPTURE nhưng ảnh dùng được (false alarm) | **`KEEP`** | `pred_action = KEEP` | `override:reject` |
| `edit` | máy đề xuất sai hành động theo chiều còn lại (bỏ sót ảnh lỗi), hoặc cần sửa hành động có kèm lý do | **`RECAPTURE`** hoặc `KEEP` | `pred_action = override_value` | `override:edit` |
| `escalate` | reviewer không đủ chắc chắn, cần owner quyết | để trống | giữ `pred_action`; owner xử lý theo §3.3 | — |
| `skip` | chưa xem được ảnh | để trống | giữ `pred_action` | — |

- `reject` hoặc `edit` mà để trống `override_value` thì **không** có thay đổi nào được áp dụng; vì vậy hai quyết định này luôn đi kèm giá trị.
- `pred_defect_type` giữ nguyên dự đoán của pipeline; loại lỗi reviewer quan sát được ghi trong `review_note`.
- Pipeline dừng với exit code 2 khi `reviewer_decision` nằm ngoài 5 giá trị trên, hoặc một dòng có quyết định nhưng thiếu `reviewer`.

### 2.2 Định nghĩa lỗi

| Nhãn | Là lỗi (→ RECAPTURE) khi | Không phải lỗi (→ KEEP) khi |
|---|---|---|
| `blur` | cạnh nhoè rõ so với các ảnh cùng cảnh (`img_XX_0..3` cùng `XX`) | ảnh cam_B mềm đồng đều trên toàn ảnh, giống các ảnh cam_B khác (đặc tính quang học) |
| `dark` | thiếu sáng do phơi sáng, mất chi tiết vật thể — so với mức sáng bình thường của cùng điều kiện `light` | ảnh đêm tối tự nhiên nhưng vẫn thấy rõ xe, biển số, vạch đường |
| `glare` | vùng cháy trắng che vật thể, kể cả vùng nhỏ như vùng biển số | đèn xe, đèn đường sáng nhưng không che vật thể |
| `compression` | khối 8×8, viền răng cưa hoặc dải màu thấy rõ | nhiễu hạt nhẹ của ảnh đêm |

Các tín hiệu pipeline dùng cho từng nhãn được khai báo trong `reports/metric_contract.md` (chuẩn hoá theo `camera_id` và `light`,
glare theo patch 4×4, blockiness 8×8, ngưỡng gắn cờ `max_score ≥ 0.45`).

### 2.3 Quy trình xem một ảnh

1. Đọc `reason` (loại lỗi dự đoán), `suggested_action` và `slice` (điều kiện ánh sáng) trên thẻ.
2. So sánh với các ảnh cùng cảnh trong `fixtures/t02_raw_qc/images/`.
3. Đối chiếu bảng 2.2 để chọn quyết định ở bảng 2.1.
4. Ghi `review_note` cho mọi ảnh, kể cả `approve`, theo mẫu `<nhãn quan sát>; <bằng chứng>`.
   Ví dụ: `none; ảnh đêm, thấy rõ xe và biển số` · `glare; cháy trắng vùng biển số, phần còn lại nét` · `blur; nhoè so với img_07_0`.
5. Ảnh thuộc ba nhóm rủi ro (ảnh đêm, lóa cục bộ, cam_B) mà pipeline dự đoán sai được đưa vào danh sách failure case.

## 3. Quyết định cho cả batch

### 3.1 Quy tắc

`recapture_rate` = số ảnh có `pred_action = RECAPTURE` (sau override) / tổng số ảnh (96).
Batch được coi là **đã review** khi file `review_queue_reviewed.csv` tồn tại và có ít nhất một dòng mang quyết định.

| # | Điều kiện | Status | Canonical | `reason_code` | `reason` |
|---|---|---|---|---|---|
| 1 | `recapture_rate > 0.20` và batch **chưa** review | `HOLD` | HOLD | `HIGH_DEFECT_RATE_HOLD` | High defect rate ({n_recapture}/{n_total}); pending human sign-off on review queue |
| 2 | `recapture_rate > 0.20` và batch **đã** review | `REWORK` | REWORK | `RECAPTURE_REQUIRED` | High defect rate ({n_recapture}/{n_total}); triage confirmed defective images require recapture |
| 3 | `recapture_rate ≤ 0.20` | `GO` | GO | `DEFECT_RATE_ACCEPTABLE` | Defect rate within acceptable operating tolerance |

### 3.2 Ngưỡng 20%

Khi hơn 20% ảnh của một đợt cần chụp lại, nguyên nhân nhiều khả năng nằm ở thiết lập chụp (camera, phơi sáng, thời điểm chụp)
thay vì ở từng ảnh, nên cả đợt chuyển sang làm lại. Ở mức này, kết quả tự động không được dùng để kết luận một mình:
batch chỉ chuyển sang `REWORK` sau khi người review đã xác nhận top-20; trước đó batch ở trạng thái `HOLD`.
Dưới ngưỡng, batch được giữ (`GO`) và các ảnh có `pred_action = RECAPTURE` được chụp lại riêng lẻ.
Ngưỡng là chính sách vận hành, không được tối ưu theo dữ liệu đánh giá.

### 3.3 Nội dung quyết định và xử lý escalate

- `out/poc/decision.json` và `out/poc/decision_log.csv` ghi: `status`, `reason_code`, `reason`, `owner`, `scope = t02`,
  `evidence` = [`ranked_review.csv`, `review_queue.csv`], `metrics` = {`n_total`, `n_recapture`, `recapture_rate`}.
- Override được ghi trong `out/poc/audit_log.jsonl` (`actor`, `action`, `item_id`, `before`, `after`, `reason`).
- **Escalate:** owner xem ảnh và ghi quyết định cuối cùng vào chính file review (`reject` / `edit` kèm `override_value`,
  `reviewer` = tên owner, `review_note` = lý do), sau đó chạy lại pipeline. Batch không được công bố trong khi còn dòng `escalate`.

## 4. Nguyên tắc

1. `score` không bị thay đổi bởi review; review chỉ cập nhật `pred_action`. Metric phản ánh năng lực xếp hạng của pipeline.
2. Nhãn từ review không được dùng để điều chỉnh tham số, vì queue có chứa ảnh eval.
3. Dự đoán gốc không bị ghi đè tại chỗ; override tạo bản sao. `audit_log.jsonl` chỉ ghi thêm, không xoá dòng.
4. Reviewer và owner là người thật, ghi tên thật.
5. Policy này không phải đánh giá tuân thủ pháp lý; nhóm không tuyên bố đạt GDPR hay luật Việt Nam.
6. Bằng chứng nộp kèm: `reports/review_queue.csv` (bản đã review), `reports/decision_log.csv`, ảnh chụp contact sheet trong `demo/`.

## 5. Kiểm thử policy

Chạy với file review mô phỏng trong thư mục output riêng (`out/poc_try`), `--offline --seed 42`, trên commit `cdf39bf`.
T1–T3 đồng thời được phủ bởi `tests/test_t02_pipeline.py`.

| # | File review | Kết quả mong đợi | Kết quả chạy (2026-11-14) |
|---|---|---|---|
| T1 | không có file | exit 0; `status` ∈ {HOLD, GO, REWORK}; `owner` có giá trị | exit 0 · `HOLD / HIGH_DEFECT_RATE_HOLD` · 58/96 ảnh RECAPTURE (60.4%) |
| T2 | 1 dòng `edit`, `override_value = KEEP` | ảnh đó `pred_action = KEEP`; audit log có `override:edit`, `after = KEEP` | đạt (`img_09_2` → KEEP, 1 sự kiện `override:edit`) |
| T3 | 1 dòng có quyết định nhưng thiếu `reviewer` | exit 2 | exit 2 |
| T4 | không có file, `recapture_rate > 0.20` | `HOLD / HIGH_DEFECT_RATE_HOLD` | đạt |
| T5 | 20/20 `approve`, `recapture_rate > 0.20` | `REWORK / RECAPTURE_REQUIRED` | đạt |
| T6 | `reject → KEEP` cho toàn bộ ảnh RECAPTURE trong top-20 | 20 sự kiện `override:reject`; `recapture_rate` giảm đúng 20/96 | đạt: 58 → 38 ảnh (39.6%), vẫn `REWORK / RECAPTURE_REQUIRED` |
| T7 | `reviewer_decision = maybe` | exit 2 | exit 2 |
| T8 | `edit → KEEP` cho 1 ảnh | `score` của mọi ảnh không đổi | đạt (`img_09_2`: 1.0429 → 1.0429) |
| T9 | 1 dòng `escalate`, 1 dòng `reject` để trống `override_value` | không có override nào được áp dụng; batch xử lý escalate theo §3.3 | đạt: 0 sự kiện override; pipeline trả `REWORK / RECAPTURE_REQUIRED` |

Với kết quả T1, review chỉ có thể đưa batch về `GO` khi số ảnh RECAPTURE ngoài top-20 không vượt 19 (20% của 96);
ở trạng thái hiện tại batch luôn kết thúc ở `REWORK` sau review. Mức gắn cờ 60.4% được báo cáo cùng kết quả đánh giá.

## 6. Liên kết với metric contract

| Mục | Metric contract | Review policy |
|---|---|---|
| Budget | B = 20 | queue 20 ảnh |
| Split | chỉnh tham số trên `dev` (56 ảnh), đánh giá trên `eval` (40 ảnh, chia theo cảnh gốc) | review diễn ra sau khi tham số đã đóng băng; nhãn review không quay lại chỉnh tham số |
| Slice báo cáo | `light`, `defect_type`, `camera_id` | thẻ review hiển thị `light` và `pred_defect_type`; `camera_id` đọc từ tên cảnh và ghi trong `review_note` khi liên quan |
| Chỉ số lỗi xấu | `False alarm in top-B` và tỉ lệ bỏ sót (`1 − Defect Recall@B`) | false alarm trong queue được sửa bằng `reject → KEEP`; ảnh bỏ sót được sửa bằng `edit → RECAPTURE`; cả hai được ghi trong audit log |
| Độ bất định | Wilson 95% CI trên `eval` (N = 40) | số liệu review báo kèm N = 20 |
