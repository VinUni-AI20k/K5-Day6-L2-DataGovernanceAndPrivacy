# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Mọi con số dưới đây lấy từ file do script sinh ra: `reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`,
> `reports/t08_selfcheck.md`, `reports/evidence_t08/`. Toàn bộ dữ liệu là MOCK, không có gì thật bị xóa.
> **Các metric được tính trên gold set do nhóm tự gán nhãn, không phải GT của giảng viên** (repo học viên không có `gt/`).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G00 — **TODO: điền mã nhóm thật** (cũng sửa trong `configs/lab.yaml`) |
| Challenge | T08 · Retention & Delete Request Simulator |
| Thành viên + vai trò | 1. Lam TherK (Lead/Integrator, policy, test, review, report) · **TODO: bổ sung thành viên khác nếu có** |
| Git URL | https://github.com/doantunglam/K5-Day6-L2-DataGovernanceAndPrivacy (nhánh `t08-work`) |
| Tag `demo-180m` (commit) | chưa tạo — xem lệnh ở mục 08 |
| Tag `final-24h` (commit) | chưa tạo — xem lệnh ở mục 08 |
| Deadline (giờ VN) | **TODO** |

## 01 · Problem statement

- **Ai bị ảnh hưởng khi hệ thống sai?** (1) Người gửi yêu cầu xóa: nếu chỉ xóa file gốc mà còn backup và embedding thì họ
  vẫn bị nhận diện. (2) Người thứ ba xuất hiện chung trong frame hoặc export: bị mất dữ liệu dù không yêu cầu. (3) Tổ chức:
  xóa dữ liệu đang bị legal hold là vi phạm nghĩa vụ lưu giữ và không hoàn tác được.
- **Điểm nghẽn:** dữ liệu của một người nằm rải ở 7 loại artefact trên 6 kho (`raw`, `glacier`, `lake`, `vector-db`,
  `labels`, `exports`); chỉ raw và backup có `filename`, phần còn lại chỉ nối với nhau qua `parent_ids`.
- **Đầu vào → đầu ra:** `data_graph.json` (212 artefact) + `requests.json` (10 yêu cầu) → `actions.csv` (một hành động cho
  mỗi cặp yêu cầu–artefact) + `audit_log.jsonl` + hàng chờ ngoại lệ + bằng chứng xóa mock + `decision.json`.
- **Tiêu chí GO / HOLD / REWORK** (chốt trong `reports/metric_contract.md` trước khi chạy): REWORK khi kiểm tra toàn vẹn
  thất bại; HOLD khi còn ngoại lệ chưa có người duyệt; GO khi mọi ngoại lệ đã duyệt, mọi lệnh xóa đã thực thi và tồn dư = 0.
- **Giả định cần DPO/legal xác nhận:** A1 legal hold trên raw bao trùm cả bản sao và dữ liệu dẫn xuất; A2 export gộp nhiều
  người thì không xóa cả file vì một người; A3 artefact chung mà mọi chủ thể đều yêu cầu thì được xóa sau khi có người xác nhận.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev = eval (fixture không chia split, `split=na`) | 212 artefact, 10 yêu cầu → 158 cặp trong phạm vi | `fixtures/t08_deletion/` (`synthetic:tools/make_fixtures.py`, seed 42) | CC0-1.0 | Có, 100% |
| hidden eval | không rõ | giảng viên giữ | — | — |

- **Schema:** artefact có `artefact_id, type, subject_ids, parent_ids, uri, owner, acl, legal_hold, origin_known, created_at`
  (raw và backup thêm `filename`). Loại: raw_video 15, backup 15, frame 45, face_crop 45, embedding 45, annotation 45,
  **training_export 2** (mỗi export gộp 9–10 chủ thể, 12 parent).
