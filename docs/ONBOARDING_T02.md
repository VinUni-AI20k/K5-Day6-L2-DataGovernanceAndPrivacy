# Onboarding T02 — Raw QC Triage

Hướng dẫn đi từ cài môi trường đến nộp bài T02 trong repo Day 06. T02 xếp hạng ảnh nghi mờ, lóa, tối hoặc nén kém để người review kiểm tra 20 ảnh có nguy cơ cao nhất.

## 0. Chuẩn bị môi trường

Repo hướng dẫn Python 3.11–3.13. Cài dependencies, kiểm tra môi trường, manifest và test nền trước khi sửa pipeline.

### Windows PowerShell

Makefile mặc định dùng đường dẫn Python kiểu Unix (.venv/bin/python). Nếu chạy PowerShell trên Windows, dùng:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m tools.preflight
.\.venv\Scripts\python.exe -m tools.verify_manifests fixtures/t02_raw_qc
.\.venv\Scripts\python.exe -m pytest -q
~~~

Nếu dùng Linux/macOS/WSL với GNU Make:

~~~bash
make setup
make preflight
make verify
make test
~~~

## 1. Cấu hình nhóm và track

Trong lúc build, giữ nguyên các giá trị mẫu trong `configs/lab.yaml`. Sau khi build xong, bạn điền `group_id` và `owner` của nhóm rồi tự commit.

~~~yaml
group_id: G__
owner: "Tên người phụ trách / vai trò"
track_config: tracks/t02.yaml
track: t02
input: fixtures/t02_raw_qc
output: out/
seed: 42
offline: true
strict_provenance: true
params: {}
~~~

`owner` mẫu khiến quyết định hiển thị trạng thái provisional. Giữ seed 42 và `offline: true` để lần chạy có thể lặp lại và không gọi mạng.

## 2. Đọc đề và hiểu dữ liệu

Đọc docs/tracks/T02.md, sau đó xem fixtures/t02_raw_qc/images.csv và các ảnh trong fixtures/t02_raw_qc/images/.

- Có 96 ảnh tổng hợp, kích thước 320×180, từ 24 cảnh gốc.
- images.csv có image_id, path, camera_id, light, split.
- Hiện có 56 ảnh dev và 40 ảnh eval; các ảnh cùng cảnh gốc được giữ cùng split.
- Nhãn đúng gồm none, blur, glare, dark, compression, nhưng nằm trong gt/labels.csv của gói giảng viên. Gói học viên không có file này.
- manifest.csv ghi hash và provenance; không sửa fixture để làm đẹp kết quả.

Không đọc gt/ trong pipeline. src.main chặn thao tác này. Khi thiếu ground truth, src.evaluate chính thức sẽ trả lỗi thiếu file; không tự tạo số liệu giả để đưa vào báo cáo.

## 3. Chốt metric contract trước khi tối ưu

Điền reports/metric_contract.md trước khi xem kết quả eval:

- Primary: Defect Recall@B, với B = 20, trên split eval.
- Secondary: Precision@B, false alarm theo điều kiện sáng; defect-type accuracy nếu pipeline xuất pred_defect_type.
- score càng cao thì ảnh càng được đưa lên đầu hàng review.
- Chỉ chọn feature, threshold và trọng số dựa trên dev hoặc một tập dev được nhóm tự gán nhãn.
- Ghi rõ ngày chốt threshold, seed 42, cách lấy mẫu và các slices sẽ báo cáo.

Diễn giải metric:

- Recall@20 = số ảnh lỗi trong top 20 / tổng số ảnh lỗi trong eval.
- Precision@20 = số ảnh lỗi trong top 20 / 20.

Recall thấp nghĩa là bỏ sót nhiều lỗi. Precision thấp nghĩa là người review phải xem nhiều ảnh tốt. Không đổi metric, threshold hoặc test set sau khi xem eval.

## 4. Tạo baseline và ghi nhận ca lỗi

Baseline T02 trong đề là một ngưỡng Laplacian toàn ảnh:

1. Đọc ảnh và tính laplacian_variance từ src/common/image_ops.py.
2. Độ nét thấp được xem là nghi blur; chuyển thành score sao cho blur có score cao hơn.
3. Xếp hạng toàn bộ pool theo score và ghi ranked_review.csv.

