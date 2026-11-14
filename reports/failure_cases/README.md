# Failure cases của baseline T02 (global Laplacian) — phân tích trên split dev

Baseline: `src/baseline_t02.py` — `score = 1/(1+lap_var/ref)`, `ref` = median lap_var của dev (không dùng nhãn).
Tái lập: xem docstring `tools/baseline_failure_cases.py`. Hạng tính trong 56 ảnh dev. Cột `verdict` là nhận định
thị giác của người phân tích, **không phải nhãn giảng viên**; số liệu chưa có `gt/` nên chưa tính Recall@20 chính thức.

## 1. Glare cục bộ bị bỏ sót (`glare_missed.png`)

| image_id | cam / light | lap_var | hạng dev (/56) | trong top-20? |
|---|---|---|---|---|
| img_22_3 | cam_A / dusk | 873 | 34 | không |
| img_02_2 | cam_A / day | 950 | 38 | không |
| img_20_3 | cam_A / day | 1266 | 50 | không |
| img_18_2 | cam_B / night | 335 | 21 | không (sát ngưỡng) |

Root cause: vùng cháy sáng chỉ chiếm vài % diện tích, phần còn lại của ảnh vẫn nét nên Laplacian toàn ảnh vẫn cao
(ngang ảnh sạch cam_A ~1000–1500). Baseline không có đặc trưng nào đo độ bão hoà (`frac_saturated`) nên không thấy glare.
Cả 4 ảnh glare đã xem trong dev đều nằm ngoài top-20 → 0/4.

## 2. cam_B sạch bị báo nhầm (`camB_false_alarm.png`)

| image_id | cam / light | lap_var | hạng dev (/56) | trong top-20? |
|---|---|---|---|---|
| img_12_0 | cam_B / dusk | 166 | 10 | có |
| img_09_0 | cam_B / day | 187 | 12 | có |
| img_21_0 | cam_B / day | 221 | 14 | có |
| img_00_0 | cam_B / day | 267 | 18 | có |

Root cause: ảnh nhìn sạch bằng mắt nhưng lap_var chỉ 170–270, thấp hơn cam_A sạch ~4–6 lần (median dev: cam_A day 955,
cam_B day 236). Một ngưỡng chung phạt cả camera. Giả thuyết đề bài: cam_B có quang học mềm hơn; **chưa kiểm chứng
được nguyên nhân thật**, vì cùng một cảnh cam_B còn có ảnh anh em lap_var 875–1366 (vd. img_09_1, img_00_1) nên cần
thêm bằng chứng trước khi kết luận.

## 3. Ảnh đêm: chưa chứng minh được trên dev

Dev chỉ có **4 ảnh night** (1 cảnh, toàn cam_B); 16/20 ảnh night và toàn bộ night của cam_A nằm ở eval (EDA:
`reports/eda/`). Trên dev, ảnh đêm sạch img_18_0 (lap 361) xếp hạng 23, ngay sau ngưỡng top-20, và img_18_1 (lap 1907) xếp
cuối — tức là chưa thấy báo nhầm rõ. Không thể kết luận về failure mode "đêm" nếu không nhìn eval (bị cấm để tune).

Hệ quả cho PoC hiện tại (`src/pipeline.py`): các hằng số ngưỡng ban đêm (`mean < 15`, `frac_dark > 0.85`,
"night normal dark ~0.50–0.65" cho cả cam_A) không thể suy ra chỉ từ dev vì dev không có ảnh đêm cam_A → cần giải trình
nguồn của các hằng số đó (nghi vấn tune bằng eval).