- **Seed:** 42. Pipeline thuần luật, không có bước ngẫu nhiên. Không chia split vì không huấn luyện hay tune gì.
- **`manifest.csv` verified (sha256):** có. Pipeline kiểm ở bước load và dừng (exit 2) nếu hash lệch; có test
  `test_tampered_input_fails_provenance_check`.
- **Dữ liệu thật:** không dùng.
- **Các tình huống cài sẵn nhóm tìm được:** legal hold trên raw `a0043` (LH-2026-03) và `a0099` (LH-2026-07); 3 embedding
  `a0075/a0079/a0083` không rõ nguồn; backup `a0156` thuộc `vendor-x`; 4 cặp frame+annotation chung hai người, trong đó
  `a0067/a0070` và `a0123/a0126` được **cả hai** chủ thể yêu cầu xóa; 2 export gộp nhiều người, cả hai đều lấy nguồn một
  phần từ dữ liệu đang bị hold.

## 03 · Research & design

- **Vì sao chọn kỹ thuật này:** bài toán là truy vết trên đồ thị và áp luật có thứ tự, không cần mô hình học máy. Duyệt đồ thị
  (BFS theo `parent_ids`) cho độ phủ; bảng luật có thứ tự ưu tiên cho tính giải thích được: mỗi quyết định có đúng một
  `reason_code`. Đề bài gợi ý thứ tự "legal hold > permission > multi-subject > delete"; nhóm giữ thứ tự đó và thêm các
  nhánh cho những ca đề không nói rõ.
- **Data flow:**

```
requests.json + data_graph.json
   │ 01 load     kiểm sha256, chuẩn hóa yêu cầu
   ▼
 02 process   phạm vi = artefact gắn tên người yêu cầu + con cháu → áp 10 luật → dry_run_plan.csv
   ▼
 03 rank      mọi cặp không phải delete → review_queue.csv + contact_sheet.html (ưu tiên theo loại ngoại lệ, rồi deadline)
   ▼
 04 review    review_queue_reviewed.csv → override + audit; chặn duyệt lệch giữa hai yêu cầu
   ▼
 05 decide    xóa mock (tombstone) → deletion_evidence.json, request_summary.csv → decision.json (GO/HOLD/REWORK)
```

- **Thành phần offline:** chỉ pandas và thư viện chuẩn; không có model, không gọi mạng.
- **Trade-off đã cân nhắc:**
  1. *Kế thừa legal hold.* Trong dữ liệu chỉ raw có cờ hold; con cháu có `legal_hold = null`. Nhóm chọn giữ cả con cháu vì
     hai kiểu sai không cân xứng: giữ thừa thì xóa bù được ở lần sau, xóa nhầm thì không lấy lại được (số liệu ở mục 06).
  2. *Kế thừa "toàn phần" và "một phần".* Artefact có **mọi** parent bị giữ thì `retain_legal_hold`; chỉ **một phần** parent
     bị giữ (hai export) thì `escalate`. Nếu coi "có bất kỳ tổ tiên nào bị giữ" là bị giữ thì lệnh hold của subj_03 sẽ khóa
     luôn export của 9 người khác.
  3. *Lineage không phải quyền sở hữu.* Frame `a0011` chụp subj_00 và subj_01, nhưng crop `a0012` cắt từ nó chỉ là mặt
     subj_00. Truy lineage từ yêu cầu của subj_01 sẽ gặp `a0012`; máy chỉ gắn `escalate` để người kiểm tra nhãn, không xóa.
  4. *Máy không tự xóa artefact chung*, kể cả khi mọi chủ thể đều yêu cầu; việc đó cần người xác nhận (mục 07).

## 04 · Baseline vs PoC

- **Baseline** (`src/baseline_t08.py`, commit `7ae6c80`): đúng mô tả trong đề — với mỗi yêu cầu, xóa một raw video có
  `filename` chứa `subject_id`; không tìm backup hay dữ liệu dẫn xuất, không kiểm tra ngoại lệ.
