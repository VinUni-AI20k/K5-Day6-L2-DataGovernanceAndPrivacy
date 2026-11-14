# Decision log — T02 Raw QC Triage

File này ghi lại các quyết định và đề xuất trong quá trình lập PRD. Mỗi mục nêu vấn đề, quyết định/lựa chọn kỹ thuật, lý do và trạng thái. Mục “Đã chốt” là điều người dùng xác nhận; mục “Ràng buộc repo” là yêu cầu từ đề, không phải quyết định riêng của nhóm.

## Bài toán hiện tại

Đây là bài lab T02 về kiểm tra chất lượng ảnh trong dữ liệu xe tự lái. Hệ thống xếp hạng ảnh có thể bị mờ, lóa, quá tối hoặc nén kém để annotators/QCs biết nên xem ảnh nào trước. Họ xem ảnh và quyết định cuối cùng, ví dụ giữ ảnh hoặc yêu cầu chụp lại.

Đây là PoC học tập dùng fixtures tổng hợp, không phải công cụ sản xuất và không chứng nhận an toàn cho xe tự lái.

## Quyết định đã chốt

### D-001 — Chọn track T02

- **Ngày:** 2026-11-14
- **Vấn đề:** Chọn một trong 14 bài toán của repo.
- **Quyết định:** Làm T02 — Raw QC Triage.
- **Lý do:** Bài này tập trung vào ảnh lỗi và quy trình QC, phù hợp với ngữ cảnh dữ liệu xe tự lái.
- **Trạng thái:** Đã chốt bởi người dùng.

### D-002 — Người dùng chính là annotators/QCs

- **Ngày:** 2026-11-14
- **Vấn đề:** Xác định ai dùng công cụ trong bối cảnh thực tế.
- **Quyết định:** Người dùng chính là annotators và QC reviewers.
- **Lý do:** Họ trực tiếp xem ảnh nghi lỗi và chịu trách nhiệm quyết định ảnh có dùng được hay cần xử lý lại.
- **Trạng thái:** Đã chốt bởi người dùng.

### D-003 — Giữ Human-in-the-loop

- **Ngày:** 2026-11-14
- **Vấn đề:** Công cụ tự quyết định ảnh bị loại/chụp lại hay chỉ hỗ trợ người kiểm tra?
- **Quyết định:** Công cụ xếp hạng ảnh và nêu lý do; annotator/QC xem rồi tự quyết định. Không tự động loại ảnh hay yêu cầu chụp lại.
- **Lý do:** Ảnh tối, mờ nhẹ hoặc thuộc điều kiện hiếm vẫn có thể hữu ích cho dữ liệu xe tự lái. Người kiểm tra cần xem ngữ cảnh trước khi quyết định.
- **Trạng thái:** Đã chốt bởi người dùng.

### D-004 — Ghi lại quyết định trong file này

- **Ngày:** 2026-11-14
- **Vấn đề:** Cách giữ lại lịch sử brainstorm và lý do chọn.
- **Quyết định:** Ghi từng quyết định giữa người dùng và PM vào file gốc logs.md, kèm bài toán và lý do chọn kỹ thuật/quyết định.
- **Lý do:** PRD cần thể hiện vì sao nhóm chọn hướng đó, không chỉ liệt kê tính năng.
- **Trạng thái:** Đã chốt bởi người dùng. Tiếp tục append mục mới khi có quyết định.

### D-005 — Hiển thị ánh sáng và camera trên review card

- **Ngày:** 2026-11-14
- **Vấn đề:** QC cần phân biệt lỗi ảnh với ảnh tối hữu ích hoặc đặc tính riêng của camera.
- **Quyết định:** Mỗi mục review hiển thị ảnh, lý do bị gắn cờ, điều kiện ánh sáng và camera ID.
- **Lý do:** Các trường hợp ảnh đêm hữu ích và camera cam_B bị báo nhầm là failure mode nêu trong đề T02. Score dùng để xếp thứ tự; vùng đánh dấu có thể bổ sung khi phát hiện glare cục bộ.
- **Trạng thái:** Đã chốt bởi người dùng.

