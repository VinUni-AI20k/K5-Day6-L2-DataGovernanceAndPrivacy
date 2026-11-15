Baseline: `baseline_blurall` (git 3919d8c, seed 42) · PoC: `poc` (git 3919d8c, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **PII Miss Rate** (GT regions with coverage < 0.9 / GT regions) | all | 0.0000 | 0.1094 | 0.1094 | baseline=0 | lower | 64 |
| Region recall (1 - miss rate) | all | 1.0000 | 0.8906 | -0.1094 | -10.9% | higher | 64 |
| Over-redaction rate (redacted px outside GT / redacted px) | all | 0.9882 | 0.1978 | -0.7904 | -80.0% | lower | None |
| Guardrail: Over-redaction rate <= 0.3 (1 = pass, 0 = fail (constrained primary)) | all | 0.0000 | 1.0000 | 1.0000 | baseline=0 | higher | None |
| PII Miss Rate (fraction) | type=face | 0.0000 | 0.0857 | 0.0857 | baseline=0 | lower | 35 |
| PII Miss Rate (fraction) | type=plate | 0.0000 | 0.1379 | 0.1379 | baseline=0 | lower | 29 |
| PII Miss Rate (fraction) | condition=blur | 0.0000 | 0.3000 | 0.3000 | baseline=0 | lower | 10 |
| PII Miss Rate (fraction) | condition=dark | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | 16 |
| PII Miss Rate (fraction) | condition=normal | 0.0000 | 0.0417 | 0.0417 | baseline=0 | lower | 24 |
| PII Miss Rate (fraction) | condition=occluded | 0.0000 | 0.3000 | 0.3000 | baseline=0 | lower | 10 |
| PII Miss Rate (fraction) | condition=small | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | 4 |
| Runtime / 100 items (s) | all | 0.1577 | 5.7822 | | | lower | |