- **PoC** (`src/pipeline.py` + `src/t08_policy.py` + `src/t08_mock_store.py`, commit `7ae6c80`; tham số trong
  `configs/lab.yaml`): lineage + 10 luật có thứ tự + hàng chờ người duyệt + xóa mock idempotent.
- **Cùng input, cùng seed 42, cùng gold:** xác nhận. Cả hai cùng dùng hàm `load()` nên cùng qua bước kiểm sha256.

**Bảng 1 · Baseline vs PoC** — output của `python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`
(PoC ở đây là bản **máy tự chạy, chưa có người duyệt**, tức đúng cái tái lập được từ một clone sạch):

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: **Deletion Completeness** (cặp phải xóa đã xóa / cặp phải xóa) | 0.0727 (8/110) | 0.9273 (102/110) | +0.8545; higher; N = 158 cặp |
| False-delete count (mục tiêu 0) | 2 | 0 | −2; lower. Baseline xóa 2 raw đang bị legal hold |
| Exception handling accuracy | 0.0000 (0/48) | 1.0000 (48/48) | baseline = 0; higher |
| Audit trace completeness | 1.0000 (10/10) | 1.0000 (164/164) | bằng nhau; higher |
| Review@B | không có hàng chờ | 62 cặp vào hàng chờ | B = 100, không cắt bớt |
| Runtime / 100 items | 0.9630 s | 0.2604 s | baseline chỉ có 10 dòng nên bị chi phối bởi thời gian khởi động; tổng thời gian chạy là 0.10 s so với 0.43 s |

Sau vòng người duyệt (`reports/metrics_poc_reviewed.json`): Completeness 1.0000 (110/110), False-delete 0, Exception accuracy
1.0000 (48/48). Con số này phụ thuộc quyết định của người duyệt ở mục 07 và giả định A3.

## 05 · Evaluation protocol

- **Công thức:** xem `reports/metric_contract.md`. Đơn vị là cặp `(request_id, artefact_id)`, ghép chính xác theo khóa. Cặp
  bỏ sót tính là chưa xóa. Dòng `delete` cho cặp ngoài gold tính là xóa nhầm.
- **Gold set:** `reports/t08_selflabel.csv`, 158 cặp = toàn bộ cặp mà người yêu cầu có trong `subject_ids` (110 delete,
  28 retain_legal_hold, 20 escalate). Gán nhãn tay bằng danh sách id tường minh, **trước** lần chạy PoC đầu tiên: commit
  `b8a9549` (17:15) đứng trước commit PoC `7ae6c80` (17:23). Không sửa nhãn sau đó.
- **Ngưỡng / budget:** không có ngưỡng số; B = 100; thứ tự luật đóng băng cùng lúc với gold.
- **Độ bất định:** Wilson 95% CI — Completeness của PoC 0.863–0.963, của baseline 0.037–0.137; Exception accuracy của PoC
  0.926–1.000 (N = 48). Bất định lớn hơn nằm ở **nhãn**, không phải ở cỡ mẫu: gold do chính nhóm gán và dùng chung giả
  định với policy, nên nó đo được lỗi cài đặt chứ không chứng minh được giả định đúng. Vì vậy nhóm chấm lại theo 4 kịch bản
  gán nhãn (mục 06).
- **Lệnh evaluate:**
  `python -m src.evaluate --track t08 --gt reports/t08_selflabel.csv --pred out/poc/actions.csv --run-name poc --out reports/metrics_poc.json`
  Giảng viên chấm chính thức bằng cùng lệnh, bỏ `--gt` (sẽ ghi đè file metric bằng số theo GT thật).

## 06 · Result slices

Trích `reports/t08_selfcheck.md` (số cặp xử lý đúng nhãn / số cặp):