### D-006 — Ưu tiên bắt lỗi trong budget review

- **Ngày:** 2026-11-14
- **Vấn đề:** Với budget cố định 20 ảnh, cần cân bằng việc bắt được ảnh lỗi với thời gian QC tiêu tốn cho báo nhầm.
- **Quyết định:** Ưu tiên Recall@20; theo dõi Precision@20 và thời gian review để kiểm soát workload.
- **Lý do:** Người dùng muốn giảm số ảnh lỗi bị bỏ sót mà vẫn nhìn thấy chi phí false alarm đối với annotators/QCs.
- **Trạng thái:** Đã chốt bởi người dùng. Recall@20 là metric chính thức của repo; Precision@20 cũng được evaluator tính. Thời gian review là chỉ số bổ sung của sản phẩm/lab.

### D-007 — Cho phép QC chọn HOLD

- **Ngày:** 2026-11-14
- **Vấn đề:** QC có thể gặp ảnh mà bằng chứng hiện có chưa đủ để quyết định giữ hay yêu cầu chụp lại.
- **Quyết định:** Thêm lựa chọn HOLD để QC không phải đoán giữa KEEP và RECAPTURE.
- **Lý do:** Giữ quyền quyết định ở con người và tránh biến score của hệ thống thành quyết định tự động.
- **Trạng thái:** Đã chốt bởi người dùng. Người hoặc hàng đợi xử lý tiếp mục HOLD chưa được chốt.

### D-008 — Chuyển mục HOLD cho QC cấp cao hơn

- **Ngày:** 2026-11-14
- **Vấn đề:** Mục HOLD cần người có kinh nghiệm hơn xem xét thay vì để reviewer ban đầu tự đoán.
- **Quyết định:** Chuyển mục HOLD cho QC cấp cao hơn xử lý.
- **Lý do:** Tạo đường xử lý cho trường hợp chưa đủ bằng chứng và giữ quyết định cuối trong quy trình review của con người.
- **Trạng thái:** Đã chốt bởi người dùng. Bằng chứng/ghi chú cần chuyển theo và cách xử lý nếu QC cấp cao vẫn chưa chắc còn mở.

### D-009 — Escalate HOLD lên chuyên gia/domain owner

- **Ngày:** 2026-11-14
- **Vấn đề:** QC cấp cao vẫn có thể chưa đủ chuyên môn hoặc bằng chứng để kết luận.
- **Quyết định:** Nếu QC cấp cao vẫn chưa chắc, giữ trạng thái HOLD và chuyển tiếp cho chuyên gia/domain owner.
- **Lý do:** Không ép reviewer đưa ra kết luận thiếu căn cứ; chuyển trường hợp khó đến đúng người có chuyên môn miền.
- **Trạng thái:** Đã chốt bởi người dùng. Quyền quyết định cuối và cách xử lý nếu domain owner vẫn chưa chắc còn mở.

### D-010 — Domain owner quyết định cuối, có thể giữ HOLD

- **Ngày:** 2026-11-14
- **Vấn đề:** Ảnh vẫn có thể thiếu bằng chứng sau khi QC cấp cao và domain owner xem xét.
- **Quyết định:** Domain owner là người quyết định cuối cho ảnh được escalate. Họ có thể chọn KEEP, RECAPTURE hoặc tiếp tục HOLD. Ảnh còn HOLD chưa được tính là đã duyệt và không tự chuyển sang KEEP/RECAPTURE.
- **Lý do:** Không ép một quyết định thiếu căn cứ; trạng thái chưa xử lý phải được giữ rõ để xem lại khi có thêm bằng chứng.
- **Trạng thái:** PM chốt theo yêu cầu người dùng “theo bạn đi”; có thể sửa nếu người dùng muốn đổi hướng.

