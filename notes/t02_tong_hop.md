# T02 · Raw QC Triage — Tổng hợp hoàn chỉnh (phần chấm điểm, thành viên 2)

> Trạng thái: khung code chạy được và đã kiểm chứng trên bộ test tự sinh. **Chưa có số liệu trên eval thật** (nhãn eval do giảng viên giữ) và **chưa có nhãn dev tự gán**. Mọi con số dưới đây ghi rõ nguồn.

## 1. Tóm tắt

- **Bài toán**: xếp hạng 96 ảnh synthetic (320×180) theo mức nghi lỗi (blur / dark / glare / compression) để người review xem **B = 20 ảnh** là bắt được nhiều ảnh lỗi nhất.
- **Chấm**: Defect Recall@20 (chính) và Precision@20 trên split `eval` (40 ảnh), do giảng viên chạy với `gt/`.
- **Cách làm**: đo 4 đặc trưng mỗi ảnh → chuẩn hóa robust z-score **trong nhóm (camera, ánh sáng)** → `score = max` các thành phần → gán loại lỗi → xếp hạng top-20 → review → KEEP/RECAPTURE.
- **Kết quả kiểm chứng** (bộ test tự sinh, 10 seed chưa dùng khi chỉnh): Recall@B **0.99** so với baseline **0.73**; thắng 10/10 seed. Đây chứng minh logic đúng, **không** chứng minh điểm trên eval thật.

## 2. Đề bài và luật chơi

| Mục | Nội dung |
|---|---|
| Dữ liệu | `fixtures/t02_raw_qc/`: `images.csv` (`image_id, path, camera_id, light, split`), 96 ảnh |
| Cơ cấu | cam_A 64, cam_B 32 · day 56, dusk 20, night 20 · dev 56, eval 40 (chia theo cảnh gốc) |
| Nhãn | `gt/labels.csv` (giảng viên giữ): `defect_type ∈ {none, blur, glare, dark, compression}`, `severity 0–2`, `is_defect` |
| Đầu ra bắt buộc | `out/ranked_review.csv`: `image_id, score` (cao = nghi lỗi hơn); tùy chọn `pred_defect_type, pred_action` |
| Metric chính | Defect Recall@B (B = 20) = ảnh lỗi thật trong top-B / tổng ảnh lỗi thật; kèm Precision@B |
| Metric phụ | báo nhầm trong top-B theo `light`, độ chính xác loại lỗi, ms/ảnh |
| Baseline bắt buộc | một ngưỡng Laplacian toàn ảnh (`image_ops.laplacian_variance`) |
| Failure mode phải phân tích | ảnh đêm hữu ích bị loại; lóa cục bộ bị bỏ sót; cam_B (quang học mềm) bị báo nhầm |
| Luật cứng | không đọc `gt/` (GT guard, exit 5); không tune hay gán nhãn trên `eval`; seed 42; offline; chốt tham số trước khi chấm |

## 3. Khái niệm chính

- **Recall@B / Precision@B**: trong B ảnh người review xem, bắt được bao nhiêu % ảnh lỗi thật / bao nhiêu % trong B là lỗi thật.
- **Hard negative**: ảnh trông như lỗi nhưng không phải (ảnh đêm bình thường, ảnh cam_B mềm). Nguồn báo nhầm chính.
- **Robust z-score**: `z = (x − median) / (1.4826·MAD)`; ít bị ảnh lỗi kéo lệch hơn mean/std.
- **Chuẩn hóa theo nhóm**: so mỗi ảnh với "ảnh bình thường của cùng camera và ánh sáng", nên ảnh đêm hay cam_B không bị coi là lỗi chỉ vì bản chất.
- **Human-in-the-loop**: hệ thống đưa top-20, người review xác nhận, mọi thay đổi vào audit log; quyết định có `reason_code` và `owner`.

## 4. Thuật toán

**Bước 1 · Đặc trưng** (`src/t02_features.py`), mỗi ảnh:

| Lỗi | Đặc trưng | Cách đo | Chiều "xấu" |
|---|---|---|---|
| blur | `blur_pct` | percentile 75 của phương sai Laplacian trên lưới 4×4 (chỉ nhìn ô có cạnh) | nhỏ là xấu (dùng log) |
| dark | `p95` | percentile 95 độ sáng toàn ảnh | nhỏ là xấu |
| glare | `glare_max_cell` | tỷ lệ pixel `>245` lớn nhất trong các ô | lớn là xấu |
| compression | `blockiness` | gradient tại biên khối 8 px / bên trong khối | lớn là xấu |

