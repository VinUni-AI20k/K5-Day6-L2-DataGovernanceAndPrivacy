# Kế hoạch T08 · Retention & Delete Request Simulator

Tài liệu làm việc của nhóm 5 người. Đọc mục 1–4 trước khi viết dòng code đầu tiên (khoảng 10 phút).
Đề gốc: [tracks/T08.md](tracks/T08.md). Rubric và quy tắc: [README.md](../README.md) mục 6–7.

## 1. Bài toán trong 5 dòng

- Đầu vào: `fixtures/t08_deletion/data_graph.json` (212 artefact giả lập) và `requests.json` (10 yêu cầu xóa, mỗi yêu cầu 1 `subject_id`).
- Việc phải làm: với mỗi yêu cầu, tìm mọi artefact chứa dữ liệu của người đó, rồi gán cho từng artefact một trong 3 hành động `delete`, `retain_legal_hold`, `escalate`.
- Đầu ra bắt buộc: `out/poc/actions.csv` với cột `request_id, artefact_id, action`, và `out/poc/audit_log.jsonl`.
- Không xóa gì thật. Đây là mô phỏng: chỉ ghi quyết định và bằng chứng.
- Mục tiêu điểm: Deletion Completeness cao nhất có thể, **False-delete = 0**, audit đủ 100%, chạy 2 lần ra cùng kết quả.

## 2. Những gì đã biết về dữ liệu

Các con số dưới đây đếm trực tiếp từ fixture. Ai sửa loader thì kiểm lại bằng test.

### 2.1 Cấu trúc cây

```
raw_video (15) ─┬─ backup (15)
                └─ frame (45) ─┬─ face_crop (45) ─┬─ embedding (45)
                               │                  └─ training_export (2, mỗi cái có 12 cha)
                               └─ annotation (45)
```

- Mỗi artefact có `subject_ids`, `parent_ids`, `acl`, `legal_hold`, `origin_known`. Mọi artefact đều có ít nhất 1 subject.
- 10 yêu cầu ứng với 10 subject: 01, 03, 04, 05, 07, 08, 09, 11, 12, 14. Năm subject còn lại (00, 02, 06, 10, 13) **không** yêu cầu xóa.
- Tổng số cặp (yêu cầu, artefact có gắn subject đó) là **158**.

### 2.2 Sáu cái bẫy trong fixture

| # | Bẫy | Artefact | Ảnh hưởng tới yêu cầu | Xử lý của nhóm |
|---|---|---|---|---|
| B1 | Legal hold trên video gốc | `a0043` (LH-2026-03), `a0099` (LH-2026-07) | DR-002, DR-005 | `retain_legal_hold` |
| B2 | Con cháu của video đang bị hold nhưng bản thân `legal_hold = null` | 14 artefact (DR-002), 15 artefact (DR-005); trong đó 26 cái chỉ có 1 chủ thể | DR-002, DR-005 | Xem câu hỏi mở Q1 |
| B3 | Không rõ nguồn gốc (`origin_known = false`) | 3 embedding `a0075`, `a0079`, `a0083` | DR-004 | `escalate` |
| B4 | Hệ thống không có quyền (`acl = ["vendor-x"]`) | backup `a0156` | DR-008 | `escalate` |
| B5 | Nhiều chủ thể: frame và annotation có 2 người; `training_export` có 9–10 người | 8 frame/annotation, 2 export (`a0211`, `a0212`) | 9 trên 10 yêu cầu | `escalate` |
| B6 | **Duyệt cây ngây thơ xóa nhầm người khác** | Frame `a0011` có subj_00 và subj_01, nhưng con của nó là `a0012`, `a0013` chỉ thuộc subj_00 | DR-001, DR-004, DR-007 | Không đưa vào `actions.csv` |

B6 là bẫy nguy hiểm nhất. Evaluator đếm mọi dòng `delete` nằm ngoài phạm vi GT là false-delete (xem `stray` trong `src/metrics/tracks.py::eval_t08`). Nếu BFS lấy hết con cháu của mọi artefact có gắn subject, ta sẽ xóa ảnh mặt và embedding của người không yêu cầu.

