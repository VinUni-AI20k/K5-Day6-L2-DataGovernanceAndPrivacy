# T02 — Baseline vs PoC v1 (40 nhan eval, B=20)

Tu dong tao boi `src.compare`, khong duoc sua tay.

| Chuan | Baseline | PoC v1 | Chenh lech |
|---|---:|---:|---:|
| Defect Recall@B (all) | 0.8696 | 0.8696 | +0.0000 |
| Defect-type accuracy (GT defects) (all) | 0.3043 | 0.8696 | +0.5652 |
| False alarm in top-B (light=day) | 0.0000 | 0.0000 | +0.0000 |
| False alarm in top-B (light=dusk) | 0.0000 | 0.0000 | +0.0000 |
| False alarm in top-B (light=night) | 0.0000 | 0.0000 | +0.0000 |
| Precision@B (all) | 1.0000 | 1.0000 | +0.0000 |

## Ket luan

- PoC v1 va baseline bang nhau tren Recall@20 (0.8696) va Precision@20 (1.0000), false alarm = 0 tat ca slice.
- PoC v1 thang ro tren Defect-type accuracy: 0.8696 vs 0.3043 (+0.5653).
- Nguong da freeze tren 56 nhan dev, khong chinh tren eval.
