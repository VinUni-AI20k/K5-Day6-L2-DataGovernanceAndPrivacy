# T02 — Calibration trên 56 nhãn dev

- Thời điểm: `2026-11-14T10:57:32+00:00`
- Nhãn: `reports\dev_labels.csv`, SHA-256 `d1364ac8e50fed4b…`
- 22 clean / 34 defect (15 defect có type, 19 chỉ có severity)
- Tất cả 56 nhãn được dùng để đo binary; 15 typed defects dùng để fit ngưỡng type/severity.

## Ngưỡng

| feature | ratio | clean extreme | typed positive gần nhất | lo exact | lo frozen | hi exact | hi frozen |
|---|---|---:|---:|---:|---:|---:|---:|
| dark | `bright_ratio` | 0.97856 | 0.21248 | 0.59552 | **0.596** | 0.12471 | **0.124** |
| blur | `lap_ratio` | 0.21349 | 0.45614 | 0.20446 | **0.205** | 0.03202 | **0.032** |
| compression | `block_ratio` | 1.0791 | 1.8637 | 1.4714 | **1.47** | 2.052 | **2.06** |
| glare | `blob` | 0.00013889 | 0.0044271 | 0.002283 | **0.0022** | 0.0053125 | **0.006** |

Quy tắc: `lo` = midpoint giữa clean extreme và positive typed gần nhất, làm tròn *về phía defect* (feature càng thấp càng xấu: lên; càng cao càng xấu: xuống); `hi` làm tròn *về phía clean* (ngược lại). Positive nằm ngoài khoảng tách được ghi nhận riêng (blur: `img_08_2`).

## Kết quả in-sample (ngưỡng frozen)

- Clean bị flag: **0/22**
- Defect bị bỏ: **2/34** (img_11_0, img_12_1)
- Defect có score > 0: **32/34**
- Type accuracy trên defect có type: **14/15** = 0.933
- Severity accuracy trên row có type: **36/37** = 0.973 (không nằm trong metric T02)

## Leave-one-group-out

- Tổng out-of-fold: **1/22 clean bị flag**, **3/34 defect bị bỏ**.
- `lo` blur thay đổi mạnh khi fold chứa `img_00_0` hoặc `img_09_0` bị giữ lại (xem bảng folds trong JSON): biên clean-vs-blur rất hẹp, đây là điểm yếu đã biết.

## Ghi chú nhãn

- `img_11_0`, `img_12_1`: severity 1 nhưng cả 4 feature đều ở mức tham chiếu nhóm; giữ nguyên nhãn người dùng, cần xem lại.
- 19 defect chỉ có severity, không có type → không dùng để fit ngưỡng type/severity; vẫn được dùng để kiểm tra binary recall.

**Freeze:** các hằng số trong `src/poc/t02_v1.py` khớp bảng trên; eval không được đọc để chỉnh ngưỡng.
