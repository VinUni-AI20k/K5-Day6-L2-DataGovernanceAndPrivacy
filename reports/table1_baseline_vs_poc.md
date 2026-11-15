Baseline: `baseline` (git 3919d8c, seed 42) · PoC: `poc` (git 3919d8c, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **PII Miss Rate** (GT regions with coverage < 0.9 / GT regions) | all | 0.5781 | 0.1094 | -0.4688 | -81.1% | lower | 64 |
| Region recall (1 - miss rate) | all | 0.4219 | 0.8906 | 0.4688 | +111.1% | higher | 64 |
| Over-redaction rate (redacted px outside GT / redacted px) | all | 0.7165 | 0.1978 | -0.5188 | -72.4% | lower | None |
| Guardrail: Over-redaction rate <= 0.3 (1 = pass, 0 = fail (constrained primary)) | all | 0.0000 | 1.0000 | 1.0000 | baseline=0 | higher | None |
| PII Miss Rate (fraction) | type=face | 0.2571 | 0.0857 | -0.1714 | -66.7% | lower | 35 |
| PII Miss Rate (fraction) | type=plate | 0.9655 | 0.1379 | -0.8276 | -85.7% | lower | 29 |
| PII Miss Rate (fraction) | condition=blur | 0.5000 | 0.3000 | -0.2000 | -40.0% | lower | 10 |
| PII Miss Rate (fraction) | condition=dark | 0.8125 | 0.0000 | -0.8125 | -100.0% | lower | 16 |
| PII Miss Rate (fraction) | condition=normal | 0.3750 | 0.0417 | -0.3333 | -88.9% | lower | 24 |
| PII Miss Rate (fraction) | condition=occluded | 0.7000 | 0.3000 | -0.4000 | -57.1% | lower | 10 |
| PII Miss Rate (fraction) | condition=small | 0.7500 | 0.0000 | -0.7500 | -100.0% | lower | 4 |
| Runtime / 100 items (s) | all | 0.4020 | 5.7822 | | | lower | |
