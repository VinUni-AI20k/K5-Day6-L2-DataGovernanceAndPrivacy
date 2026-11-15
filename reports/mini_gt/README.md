# reports/mini_gt/ — bộ nhãn tự kiểm của nhóm (T07, chỉ split dev)

| File             | Nội dung                                                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gt_regions.csv` | 64 vùng PII (35 `face`, 29 `plate`) trên 12 ảnh `dev`: `image_id, region_id, type, x, y, w, h, condition, size, split, must_redact, label_source` |
| `images.csv`     | 12 dòng tương ứng của `fixtures/t07_redaction/images.csv` (evaluator dùng để lấy kích thước ảnh và giới hạn pool)                                 |

- Ảnh được chọn để phủ các điều kiện: thường (`pii_00, 21, 25, 30`), hoàng hôn (`pii_02`), đêm (`pii_08, 10, 14`), mờ (`pii_15, 19`), bị che khuất (`pii_27, 47`).
- Cách gán nhãn (`label_source`): `pre` = khung do bộ dò đề xuất (không padding), đã kiểm bằng mắt trên ảnh phóng 2× có lưới tọa độ, nới 1 px mỗi cạnh cho viền; `pre+edit` = khung đề xuất được sửa tay; `manual` = vùng bộ dò bỏ sót, người gán nhãn tự đo tọa độ.
- Đầu người đi bộ (nhìn từ sau) và biển báo không được gán nhãn, theo định nghĩa PII của đề.
- `condition`: `blur`/`dark` theo ảnh, `occluded` nếu mặt có vật che hoặc biển số bị vật khác che một phần, `small` nếu mặt có cạnh < 12 px hoặc biển số cao < 7 px, còn lại `normal`. `size`: diện tích < 200 px² = small, < 700 px² = medium, còn lại large.
- **Không phải ground truth chính thức.** Không có ảnh `eval` nào ở đây; pipeline không đọc thư mục này. Vì khung `pre` xuất phát từ chính bộ dò, số đo trên bộ này lạc quan cho PoC.

Lệnh dùng:

```bash
python -m src.evaluate --track t07 --gt reports/mini_gt/gt_regions.csv --split dev --pred out/poc/redactions.csv --run-name poc --out reports/metrics_poc.json
```