| Slice | N | Baseline | PoC (máy) | PoC + review | Ghi chú |
|---|---|---|---|---|---|
| own_single (phải xóa) | 102 | 8 | 102 | 102 | baseline chỉ trúng raw của 8 người không bị hold |
| legal_hold_direct | 2 | 0 | 2 | 2 | baseline xóa nhầm cả 2 |
| legal_hold_inherited | 26 | 0 | 26 | 26 | phụ thuộc giả định A1 |
| multi_subject_all_requested (gold = delete) | 8 | 0 | 0 | 8 | máy cố ý không tự xóa; người duyệt quyết |
| multi_subject_one_requester | 4 | 0 | 4 | 4 | |
| export_multi_subject | 12 | 0 | 12 | 12 | |
| unknown_origin | 3 | 0 | 3 | 3 | |
| no_permission | 1 | 0 | 1 | 1 | |

**Độ nhạy theo giả định gán nhãn** (Completeness / False-delete / Exception accuracy):

| Kịch bản nhãn | Baseline | PoC (máy) | PoC + review | Biến thể không kế thừa hold |
|---|---|---|---|---|
| S0: như đã gán | 0.073 / 2 / 0.000 | 0.927 / 0 / 1.000 | 1.000 / 0 / 1.000 | 0.927 / **26** / 0.458 |
| S1: hold không kế thừa | 0.059 / 2 / 0.000 | 0.750 / 0 / 1.000 | 0.809 / 0 / 1.000 | 0.941 / 0 / 1.000 |
| S2: artefact chung luôn phải escalate | 0.078 / 2 / 0.000 | 1.000 / 0 / 1.000 | 1.000 / **8** / 0.857 | 1.000 / **26** / 0.536 |
| S3: S1 + S2 | 0.062 / 2 / 0.000 | 0.797 / 0 / 1.000 | 0.797 / **8** / 0.733 | 1.000 / 0 / 1.000 |

Đọc bảng: PoC bản máy giữ **False-delete = 0 ở cả 4 kịch bản**; cái giá là Completeness có thể xuống 0.750 nếu GT của giảng
viên không kế thừa hold. Đây là kết quả bất lợi cần báo: nếu S1 đúng thì PoC còn nợ 26–34 lệnh xóa. Ngược lại, bản sau review
sẽ có 8 lần xóa nhầm nếu S2 đúng — rủi ro này đến từ quyết định của người duyệt, không phải của máy.

**Ablation** (không có người duyệt): bỏ dòng cho dữ liệu dẫn xuất của người khác (V2) không đổi metric nào (158 thay vì
164 dòng); "xóa hết những gì lineage tìm thấy" (V3) đạt Completeness 1.000 nhưng xóa nhầm **54** cặp.

- **Failure case 1 — chỉ xóa raw, còn bản sao và embedding.** Với DR-001 (subj_01) baseline xóa `a0015`
  (`drive_subj_01_001.mp4`) và dừng. Còn lại: backup `a0016` (`mock://glacier/backup/a0016`), 3 frame, 3 face crop, 3 annotation
  và 3 embedding `a0019/a0023/a0027` trong `vector-db`. Trên toàn bộ 10 yêu cầu baseline để lại **30/30** embedding của người
  yêu cầu, trong đó 21 cái phải xóa; PoC còn 9/30 và cả 9 đều có lý do (6 thuộc lineage bị hold, 3 không rõ nguồn).
  *Root cause:* baseline tìm theo `filename`, mà chỉ raw và backup có trường này (backup lại có đuôi `.bak` và nằm ở kho khác);
  dữ liệu dẫn xuất chỉ nối bằng `parent_ids`, nên không duyệt đồ thị thì không thấy.
- **Failure case 2 — xóa nhầm dữ liệu thuộc ngoại lệ.** Baseline xóa `a0043` (LH-2026-03) và `a0099` (LH-2026-07).
  *Root cause:* không đọc `legal_hold` trước khi hành động. Một policy có kiểm tra cờ này vẫn sai theo kiểu tinh vi hơn: backup
  `a0044` của `a0043` có `legal_hold = null`, vì cờ hold chỉ nằm trên artefact gốc và không được chép xuống bản sao. Kiểm tra
  từng artefact riêng lẻ (biến thể V1) sẽ xóa 26 cặp như vậy nếu hold có kế thừa. Tương tự, V3 xóa `a0012` — mặt của subj_00 —
  theo yêu cầu của subj_01, vì nhầm "dẫn xuất từ" thành "thuộc về".
