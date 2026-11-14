# T02 — So sánh queue baseline vs PoC v0 (40 ảnh eval)

> **Historical (PoC v0, baseline `T=800`).** Không dùng để chấm eval.
> Xem `reports/t02_dev_eval.md` cho PoC v1 và baseline `T=760`.

**Không có GT**: đây là so sánh queue, không phải Recall/Precision. Không dùng kết quả này để chỉnh threshold.

Baseline: `lap < 800` (score = 1000/(lap+1e-5)). PoC v0: 4 feature group-relative, ngưỡng sơ bộ từ 14 nhãn dev.

Thứ tự xếp hạng dùng chung cho mọi bảng và mọi tập top-B: `score` giảm dần, hoà thì `image_id` tăng dần. Tie-break chỉ để kết quả tái lập được, không mang ý nghĩa chất lượng.

## Tóm tắt

| Chỉ số | Baseline | PoC v0 |
|---|---:|---:|
| Số ảnh bị flag | 18/40 | 19/40 |
| Overlap@10 | — | 3/10 |
| Overlap@20 | — | 16/20 |
| Overlap tập bị flag (score > 0) | — | 15/22 (Jaccard 0.682) |
| Jaccard@20 | — | 0.667 |
| Spearman ρ (40 ảnh) | — | 0.511 |

**4 ảnh vào top-20 của PoC** (baseline không có): img_01_0, img_01_3, img_05_3, img_13_2

**4 ảnh rời top-20** (baseline có, PoC không): img_03_0, img_06_0, img_15_0, img_19_2

**Tie ở biên top-20:** baseline score rank 20 = 1.1002 (1 ảnh cùng score); PoC score rank 20 = 0.0000 (21 ảnh cùng score). PoC có 21 ảnh score 0.000 tranh 1 slot cuối → slot 20 chỉ là ảnh thắng tie-break theo `image_id`, không phải ảnh suspicious hơn. Mọi so sánh nên đọc top-19 (các ảnh score > 0) hoặc dùng overlap không phụ thuộc tie.

## PoC v0 — top 20

| rank | image_id | score | type | sev | baseline score | baseline top-20 |
|---:|---|---:|---|---:|---:|:---:|
| 1 | img_17_2 | 2.615 | glare | 2 | 2.15 | ✓ |
| 2 | img_06_2 | 2.228 | compression | 2 | 2.88 | ✓ |
| 3 | img_05_3 | 1.242 | glare | 2 | 0.76 |  |
| 4 | img_05_2 | 1.205 | compression | 2 | 1.24 | ✓ |
| 5 | img_13_2 | 1.091 | compression | 2 | 0.83 |  |
| 6 | img_01_3 | 1.067 | compression | 2 | 0.91 |  |
| 7 | img_23_2 | 1.058 | compression | 2 | 1.47 | ✓ |
| 8 | img_13_3 | 1.046 | blur | 2 | 537.85 | ✓ |
| 9 | img_15_3 | 1.045 | dark | 2 | 68.84 | ✓ |
| 10 | img_15_2 | 1.040 | blur | 2 | 523.99 | ✓ |
| 11 | img_23_3 | 1.017 | dark | 2 | 20.31 | ✓ |
| 12 | img_17_3 | 1.010 | dark | 2 | 21.02 | ✓ |
| 13 | img_19_3 | 0.982 | blur | 1 | 205.42 | ✓ |
| 14 | img_16_2 | 0.945 | blur | 1 | 190.51 | ✓ |
| 15 | img_01_2 | 0.867 | dark | 1 | 2.83 | ✓ |
| 16 | img_16_3 | 0.380 | compression | 1 | 1.49 | ✓ |
| 17 | img_06_3 | 0.311 | glare | 1 | 4.25 | ✓ |
| 18 | img_03_3 | 0.243 | compression | 1 | 2.66 | ✓ |
| 19 | img_03_2 | 0.184 | glare | 1 | 3.01 | ✓ |
| 20 | img_01_0 | 0.000 | none | 0 | 0.51 |  |

## Baseline — top 20 nhưng không nằm trong PoC top-20

| base rank | image_id | baseline score | PoC score | PoC type |
|---:|---|---:|---:|---|
| 9 | img_06_0 | 3.63 | 0.000 | none |
| 10 | img_15_0 | 3.19 | 0.000 | none |
| 13 | img_03_0 | 2.83 | 0.000 | none |
| 20 | img_19_2 | 1.10 | 0.000 | none |

## Vì sao 8 ảnh đổi chỗ

| image_id | light | hướng | PoC score | type | lap_ratio | bright_ratio | block_ratio | blob % | feature áp đảo |
|---|---|---|---:|---|---:|---:|---:|---:|---|
| img_01_0 | night | vào | 0.000 | none | 1.000 | 1.002 | 1.00 | 0.002 | — (score 0) |
| img_01_3 | night | vào | 1.067 | compression | 0.554 | 0.927 | 2.25 | 0.003 | compression (1.07) |
| img_05_3 | day | vào | 1.242 | glare | 0.880 | 1.011 | 1.02 | 0.873 | glare (1.24) |
| img_13_2 | night | vào | 1.091 | compression | 0.533 | 0.928 | 2.26 | 0.024 | compression (1.09) |
| img_03_0 | night | rời | 0.000 | none | 0.190 | 1.000 | 1.00 | 0.005 | — (score 0) |
| img_06_0 | night | rời | 0.000 | none | 0.187 | 0.997 | 1.03 | 0.003 | — (score 0) |
| img_15_0 | dusk | rời | 0.000 | none | 0.183 | 1.000 | 1.11 | 0.019 | — (score 0) |
| img_19_2 | day | rời | 0.000 | none | 0.717 | 0.997 | 1.47 | 0.007 | — (score 0) |

- `img_05_3` (day): glare, blob chiếm 0.87% diện tích — 17× ngưỡng `lo` = 0.0005. `lap` = 1324 vẫn cao nên baseline coi là ảnh nét; đây là loại lỗi baseline không có feature.
- `img_13_2` và `img_01_3` (night): compression, `block_ratio` = 2.26 / 2.25, vượt `hi` = 2.2 → severity 2. Baseline xếp hai ảnh này ở nửa dưới vì `lap` cao.
- Ba ảnh rời queue (`img_03_0`, `img_06_0` night; `img_15_0` dusk) đều có PoC score = 0: `lap` thấp do cảnh thiếu tương phản chứ không phải blur, và không feature nào vượt ngưỡng. Đây đúng là kiểu false alarm của baseline.
- `img_19_2` (day) là ca sát ngưỡng: `block_ratio` = 1.47 (lo = 1.5), blob = 0.007% (lo = 0.05%) → lọt qua mọi ngưỡng. Cần nhãn eval mới biết đây là miss hay đúng là clean.
- `img_01_0` không thực sự "được thăng hạng": score = 0, chỉ lấp slot 20 sau khi hết ảnh suspicious (xem tie ở trên).

**Chưa có nhãn eval**, nên các nhận xét trên chỉ giải thích *vì sao queue đổi*, không khẳng định ảnh nào bị bỏ sót hay báo nhầm.

## Phân bố type trong top-20

| type | baseline | PoC v0 |
|---|---:|---:|
| blur | 18 | 4 |
| dark | 0 | 4 |
| glare | 0 | 4 |
| compression | 0 | 7 |
| none | 2 | 1 |

Baseline chỉ có một score Laplacian nên type dự đoán chỉ là `blur`/`none`; PoC phân bổ queue sang nhiều loại lỗi hơn. Không có GT nên chưa biết phân bổ nào đúng hơn.
