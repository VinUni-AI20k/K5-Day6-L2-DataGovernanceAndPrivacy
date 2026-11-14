# T08 — Phân công và cách bàn giao nhóm skyyyyy

Owner quyết định cuối: **LeVanKhoi**. Bốn phần còn lại được bốc ngẫu nhiên:
Núi (lineage), Vinh (policy), Anh (review), Nam (executor/audit/evaluation).
Đã ghi tên vào reports/team_contributions.csv; Git name/email vẫn cần từng
thành viên điền đúng danh tính commit thực tế.

## Phạm vi và trạng thái

Tình huống: người dùng bấm yêu cầu xóa trên app. Hệ thống tìm dữ liệu liên
quan, xét ngoại lệ, cho người duyệt rồi mô phỏng xóa và ghi bằng chứng.
Input là requests.json (10 request), data_graph.json (212 artefact).

Đã có: config T08, sửa LF cho fixture, loader đọc JSON và kiểm ID.
Các thuật toán còn TODO; chỉ load_input() đã nối vào pipeline. Chạy hiện
dừng status=3 tại process(), chưa có output/metric hoàn chỉnh. Đây là khung
được chuẩn bị với hỗ trợ AI, không phải bài giải đã xong của các thành viên.

## Phân công 5 người

| Người | File được giao | Kết quả phải bàn giao |
|---|---|---|
| 1 — LeVanKhoi | src/pipeline.py, src/t08/input_data.py, src/t08_baseline.py, configs/lab.yaml | Hiểu loader; ghép module; baseline; xuất actions.csv và decision |
| 2 — Núi | src/t08/lineage.py | Tìm đủ artefact liên quan; không trùng/vòng lặp; giải thích cách tìm |
| 3 — Vinh | src/t08/policy.py | Bảng rule và action/reason/score cho từng cặp request–artefact |
| 4 — Anh | src/t08/human_review.py | Queue CSV; đọc kết quả duyệt; áp override có kiểm tra và audit |
| 5 — Nam | src/t08/executor.py | Dry-run, mock state, idempotency, audit thực hiện; tổng hợp đánh giá |

Mỗi người thêm test cho phần mình và viết đoạn report tương ứng. Các đường
dẫn tests/test_t08_*.py trong CSV là file dự kiến tạo, hiện chưa có.
Người 5 tổng hợp kết quả, cả nhóm duyệt report. Chỉ ghi commit và bằng chứng
đóng góp thực tế sau khi đã làm, không nhận TODO sẵn như thuật toán hoàn chỉnh.

## Hợp đồng đầu vào/đầu ra

1. `load_input(input_dir)` -> dict có `requests` và `artefacts`, đều list[dict].
2. `find_related(request, artefacts)` -> list bản ghi artefact liên quan,
   không trùng, sắp theo artefact_id. Chỉ tìm liên quan, chưa quyết định xóa.
   Nhóm chốt cách xử lý thiếu parent/subject và phạm vi duyệt. Không lan sang
   mọi cha/anh em rồi tự xem tất cả là dữ liệu phải xóa.
3. `propose_action(request, artefact, actor)` -> dict có các cột sau:

   ```text
   item_id       = request_id + "::" + artefact_id
   request_id    = ID từ request
   artefact_id   = ID từ artefact
   action        = delete | retain_legal_hold | escalate
   reason_code   = mã lý do do nhóm chốt
   reason        = giải thích cho người duyệt
   score         = float; cao là cần review trước
   needs_review  = bool
   ```

   ID ghép tránh ghi đè khi hai request cùng liên quan một artefact. Actor xét
   ACL là danh tính thực hiện, phải chốt riêng; owner không có mọi quyền mặc định.
4. Người 1 gom dict thành DataFrame. Người 4 dùng item_id trong review queue,
   giữ nguyên proposal để so diff; thêm trạng thái phê duyệt nếu executor cần.
   Nhóm chốt nghĩa approve/reject/edit/escalate/skip. Chưa duyệt không đồng
   nghĩa được thực hiện xóa. Override phải tuân thủ các policy chặn xóa.
5. Người 5 nhận bảng sau review, chỉ cập nhật mock state trong thư mục output
   khi dry_run=False và hành động hợp lệ đã được duyệt. dry_run=True chỉ lập
   kế hoạch. Không ghi planned như executed. Chạy hai lần không xóa lần hai.
6. Xuất actions.csv có request_id, artefact_id, action; giữ hành động cuối và
   lưu bằng chứng thực hiện riêng. Audit phân biệt proposal/review/execution.

## Cách ghép — người 1 sửa pipeline.py

```text
load     -> load_input() (đã nối)
process  -> từng request: find_related() -> propose_action() -> DataFrame
rank     -> build_queue()
review   -> apply_review()
run      -> execute_mock() sau review, trước xuất kết quả cuối
decide   -> quyết định chung kèm reason_code + owner
```

Các bước sau load CHƯA nối. Khi ghép phải kiểm tra ràng buộc và quyết định
chưa được duyệt; không thay toàn bộ HOLD bằng GO để demo trông thành công.
Không cần sửa main.py/evaluator. Không sửa manifest hay tắt strict_provenance.

## Việc bắt đầu ngay

- Người 1: chạy main; đọc hiểu loader; chuẩn bị vòng lặp request và baseline.
- Người 2: lần tay DR-001, lập expected IDs cho một đồ thị nhỏ rồi viết traversal.
- Người 3: chốt precedence của hold/quyền/nguồn không rõ/nhiều subject/xác minh
  request; xác định thời điểm xét hold trước đánh giá.
- Người 4: thiết kế một dòng queue mẫu và kết quả duyệt, thống nhất với executor.
- Người 5: thiết kế mock state; kiểm dry-run, chạy hai lần, tiếp tục sau gián đoạn.

Mốc: phút 30 chốt interface/metric; phút 60 ghép được một request; phút 120
đủ luồng và baseline; phút 150 kiểm ngoại lệ; phút 180 freeze demo.

## Chạy trên Windows

Terminal tại thư mục gốc repo (có requirements.txt). Mỗi máy tự tạo .venv:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Những lần sau chỉ cần:

```powershell
.\.venv\Scripts\python.exe -m src.main --offline --seed 42
```

Hiện dự kiến thấy `[load] T08: 10 requests, 212 artefacts` rồi status=3 vì
process chưa implement. Không coi là đã hoàn thành PoC. Repo hướng dẫn Python
3.11–3.13; ghi đúng phiên bản thực dùng của máy khi báo cáo.

## Git và bằng chứng

Các bạn lấy cùng bản khung, tạo branch riêng (ví dụ member2-lineage), sửa file
được giao, test rồi commit/push branch và tạo PR. Người tích hợp review/merge
từng PR, chạy tích hợp sau mỗi lần ghép. Không cùng sửa pipeline.py.
Không đưa .venv/, out/ và cache lên Git; không thay GT hoặc metric.

Đánh giá chính thức cần GT overlay giảng viên. Khi chưa có, dùng case tự tạo
hoặc tự kiểm với nhãn khai báo rõ; không tự ghi số chấm thật. Baseline/PoC dùng
cùng pool, seed, protocol; phân tích xóa sót, xóa nhầm và ít nhất hai failure case.