- **Giới hạn của chính PoC:** 8 cặp artefact chung không được tự xóa (cần người); 9 embedding định danh vẫn tồn tại hợp lệ
  nhưng người yêu cầu phải được thông báo.
- **Latency / compute:** PoC 0.43 s cho 164 cặp (≈ 2.6 ms/cặp), Windows 11, AMD64 Family 25 Model 97, Python 3.13.1, không GPU.

## 07 · Human & decision

- **Review queue:** `out/<run>/review_queue.csv` + `contact_sheet.html` (có nút Export CSV). Vào hàng chờ là **mọi** cặp máy
  không gắn `delete`: 62 cặp, B = 100. Ưu tiên theo loại ngoại lệ (việc người gỡ được ngay và việc phải chờ bên ngoài lên
  trước), rồi theo deadline của yêu cầu.
- **Override + audit:** người duyệt điền `reviewer`, `reviewer_decision`, `override_value`, lưu thành
  `review_queue_reviewed.csv` trong thư mục output rồi chạy lại. Mỗi dòng đã duyệt sinh một entry audit có người duyệt,
  hành động trước/sau và ghi chú (`override:edit` nếu đổi, `review:approve` nếu giữ). Chốt chặn: giá trị override lạ → dừng
  (exit 2); đổi artefact **đang mang cờ legal hold** thành `delete` → dừng; quyết định dựa trên kế hoạch cũ → bỏ qua và ghi
  log; chỉ duyệt xóa ở một phía của artefact chung → lệnh xóa bị hạ về `escalate` (`CONFLICTING_ACTIONS`).
- **Bảng review** (đầy đủ 62 dòng: `reports/review_queue.csv`; log: `reports/evidence_t08/audit_log.jsonl`):

| Request → artefact | Ngoại lệ | Người duyệt | Hành động cuối & log |
|---|---|---|---|
| DR-003, DR-004 → `a0067`, `a0070`; DR-006, DR-007 → `a0123`, `a0126` (8 cặp) | MULTI_SUBJECT_ALL_REQUESTED | Lam TherK | `edit` → **delete**; 8 entry `override:edit` |
| DR-008 → `a0156` | NO_PERMISSION (vendor-x) | Lam TherK | giữ `escalate`: mở yêu cầu xóa với vendor |
| DR-004 → `a0075`, `a0079`, `a0083` | UNKNOWN_ORIGIN | Lam TherK | giữ `escalate`: data steward truy nguồn |
| DR-001 → `a0011`, `a0014`; DR-009 → `a0179`, `a0182` | MULTI_SUBJECT | Lam TherK | giữ `escalate`: che người yêu cầu, không xóa |
| 9 yêu cầu → `a0211`, `a0212` (12 cặp) | PARTIAL_LEGAL_HOLD (export gộp) | Lam TherK | giữ `escalate`: dựng lại export |
| DR-002, DR-005 → 26 artefact dẫn xuất | LEGAL_HOLD_INHERITED | Lam TherK | giữ `retain_legal_hold` theo A1 |
| DR-002 → `a0043`; DR-005 → `a0099` | LEGAL_HOLD | Lam TherK | giữ `retain_legal_hold`, xóa khi hết hold |
| DR-001 → `a0012`, `a0013`; DR-004 → `a0068`, `a0069`; DR-007 → `a0124`, `a0125` | DERIVED_OTHER_SUBJECT | Lam TherK | giữ `escalate`: không phải dữ liệu của người yêu cầu |

