# BẢNG PHÂN CÔNG VAI TRÒ & KẾ HOẠCH TRIỂN KHAI TRACK T03 (SYNTHETIC-VS-REAL)
**Dự án:** Field-to-Release PoC (AI20K · Data Track)  
**Quy mô nhóm:** 6 thành viên  
**Track:** T03 · Synthetic-vs-Real: Tạo và kiểm dữ liệu khó  

---

## 1. BẢNG PHÂN NHIỆM CHI TIẾT 6 THÀNH VIÊN THEO CẤU TRÚC THƯ MỤC

| Thành viên | Tên Role | File & Thư mục sở hữu chính | Nhiệm vụ kỹ thuật cụ thể (Code & Deliverables) | Bằng chứng Commit & Output |
|---|---|---|---|---|
| **Member 1** | **Tech Lead & Pipeline Integrator** | • `src/main.py`<br>• `src/pipeline.py` (hàm `run()`)<br>• `configs/lab.yaml`<br>• `configs/tracks/t03.yaml`<br>• `Makefile`, `run.sh` | 1. Cập nhật `configs/lab.yaml` trỏ `track: t03`, `input: fixtures/t03_synthetic`.<br>2. Điều phối luồng 5 bước E2E trong `pipeline.py` đảm bảo exit code `0`.<br>3. Kiểm soát cờ `--offline` và `--seed 42` theo đúng Contract.<br>4. Quản lý Git repository, giải quyết merge conflicts, tạo tag `demo-180m` và `final-24h`. | • Commit cấu hình cấu trúc lab & wiring E2E.<br>• Thẻ git: `demo-180m`, `final-24h`. |
| **Member 2** | **Data Governance & Provenance Specialist** | • `fixtures/t03_synthetic/`<br>• `tools/verify_manifests.py`<br>• `src/common/manifest.py`<br>• `src/common/offline.py`<br>• `src/common/gt_guard.py` | 1. Xác thực tính toàn vẹn của 30 ảnh gốc và 45 ảnh test qua SHA256 (`make verify`).<br>2. Kiểm soát GT Guard, ngăn chặn mọi hành vi đọc lén `fixtures/t03_synthetic/gt/`.<br>3. Chuẩn hóa schema xuất khẩu file `out/transform_manifest.csv` đạt **Provenance Completeness = 100%** (chuẩn PROV-O/Croissant).<br>4. Tiền xử lý và lập chỉ mục `objects.csv` phục vụ kiểm tra bbox. | • Commit kịch bản xác thực SHA256 & Provenance Manifest.<br>• File: `out/transform_manifest.csv`. |
| **Member 3** | **Synthetic Generator & Baseline Engineer** | • `src/common/corruptions.py`<br>• `src/pipeline_baseline.py`<br>• `src/examples/random_baseline.py` | 1. Xây dựng module sinh dữ liệu synthetic trên 20 ảnh `dev` (night, glare, fog, blur các mức severity 0–2).<br>2. Lập trình mô hình **Baseline**: Bộ phân loại ngẫu nhiên hoặc rule đơn giản (Laplacian/độ sáng) không kiểm tra bbox và không lưu lineage.<br>3. Chạy baseline, xuất file `out/baseline/qc.csv` và đo lường metric đối chứng.<br>4. Đảm bảo toàn bộ quá trình biến đổi ảnh tuân thủ nghiêm ngặt seed cố định (`seed=42`). | • Commit mã nguồn Baseline và Synthetic Generator.<br>• File: `out/baseline/qc.csv`, `reports/metrics_baseline.json`. |
| **Member 4** | **Quality Gate Algorithm Engineer (Core PoC)** | • `src/pipeline.py` (hàm `process()`)<br>• `src/common/image_ops.py` | 1. Hiện thực thuật toán **Quality Gate tự động**: <br>   - *Dò tâm lóa (Glare Detection)*: Tìm toạ độ cực đại cường độ sáng, đối chiếu xem có nằm trong bbox của `objects.csv` không.<br>   - *Dò xóa vật thể (Erase Detection)*: Đo phương sai màu sắc/cạnh trong vùng bbox; nếu là mảng xám/đơn sắc mà nhãn còn tồn tại $\rightarrow$ bắt lỗi `object_removed_label_kept`.<br>   - *Ước lượng Severity*: Đo suy giảm SSIM, độ tương phản và Laplacian để xác định severity == 2.<br>2. Xuất `pred_unusable` (0/1) và tính điểm nghi ngờ `score`. | • Commit thuật toán Quality Gate trong `process()`.<br>• File: `out/qc.csv` đạt F1 cao trên tập holdout. |
| **Member 5** | **Human-in-the-Loop & Decision Officer** | • `src/pipeline.py` (`rank`, `review`, `decide`)<br>• `src/common/review.py`<br>• `src/common/contact_sheet.py`<br>• `src/common/decision.py` | 1. Hiện thực hàm `rank()` trích xuất top-10 ảnh nghi ngờ nhất vào `out/review_queue.csv`.<br>2. Cấu hình `contact_sheet.py` sinh giao diện lưới HTML offline hiển thị Before (gốc) vs After (biến đổi) kèm bbox.<br>3. Xử lý cơ chế nạp file `review_queue_reviewed.csv`, áp dụng ghi đè (overrides) và ghi log kiểm toán bất biến `out/audit_log.jsonl`.<br>4. Thiết lập chính sách quyết định: Ban hành **GO** khi tỷ lệ unusable đạt chuẩn và provenance đầy đủ; ngược lại ra lệnh **HOLD / REWORK**. | • Commit module HITL, Contact Sheet & Decision Policy.<br>• File: `out/contact_sheet.html`, `out/decision.json`, `out/audit_log.jsonl`. |
| **Member 6** | **QA, Benchmarking & Reporting Lead** | • `tests/test_t03.py`<br>• `reports/group_report.md`<br>• `reports/metric_contract.md`<br>• `reports/team_contributions.csv`<br>• `demo/` | 1. Viết ít nhất $\ge 2$ bài kiểm thử tự động trong `tests/test_t03.py` (kiểm tra hợp lệ schema và logic phát hiện lóa). Đảm bảo `pytest -q` đạt 0 failed.<br>2. Thực hiện benchmark so sánh tự động qua `python -m src.compare` sinh ra `reports/table1_baseline_vs_poc.md`.<br>3. Hoàn thiện báo cáo kỹ thuật `reports/group_report.md`, tài liệu hóa 2 Failure Cases và khoảng cách sim-to-real gap.<br>4. Soạn 3–5 slide demo trong `demo/` và chuẩn bị kịch bản bảo vệ tranh biện (Adversarial Debate). | • Commit test suite tự động và tài liệu báo cáo.<br>• File: `reports/group_report.md`, `reports/table1_baseline_vs_poc.md`, slide demo. |

