# T02 — Dev evaluation: baseline vs PoC v1 (56 nhãn tay)

**Phạm vi:** 56/56 ảnh `dev` có nhãn tay trong `reports/dev_labels.csv`; không đọc `fixtures/*/gt/`, không chấm 40 ảnh `eval` (chưa có nhãn). Đây là proxy dev, **không phải** metric chính thức.

- Clean: **22** · Defect: **34** (15 defect có type, 19 chỉ có severity).
- Budget chính trên dev: **B=28** = 50% của 56, tương ứng B=20/40 của eval. B=20 cũng được báo để so sánh trực tiếp với budget chính thức.
- Tie-break: `score` giảm dần, `image_id` tăng dần (giống file dự đoán).
- Type accuracy chỉ tính **15 defect có type**; 19 defect severity-only không có type nên không thể chấm type.

## 1. Freeze / provenance

- Labels SHA-256: `d1364ac8e50fed4b…`
- Pipeline `src/poc/t02_v1.py` SHA-256: `9a20fe76e636becb…`
- Baseline `src/baselines/t02_laplacian.py` SHA-256: `4be61b6c8ccfca69…`
- PoC thresholds: dark `0.596/0.124`, blur `0.205/0.032`, compression `1.47/2.06`, glare `0.0022/0.006`.
- Baseline: `lap < 760` (re-freeze trên 56 nhãn dev; mọi T trong `(745, 772.7]` cho cùng quyết định).

## 2. Ranking quality

| Metric | Baseline (`lap<760`) | PoC v1 |
|---|---:|---:|
| Average Precision (56 ảnh) | 0.9376 | 0.9831 |
| Recall@28 (50% dev) | 79.4% | 82.4% |
| Precision@28 | 96.4% | 100.0% |
| Recall@20 (budget official) | 55.9% | 58.8% |
| Precision@20 | 95.0% | 100.0% |

Ở B=28: baseline đúng **27/28** slot, PoC đúng **28/28** slot. Baseline có 1 ảnh clean trong top-28 (`img_09_0`); PoC có 0.

Ở B=20: baseline **19/20**, PoC **20/20**.

AP là metric phụ (không nằm trong `eval_t02` chính thức); Recall@B/Precision@B mới là metric chính. AP dùng cùng tie-break `score` giảm dần, `image_id` tăng dần.

## 3. Threshold (flagged set)

| Metric | Baseline | PoC v1 |
|---|---:|---:|
| TP / FP / FN / TN | 28 / 1 / 6 / 21 | 32 / 0 / 2 / 22 |
| Precision | 96.6% | 100.0% |
| Recall | 82.4% | 94.1% |
| F1 | 88.9% | 97.0% |
| Số ảnh bị flag | 29/56 | 32/56 |

- Baseline false alarm: `img_09_0`.
- Baseline miss: `img_02_2, img_11_0, img_12_1, img_14_3, img_20_3, img_22_3`.
- PoC false alarm: `—`.
- PoC miss: `img_11_0, img_12_1` (cả hai đều là nhãn severity-only, feature-neutral; xem mục 7).

- Baseline cũ `T=800` sẽ flag thêm **3 clean** (`img_04_0` (lap=791, dusk), `img_04_1` (lap=782, dusk), `img_22_1` (lap=772.7, dusk)) mà không thêm TP nào: TP/FP = **28/4** so với **28/1** ở T=760. Vì ranking score là monotonic theo `lap`, thay đổi này **không đổi Recall@B/Precision@B**.

## 4. Type accuracy (15 defect có type)

| Model | Đúng | Accuracy |
|---|---:|---:|
| Baseline | 6/15 | 40.0% |
| PoC v1 | 14/15 | 93.3% |

PoC confusion (hàng = GT, cột = dự đoán):

| GT \ Pred | none | blur | compression | dark | glare |
|---|---:|---:|---:|---:|---:|
| blur | 0 | 5 | 1 | 0 | 0 |
| compression | 0 | 0 | 4 | 0 | 0 |
| dark | 0 | 0 | 0 | 4 | 0 |
| glare | 0 | 0 | 0 | 0 | 1 |

PoC type sai:

- `img_08_2`: GT `blur/1` → pred `compression`.