- **Decision:** lần chạy đầu `HOLD / EXCEPTIONS_PENDING_REVIEW` (62/62 chưa duyệt); sau review
  `GO / PLAN_EXECUTED_EXCEPTIONS_TRACKED` — 110 delete, 28 retain_legal_hold, 26 escalate; 106 artefact đã xóa mock, tồn dư 0.
  Owner: Lam TherK. Lịch sử trong `reports/decision_log.csv`.
- **Trạng thái từng yêu cầu** (`reports/evidence_t08/request_summary.csv`): chỉ DR-006 hoàn tất 100%; 9 yêu cầu còn lại ở
  trạng thái `PARTIAL_EXCEPTIONS_OPEN` và còn 21–30 ngày đến hạn (tính từ ngày nhận yêu cầu cuối cùng, 2026-11-10;
  đổi mốc bằng tham số `as_of`). GO ở đây nghĩa là "đợt xử lý chạy đúng và mọi việc còn mở
  đều có người phụ trách", **không** phải "mọi yêu cầu đã được đáp ứng xong".
- **Idempotency và resume:** chạy lại cùng thư mục cho `actions.csv` và `mock_store_state.json` giống từng byte,
  `newly_deleted = 0`. Lần chạy sau review chỉ xóa thêm 4 artefact mới được duyệt (102 cái cũ là no-op).

## 08 · Reproduce & tests

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt     # macOS/Linux: make setup
# baseline và PoC (máy tự chạy)
python -m src.main --track t08 --pipeline src.baseline_t08 --output out/baseline --run-name baseline --offline --seed 42
python -m src.main --config configs/lab.yaml --track t08 --output out/poc --run-name poc --offline --seed 42
# PoC + quyết định của người duyệt đã lưu trong repo
mkdir -p out/poc_reviewed && cp reports/review_queue.csv out/poc_reviewed/review_queue_reviewed.csv
python -m src.main --config configs/lab.yaml --track t08 --output out/poc_reviewed --run-name poc_reviewed --offline --seed 42
# chấm trên gold tự gán + báo cáo tự kiểm
python -m src.evaluate --track t08 --gt reports/t08_selflabel.csv --pred out/baseline/actions.csv --run-name baseline --out reports/metrics_baseline.json
python -m src.evaluate --track t08 --gt reports/t08_selflabel.csv --pred out/poc/actions.csv --run-name poc --out reports/metrics_poc.json
python -m src.evaluate --track t08 --gt reports/t08_selflabel.csv --pred out/poc_reviewed/actions.csv --run-name poc_reviewed --out reports/metrics_poc_reviewed.json
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
python -m tools.t08_selfcheck
pytest -q
# nộp bài
git tag -a demo-180m -m "Demo freeze at minute 180" && git tag -a final-24h -m "Final submission"
git push origin t08-work --follow-tags
```

- **`pytest`:** 73 passed, 39 skipped (39 test bị skip đều cần `gt/` của giảng viên). Nhóm thêm 26 test: 14 test luật
  (`tests/test_t08_policy.py`) và 12 test E2E (`tests/test_t08_pipeline.py`), gồm cả ca thành công lẫn ca lỗi.
- **Máy:** Windows 11 (10.0.26300), AMD64 Family 25 Model 97, Python 3.13.1 · git sha của các lần chạy: `1af063c`.

## 09 · Limitations & ethics

- **Không phải tư vấn pháp lý.** Nhóm không tuyên bố hệ thống "đạt GDPR" hay "đạt luật Việt Nam". Các giả định A1–A5 là lựa
  chọn kỹ thuật theo hướng thận trọng và phải được DPO/legal xác nhận trước khi dùng thật; đặc biệt là phạm vi của legal hold.
- **Điều chưa biết:** GT của giảng viên xử lý thế nào với (a) con cháu của raw bị hold, (b) artefact chung khi mọi chủ thể đều
  yêu cầu, (c) cặp "dẫn xuất nhưng không gắn tên người yêu cầu". Mục 06 cho biết PoC lệch bao nhiêu trong từng trường hợp.
- **False alarm:** 6 cặp DERIVED_OTHER_SUBJECT gần như chắc chắn không cần hành động; chúng tốn công người duyệt.
  26 cặp kế thừa hold sẽ là giữ thừa nếu A1 sai.
- **Giới hạn kỹ thuật:** tin hoàn toàn vào `subject_ids` và `parent_ids` (nhãn sai thì kết quả sai); chỉ mô phỏng xóa, chưa
  nói gì về xóa thật trên backup lạnh hay trên model đã huấn luyện từ export; chưa có bước gửi thông báo cho người yêu cầu
  và cho bên nhận dữ liệu; `escalate` chưa có vòng đời (ai đóng, khi nào).
- **Lỗi tìm thấy ở hạ tầng chấm:** `eval_t08` đọc `audit_log.jsonl` bằng encoding mặc định của hệ điều hành. Trên Windows
  (cp1252) một ghi chú tiếng Việt lưu UTF-8 làm evaluator dừng với `UnicodeDecodeError` (đã tái hiện). Nhóm không sửa code
  metric; pipeline chuẩn hóa mọi entry audit về ASCII và có test cho việc này. Hệ quả: ghi chú của người duyệt mất dấu
  trong audit log.
- **Scale 10×:** thuật toán tuyến tính theo số cặp, nhưng hàng chờ 62 cặp cho 10 yêu cầu sẽ thành hàng trăm; cần gộp duyệt
  theo artefact hoặc theo lệnh hold thay vì theo từng cặp.
- **Kế hoạch cải tiến:** duyệt theo nhóm; vòng đời cho escalation kèm nhắc hạn; lịch tự xóa khi hold được gỡ; yêu cầu xóa
  lan sang vendor và sang các bản export đã phát hành.

## 10 · Team contribution

**Bảng 2** (đối chiếu `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA | Trình bày? |
|---|---|---|---|---|
| Lam TherK | Lam TherK <dtlam122003@gmail.com> | Cấu hình, metric contract + gold, baseline, policy, pipeline, test, review, report | `619e058`, `b8a9549`, `7ae6c80`, `c67289e`, `1af063c` và commit report | **TODO** |
| **TODO: thành viên khác** | | | | |