### 2.3 Quy tắc phạm vi (scope) của nhóm

Một artefact thuộc phạm vi của yêu cầu khi và chỉ khi `subject_id` nằm trong `subject_ids` của nó. Duyệt cây (BFS) vẫn cần, nhưng dùng cho 3 việc khác:

1. Ghi đường đi lineage vào audit log làm bằng chứng (ví dụ `a0043 > a0045 > a0046 > a0047`).
2. Phát hiện con cháu của artefact đang bị legal hold (bẫy B2).
3. Kiểm tra chéo: báo cảnh báo nếu có con cháu không gắn subject (bẫy B6) hoặc `parent_ids` trỏ tới artefact không tồn tại.

### 2.4 Ước tính kết quả

Giảng viên có bộ hidden eval tương đương, nên **không hard-code artefact ID** ở bất kỳ đâu trong pipeline. Các số dưới đây là dự đoán theo quy tắc của nhóm, chưa đối chiếu được với GT vì repo học viên không có `gt/`.

| Cách làm | Số dòng `delete` | Dự đoán |
|---|---|---|
| Baseline (xóa video gốc theo tên file) | 10 | Completeness khoảng 8/128 (6%), false-delete = 2 vì xóa cả 2 video đang bị hold |
| BFS ngây thơ, xóa hết con cháu | 164 | Completeness 100% nhưng false-delete khoảng 36 (30 ngoại lệ + 6 dòng ngoài phạm vi) |
| PoC của nhóm | 128 | Completeness 100%, false-delete 0, với 2 `retain_legal_hold` và 28 `escalate` |

## 3. Câu hỏi mở phải chốt trước phút 30

| # | Câu hỏi | Đề xuất mặc định | Ai chốt |
|---|---|---|---|
| Q1 | Legal hold trên video gốc có lan xuống backup, frame, crop, embedding không? | **Không lan.** Chỉ artefact có `legal_hold` khác null mới `retain_legal_hold`. Bản gốc đã giữ đủ bằng chứng, bản phái sinh vẫn xóa theo nguyên tắc tối thiểu hóa dữ liệu. Các dòng này được đẩy lên đầu review queue với reason `DERIVED_FROM_HELD` để người duyệt xác nhận. | M3 hỏi giảng viên, M1 chốt |
| Q2 | Artefact nhiều chủ thể: `escalate` hay `delete`? | `escalate`. Xóa sẽ làm mất dữ liệu của người không yêu cầu; cách xử lý đúng (che mặt, dựng lại export) cần người quyết. | M3 |
| Q3 | Review budget B bằng bao nhiêu? | B = 60, đủ chứa 30 ngoại lệ và 26 dòng `DERIVED_FROM_HELD`. | M5 |

Q1 là rủi ro điểm lớn nhất: nếu GT cho rằng hold lan xuống, 26 dòng `delete` của ta thành false-delete. Vì vậy phải làm 3 việc: hỏi giảng viên ngay phút đầu, để hành vi này thành tham số `hold_scope: direct | descendants` trong `configs/lab.yaml`, và ghi quyết định cùng lý do vào `reports/metric_contract.md` **trước** khi có kết quả eval. Không đổi tham số sau khi thấy điểm.

## 4. Thiết kế kỹ thuật

### 4.1 Cấu trúc file và người sở hữu

Mỗi file chỉ một người sửa. Đây là cách chính để tránh conflict.

| File | Người sở hữu | Nội dung |
|---|---|---|
| `src/pipeline.py`, `src/t08/contracts.py`, `configs/lab.yaml` | M1-Lộc | Nối dây 5 bước, kiểu dữ liệu chung, cấu hình |
| `src/t08/loader.py`, `src/t08/lineage.py` | M2-Tùng | Đọc JSON, kiểm tra schema, dựng graph, BFS, phạm vi |
| `src/t08/policy.py`, `configs/t08_policy.yaml` | M3-Hưng | Luật ưu tiên, reason code, điểm ưu tiên review |
| `src/t08/baseline.py`, `tests/test_t08_*.py`, `tests/data/t08_mini/` | M4-Dũng | Baseline, test, bộ gold tự dựng |
| `src/t08/audit.py`, `reports/*.md`, `demo/` | M5-Nam | Dry-run, audit log, áp override, báo cáo, slides |