### D-011 — Chuyển đủ ngữ cảnh khi escalate HOLD

- **Ngày:** 2026-11-14
- **Vấn đề:** QC cấp cao hoặc domain owner cần hiểu vì sao ảnh được chuyển lên và những đánh giá đã có.
- **Quyết định:** Hồ sơ HOLD chuyển kèm lý do gắn cờ, ghi chú của reviewer trước và lịch sử quyết định.
- **Lý do:** Người nhận có thể tiếp tục xem xét từ bằng chứng hiện có; giảm việc làm lại và giữ được audit trail.
- **Trạng thái:** Đã chốt bởi người dùng.

### D-012 — Score là thông tin phụ, không phải xác suất

- **Ngày:** 2026-11-14
- **Vấn đề:** Score có thể bị hiểu nhầm thành xác suất chính xác hoặc quyết định thay cho QC.
- **Quyết định:** Dùng score để xếp thứ tự; giao diện trình bày nó như thông tin phụ, không nổi bật hơn ảnh, lý do, điều kiện sáng và camera ID. Không gọi score là xác suất nếu chưa hiệu chuẩn.
- **Lý do:** Giữ lợi ích ưu tiên review nhưng để con người đánh giá bằng bằng chứng và ngữ cảnh.
- **Trạng thái:** Đã chốt bởi người dùng.

### D-013 — Không bắt buộc đánh dấu vùng nghi lỗi trong MVP

- **Ngày:** 2026-11-14
- **Vấn đề:** Đánh dấu vùng có thể giúp với glare cục bộ nhưng không áp dụng cho mọi lỗi và có thể làm tăng phạm vi PoC.
- **Quyết định:** MVP hiển thị ảnh đầy đủ và lý do gắn cờ; không bắt buộc overlay vùng nghi lỗi. Chỉ bổ sung vùng đánh dấu nếu PoC định vị vùng glare đủ tin cậy.
- **Lý do:** Ưu tiên giúp QC hiểu ảnh bị gắn cờ mà không đòi thuật toán định vị chính xác cho blur, dark hoặc compression.
- **Trạng thái:** Đã chốt bởi người dùng.

### D-014 — Bắt buộc ghi chú cho HOLD/RECAPTURE

- **Ngày:** 2026-11-14
- **Vấn đề:** Các mục HOLD hoặc RECAPTURE cần đủ ngữ cảnh cho reviewer cấp cao, nhưng ghi chú cho mọi ảnh có thể làm chậm QC.
- **Quyết định:** Bắt buộc ghi chú khi chọn HOLD hoặc RECAPTURE; ghi chú cho KEEP là tùy chọn.
- **Lý do:** Lý do đi kèm các mục cần escalation hoặc làm lại; trường hợp bình thường vẫn xử lý nhanh.
- **Trạng thái:** Đã chốt bởi người dùng.

### D-015 — Reason code kết hợp ghi chú tự do

- **Ngày:** 2026-11-14
- **Vấn đề:** Chỉ có ghi chú tự do khó thống kê; chỉ có mã lý do không truyền đủ ngữ cảnh cho trường hợp khó.
- **Quyết định:** QC chọn một hoặc nhiều reason code chuẩn: blur, glare, dark, compression, insufficient evidence hoặc other. Khi chọn HOLD/RECAPTURE, QC phải viết thêm ghi chú tự do; với KEEP, ghi chú là tùy chọn.
- **Lý do:** Mã chuẩn cho phép tổng hợp lỗi; ghi chú tự do giải thích trường hợp cụ thể cho reviewer tiếp theo.
- **Trạng thái:** Đã chốt bởi người dùng.

### D-016 — PoC dùng score từ feature ảnh giải thích được

