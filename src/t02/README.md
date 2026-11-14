# T02 · Giao diện giữa các module (chốt bởi TV1)

Quy ước chung
- Đầu vào: `images` = bảng `images.csv` (cột `image_id, path, camera_id, light, split`).
  Đường dẫn ảnh đầy đủ = `root / path`, với `root = ctx.input_dir`.
- Mỗi hàm trả **đúng 1 dòng cho mỗi ảnh, đủ 96 ảnh** (cả dev và eval), có cột `image_id` (str).
- Không đọc `fixtures/*/gt/`. Mọi ngưỡng / trọng số / trung vị chỉ tính trên `split == "dev"`.
- Chạy lại phải ra cùng kết quả (seed 42, không random nếu không cần).

| File | Chủ | Hàm | Cột trả về |
|---|---|---|---|
| `feat_sharpness.py` | TV3 | `compute(images, root) -> DataFrame` | `image_id, lap_var, lap_tile_min, blockiness` (+ `lap_norm` sau khi chuẩn hoá) |
| `feat_exposure.py` | TV4 | `compute(images, root) -> DataFrame` | `image_id, luma_mean, luma_p05, luma_p95, sat_frac, sat_tile_max` (+ `luma_rel`) |
| `score.py` | TV5 | `combine(feats, meta, params) -> DataFrame` | `image_id, score, pred_defect_type, pred_action, reason` |
| `review_step.py` | TV5 | `run(ctx, scored) -> DataFrame` | như `scored`, đã áp override; ghi `contact_sheet.html`, audit log |
| `baseline.py` | TV2 | `run(ctx)` | ghi `ranked_review.csv` + `decision.json` |

Ý nghĩa giá trị
- `lap_var`, `lap_tile_min`: càng **cao** càng **nét**. `blockiness`: càng cao càng nhiều lỗi nén.
- `luma_*`: thang 0–255. `sat_frac`, `sat_tile_max`: tỉ lệ 0–1 pixel cháy sáng (> 245).
- `score`: càng **cao** càng **cần review trước**.
- `pred_defect_type` ∈ {`none`, `blur`, `glare`, `dark`, `compression`}; `pred_action` ∈ {`KEEP`, `RECAPTURE`}.

Bản khung (push trước phút 30, tạm trả 0)

```python
import pandas as pd
from pathlib import Path

def compute(images: pd.DataFrame, root: Path) -> pd.DataFrame:
    out = images[["image_id"]].copy()
    out["lap_var"] = 0.0          # đổi tên cột theo bảng ở trên
    return out
```