Ảnh không đọc được → `ok = False`, không làm sập pipeline.

**Bước 2 · Chuẩn hóa theo nhóm** (`src/t02_scoring.py`): robust z-score trong nhóm `(camera_id, light)`; nhóm < 6 ảnh thì lùi về `light`, rồi toàn bộ. Có `scale_floor` để MAD ≈ 0 không làm z nổ.

**Bước 3 · Điểm và loại lỗi**: `score = max(0, z_blur, z_dark, z_glare, z_compression)`. Loại lỗi = thành phần lớn nhất; `score < 1.5` thì `none`. `pred_action` = `RECAPTURE` nếu có lỗi, ngược lại `KEEP`. Ảnh hỏng: `score = +inf`, loại `unreadable`.

**Bước 4 · Xếp hạng** top-B → `review_queue.csv`, contact sheet HTML, `ranked_review.csv`, `decision.json`.

**Tham số (mặc định trong code; ghi đè qua `configs/lab.yaml → params.t02`)**

| Tham số | Giá trị |
|---|---|
| lưới ô | 4×4 |
| ngưỡng cháy / tối | `>245` / `<30` |
| `blur_percentile` | **75** (ban đầu 25, đổi sau khi test, xem mục 6) |
| `none_threshold` | 1.5 |
| `min_group` | 6 |
| `scale_floor` | blur 0.10 · dark 2.0 · glare 0.02 · compression 0.05 |
| trọng số | bằng nhau (1.0) |
| seed | 42 |

## 5. Cấu trúc code và cách chạy

| File | Vai trò |
|---|---|
| `src/t02_features.py` | trích 4 đặc trưng |
| `src/t02_scoring.py` | chuẩn hóa nhóm, điểm, loại lỗi (`score_images(images, input_dir, config)`) |
| `src/t02_baseline.py` | baseline Laplacian (`run(ctx)` cho `--pipeline`) |
| `src/t02_poc.py` | PoC chạy độc lập; thành viên 3 có thể dán logic vào `src/pipeline.py` |
| `tools/t02_make_dev_sheet.py` | contact sheet **chỉ ảnh dev**, không điểm + mẫu `labels/dev_labels.csv` |
| `tools/t02_eval_dev.py` | đo baseline/PoC trên nhãn dev tự gán (Recall/Precision/AP, báo nhầm theo slice, Wilson CI) |
| `tools/t02_selftest.py` | bộ test tự sinh có nhãn chắc chắn (nhiều seed) |
| `tests/test_t02_scoring.py` | 15 test |

```bash
make setup && make test                                            # 0 failed
python -m src.main --track t02 --pipeline src.t02_baseline --output out/baseline --run-name baseline --offline --seed 42
python -m src.main --track t02 --pipeline src.t02_poc      --output out/poc      --run-name poc      --offline --seed 42
python -m tools.t02_make_dev_sheet          # -> out/dev_sheet.html + labels/dev_labels.csv  (gán nhãn tay)
python -m tools.t02_eval_dev                # sau khi điền nhãn dev
python -m tools.t02_selftest --seed-start 101 --seeds 10
```

Giảng viên (có `gt/`): `python -m src.evaluate --track t02 --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json`.

## 6. Kiểm chứng

**6.1 Bộ test tự sinh** (`tools/t02_selftest.py`): cảnh sạch từ `tools/synth/scene.py` (seed khác fixtures) + lỗi từ `corruptions.py`; ngày/hoàng hôn/đêm; cam_B mềm nhưng không lỗi; ~40% ảnh lỗi, mức 1-2. Kết quả 10 seed (101–110) **chưa dùng khi chọn tham số**, N = 120, B = 60:

| Chỉ số | Baseline | PoC |
|---|---|---|
| Recall@B | 0.733 ± 0.061 | **0.989 ± 0.015** |
| Precision@B (trần = 0.80) | 0.582 ± 0.052 | **0.793 ± 0.114** |
| AP | 0.747 ± 0.060 | **0.984 ± 0.017** |
| Recall: blur / dark | 1.00 / 0.98 | 1.00 / 1.00 |
| Recall: glare | 0.378 | **0.960** |
| Recall: compression | 0.523 | **1.000** |
| Báo nhầm ảnh cam_B sạch | **1.000** | 0.168 |
| Báo nhầm ảnh đêm sạch | 0.327 | 0.123 |
| Đoán đúng loại lỗi | không có | 0.892 |

PoC thắng baseline ở 10/10 seed.