File dùng chung (`requirements.txt`, `reports/team_contributions.csv`, `.github/`) chỉ M1 sửa.

### 4.2 Interface chốt ở phút 15

M1 push `contracts.py` cùng các stub chạy được. Sau đó không ai đổi chữ ký hàm nếu chưa báo cả nhóm.

```python
# src/t08/contracts.py
ACTIONS = ("delete", "retain_legal_hold", "escalate")

# loader.py (M2)
def load_inputs(input_dir) -> tuple[dict[str, dict], list[dict]]:
    """Trả (graph: artefact_id -> artefact, requests). Raise ValueError nếu thiếu trường bắt buộc."""

# lineage.py (M2)
def build_index(graph) -> dict:            # children, ancestors, cảnh báo dangling/cycle
def scope_for(graph, subject_id) -> list[str]            # artefact có gắn subject, đã sắp xếp
def lineage_path(graph, artefact_id) -> str              # "a0043 > a0045 > a0046"
def held_ancestor(graph, artefact_id) -> str | None      # mã hold của tổ tiên gần nhất, nếu có

# policy.py (M3)
def decide_action(artefact, request, ctx_info, params) -> tuple[str, str, float]:
    """Trả (action, reason_code, review_score). review_score cao = cần người xem trước."""

# audit.py (M5)
def write_audit(ctx, rows) -> None          # mỗi dòng actions.csv ứng với 1 dòng log
def apply_review(ctx, scored, reviewed) -> pd.DataFrame
```

### 4.3 Luật quyết định

Xét từ trên xuống, khớp luật nào thì dừng ở luật đó. Thứ tự theo gợi ý của đề: legal hold > quyền > nhiều chủ thể > xóa.

| Thứ tự | Điều kiện | Action | `reason_code` |
|---|---|---|---|
| 1 | `legal_hold` khác null | `retain_legal_hold` | `LEGAL_HOLD_ACTIVE` |
| 2 | `identity_verified` của yêu cầu là false | `escalate` | `IDENTITY_UNVERIFIED` |
| 3 | `acl` không chứa đơn vị vận hành (`data-platform`) | `escalate` | `NO_DELETE_PERMISSION` |
| 4 | `origin_known` là false | `escalate` | `UNKNOWN_ORIGIN` |
| 5 | `subject_ids` có hơn 1 người | `escalate` | `MULTI_SUBJECT` |
| 6 | Có tổ tiên đang bị hold và `hold_scope = descendants` | `retain_legal_hold` | `DERIVED_FROM_HELD` |
| 7 | Còn lại | `delete` | `SUBJECT_ONLY` |

Luật 2 không xuất hiện trong fixture (cả 10 yêu cầu đều đã xác minh) nhưng hidden eval có thể có, nên vẫn cài và viết test. Luật nằm trong `configs/t08_policy.yaml` kèm `source` (GDPR Đ.17(3), Luật 91/2025, NĐ 356/2025), không viết cứng trong code.

Mỗi dòng `retain_legal_hold` ghi thêm mã hold và ghi chú "xóa khi hết hold" vào audit log.

### 4.4 Ba điểm kỹ thuật dễ sai

1. **`rank()` mặc định lấy cột đầu tiên làm id.** Cột đầu của ta là `request_id`, không duy nhất. M1 sửa `rank()` để dùng `item_id = "<request_id>|<artefact_id>"`, và `apply_review()` tách lại theo dấu `|`.
2. **Evaluator chấm audit bằng `item_id == artefact_id`.** Khi gọi `ctx.audit.log(...)`, truyền `item_id=artefact_id` đúng nguyên văn, còn `request_id`, `reason_code`, `lineage_path`, `deadline` đưa vào tham số phụ.
3. **`actions.csv` không được có cặp (request_id, artefact_id) trùng.** Evaluator sẽ từ chối file. Sắp xếp theo `request_id, artefact_id` trước khi ghi để file giống hệt nhau giữa các lần chạy.