make baseline TRACK=t02 gọi src.examples.random_baseline: nó hữu ích để kiểm tra dây chuyền và output, nhưng là xếp hạng ngẫu nhiên, không phải baseline Laplacian quy định riêng trong đề T02. Khi so sánh chính thức, dùng baseline Laplacian do nhóm cài.

Có thể đặt baseline ở một module riêng, ví dụ src/baseline_t02.py với hàm run(ctx), rồi chạy:

~~~powershell
.\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t02 --input fixtures/t02_raw_qc --output out/baseline --run-name baseline --pipeline src.baseline_t02 --offline --seed 42
~~~

Thay src.baseline_t02 bằng tên module thực tế của nhóm nếu chọn tên khác.

Trước khi làm PoC, chọn và ghi lại 2–3 ca đáng chú ý trong dev: ví dụ ảnh đêm hữu ích, lóa cục bộ trên vùng nhỏ, hoặc ảnh từ camera cam_B bị báo nhầm. Mô tả ảnh, metadata và vì sao baseline sai.

## 5. Cài pipeline trong src/pipeline.py

Pipeline phải nối đủ năm bước mà src.main gọi:

1. **load** — kiểm tra hash manifest và đường dẫn ảnh, đọc metadata `images.csv`; không đọc `gt/`.
2. **process** — đo blur, vùng tối, glare cục bộ và JPEG blockiness; chuẩn hóa theo dev và tạo score giải thích được.
3. **rank** — xếp hạng đủ 96 ảnh, rồi tạo queue gồm top-20 của split eval.
4. **review** — nhập CSV riêng theo cấp QC, senior QC và domain owner; HOLD được chuyển tiếp cùng lịch sử, còn quyết định được ghi vào audit.
5. **decide** — phát hành `decision.json` và `decision_log.csv`; GO chỉ áp dụng queue top-20, không duyệt cả batch.

PoC có thể kết hợp nhiều feature thay vì chỉ nhìn độ nét. Chuẩn hóa theo camera_id hoặc light để tránh coi đặc tính riêng của một camera hay ảnh ban đêm là lỗi tự động. Có thể tính glare theo vùng nhỏ vì ảnh rõ tổng thể vẫn có thể bị lóa cục bộ.

Output bắt buộc:

- out/poc/ranked_review.csv: có image_id, score.
- out/poc/review_queue.csv: các mục ưu tiên review.
- out/poc/audit_log.jsonl, out/poc/decision.json, out/poc/decision_log.csv.
- out/poc/run_info.json: thông tin lần chạy và kiểm tra output.

Reviewer chọn KEEP/RECAPTURE/HOLD. KEEP ánh xạ GO, RECAPTURE ánh xạ REWORK, HOLD giữ trạng thái HOLD và được chuyển QC → senior QC → domain owner. Tất cả KEEP chỉ tạo GO cho eval top-20 queue; đây không phải phê duyệt toàn batch.

## 6. Chạy baseline và PoC

Trong lúc phát triển, chạy kiểm tra manifest và pipeline. Với PowerShell:

~~~powershell
.\.venv\Scripts\python.exe -m tools.verify_manifests fixtures/t02_raw_qc
.\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t02 --input fixtures/t02_raw_qc --output out/poc --run-name poc --offline --seed 42
~~~

Hoặc với Make:

~~~bash
make run TRACK=t02
~~~

src/pipeline.py hiện là starter skeleton. Trước khi process() được cài, lần chạy có thể kết thúc với exit code 3 (NOT IMPLEMENTED). Sau khi hoàn thành, kỳ vọng exit code 0 và đúng các output contract.

Chạy baseline vào out/baseline/ và PoC vào out/poc/. Cả hai phải dùng cùng input, split, seed và budget 20. Ghi lại command, config và commit tương ứng.

## 7. Human review

Mở contact sheet offline của top 20 ảnh. Mỗi người review ghi tên, quyết định, một hay nhiều reason code phân tách bằng `;`, và note khi quyết định là HOLD/RECAPTURE. KEEP dùng `no_defect` nếu không thấy lỗi; note KEEP được để trống.

