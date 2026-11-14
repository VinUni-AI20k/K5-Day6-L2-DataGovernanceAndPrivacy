# T07 Data Protocol — Baseline and Held-out Evaluation

## 1. Dataset and provenance

- Public fixture: `fixtures/t07_redaction/`.
- Inventory: 60 synthetic images at 640×360 pixels.
- Development split: 36 images.
- Evaluation split: 24 images.
- Source/license: synthetic fixture, CC0-1.0, as recorded in `manifest.csv`.
- The fixture contains cartoon faces and fictional `SYN-…` plates, not real PII.
- `python -m tools.verify_manifests` must report zero failing manifests before a run.

The committed `split` column in `images.csv` is used unchanged. Baseline and
PoC use the same candidate pool, split definition, and seed.

## 2. Ground-truth and leakage policy

The baseline and production pipeline must never read
`fixtures/t07_redaction/gt/`. Ground truth is available only to
`src.evaluate` when the instructor overlay is installed. Hidden labels are not
copied, inferred, reconstructed, or used to tune detector parameters.

The development split may be inspected to diagnose detector behaviour. The
evaluation split is held out from threshold selection. All parameters below
are frozen before official evaluation; they will not be changed after viewing
evaluation metrics.

## 3. Reproducibility and execution policy

- Seed: 42.
- Execution: CPU and fully offline.
- Network calls and automatic model downloads are forbidden.
- The OpenCV-bundled Haar cascade is loaded from `cv2.data.haarcascades`
  when the installed wheel includes its XML data.
- Input fixture images are read-only; redacted copies are written under the
  run output directory.
- Missing local dependencies or corrupt inputs cause an explicit failure.

Baseline command on Windows:

```powershell
.\.venv\Scripts\python.exe -m src.main `
  --config configs/lab.yaml `
  --track t07 `
  --pipeline src.t07_baseline `
  --output out/baseline `
  --run-name baseline `
  --offline `
  --seed 42
```

## 4. Default detector baseline

The no-review baseline uses:

1. OpenCV Haar cascade candidates for faces.
2. Canny edges, morphological closing, and rectangular contour filters for
   plate candidates.
3. Fixed proportional padding, clipped to image bounds.
4. Deterministic non-maximum suppression.
5. Strong pixelation inside each final candidate box.

Haar cascade scores from the basic OpenCV API are not calibrated
probabilities. Face confidence is therefore recorded as a fixed heuristic
value and must not be interpreted as a probability.

The installed OpenCV 5.0 wheel exposes `cv2.data.haarcascades` but may omit the
actual cascade XML. In that explicit missing-data case, the baseline uses a
declared offline fallback that searches for warm-coloured circular shapes in
the synthetic fixture. The selected backend is recorded as `face_backend` in
`run_info.json`. This fallback is fixture-oriented, is not a detector for real
people, and must not be represented as production-ready. It performs no
download and does not access ground truth.

Frozen parameters:

| Parameter | Value |
|---|---:|
| Face scale factor | 1.10 |
| Face minimum neighbours | 4 |
| Face minimum size | 18×18 px |
| Face padding | 15% |
| Plate minimum size | 25×8 px |
| Plate minimum area | 250 px² |
| Plate aspect ratio | 2.0–6.5 |
| Plate minimum rectangularity | 0.30 |
| Plate edge density | 0.04–0.65 |
| Plate padding | 10% |
| NMS IoU threshold | 0.50 |
| Seed | 42 |

The main baseline writes `out/baseline/redactions.csv` with at least:

```text
image_id,x,y,w,h
```

It also writes redacted image copies and provenance/decision artifacts. It has
no human-review stage and therefore records a `HOLD`/`BASELINE_ONLY` decision.

## 5. Trivial blur-all baseline

`out/baseline/redactions_blur_all.csv` contains one full-image box per input
image. This intentionally trivial comparator can obtain zero PII Miss Rate by
covering every pixel, but it should fail the over-redaction guardrail. It is
reported separately and must never be presented as the main PoC.

## 6. Evaluation contract

Primary metric:

```text
PII Miss Rate
= number of ground-truth PII regions with pixel coverage < 0.9
  / total number of ground-truth PII regions
```

Lower is better. The evaluation unit is one PII region.

Guardrail:

```text
Over-redaction rate <= 0.3
```

The primary result is valid only when the guardrail passes. Results are also
reported by PII type (`face`, `plate`), condition (`normal`, `small`, `dark`,
`blur`, `occluded`), and object size (`small`, `medium`, `large`). Baseline and
PoC evaluation use the same held-out split, seed, and evaluator.

If the instructor overlay is absent, evaluator exit code 2 is expected. The
team must not manufacture or guess the missing ground truth.

## 7. Privacy and reporting language

Raw real-world PII must not be uploaded to a public repository or cloud
service. Outputs are described as **redacted** or **pseudonymised**, not fully
anonymous. This technical experiment does not claim automatic compliance with
GDPR or Vietnamese law; legal and DPO review remain necessary.
