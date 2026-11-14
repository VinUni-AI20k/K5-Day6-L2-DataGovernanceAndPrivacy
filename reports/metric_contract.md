# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T08 · Retention & Delete Request Simulator |
| Primary metric (tên đúng như evaluator in ra) | `Deletion Completeness` |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | pair = cặp `(request_id, artefact_id)` |
| Công thức + numerator / denominator | số cặp "phải xóa" mà output ghi `delete` ÷ tổng số cặp "phải xóa" trong gold. Cặp bỏ sót (không có dòng) tính là chưa xóa. |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | join chính xác theo khóa `(request_id, artefact_id)`; không có tolerance. Mỗi khóa đúng 1 dòng (evaluator từ chối khóa trùng). |
| Candidate pool cố định | 212 artefact trong `data_graph.json` × 10 yêu cầu trong `requests.json`; baseline và PoC cùng đọc đúng 2 file này (sha256 kiểm ở bước load). |
| Review budget B / K | B = 100 cặp. Mọi cặp ngoại lệ (không phải `delete`) đều vào hàng chờ; nếu số ngoại lệ > B thì quyết định là HOLD chứ không cắt bớt. |
| Seed | 42 (pipeline thuần luật, không có bước ngẫu nhiên; sắp xếp cố định theo id) |
| Threshold policy (chọn trên dev như thế nào) | Không có ngưỡng số. Thứ tự ưu tiên luật được đóng băng (xem dưới), chọn từ đề bài + đọc dữ liệu đầu vào, **không** nhìn kết quả chấm. |
| Eval split (không dùng để tune) | Chấm chính thức: GT của giảng viên + hidden eval (nhóm không có). Tự kiểm: `reports/t08_selflabel.csv` (158 cặp, gán nhãn tay **trước** lần chạy PoC đầu tiên — commit của file này đứng trước commit PoC). Không sửa nhãn sau khi thấy kết quả. |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | `False-delete count` (mục tiêu 0) là lỗi nặng nhất vì không hoàn tác được; sau đó mới đến bỏ sót (completeness < 1). Không đánh đổi false-delete để lấy completeness. |
| Slices sẽ báo cáo (≥2) | (1) theo `expected_action`: delete / retain_legal_hold / escalate; (2) theo loại tình huống `label_case` (legal hold trực tiếp, legal hold kế thừa, không rõ nguồn, thiếu quyền, nhiều chủ thể, export); (3) trước và sau vòng người duyệt. |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Wilson 95% CI cho Deletion Completeness và Exception accuracy. Thêm phân tích độ nhạy: tính lại metric khi đổi 2 giả định gán nhãn còn tranh cãi (A1, A3 bên dưới). |
| Ngày giờ chốt + người chốt | 2026-11-14 (giờ VN), Lam TherK — bằng chứng thời điểm là commit chứa file này, đứng trước commit PoC trong `git log`. |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.

## Phạm vi (cặp nào phải có dòng trong `actions.csv`)

Một cặp `(request, artefact)` nằm trong phạm vi khi `subject_id` của request có trong `subject_ids` của artefact.
Trên fixture: 158 cặp. PoC còn ghi thêm dòng `escalate` cho con cháu của các artefact đó mà **không** gắn tên người
yêu cầu (ví dụ face crop của người khác cắt ra từ frame chung) để người duyệt kiểm tra nhãn subject; các dòng này
không bao giờ là `delete` và không thuộc gold.

## Thứ tự ưu tiên luật (đóng băng)

Áp cho từng cặp, luật đầu tiên khớp sẽ quyết định:

| # | Điều kiện | Hành động | `reason_code` |
|---|---|---|---|
| 1 | Artefact có `legal_hold` | `retain_legal_hold` | `LEGAL_HOLD` |
| 2 | Mọi parent đều bị giữ (dẫn xuất hoàn toàn từ dữ liệu bị hold) | `retain_legal_hold` | `LEGAL_HOLD_INHERITED` |
| 3 | Chỉ một phần parent bị giữ | `escalate` | `PARTIAL_LEGAL_HOLD` |
| 4 | Yêu cầu chưa xác minh danh tính | `escalate` | `IDENTITY_NOT_VERIFIED` |
| 5 | `acl` không chứa nhóm quyền của pipeline | `escalate` | `NO_PERMISSION` |
| 6 | `origin_known` không phải `true`, hoặc parent không tồn tại trong graph | `escalate` | `UNKNOWN_ORIGIN` / `BROKEN_LINEAGE` |
| 7 | Artefact không gắn tên người yêu cầu (chỉ là con cháu) | `escalate` | `DERIVED_OTHER_SUBJECT` |
| 8 | Nhiều chủ thể, mọi chủ thể đều có yêu cầu xóa đã xác minh trong đợt này | `escalate` (chờ người xác nhận rồi mới xóa) | `MULTI_SUBJECT_ALL_REQUESTED` |
| 9 | Nhiều chủ thể, còn người chưa yêu cầu | `escalate` | `MULTI_SUBJECT` |
| 10 | Còn lại | `delete` | `OK_DELETE` |