- **Ngày:** 2026-11-14
- **Vấn đề:** Baseline Laplacian một tín hiệu dễ bỏ qua glare cục bộ, độ tối và lỗi nén; QC cũng cần hiểu vì sao ảnh bị xếp hạng cao.
- **Quyết định:** PoC kết hợp dấu hiệu độ nét thấp, vùng tối, vùng cháy sáng/glare cục bộ và nén JPEG thành score xếp hạng. Có thể chuẩn hóa theo camera hoặc điều kiện sáng nếu dev cho thấy cần. Reason code phản ánh dấu hiệu chính. MVP không huấn luyện model.
- **Lý do:** Dấu hiệu ảnh giải thích được, chạy CPU/offline và có thể đưa lý do cụ thể cho QC; phù hợp quy mô fixture nhỏ của lab.
- **Trạng thái:** Đã chốt bởi người dùng. Trọng số, threshold và cách tính feature cụ thể vẫn phải chọn trên dev.

### D-017 — Diễn đạt vấn đề theo budget review cố định

- **Ngày:** 2026-11-14
- **Vấn đề:** Cần mô tả đúng động lực bài lab mà không khẳng định một quy trình QC ngoài đời chưa được xác minh.
- **Quyết định:** PRD mô tả rằng T02 có budget review cố định B=20 và công cụ xếp hạng ảnh nghi lỗi để QC xem trước; không tuyên bố QC thực tế không thể xem hết batch.
- **Lý do:** Đây là ràng buộc rõ trong đề T02; bối cảnh giới hạn thời gian ngoài đời chưa được người dùng xác nhận.
- **Trạng thái:** Đã chốt bởi người dùng.

## Ràng buộc từ repo

Các điểm dưới đây được lấy từ docs/tracks/T02.md, configs/tracks/t02.yaml, src/metrics/tracks.py và README.md.

- **Input:** 96 ảnh tổng hợp 320×180 từ 24 cảnh; metadata gồm image ID, đường dẫn, camera, điều kiện sáng và split. Repo hiện có 56 ảnh dev và 40 ảnh eval.
- **Nhãn:** Ground truth có loại lỗi none, blur, glare, dark, compression, severity 0–2 và cờ có lỗi/không lỗi. Ground truth chính thức nằm trong gói giảng viên; pipeline không được đọc gt/.
- **Output:** ranked_review.csv, bắt buộc có image_id, score; score cao nghĩa là review trước. Có thể thêm loại lỗi dự đoán và hành động gợi ý.
- **Review budget:** B = 20 ảnh.
- **Metric chính thức:** Defect Recall@20; Precision@20 là metric đi kèm. Eval chạy trên split eval. Không thay định nghĩa metric chính thức.
- **Baseline theo đề T02:** Một ngưỡng Laplacian toàn ảnh. Lệnh make baseline TRACK=t02 hiện gọi random baseline để thử wiring, nên không thay thế baseline Laplacian trong báo cáo cuối.
- **Reproducibility:** seed 42, chạy offline; baseline và PoC phải dùng cùng pool, split, seed và budget.
- **Ground truth:** Không có trong repo học viên; không tạo hoặc báo số liệu giả như kết quả chính thức.

## Đề xuất đang chờ thống nhất

### P-005 — Báo riêng theo mức độ lỗi

- **Vấn đề:** Metric hiện tại đếm mọi ảnh lỗi như nhau, dù nhãn có severity 0–2.
- **Đề xuất:** Nếu nhãn được cung cấp, báo thêm Recall@20 theo severity như metric phụ; không đổi metric chính thức.
- **Lý do:** Kết quả tổng thể có thể che lấp việc nhóm bỏ sót các lỗi nặng hơn.
- **Trạng thái:** Đã để ngoài scope build theo quyết định D-022 của người dùng.

## Quyết định kỹ thuật dựa trên contract repo

