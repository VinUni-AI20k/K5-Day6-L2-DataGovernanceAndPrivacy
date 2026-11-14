# T02 baseline — dev proxy

> **Historical (14 nhãn folder 2).** Đã được thay bằng `reports/t02_dev_eval.md`
> (56 nhãn, baseline `T=760`, PoC v1). Giữ lại để đối chiếu quá trình.

**Baseline:** một ngưỡng Laplacian toàn ảnh duy nhất.
`score = 1000 / (lap + 1e-5)`, `pred_defect_type = blur` nếu `lap < 800`.

**Phạm vi:** 14 ảnh dev đã label (folder 2, 4 nhóm), 8 defect / 6 clean. B = 7 = 50% của 14, tương ứng B = 20/40 của eval. Đây là proxy, **không phải** metric chính thức: repo không có `fixtures/t02_raw_qc/gt/`.

Ngưỡng `T = 800` chốt trên chính 14 nhãn này; mọi T trong (745, 876] cho cùng quyết định. Chưa có nhóm đêm và chưa có nhãn glare → kết quả lạc quan.

## Ranking

| rank | image_id | light | GT | lap | score | top-B | pred |
|---:|---|---|---|---:|---:|:---:|---|
| 1 | img_09_2 | day | blur/2 | 1.7 | 601.78 | ✓ | blur |
| 2 | img_07_3 | day | blur/2 | 4.6 | 216.66 | ✓ | blur |
| 3 | img_09_0 | day | none/0 | 187.0 | 5.35 | ✓ | blur |
| 4 | img_09_3 | day | compression/1 | 196.1 | 5.10 | ✓ | blur |
| 5 | img_07_2 | day | dark/1 | 222.8 | 4.49 | ✓ | blur |
| 6 | img_08_3 | dusk | dark/1 | 264.1 | 3.79 | ✓ | blur |
| 7 | img_10_3 | day | dark/1 | 326.3 | 3.06 | ✓ | blur |
| 8 | img_08_2 | dusk | blur/1 | 478.9 | 2.09 |  | blur |
| 9 | img_10_2 | day | compression/2 | 745.0 | 1.34 |  | blur |
| 10 | img_09_1 | day | none/0 | 875.8 | 1.14 |  | none |
| 11 | img_08_0 | dusk | none/0 | 1037.0 | 0.96 |  | none |
| 12 | img_08_1 | dusk | none/0 | 1049.9 | 0.95 |  | none |
| 13 | img_10_1 | day | none/0 | 1234.6 | 0.81 |  | none |
| 14 | img_10_0 | day | none/0 | 1248.5 | 0.80 |  | none |

## Metrics (official `eval_t02`, proxy GT)

| Metric | Value | num/den | N |
|---|---:|---:|---:|
| Defect Recall@B | 0.7500 | 6/8 | 14 |
| Precision@B | 0.8571 | 6/7 | 14 |
| Defect-type accuracy (GT defects) | 0.3750 |  | 8 |
| False alarm in top-B [light=day] | 0.2500 | 1/4 | 10 |
| False alarm in top-B [light=dusk] | 0.0000 | 0/2 | 4 |
| Average Precision | 0.8755 |  | 14 |

## Binary confusion at `lap < 800`

| TP | FP | FN | TN | Precision | Recall | F1 |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 1 | 0 | 5 | 0.8889 | 1.0000 | 0.9412 |

**Đọc kết quả:** baseline bắt 3 ảnh dark vì `lap` thấp (do thiếu tương phản), không phải vì nhận ra dark. False alarm duy nhất là `img_09_0` (clean nhưng mềm). Top-7 bỏ sót `img_08_2` (blur/1) và `img_10_2` (compression/2). Vì vậy con số này không chứng minh baseline tốt — nó chỉ cho thấy tập 14 ảnh chưa có nhóm đêm/glare, nơi baseline được dự đoán sẽ sụp.

Files: `out\baseline\ranked_review.csv`, `reports\metrics_baseline_dev.json`.