Máy **không bao giờ** tự xóa một artefact có ngoại lệ; chỉ người duyệt mới đổi được `escalate` thành `delete`.

## Giả định gán nhãn gold (cần DPO/legal xác nhận)

- **A1 — Legal hold kế thừa.** Lệnh giữ đặt trên raw video được hiểu là giữ cả bản sao và dữ liệu dẫn xuất
  (backup, frame, crop, embedding, annotation). Gold gán `retain_legal_hold` cho các cặp này.
  Lý do chọn: xóa nhầm dữ liệu đang bị giữ là không hoàn tác được, còn giữ thừa thì sửa được ở lần chạy sau.
- **A2 — Export gộp nhiều người.** `training_export` chứa 9–10 chủ thể: không xóa cả file vì một người; gold gán `escalate`
  (hướng xử lý: dựng lại export không có người đó). Áp dụng cả khi một phần nguồn của export đang bị hold.
- **A3 — Artefact chung mà mọi chủ thể đều yêu cầu xóa** (`a0067/a0070` với DR-003 + DR-004; `a0123/a0126` với DR-006 + DR-007).
  Gold gán `delete` là kết quả **cuối cùng đúng** (không còn quyền lợi của người thứ ba), nhưng máy chỉ được `escalate`
  và phải có người xác nhận. Vì vậy PoC trước review được kỳ vọng < 1.0 trên gold ở 8 cặp này.
- **A4 — Artefact chung mà chỉ một người yêu cầu**: gold gán `escalate` (hướng xử lý: che/cắt người yêu cầu, không xóa cả artefact).
- **A5 — Không rõ nguồn gốc / bản sao ở vendor**: gold gán `escalate`.

Gold do chính nhóm gán nên **không độc lập** với policy: nó bắt được lỗi cài đặt và đo mức nhất quán với các giả định
trên, không chứng minh được các giả định đó trùng với GT của giảng viên. Phân tích độ nhạy cho A1 và A3 nằm trong
`reports/t08_selfcheck.md`.

## Tiêu chí quyết định (chốt trước)

| Trạng thái | Điều kiện | `reason_code` |
|---|---|---|
| REWORK | Kiểm tra toàn vẹn thất bại: khóa trùng, hành động không hợp lệ, cặp thiếu audit entry, hoặc sau khi xóa mock vẫn còn artefact lẽ ra đã xóa | `INTEGRITY_CHECK_FAILED` |
| HOLD | Còn cặp ngoại lệ chưa có quyết định của người duyệt, hoặc số ngoại lệ vượt budget B | `EXCEPTIONS_PENDING_REVIEW` / `REVIEW_BUDGET_EXCEEDED` |
| GO | Mọi cặp ngoại lệ đã có người duyệt, mọi cặp `delete` đã thực thi (mock) và kiểm tra tồn dư = 0; các cặp giữ/escalate còn lại được theo dõi kèm người phụ trách | `PLAN_EXECUTED_EXCEPTIONS_TRACKED` |

**Bổ sung làm rõ sau khi cài đặt (2026-11-14, không đổi metric, nhãn gold hay thứ tự luật):** hai trường hợp không đạt
điều kiện GO ở trên được gán mã riêng thay vì dùng chung một mã HOLD:

| Trạng thái | Điều kiện | `reason_code` |
|---|---|---|
| HOLD | Người duyệt cho xóa một artefact ở yêu cầu này nhưng dòng của yêu cầu khác trên cùng artefact vẫn còn ngoại lệ mở; lệnh xóa bị hạ về `escalate` | `CONFLICTING_ACTIONS` |
| HOLD | Chạy với `dry_run: true`: kế hoạch đã duyệt nhưng chưa thực thi | `DRY_RUN_ONLY` |