### D-018 — Ánh xạ quyết định QC sang trạng thái chuẩn của repo
- **Ngày:** 2026-11-14
- **Vấn đề:** Pipeline phải ghi quyết định KEEP, RECAPTURE hoặc HOLD vào contract quyết định GO/HOLD/REWORK của repo.
- **Quyết định:** Dùng ánh xạ có sẵn trong `src/common/decision.py`: KEEP → GO, RECAPTURE → REWORK, HOLD → HOLD. Domain owner là người quyết định cuối cho các mục được escalate theo D-010; nếu domain owner vẫn HOLD thì mục chưa được duyệt và không tự chuyển trạng thái.
- **Lý do:** Tái sử dụng alias chuẩn của repo, giữ nguyên metric/evaluator và tránh tạo trạng thái không tương thích.
- **Trạng thái:** Ràng buộc repo kết hợp quyết định đã chốt ở D-010.
- **Nguồn hoặc bằng chứng:** `src/common/decision.py::ALIASES`, `src/common/decision.py::canonical_status`, D-010.

### D-019 — Dùng các lượt review CSV/HTML offline theo cấp
- **Ngày:** 2026-11-14
- **Vấn đề:** Repo là lab offline, nhưng T02 đã chốt escalation tuần tự qua QC, senior QC và domain owner.
- **Quyết định:** Đề xuất một queue/contact sheet cho mỗi cấp; reviewer điền CSV của cấp mình rồi chạy lại pipeline để sinh cấp kế tiếp. Mỗi lần HOLD giữ reason, note, reviewer và lịch sử trong audit log.
- **Lý do:** Tái sử dụng contact sheet offline hiện có, không cần server, và cho phép lần theo quyết định qua các cấp.
- **Trạng thái:** Người dùng duyệt cùng spec T02.
- **Nguồn hoặc bằng chứng:** `src/common/contact_sheet.py`, `src/common/review.py`, PRD T02 FR-08/FR-09.

### D-020 — Giới hạn ý nghĩa của batch decision ở hàng đợi top-20
- **Ngày:** 2026-11-14
- **Vấn đề:** Chỉ top-20 trong batch được xem xét; GO không thể hàm ý toàn bộ 96 ảnh đã được QC hoặc được chấp thuận phát hành.
- **Quyết định:** Đề xuất `decision.json` chỉ biểu thị kết quả của hàng đợi review top-20: HOLD nếu còn mục HOLD/chưa được giải quyết; nếu không, REWORK khi có RECAPTURE; GO khi cả 20 mục đã được KEEP. Scope/reason phải nói rõ đây không phải quyết định release dataset.
- **Lý do:** Không suy rộng từ mẫu ưu tiên sang toàn batch, đồng thời vẫn đáp ứng bước decision của contract lab.
- **Trạng thái:** Đã chốt bởi người dùng.
- **Nguồn hoặc bằng chứng:** D-003, D-006, `docs/tracks/T02.md` (budget B=20), `src/common/decision.py`.

### D-021 — Để người dùng điền config và tự commit
- **Ngày:** 2026-11-14
- **Vấn đề:** `configs/lab.yaml` còn `group_id: G00` và owner mẫu; người dùng muốn tự thay giá trị trước khi nộp.
- **Quyết định:** Không sửa config trong lúc build, không tự commit. Sau build, người dùng tự điền group/owner rồi tự commit.
- **Lý do:** Giữ quyền kiểm soát thông tin ký duyệt và thời điểm commit ở người dùng.
- **Trạng thái:** Đã chốt bởi người dùng.
- **Nguồn hoặc bằng chứng:** Người dùng trả lời câu hỏi mở 1 trong phiên build T02.

### D-022 — Không thêm severity breakdown vào build
- **Ngày:** 2026-11-14
- **Vấn đề:** PRD có đề xuất báo Recall@20 theo severity như metric phụ.
- **Quyết định:** Để severity breakdown ngoài scope; dùng metric evaluator repo định nghĩa, không thêm metric phụ này.
- **Lý do:** Người dùng chọn giữ scope gọn và metric chính thức không đổi.
- **Trạng thái:** Đã chốt bởi người dùng.
- **Nguồn hoặc bằng chứng:** Người dùng trả lời câu hỏi mở 2 trong phiên build T02.