### 4.5 Năm bước của pipeline

| Bước | Hàm | Việc làm |
|---|---|---|
| 01 load | `load()` | Kiểm sha256 theo `manifest.csv`, gọi `load_inputs()`, ghi cảnh báo dữ liệu vào audit |
| 02 process | `process()` | Với mỗi yêu cầu: `scope_for()` rồi `decide_action()` cho từng artefact. Trả bảng `request_id, artefact_id, action, score, reason, type, lineage_path, deadline` |
| 03 rank | `rank()` | Top B theo `score`: ngoại lệ và `DERIVED_FROM_HELD` lên đầu, trong cùng mức thì deadline gần xếp trước |
| 04 review | `review()` | Đọc `review_queue_reviewed.csv`, áp override, ghi tên người duyệt vào audit |
| 05 decide | `decide()` | `GO` nếu mọi dòng `escalate` đã có người duyệt; `HOLD` nếu còn dòng chưa duyệt hoặc có cảnh báo dữ liệu. Kèm `reason_code` và `owner` |

`dry_run: true` (mặc định trong `configs/tracks/t08.yaml`) nghĩa là chỉ in kế hoạch. Khi tắt dry-run, pipeline ghi thêm `out/poc/tombstones.json` (danh sách artefact đã "xóa" giả lập). Lần chạy thứ hai đọc file này và phải cho ra `actions.csv` giống hệt.

## 5. Phân công chi tiết

Điền tên thật vào bảng này và vào `reports/team_contributions.csv` ngay phút đầu.

| | Vai trò | Sản phẩm phải có | Commit tối thiểu |
|---|---|---|---|
| **M1** (Leader) | Integrator | Bộ khung chạy exit 0; `pipeline.py` nối đủ 5 bước; `rank()` và `decide()`; merge PR; 2 tag | 3 |
| **M2** | Data & lineage | `loader.py` có kiểm schema; `lineage.py` (index, phạm vi, đường đi, tổ tiên bị hold); phát hiện dangling và vòng lặp | 3 |
| **M3** | Policy | `policy.py`; `t08_policy.yaml` có nguồn luật; chốt Q1 và Q2; ablation `hold_scope` | 3 |
| **M4** | QA & metric | `baseline.py`; bộ gold mini; tối thiểu 8 test; `metrics_baseline.json`, `metrics_poc.json`, bảng so sánh | 3 |
| **M5** | Review & report | `audit.py`; review queue và contact sheet; đóng vai người duyệt; `metric_contract.md`; `group_report.md`; slides | 3 |

Duyệt PR theo cặp: M2 và M3 duyệt cho nhau, M4 duyệt PR của M5, M5 duyệt PR của M4, M1 duyệt mọi PR chạm `pipeline.py`. Mục tiêu duyệt xong trong 5 phút.

### Việc của M4: tự dựng gold set

Repo học viên không có `gt/`, nên nhóm phải tự chứng minh kết quả. Đây cũng là tiêu chí 18 điểm "Gold set + metric rõ".

1. **Graph mini tự viết tay** tại `tests/data/t08_mini/` (khoảng 15 artefact, 3 yêu cầu), chứa đủ 6 bẫy cùng một yêu cầu chưa xác minh danh tính và một `parent_ids` trỏ sai. Đáp án viết tay trong `expected_actions.csv`.
2. **Gán nhãn độc lập trên fixture thật:** M4 và M5 mỗi người tự gán tay 2 yêu cầu (DR-004 và DR-005, khoảng 34 dòng) trước khi xem output của pipeline, rồi so với nhau và so với pipeline. Lưu tại `reports/self_check_labels.csv` và ghi tỷ lệ đồng thuận vào báo cáo.

Không đặt các file này trong `fixtures/*/gt/` vì GT guard sẽ chặn pipeline.

### Danh sách test tối thiểu (`tests/test_t08_*.py`)

