# Usability rule (frozen before evaluation)

An image is **unusable** (positive class, `unusable=1`) if ANY of:

1. `severity == 2` for night / fog / blur / glare;
2. `glare` of severity >= 1 whose centre falls inside a labelled object box (object washed out);
3. `erase` (cut-out) removed a labelled object but the label file still lists it (label no longer valid).

Otherwise `unusable=0`. The GT for `holdout_transformed/` was produced with exactly this rule.
Groups may argue for a different rule in their report, but must evaluate with this one.