### D-023 — Queue review lấy top-20 từ split eval
- **Ngày:** 2026-11-14
- **Vấn đề:** Nếu queue lấy top-20 từ cả 96 ảnh thì khác pool eval 40 ảnh mà metric Recall@20 dùng.
- **Quyết định:** Đề xuất xếp hạng đủ 96 ảnh nhưng tạo queue/contact sheet từ top-20 trong split eval. Baseline và PoC dùng cùng pool, seed và budget.
- **Lý do:** Bằng chứng con người kiểm tra trùng với tập mà evaluator chấm; dev chỉ dùng để hiệu chỉnh.
- **Trạng thái:** Người dùng duyệt cùng spec T02.
- **Nguồn hoặc bằng chứng:** `src/metrics/tracks.py::eval_t02`, `configs/tracks/t02.yaml`, `docs/ONBOARDING_T02.md`.

### D-024 — Baseline Laplacian là module chạy riêng
- **Ngày:** 2026-11-14
- **Vấn đề:** Repo có random baseline thử wiring; baseline chính thức T02 phải dùng Laplacian và chạy so sánh cùng PoC.
- **Quyết định:** Đề xuất `src/baseline_t02.py` chạy qua `src.main --pipeline`, ghi vào `out/baseline`; PoC ghi vào `out/poc`.
- **Lý do:** Giữ hai output độc lập, dễ tái lập và đúng hướng dẫn onboarding của repo.
- **Trạng thái:** Người dùng duyệt cùng spec T02.
- **Nguồn hoặc bằng chứng:** `docs/ONBOARDING_T02.md`, `src/examples/random_baseline.py`.

### D-025 — Khóa ngữ cảnh và chống ghi trùng khi import review
- **Ngày:** 2026-11-14
- **Vấn đề:** CSV review chung không tự kiểm stage, item ID, phiên ranking; chạy lại pipeline có thể thêm trùng audit/decision log.
- **Quyết định:** Đề xuất thêm stage và queue ID vào CSV, mã reason của con người riêng reason máy, xác thực ID và nhập lặp không tạo sự kiện trùng; sửa quyết định được ghi như override mới.
- **Lý do:** Bảo toàn lịch sử tin cậy qua ba cấp, tránh nhận nhầm CSV cũ và tránh đếm một quyết định nhiều lần.
- **Trạng thái:** Người dùng duyệt cùng spec T02.
- **Nguồn hoặc bằng chứng:** `src/common/review.py`, `src/common/contact_sheet.py`, `src/common/decision.py`.

### D-026 — Thêm `no_defect` cho KEEP
- **Ngày:** 2026-11-14
- **Vấn đề:** D-015 chưa có mã cho ảnh được QC chọn KEEP, trong khi PRD yêu cầu mọi quyết định có reason code.
- **Quyết định:** Bổ sung mã `no_defect` cho KEEP; mỗi quyết định review phải có ít nhất một mã. Note của KEEP vẫn tùy chọn, HOLD/RECAPTURE vẫn bắt buộc note.
- **Lý do:** Phân biệt ảnh đã được người xem và thấy không lỗi với trường hợp thiếu mã, giữ được audit đầy đủ.
- **Trạng thái:** Đã chốt bởi người dùng khi review spec.
- **Nguồn hoặc bằng chứng:** Người dùng chọn phương án 1; PRD FR-06/FR-11 và D-015.

