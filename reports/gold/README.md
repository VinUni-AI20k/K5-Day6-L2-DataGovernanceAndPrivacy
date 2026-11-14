# T07 internal labels (CVAT, COCO format)

`t07_cvat_coco.json`: bounding boxes for `face` (id 1) and `plate` (id 2) drawn by the team in CVAT
on the 60 synthetic fixture images in `fixtures/t07_redaction/images/` (640×360, CC0, no real PII).

**This is NOT the official ground truth.** The official GT (`fixtures/t07_redaction/gt/`) is held by the
instructor and is only read by `src.evaluate`.

Rules for using this file:

- `src/pipeline.py` and every module it imports must **never** read this file.
- Labels for the 24 `eval` images are for reporting only. Do **not** tune detector settings or thresholds on them.
  Use the 36 `dev` images for sanity checks.
- Boxes use COCO `[x, y, w, h]` pixel coordinates with the origin at the top-left corner.

Known gaps (to fix in CVAT and re-export):

- Some plates are missing: 16 images have no plate box, although every image shows `SYN-…` plates.
- Some small faces are missing, e.g. `pii_07`, `pii_19`, `pii_39`.
- Possible duplicate boxes: `pii_06` (ann 28/29) and `pii_47` (ann 206/207, 208/209); check `pii_32` (ann 149/151).
- No condition attributes: every box has `occluded: false`, so slice metrics (small/dark/blur/occluded) cannot be computed from this file.

Images were annotated in CVAT. That is acceptable only because the fixture is synthetic; real images with people
or plates must not be uploaded to cloud annotation tools.