| Test | Kiểm tra |
|---|---|
| `test_scope_excludes_other_subjects` | Bẫy B6: yêu cầu của subj_01 không chứa `a0012`, `a0013` |
| `test_legal_hold_never_deleted` | Không dòng nào có `legal_hold` mà action là `delete` |
| `test_multi_subject_escalated` | Frame 2 người và export nhiều người đều `escalate` |
| `test_unknown_origin_and_acl_escalated` | Bẫy B3 và B4 |
| `test_unverified_identity_escalates_all` | Dùng graph mini |
| `test_actions_unique_and_valid` | Không trùng cặp khóa; action thuộc 3 giá trị hợp lệ |
| `test_idempotent_two_runs` | Chạy 2 lần, sha256 của `actions.csv` bằng nhau |
| `test_audit_covers_every_action` | Mọi `artefact_id` trong `actions.csv` có trong audit log |
| `test_bad_input_fails_loudly` | Thiếu trường hoặc JSON hỏng thì báo lỗi rõ, không ra file rỗng |
| `test_mini_gold_exact_match` | Pipeline khớp 100% đáp án viết tay của graph mini |

## 6. Quy trình Git

### 6.1 Thiết lập một lần

M1 làm trên GitHub trước khi cả nhóm bắt đầu:

1. Mời 4 thành viên làm Collaborator với quyền Write.
2. Settings → General → Pull Requests: **tắt Squash merging**, giữ Merge commit, bật tự xóa nhánh sau khi merge. Squash làm mất tên tác giả, mà giảng viên chấm bằng `git shortlog -sne --all`.
3. Push bộ khung lên `main`, sau đó mới bật rule bảo vệ `main` (bắt buộc PR và 1 approval, cấm force push).

Mỗi thành viên làm trên máy mình:

```powershell
git clone https://github.com/nguyenloc2004/K5-Day6-L2B-DataGovernanceAndPrivacy.git
cd K5-Day6-L2B-DataGovernanceAndPrivacy
git config user.name  "Họ Tên"          # phải khớp reports/team_contributions.csv
git config user.email "email@cua.ban"
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q        # phải xanh trước khi bắt đầu
```

### 6.2 Nhánh

- `main` luôn chạy được. Không ai push thẳng, kể cả M1.
- Tên nhánh: `m<số>/<việc>`, ví dụ `m2/lineage-bfs`, `m3/policy-precedence`, `m4/baseline`.
- Mỗi nhánh làm một việc và sống tối đa 45 phút. Merge xong thì xóa, tạo nhánh mới từ `main`.

### 6.3 Vòng lặp cho mỗi việc

```powershell
git switch main; git pull
git switch -c m2/lineage-bfs
# code, commit nhỏ
git add src/t08/lineage.py
git commit -m "feat(t08-lineage): scope theo subject_ids, bỏ con cháu của người khác"
git pull --rebase origin main
.venv\Scripts\python -m pytest -q
git push -u origin m2/lineage-bfs
# mở PR, người duyệt theo cặp bấm Merge (không Squash)
```

Quy ước commit: `feat|fix|test|docs|chore(t08-<module>): <nội dung>`. Commit chỉ sửa khoảng trắng không được tính điểm.

### 6.4 Lệnh chạy trên Windows

Makefile viết cho Linux/Mac. Trên Windows gọi trực tiếp:

```powershell
# PoC
.venv\Scripts\python -m src.main --config configs/lab.yaml --track t08 --output out/poc --run-name poc --offline --seed 42
# Baseline
.venv\Scripts\python -m src.main --track t08 --pipeline src.t08.baseline --output out/baseline --run-name baseline --offline --seed 42
# Test
.venv\Scripts\python -m pytest -q
```

Trước mỗi lần chạy lấy số liệu chính thức, xóa thư mục `out/` vì `audit_log.jsonl` là file chỉ ghi nối thêm.

## 7. Lịch 240 phút