**6.2 Điểm yếu tìm được và đã sửa**: bản đầu dùng percentile 25 cho độ nét nên chỉ bắt **61%** ảnh blur (kém baseline), vì percentile thấp rơi vào ô phẳng (trời, mặt đường). Đổi sang percentile 75 → recall blur 1.00. Percentile được chọn trên seed 1–8; con số ở 6.1 lấy từ seed khác.

**6.3 Ảnh dev thật (chưa có nhãn)**: trong top-28 ảnh dev, baseline chứa 15 ảnh cam_B (cam_B chỉ 20/56 ảnh dev), PoC chứa 10. Nhất quán với failure mode của đề, nhưng chưa phải bằng chứng chất lượng.

**6.4 Test**: `pytest -q` pass (các test cần `gt/` bị skip như thường lệ). Test của nhóm gồm: lỗi tiêm vào làm đặc trưng đổi đúng chiều (4 loại), ảnh tiêm lỗi có điểm cao hơn bản gốc và đúng loại, ảnh hỏng không làm sập, nhóm nhỏ không NaN, tái lập, bất biến toàn lô, chạy end-to-end qua `src.main`, sheet dev không chứa ảnh eval, self-test có nhãn.

## 7. Giới hạn (nói thẳng)

1. **Chưa có Recall@20 trên eval thật.** Chỉ giảng viên có `gt/`.
2. Ảnh synthetic của bộ test tự sinh **dễ hơn** ảnh thật; thắng ở đó không bảo đảm thắng ở eval. Bộ sinh chưa có mờ chuyển động, lóa rất nhỏ, lỗi chồng nhiều loại.
3. `blur_percentile = 75` được chọn bằng bộ test tự sinh nên có nguy cơ chỉnh theo bộ sinh; cần xác nhận lại bằng nhãn dev thật.
4. Eval chỉ 40 ảnh: đổi thứ hạng một ảnh làm Recall nhảy khoảng 4-5 điểm phần trăm; phải báo kèm khoảng tin cậy.
5. Dev chỉ có 4 ảnh đêm, nên nhóm `(camera, night)` thường < 6 ảnh và tự lùi về nhóm rộng hơn.
6. Ngưỡng `none_threshold = 1.5`, `scale_floor` là giá trị khởi điểm có lý do, chưa chỉnh trên nhãn dev thật.
7. Nếu thay bằng dữ liệu thật ngoài repo: tham số (lưới, ngưỡng cháy, percentile, `scale_floor`) phải hiệu chỉnh lại theo từng camera/điều kiện bằng một tập nhãn nhỏ.

## 8. Việc còn lại (theo thứ tự)

- [ ] Gán nhãn tay ảnh **dev** trong `labels/dev_labels.csv` (không xem/gán nhãn ảnh eval).
- [ ] `python -m tools.t02_eval_dev`; nếu cần chỉnh `none_threshold`, `scale_floor`, trọng số trên **dev**, rồi **đóng băng** và ghi vào `reports/metric_contract.md`.
- [ ] Điền `configs/lab.yaml`: `group_id`, `owner`, `track: t02`; nếu đổi tham số, đặt dưới `params.t02`.
- [ ] Thành viên 3: nối `score_images(...)` vào `process()` của `src/pipeline.py`, `make run TRACK=t02` exit 0.
- [ ] Ablation trên dev/self-test: tắt chuẩn hóa nhóm; dùng toàn ảnh thay lưới ô; `max` so với tổng có trọng số.
- [ ] 2 failure case có ảnh và nguyên nhân gốc (ví dụ cam_B báo nhầm ở baseline; ảnh đêm). Chỉ dùng ảnh dev để minh họa.
- [ ] Điền `reports/group_report.md`, `reports/team_contributions.csv`; `make tag-demo` (phút 180), `make tag-final` (+24h).

## 9. Chia việc 3 người

| Người | Phụ trách | Sản phẩm |
|---|---|---|
| 1 | Đặc trưng, đọc ảnh, kiểm tra manifest, ảnh hỏng | `src/t02_features.py` + test |
| 2 | Baseline, chuẩn hóa nhóm, điểm, loại lỗi, phân tích báo nhầm | `src/t02_scoring.py`, `src/t02_baseline.py`, `tools/t02_*` |
| 3 | Duy nhất sửa `src/pipeline.py`; queue, contact sheet, decision, chạy test và đánh giá, báo cáo | `ranked_review.csv`, `metrics_*.json`, `group_report.md` |

Mỗi người cần ≥ 1 commit thực chất, khớp `reports/team_contributions.csv`.