Công cụ hỗ trợ: code và báo cáo được soạn cùng trợ lý AI (Claude Code); các commit có dòng `Co-Authored-By`.

## 11 · References

| Nguồn | Ngày xem | Ý nghĩa với bài |
|---|---|---|
| GDPR, Điều 17 (quyền xóa) và 17(3) (ngoại lệ) — https://eur-lex.europa.eu/eli/reg/2016/679/oj | **TODO** (chưa mở được trong lúc làm bài) | Quyền xóa không tuyệt đối: không áp dụng khi phải giữ dữ liệu theo nghĩa vụ pháp lý hoặc để phục vụ khiếu kiện → căn cứ cho `retain_legal_hold`. |
| GDPR, Điều 19 (thông báo cho bên nhận dữ liệu) — cùng link | **TODO** | Bên kiểm soát phải báo việc xóa cho các bên đã nhận dữ liệu → căn cứ để `escalate` bản sao ở `vendor-x` thay vì bỏ qua. |
| Data Cards Playbook — https://sites.research.google/datacardsplaybook/ | 2026-11-14 | Bộ công cụ ghi chép minh bạch về dataset; gợi ý việc ghi nguồn gốc và lineage ngay trong metadata, thứ mà pipeline này dựa vào. |
| Luật 91/2025 và Nghị định 356/2025 (Việt Nam) — được dẫn trong `docs/tracks/T08.md` | chưa đọc văn bản gốc | Nhóm chỉ dùng nguyên tắc đề bài nêu: quyền xóa có ngoại lệ. Không trích điều khoản cụ thể. |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật. *(link đã có; tag chưa tạo)*
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên. *(mới có 1 thành viên)*
