# T07 integration contract

This file freezes the interface between the T07 team modules. The production
pipeline must not read `fixtures/t07_redaction/gt/` and must run offline.

## Detector module (Person 1)

File: `src/t07_detector.py`

Required API:

```python
def detect_and_score(ctx, images: pandas.DataFrame) -> pandas.DataFrame:
    ...
```

Required output columns:

```text
region_id,image_id,type,x,y,w,h,confidence,score,reason,slice,path
```

- `region_id` is stable and unique for every candidate region.
- `type` is `face` or `plate`.
- boxes use pixel `x,y,w,h` with top-left origin and remain inside the image.
- `confidence` is in `[0,1]`.
- a larger `score` means the region should be reviewed earlier.
- `path` is relative to the fixture folder, for example `images/pii_01.jpg`.

## Review module (Person 3)

File: `src/t07_review.py`

Required API:

```python
def apply_review(ctx, candidates: pandas.DataFrame, reviewed: pandas.DataFrame) -> pandas.DataFrame:
    ...
```

Semantics:

- `approve`: keep the region unchanged;
- `reject`: remove the false-positive region;
- `edit`: parse `override_value` JSON and update `type,x,y,w,h`;
- `escalate`: keep the region but make the release decision `REWORK`;
- `skip`: unresolved and therefore not release-ready.

Every reject/edit/escalate action must append an event through `ctx.audit` with
the reviewer, region ID, before, after, and reason.

## Export module (Person 3)

File: `src/t07_export.py`

Required API:

```python
def export_redacted_images(ctx, regions: pandas.DataFrame, images: pandas.DataFrame) -> None:
    ...
```

The exporter writes redacted copies under `out/<run>/redacted_images/`. It must
never modify source fixture images. It must clamp or reject invalid boxes before
rendering; the integration layer independently validates geometry as a guardrail.

## Baseline module (Person 2)

File: `src/t07_baseline.py`

Required API:

```python
def run(ctx) -> None:
    ...
```

It writes `redactions.csv` and the normal run artifacts without human review.
The trivial blur-all baseline must be reported separately because it can reach a
zero miss rate while failing the over-redaction guardrail.