### D-027 — Dùng trực tiếp tên file export trong HTML
- **Ngày:** 2026-11-14
- **Vấn đề:** Tên file export đã được nhúng thành chuỗi JavaScript hợp lệ, nhưng HTML lại gọi `JSON.parse` lần nữa; trình duyệt sẽ ném lỗi và không tải CSV.
- **Quyết định:** Gán trực tiếp `EXPORT_FILENAME` cho `a.download` và thêm test kiểm tra tên file cấu hình xuất hiện trong HTML sinh ra.
- **Lý do:** `JSON.stringify` phía Python đã mã hóa tên file thành chuỗi JS; parse lần hai là không cần thiết và làm hỏng luồng export.
- **Trạng thái:** Đã sửa trong build T02.
- **Nguồn hoặc bằng chứng:** `src/common/contact_sheet.py`, `tests/test_t02_pipeline.py`.

### D-028 — Ghi rõ phạm vi quyết định ở eval top-20
- **Ngày:** 2026-11-14
- **Vấn đề:** Quyết định GO/HOLD/REWORK phải nói rõ chỉ áp dụng queue đã review, nếu không người đọc có thể hiểu nhầm là duyệt cả batch.
- **Quyết định:** Nêu rõ kích thước và phạm vi `eval top-B review queue` trong reason của `decision.json`.
- **Lý do:** Bảo toàn chính sách người dùng đã chốt: GO cho top-20 không phải phê duyệt release toàn batch.
- **Trạng thái:** Đã sửa; test luồng HOLD kiểm tra nội dung này.
- **Nguồn hoặc bằng chứng:** Acceptance của spec T02 và `tests/test_t02_pipeline.py`.

## Câu hỏi còn mở

- Ai là owner ký quyết định và mã group_id nào cần điền trong configs/lab.yaml?
- Quy trình QC hiện tại của nhóm/đơn vị đang diễn ra như thế nào và điểm đau cụ thể nhất là gì?

## Cách cập nhật log từ đây

Khi có quyết định mới, thêm mục theo mẫu:

~~~text
### D-00X — Tên quyết định
- Ngày:
- Vấn đề:
- Quyết định:
- Lý do:
- Trạng thái: Đã chốt / Đề xuất / Chưa quyết
- Nguồn hoặc bằng chứng:
~~~



### D-020 — Phân vai dự kiến cho nhóm 7 người

- **Ngày:** 2026-11-14
- **Vấn đề:** Repo yêu cầu báo cáo đóng góp nhóm và đối chiếu tên/email với `git shortlog`; hiện chưa có danh sách danh tính thật từ nhóm.
- **Quyết định:** Chia 7 vai trò dự kiến trong `reports/team_contributions.csv`: lead/integrator; data & provenance; core algorithm & baseline; human review & audit; metric & evaluation; QA & reproducibility; demo & documentation. Để trống tên Git, email và commit SHA để nhóm tự điền.
- **Lý do:** Bao phủ các phần việc T02 theo cấu trúc repo mà không ghi nhận giả danh tính hoặc commit chưa có.
- **Trạng thái:** Phân công dự kiến theo yêu cầu người dùng; cần cập nhật theo đóng góp thực tế trước khi nộp.


### D-021 — Thêm sơ đồ workflow vào web demo

- **Ngày:** 2026-11-14
- **Vấn đề:** Người mới mở demo cần hiểu dữ liệu đi từ đâu, pipeline xử lý gì và quyết định cuối liên quan thế nào tới hàng đợi QC.
- **Quyết định:** Thêm sơ đồ Input → kiểm tra manifest/hash → đo Blur/Dark/Glare/JPEG → chọn Top 20 → review Annotator/QC → Senior QC → Domain owner → GO/REWORK/HOLD.
- **Lý do:** Làm rõ vai trò của score là xếp thứ tự review, đồng thời cho thấy HOLD chưa được xem là đã duyệt; sơ đồ cũng ghi rõ kết quả chỉ áp dụng cho Top 20 eval queue.
- **Trạng thái:** Đã thêm theo yêu cầu người dùng. Tương tác trong HTML vẫn chỉ lưu trong bộ nhớ trình duyệt.