Severity sanity (không nằm trong metric T02): PoC đúng **14/15** severity trên defect có type; **36/37** trên toàn bộ row có type.

## 5. Slice theo `light` ở B=28

| Slice | n (defect/clean) | Baseline recall | Baseline FA | PoC recall | PoC FA |
|---|---:|---:|---:|---:|---:|
| light=day | 36 (21/15) | 16/21 (76.2%) | 1/15 | 18/21 (85.7%) | 0/15 |
| light=dusk | 16 (10/6) | 8/10 (80.0%) | 0/6 | 7/10 (70.0%) | 0/6 |
| light=night | 4 (3/1) | 3/3 (100.0%) | 0/1 | 3/3 (100.0%) | 0/1 |

## 6. Slice theo `camera_id` ở B=28

| Slice | n (defect/clean) | Baseline recall | Baseline FA | PoC recall | PoC FA |
|---|---:|---:|---:|---:|---:|
| camera_id=cam_A | 36 (19/17) | 13/19 (68.4%) | 0/17 | 18/19 (94.7%) | 0/17 |
| camera_id=cam_B | 20 (15/5) | 14/15 (93.3%) | 1/5 | 10/15 (66.7%) | 0/5 |

## 7. Danh sách lỗi / ghi chú

**PoC top-28 bỏ sót:** `img_12_0 (?/2)`, `img_00_0 (blur/1)`, `img_12_2 (?/2)`, `img_21_0 (?/1)`, `img_11_0 (?/1)`, `img_12_1 (?/1)`.

**Baseline top-28 bỏ sót:** `img_10_2 (compression/2)`, `img_22_3 (?/1)`, `img_12_1 (?/1)`, `img_02_2 (glare/1)`, `img_14_3 (?/2)`, `img_11_0 (?/1)`, `img_20_3 (?/1)`.

- `img_11_0` và `img_12_1` được label severity 1 nhưng cả 4 feature đều ở mức tham chiếu nhóm (sạch hoàn hảo). Giữ nguyên nhãn người dùng, không tự sửa; đây là 2 FN duy nhất ở ngưỡng của PoC. Cần xem lại ảnh/nhãn.
- `img_08_2` (GT `blur/1`) bị PoC dự đoán `compression`: `block_ratio` vượt ngưỡng compression trong khi `lap_ratio` không tách được khỏi clean. Đây là type error duy nhất của PoC.
- Glare: baseline bỏ `img_02_2` (glare/1) ngoài top-28 và bỏ cả `img_20_3`, `img_22_3`; PoC đưa 4 ảnh glare vào top-28. Đây là gain chính về recall/type.
- `camera_id`: baseline false alarm `img_09_0` (cam_B, clean, lap=187) vì quang học mềm; PoC không flag ảnh này. Ở chiều ngược lại, top-28 của PoC chỉ có 10/15 defect cam_B (baseline 14/15) vì 4 defect cam_B có score thấp (0.005–0.089) bị đẩy ra khỏi budget; baseline bắt chúng nhờ `lap` thấp, nhưng đồng thời tạo false alarm.

## 8. Kết luận dev

- PoC v1 tăng Recall@28 từ **27/34** lên **28/34**, Precision@28 từ **96.4%** lên **100.0%**; AP từ **0.9376** lên **0.9831**.
- Ở ngưỡng flag: PoC **32 TP / 0 FP / 2 FN** so với baseline **28 TP / 1 FP / 6 FN**.
- Type accuracy tăng từ **6/15** lên **14/15**.
- **Chưa có kết luận eval.** 40 nhãn eval chưa có; khi có, chỉ chấm bằng pipeline đã freeze này, không chỉnh ngưỡng.

## 9. Tái lập

```powershell
.\.venv\Scripts\python.exe tools\_t02_calibrate.py
.\.venv\Scripts\python.exe tools\_t02_dev_eval.py
.\.venv\Scripts\python.exe -m src.main --track t02 --input fixtures/t02_raw_qc --output out/poc_v1 --run-name poc_v1 --pipeline src.poc.t02_v1 --offline
.\.venv\Scripts\python.exe -m src.main --track t02 --input fixtures/t02_raw_qc --output out/baseline --run-name baseline --pipeline src.baselines.t02_laplacian --offline
```
