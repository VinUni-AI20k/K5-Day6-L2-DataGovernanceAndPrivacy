# Data & Provenance audit — t02

Input: `fixtures/t02_raw_qc` · reproduce with `python tools/data_audit.py --track t02`

## 1. Provenance

```
OK   · verify_manifest: all hashes match
WARN · CRLF fragility: 1 hashed text file(s) would break: ['images.csv']
```

## 2. Schema

```
OK   · columns present: image_id, path, camera_id, light, split
OK   · no null cells
OK   · image_id unique (96 rows)
```

## 3. Split

```
OK   · split is scene-disjoint (24 scenes)
WARN · eval strata with NO dev example (cannot calibrate a per-stratum threshold): cam_A/night
WARN · dev strata never seen at eval (calibration effort wasted): cam_A/dusk, cam_B/day
```

Images per (camera, light) × split:

| camera_id | light | dev | eval |
|---|---|---:|---:|
| cam_A | day | 24 | 20 |
| cam_A | dusk | 12 | 0 |
| cam_A | night | 0 | 8 |
| cam_B | day | 12 | 0 |
| cam_B | dusk | 4 | 4 |
| cam_B | night | 4 | 8 |

## 4. Image statistics

| camera_id | light | n | lap_median | lap_p10 | sat_mean | dark_mean | bright_mean |
|---|---|---:|---:|---:|---:|---:|---:|
| cam_A | day | 44 | 944.304 | 18.319 | 0.005 | 0.066 | 108.437 |
| cam_A | dusk | 12 | 777.316 | 285.56 | 0.001 | 0.053 | 87.103 |
| cam_A | night | 8 | 1578.123 | 248.098 | 0.0 | 0.254 | 29.097 |
| cam_B | day | 12 | 235.766 | 2.204 | 0.0 | 0.0 | 117.864 |
| cam_B | dusk | 8 | 174.464 | 10.741 | 0.0 | 0.201 | 71.991 |
| cam_B | night | 12 | 350.414 | 239.22 | 0.001 | 0.091 | 39.251 |

`lap_median` is the per-group sharpness level a global threshold would be compared against.

Per-image features written to `reports/data_stats_t02.csv`.

## 5. Verdict

`0 FAIL, 3 WARN`
