# T07 demo plan

This plan is owned by the integration/report role. Replace every `PENDING`
marker with generated evidence before the demo; do not type metric values by
hand.

## Slide 1 — Risk and contract

- Risk: missed faces/plates expose PII; excessive redaction destroys utility.
- Input: 60 synthetic 640×360 images (36 dev, 24 eval).
- Output: `redactions.csv` plus redacted image copies and audit evidence.
- Primary: PII Miss Rate at coverage 0.9, constrained by over-redaction ≤0.3.

## Slide 2 — Offline data flow

```text
manifest/images
  -> detector + padded candidate boxes
  -> risk score and top-15 review queue
  -> approve/reject/edit/escalate
  -> final redactions and redacted images
  -> operational decision and evaluation report
```

Evidence to capture:

- `out/poc/contact_sheet.html`
- one original image with candidate boxes
- the corresponding final redacted image

## Slide 3 — Human review and audit

- Show one approved region.
- Show one edited/rejected region.
- Show its append-only event from `out/poc/audit_log.jsonl`.
- Show `out/poc/decision.json` and explain the reason code.

## Slide 4 — Baseline versus PoC

Generate this slide from:

```text
reports/table1_baseline_vs_poc.md
reports/slices_baseline.csv
reports/slices_poc.csv
```

Include the trivial blur-all baseline and explain why it fails the
over-redaction guardrail even if its miss rate is zero.

## Slide 5 — Failure cases and limitations

- Small/dark/occluded faces can be missed.
- Large padding can remove useful downstream signal.
- Raw PII must never be uploaded to cloud services.
- Redaction is described as pseudonymisation, not guaranteed anonymisation.

## Live demo commands (Windows)

```powershell
.\.venv\Scripts\python.exe -m tools.preflight
.\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t07 --output out/poc --run-name poc --offline --seed 42
.\.venv\Scripts\python.exe -m pytest -q --basetemp out\pytest-tmp -p no:cacheprovider
```
