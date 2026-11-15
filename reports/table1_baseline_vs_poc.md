Baseline: `baseline` (git e9e08fd, seed 42) · PoC: `poc_v1` (git e9e08fd, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Defect Recall@B** (GT defects in top-B / GT defects) | all | 0.8696 | 0.8696 | 0.0000 | +0.0% | higher | 40 |
| Precision@B (GT defects in top-B / B) | all | 1.0000 | 1.0000 | 0.0000 | +0.0% | higher | 40 |
| Defect-type accuracy (GT defects) (fraction) | all | 0.3043 | 0.8696 | 0.5652 | +185.7% | higher | 23 |
| False alarm in top-B (clean images in top-B / clean images) | light=day | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | 20 |
| False alarm in top-B (clean images in top-B / clean images) | light=dusk | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | 4 |
| False alarm in top-B (clean images in top-B / clean images) | light=night | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | 16 |
| Runtime / 100 items (s) | all | 0.3694 | 0.7231 | | | lower | |