| Phút | M1 | M2 | M3 | M4 | M5 | Mốc kiểm |
|---|---|---|---|---|---|---|
| 0–15 | Sửa `lab.yaml` sang t08, push khung và stub | Cài môi trường, đọc fixture | Đọc đề, hỏi giảng viên Q1 | Cài môi trường, đọc evaluator | Bắt đầu `metric_contract.md` | Mỗi người có 1 commit; lệnh PoC exit 0 với stub |
| 15–30 | Sửa `rank()` dùng `item_id` | `loader.py` | Viết `t08_policy.yaml` | Viết graph mini và đáp án | Chốt Q3, điền xong contract | **Chốt `metric_contract.md`** và Q1–Q3 |
| 30–50 | Duyệt PR | `scope_for()`, `build_index()` | `decide_action()` luật 1, 5, 7 | `baseline.py` và test baseline | Khung `write_audit()` | **Merge 1:** có `out/baseline/actions.csv` |
| 50–90 | Nối `process()` với code thật | `lineage_path()`, `held_ancestor()` | Luật 2, 3, 4, 6 và `review_score` | 6 test đầu trong danh sách | Audit đủ trường, dry-run | **Merge 2:** PoC ra 158 dòng, test xanh |
| 90–145 | `decide()`, tombstones, sửa lỗi tích hợp | Cảnh báo dangling/cycle, hỗ trợ M4 | Ablation `hold_scope`, viết lập luận pháp lý | Test idempotency và audit; gán nhãn tay DR-004, DR-005 | Review queue, contact sheet, đóng vai người duyệt | **Merge 3:** vòng review chạy đủ, có override trong audit log |
| 145–170 | Đóng băng `pipeline.py`, chạy sạch từ đầu | 2 failure case có minh họa | Bảng ablation | Sinh `metrics_*.json` và bảng so sánh nếu có GT | Slides 3–5 trang | Clone mới chạy được bằng 3 lệnh |
| 170–180 | Tag `demo-180m` và push tag | | | | | **Tag đã lên GitHub** |
| 180–240 | Trình bày | Trả lời về lineage | Trả lời về luật | Trả lời về metric và test | Demo vòng review | |

Bốn mốc Merge là bắt buộc: đến giờ, ai cũng merge phần đã xong (miễn test xanh) rồi rebase lên `main`.

```powershell
# Phút 170
git switch main; git pull
git tag -a demo-180m -m "Demo freeze at minute 180"; git push origin demo-180m
# Trước hạn +24h
git tag -a final-24h -m "Final submission"; git push origin final-24h
```

## 8. Việc trong 24 giờ sau buổi lab

| Việc | Ai |
|---|---|
| Hoàn thiện `group_report.md` đủ 11 mục, số liệu lấy từ file script sinh ra | M5, mỗi người viết phần của mình |
| Resume sau khi job bị ngắt giữa chừng (dùng `tombstones.json`) và test | M1, M4 |
| Bảng SLA: yêu cầu nào sắp tới hạn, bao nhiêu dòng còn chờ duyệt | M2 |
| Ablation: `hold_scope`, bỏ từng luật, BFS ngây thơ | M3 |
| Điền `team_contributions.csv` với SHA commit, đối chiếu `git shortlog -sne --all` | M1 |
| Tag `final-24h` | M1 |

## 9. Đối chiếu với rubric

| Tiêu chí | Điểm | Nhóm đáp ứng bằng |
|---|---|---|
| End-to-end, đúng yêu cầu | 22 | Một lệnh chạy đủ 5 bước, exit 0, sinh `actions.csv`, `review_queue.csv`, `audit_log.jsonl`, `decision.json` |
| Gold set và metric rõ | 18 | `metric_contract.md` chốt phút 30; graph mini có đáp án; nhãn tay độc lập của 2 người |
| Baseline và so sánh | 18 | `baseline.py` cùng seed và cùng input; báo cả số xấu của baseline; thêm dòng "BFS ngây thơ" để cho thấy vì sao không xóa hết |
| Human-in-the-loop | 12 | Queue ưu tiên ngoại lệ; override có tên người duyệt; `reason_code` và `owner` ở mọi quyết định |
| Reliability | 12 | Offline, chạy sạch từ clone mới, 10 test, idempotency, 2 failure mode có phân tích |
| Report và Git | 10 | Mỗi người tối thiểu 3 commit thực chất; không squash; CSV khớp shortlog |
| Showcase và debate | 8 | Mục 10 |
| Bonus | tối đa 15 | Tag trước phút 180 (+5); ablation và graph mini làm hidden test (+5); test bắt được lỗi thật khi debate (+5) |

