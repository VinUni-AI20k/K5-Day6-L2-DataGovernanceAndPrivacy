# Team 6 · G06 · T02 Raw QC Triage

Lead: **Hoàng Trọng Trà – 2A202603342**. Đề bài: [tracks/T02.md](tracks/T02.md).

## 1. Thành viên và quyền sở hữu

| Thành viên | MSSV | Vai trò | File chính | Nhánh đề xuất |
|---|---|---|---|---|
| Hoàng Trọng Trà | 2A202603342 | Lead / Integrator | `src/pipeline.py`, `src/team06/policy.py`, `configs/lab.yaml` | `feat/team06-integration` |
| Nguyễn Quốc Hưng | 2A202603324 | Data & Provenance | `src/team06/data.py`, công cụ kiểm dữ liệu | `feat/team06-data` |
| Phạm Văn Dương | 2A202603332 | Baseline & Research | `src/team06/baseline.py`, nghiên cứu/đối chứng | `feat/team06-baseline` |
| Nguyễn Nhật Hạ | 2A202603325 | Core Algorithm / PoC | `src/team06/features.py`, `src/team06/scoring.py` | `feat/team06-poc` |
| Lê Trần Phi Hùng | 2A202603353 | QA & Evaluation | `tests/test_team06.py`, test bổ sung, báo cáo metric | `test/team06-qa` |
| Nguyễn Tuấn Minh | 2A202603349 | Human Review & Demo | `src/team06/human_review.py`, `demo/` | `feat/team06-review` |

Trà tích hợp pipeline chung. Các thành viên phát triển module riêng để giảm conflict.
Git author/email, commit SHA và người trình bày để trống trong bảng đóng góp cho đến khi từng người xác nhận;
không coi phân công hay commit thiết lập là bằng chứng đã hoàn thành công việc của cả nhóm.

## 2. Phạm vi và protocol ban đầu

- Input cố định: `fixtures/t02_raw_qc`; 96 ảnh, 56 dev / 40 eval. Giữ ID và split gốc.
- Seed 42; budget chính B=20. Primary: Defect Recall@B, đi kèm Precision@B.
- Baseline: Laplacian toàn ảnh với một ngưỡng; random example chỉ kiểm tra wiring.
- PoC: thử phối hợp sharpness, brightness, glare cục bộ và compression; giải thích score.
- Fit chuẩn hóa, ngưỡng và trọng số trên dev. Chốt trước khi đánh giá eval.
- Evaluator lọc eval trước khi lấy top-20. Queue mặc định hiện lấy top-20 toàn input;
  Minh/Trà phải khai báo pool review rõ ràng, không đồng nhất hai queue này trong báo cáo.
- Không đọc `gt/`, không tải model trong run offline. GT chính thức chỉ có ở overlay giảng viên.
- Nhãn nội bộ do Hưng/Phi Hùng chuẩn bị phải ghi protocol; không báo là kết quả official.
- Tham số thuật toán, ngưỡng quyết định và thời điểm freeze còn **chưa chốt**; cập nhật
  `reports/metric_contract.md` trước evaluation, không suy diễn từ cấu hình B/seed rằng thuật toán đã freeze.

## 3. Giao diện module và trạng thái

| Hàm | Đầu vào/đầu ra | Trạng thái |
|---|---|---|
| `data.load_inputs(ctx)` | `{manifest, images}`; metadata `image_id,path,camera_id,light,split` | Có loader ban đầu: verify manifest, schema, ID và split |
| `features.extract_features(ctx, images)` | DataFrame feature theo `image_id` | TODO — Nhật Hạ |
| `scoring.score_images(ctx, data)` | DataFrame scored | TODO — Nhật Hạ; runner exit 3 |
| `baseline.score_baseline(ctx, data)` | Cùng schema scored với PoC | TODO — Văn Dương; runner exit 3 |
| `human_review.apply_human_review(ctx, scored, queue)` | DataFrame sau review | Chưa có quyết định: copy; có quyết định: báo TODO, không âm thầm bỏ qua |
| `policy.decide(ctx, final)` | `Decision` | HOLD / POLICY_NOT_IMPLEMENTED — Trà cần hoàn thiện |

Schema scored thống nhất:
`image_id,path,camera_id,light,split,score,reason,pred_defect_type,pred_action`.
Một dòng/ảnh, `score` hữu hạn, càng cao càng cần review. `pred_action`: KEEP / RECAPTURE / REVIEW.
Mỗi module giữ metadata để phân tích camera/light và tạo contact sheet.

`src.pipeline.run_pipeline(ctx, scorer=...)` dùng chung load → score → rank → review → decide;
`src.pipeline.run(ctx)` chọn PoC; `src.team06.baseline.run(ctx)` chọn baseline.
Runner và metric chuẩn vẫn do hạ tầng gốc quản lý; không đổi định nghĩa metric để cải thiện điểm.