---

## 2. MA TRẬN TRÁCH NHIỆM RACI (T03)

* **R (Responsible):** Người trực tiếp thực hiện công việc.
* **A (Accountable):** Người chịu trách nhiệm phê duyệt cuối cùng.
* **C (Consulted):** Người được tham vấn chuyên môn.
* **I (Informed):** Người được thông báo kết quả.

| Hạng mục công việc / Giai đoạn | M1 (Lead) | M2 (Data) | M3 (Gen/Base) | M4 (Core Alg) | M5 (HITL) | M6 (QA/Rep) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| 1. Khởi tạo repo, config `lab.yaml`, preflight | **A / R** | C | I | I | I | I |
| 2. Kiểm tra SHA256 manifest & GT Guard | A | **R** | I | C | I | C |
| 3. Chốt Metric Contract (`reports/metric_contract.md`) | A | C | I | C | I | **R** |
| 4. Xây dựng Baseline & chạy đối chứng | A | I | **R** | C | I | C |
| 5. Phát triển thuật toán Quality Gate (`process()`) | A | C | C | **R** | C | C |
| 6. Xây dựng Review Queue & Contact Sheet HTML | A | I | I | C | **R** | I |
| 7. Thiết lập Decision Policy (GO/HOLD/REWORK) | C | I | I | C | **R** | A |
| 8. Viết Unit tests (`tests/test_t03.py`) | A | C | I | C | I | **R** |
| 9. Benchmark so sánh Baseline vs PoC | A | I | C | C | I | **R** |
| 10. Hoàn thiện Group Report & Đóng băng Demo (180m) | A | C | C | C | C | **R** |

---

## 3. TIẾN TRÌNH THỰC THI 240 PHÚT CỦA TỪNG THÀNH VIÊN

```
Phút       M1 (Lead)       M2 (Data)       M3 (Gen/Base)     M4 (Core Alg)       M5 (HITL)        M6 (QA/Rep)
00-10   Setup lab.yaml   Check SHA256    Commit vai trò    Commit vai trò     Commit vai trò    Metric Contract
10-30   Wiring luồng 5b  Lock GT Guard   Tạo pipeline_base Bóc tách bbox      Thiết kế Queue    Viết tests khởi tạo
30-60   Test CLI offline Audit originals Chạy baseline     Dò tâm lóa Glare   Tạo contact_sheet Test F1 evaluator
60-145  Tích hợp PoC     Build manifest  Sinh dev mix      Dò mảng xóa Erase  Duyệt override    Chạy src.compare
145-170 Chạy E2E eval    Check provenance Kiểm tra seed 42 Hoàn thiện F1      Ghi audit_log     Viết Group Report
170-180 Tag demo-180m    Freeze data     Freeze baseline   Freeze algorithm   Freeze decision   3-5 Slide demo
180-240 Showcase demo    Showcase data   Phản biện         Phản biện kỹ thuật Phản biện HITL    Thuyết trình
+24h    Tag final-24h    Lưu trữ hash    Tài liệu hóa      Clean code         Audit log cuối    Nộp report.md
```

---

## 4. BỘ LỆNH THỰC THI CHUẨN DÀNH CHO CẢ NHÓM

### Lệnh của Member 1 & 2 (Kiểm tra môi trường và dữ liệu):
```bash
# Cài đặt môi trường
make setup
# Kiểm tra offline và mã hash manifest
python -m tools.preflight
python -m tools.verify_manifests
```

### Lệnh của Member 3 (Chạy Baseline đối chứng):
```bash
python -m src.main --track t03 --pipeline src.pipeline_baseline --output out/baseline --run-name baseline --offline
```

### Lệnh của Member 4, 5 & 1 (Chạy PoC chính thức):
```bash
python -m src.main --track t03 --output out/poc --run-name poc --offline
```

### Lệnh của Member 6 & 1 (Đánh giá, Test và Đóng băng demo):
```bash
# Chạy bộ test tự động (bắt buộc 0 failed)
pytest -q

# So sánh tự động Baseline vs PoC
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md

# Đóng băng demo mốc 180 phút
git add .
git commit -m "feat(t03): complete end-to-end poc with quality gate and human review"
git tag demo-180m
git push origin demo-180m
```