## 10. Chuẩn bị cho phần tranh biện

| Câu hỏi dễ gặp | Hướng trả lời |
|---|---|
| Sao không xóa hết cho chắc? | False-delete: xóa bằng chứng đang bị hold là vi phạm nghĩa vụ pháp lý; xóa frame chung là xâm phạm dữ liệu của người khác. Đưa số của dòng "BFS ngây thơ". |
| Giữ video bị hold có vi phạm quyền xóa không? | GDPR Đ.17(3) và Luật 91/2025 có ngoại lệ. Nhóm ghi mã hold, lý do, và hẹn xóa khi hết hold. |
| Sao con cháu của video bị hold vẫn xóa? | Trình bày quyết định Q1, lý do, và kết quả ablation của phương án ngược lại. Nêu rõ đây là giả định cần pháp chế xác nhận. |
| `escalate` rồi thì sao? | Vào review queue kèm deadline; người duyệt chọn che mặt, dựng lại export, hoặc xin quyền từ vendor. `decide()` trả `HOLD` khi còn dòng chưa duyệt. |
| Embedding có phải dữ liệu cá nhân không? | Có, vì vẫn nhận diện được người. Đây chính là failure mode "chỉ xóa raw" mà đề yêu cầu phân tích. |
| Kết quả có tái lập không? | Seed 42, output sắp xếp cố định, test so sha256 giữa 2 lần chạy. |

Không tuyên bố "đạt GDPR" hay "đúng luật Việt Nam". Chỉ nói "theo giả định của nhóm, cần DPO/pháp chế xác nhận".

## 11. Rủi ro và cách phòng

| Rủi ro | Dấu hiệu | Phòng |
|---|---|---|
| Đoán sai Q1 | Không biết được trước khi chấm | Hỏi giảng viên; để tham số; ghi quyết định trước eval; có ablation |
| Xóa ngoài phạm vi (B6) | Số dòng lớn hơn 158 | `test_scope_excludes_other_subjects` |
| Hard-code theo fixture | Hidden eval ra điểm thấp | Không có ID nào trong code; graph mini khác fixture vẫn qua |
| Conflict ở `pipeline.py` | PR báo conflict | Chỉ M1 sửa file này |
| Mất tên tác giả | `git shortlog` thiếu người | Tắt squash; kiểm `git config` ở commit đầu |
| Audit log bị cộng dồn | File dài bất thường | Xóa `out/` trước khi chạy lấy số chính thức |
| `make` không chạy trên Windows | Lỗi `.venv/bin/python` | Dùng lệnh ở mục 6.4 |
| Trễ mốc 180 phút | Phút 145 chưa chạy trọn vòng | Từ phút 145 chỉ sửa lỗi, không thêm tính năng |

## 12. Định nghĩa "xong"

- [ ] Clone mới, cài môi trường, chạy lệnh PoC ra exit 0 khi không có mạng.
- [ ] `actions.csv` có 158 dòng trên fixture, không trùng khóa, action hợp lệ.
- [ ] Không artefact nào có `legal_hold` bị `delete`; không dòng nào nằm ngoài phạm vi subject.
- [ ] Mọi dòng có bản ghi audit với `item_id = artefact_id`, `reason_code`, đường đi lineage.
- [ ] Chạy 2 lần cho `actions.csv` giống hệt.
- [ ] `pytest -q` không có test fail; nhóm có tối thiểu 10 test riêng.
- [ ] Graph mini khớp đáp án 100%.
- [ ] Có baseline, bảng so sánh, 2 failure case, review queue đã có người duyệt, `decision.json`.
- [ ] `metric_contract.md` chốt trước khi chạy eval; `group_report.md` đủ 11 mục.
- [ ] 5 người đều có commit thực chất; `team_contributions.csv` khớp `git shortlog -sne --all`.
- [ ] Tag `demo-180m` và `final-24h` đã push lên GitHub.