## 4. Khởi động trên Windows / PowerShell

Mở terminal tại gốc repo. Máy đã có uv và Python 3.12 có thể dùng:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

Nếu dùng Python launcher đã cài 3.12, thay bằng:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Cài dependency ở bước chuẩn bị có mạng; các run demo phải offline. Dùng Python trong `.venv`
để tránh chạy nhầm Python hệ thống. Không commit `.venv/` hay output trong `out/`.

```powershell
.\.venv\Scripts\python.exe -m tools.verify_manifests
.\.venv\Scripts\python.exe -m tools.preflight
.\.venv\Scripts\python.exe -m pytest -o addopts="" -q
```

Smoke hạ tầng (không phải baseline Laplacian):

```powershell
.\.venv\Scripts\python.exe -m src.main --track t02 --pipeline src.examples.random_baseline --output out/smoke --offline --seed 42
```

Lệnh của nhóm (hiện chủ động exit 3 cho đến khi module thuật toán được triển khai):

```powershell
.\.venv\Scripts\python.exe -m src.main --track t02 --pipeline src.team06.baseline --output out/baseline --run-name baseline --offline --seed 42
.\.venv\Scripts\python.exe -m src.main --track t02 --output out/poc --run-name poc --offline --seed 42
```

Khi có overlay giảng viên mới chạy evaluate:

```powershell
.\.venv\Scripts\python.exe -m src.evaluate --track t02 --pred out/baseline/ranked_review.csv --run-name baseline --out reports/metrics_baseline.json
.\.venv\Scripts\python.exe -m src.evaluate --track t02 --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
.\.venv\Scripts\python.exe -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
```

Không có GT: evaluate trả exit 2 và các test `requires_gt` skip theo thiết kế.

## 5. Git và xuống dòng

Repo: https://github.com/trahoangdev/K5-Day6-L2B-HoangTrongTra-2A202603342-DataGovernanceAndPrivacy

`.gitattributes` giữ text LF vì manifest hash theo byte; ảnh/binary không đổi.
Đợt thiết lập khôi phục xuống dòng về LF, không cập nhật SHA-256 gốc của fixtures.
Nếu hash lỗi sau này, kiểm tra nguyên nhân; không sinh lại manifest chỉ để làm PASS.

Trong khi bản thiết lập còn ở nhánh `chore/team06-setup`, thành viên mới clone đúng nhánh này:

```powershell
git clone --branch chore/team06-setup https://github.com/trahoangdev/K5-Day6-L2B-HoangTrongTra-2A202603342-DataGovernanceAndPrivacy.git
Set-Location K5-Day6-L2B-HoangTrongTra-2A202603342-DataGovernanceAndPrivacy
git switch -c feat/team06-data
```

Đổi tên nhánh công việc theo bảng phân công và đặt Git name/email của chính mình trước khi commit.
Không phát triển trực tiếp trên nhánh thiết lập chung.

Sau khi Trà đã merge bản thiết lập vào main, thành viên bắt đầu công việc mới từ main:

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/team06-data
```

Đổi tên nhánh theo bảng trên. Pull request vào main cần nêu thay đổi, lệnh chạy, test và giới hạn.
Trà tích hợp theo thứ tự data → baseline → PoC → review → QA hoàn thiện.
Thông tin author/email thực tế và commit thực chất bổ sung vào `reports/team_contributions.csv`.

## 6. Tiêu chí bàn giao

- **Quốc Hưng:** 14 manifest PASS; thống kê camera/light/split; loader fail rõ khi thiếu/hỏng input;
  protocol nhãn nội bộ và hai mẫu dữ liệu khó.
- **Văn Dương:** baseline Laplacian chạy riêng; score đúng chiều; giải thích ngưỡng chọn trên dev;
  cùng pool/seed/budget với PoC và tài liệu tham khảo.
- **Nhật Hạ:** feature và score có giải thích; giữ đủ ID; kiểm tra ảnh đêm hữu ích, glare cục bộ,
  camera khác quang học; không tune trên eval.
- **Phi Hùng:** test success + failure/edge; schema/seed/offline; so sánh công bằng và hai failure cases.
  Khi PoC hoàn thiện, chuyển test exit 3 của template sang stub riêng và thêm test PoC success.
- **Tuấn Minh:** contact sheet offline; reviewer CSV có tên; áp sửa đổi, validate ID, log before/after;
  giữ raw predictions; escalate dẫn tới chờ duyệt; slide 3–5 trang và minh họa review.
- **Trà:** tích hợp một lệnh; policy có reason/owner/evidence; kiểm tra clone sạch; tổng hợp báo cáo
  và gắn tag demo/final sau khi nghiệm thu thực tế.

Mốc: phút 30 chốt contract; phút 50 baseline; phút 145 E2E; phút 170 QA; phút 180 freeze demo;
+24h báo cáo và bằng chứng Git. Tag chưa được tạo trong đợt thiết lập này.
