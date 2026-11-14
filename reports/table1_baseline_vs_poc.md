Baseline: `baseline` (git 1af063c, seed 42) · PoC: `poc` (git 1af063c, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Deletion Completeness** (must-delete artefacts deleted / must-delete artefacts) | all | 0.0727 | 0.9273 | 0.8545 | +1175.0% | higher | 158 |
| False-delete count (count (target 0): exceptions deleted + deletes outside request scope) | all | 2.0000 | 0.0000 | -2.0000 | -100.0% | lower | None |
| Exception handling accuracy (legal-hold/escalate rows handled as expected / such rows) | all | 0.0000 | 1.0000 | 1.0000 | baseline=0 | higher | None |
| Audit trace completeness (actions with an audit entry / actions) | all | 1.0000 | 1.0000 | 0.0000 | +0.0% | higher | None |
| Runtime / 100 items (s) | all | 0.9630 | 0.2604 | | | lower | |