1. QC lưu file đã review thành `out/poc/review_queue_reviewed.csv`.
2. Chạy lại pipeline. Mục HOLD xuất hiện trong `senior_review_queue.csv` và `senior_contact_sheet.html`.
3. Nếu senior QC tiếp tục HOLD, chuyển tiếp bằng `domain_owner_review_queue.csv` và `domain_owner_contact_sheet.html`.
4. Domain owner có thể tiếp tục HOLD; khi đó quyết định cuối vẫn là HOLD. Chạy lại với cùng CSV không được tạo audit event trùng.
5. Chép bằng chứng review/decision cần nộp vào `reports/`.

Review queue chỉ chứa ảnh được xếp hạng. Nó không tự phát hiện ảnh bị bỏ sót hoàn toàn vì ảnh đó không có dấu hiệu nào để xếp hạng. Vì vậy, kiểm tra thêm một mẫu ảnh đầy đủ để tìm false negative.

## 8. Test và đánh giá

Nhóm cần thêm ít nhất hai test của mình:

- Test thành công: ảnh blur được xếp hạng trước ảnh rõ trong tình huống kiểm soát.
- Test lỗi/edge: thiếu ảnh, ảnh hỏng, score không hợp lệ hoặc trường hợp dễ báo nhầm phải được xử lý rõ ràng.

Chạy test và preflight trước demo/nộp:

~~~powershell
.\.venv\Scripts\python.exe -m tools.preflight
.\.venv\Scripts\python.exe -m pytest -q
~~~

Khi giảng viên cung cấp ground truth, đánh giá baseline và PoC rồi tạo bảng so sánh:

~~~bash
python -m src.evaluate --track t02 --pred out/baseline/ranked_review.csv --run-name baseline --out reports/metrics_baseline.json
python -m src.evaluate --track t02 --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
~~~

Evaluator chính thức dùng hidden ground truth, không có trong repo học viên. Trước lúc được cấp GT, có thể tự gán nhãn một phần dev để debug; ghi rõ đó là đánh giá nội bộ, không phải điểm official.

Đánh giá PoC có đáng tin hay không bằng cách:

- So baseline với PoC trên cùng pool eval và cùng B=20.
- Báo cả Recall@20 và Precision@20, không chỉ một chỉ số.
- Báo false alarm theo day/dusk/night; trình bày ca lỗi đã tìm và nguyên nhân.
- Không tune threshold trên eval. Tập eval nhỏ nên mô tả giới hạn, không tuyên bố chắc chắn hiệu quả trên dữ liệu thật.

## 9. Hoàn thiện report và nộp

Điền các file sau:

- reports/metric_contract.md: metric và protocol đã chốt.
- reports/group_report.md: vấn đề, dữ liệu/provenance, thiết kế, baseline so với PoC, kết quả, failure cases, human review, giới hạn và cách tái lập.
- reports/metrics_baseline.json, reports/metrics_poc.json, reports/table1_baseline_vs_poc.md: do script sinh; không sửa số bằng tay.
- reports/review_queue.csv và reports/decision_log.csv: bằng chứng review và quyết định.
- reports/team_contributions.csv: tên/email, vai trò, file/commit evidence và presenter.

Trước khi nộp:

1. Chạy lại preflight, manifest verification, tests và one-command PoC.
2. Kiểm tra report có Git URL, tag demo/final và đúng thông tin nhóm.
3. Đảm bảo mỗi thành viên có ít nhất một commit thực chất; đối chiếu git shortlog -sne --all với team_contributions.csv.
4. Tạo tag theo mốc repo: make tag-demo, sau đó make tag-final. Đẩy branch/tag lên remote theo hướng dẫn của lớp.
5. Nộp Git repo, report và demo theo kênh/lớp quy định; repo không chỉ định một LMS cụ thể.

Metric JSON và bảng so sánh phải được evaluator sinh lại được. Không commit ảnh/người/biển số thật nếu chưa có quyền; fixtures T02 hiện là dữ liệu synthetic.

## Mốc làm việc gợi ý trong repo

- 00–10 phút: setup, chọn track, chia vai trò; mỗi người tạo commit đầu.
- 10–30 phút: đọc đề và chốt metric contract.
- 30–50 phút: baseline và các ca lỗi ban đầu.
- 50–145 phút: pipeline, review queue, contact sheet và report.
- 145–170 phút: kiểm heldout khi có GT, ablation, sửa lỗi, ghi hai failure cases.
- 170–180 phút: freeze demo, tag demo-180m, chuẩn bị 3–5 slide.
- +24 giờ: hoàn thiện report, contributions và tag final-24h.
