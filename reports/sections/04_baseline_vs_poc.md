# 04 · Baseline vs PoC (phần C — QA / metric)

- **Baseline** (`--pipeline src.t08.baseline`, B): khớp tên file `drive_<subject>_*.mp4` → chỉ xoá đúng 1 raw video / request; không đọc lineage, `legal_hold`, ACL.
- **PoC** (`src.pipeline` + `configs/t08_policy.yaml` v1.0): duyệt lineage tìm phạm vi, quyết bằng `subject_ids`, chính sách R1–R8 (luật đầu tiên khớp thắng), ngoại lệ vào hàng chờ DPO.
- **Cùng data / cùng seed:** cùng `fixtures/t08_deletion` (sha256 đã kiểm), seed 42, `--offline`, cùng bộ chấm 158 dòng.

**Bảng 1 · Baseline vs PoC** — chấm trên **self-check** (`reports/selfcheck/t08_expected.csv`), **không phải GT giảng viên**.
Output của `python -m src.compare reports/selfcheck/metrics_baseline_selfcheck.json reports/selfcheck/metrics_poc_selfcheck.json` (file `reports/selfcheck/table1_selfcheck.md`):

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Deletion Completeness** (must-delete artefacts deleted / must-delete artefacts) | all | 0.0784 | 1.0000 | 0.9216 | +1175.0% | higher | 158 |
| False-delete count (count (target 0): exceptions deleted + deletes outside request scope) | all | 2.0000 | 0.0000 | -2.0000 | -100.0% | lower | None |
| Exception handling accuracy (legal-hold/escalate rows handled as expected / such rows) | all | 0.0000 | 1.0000 | 1.0000 | baseline=0 | higher | None |
| Audit trace completeness (actions with an audit entry / actions) | all | 1.0000 | 1.0000 | 0.0000 | +0.0% | higher | None |
| Runtime / 100 items (s) | all | 0.3070 | 0.1186 | | | lower | |

Ghi chú đọc bảng:
- Baseline Completeness = 8/102; Exception accuracy **baseline = 0** (0/56) nên không tính % cải thiện.
- Baseline Audit = 1.0 chỉ vì nó có 10 action (10/10 có log) — không có nghĩa là bao phủ đủ.
- PoC đạt 1.0 / 0 vì self-check được gán **theo đúng chính sách nhóm**: con số này chứng minh code làm đúng chính sách đã chốt, **không** chứng minh chính sách đúng luật; cần GT giảng viên / DPO.
- Wilson 95% CI (`reports/selfcheck/t08_slices.md`): PoC Completeness 102/102 [0.964, 1.000]; Exception acc 56/56 [0.936, 1.000]. Baseline Completeness 8/102 [0.040, 0.147].

**Ablation** — `configs/t08_policy_backup_only.yaml` (hold chỉ thừa kế cho `backup`), chấm cùng self-check:

| Run | delete | retain_legal_hold | escalate | Completeness | Exception acc | False-delete |
|---|---|---|---|---|---|---|
| PoC | 102 | 40 | 16 | 1.000 | 1.000 (56/56) | **0** |
| Ablation | 126 | 4 | 28 | 1.000 | 0.357 (20/56) | **24** |

→ Bỏ thừa kế hold cho cây con làm **24** dòng bị xoá nhầm (6 frame · 6 face_crop · 6 embedding · 6 annotation, toàn ở DR-002 và DR-005). R3 là luật bắt buộc.

Lệnh chính thức (chỉ chạy được khi giảng viên chép `gt/`):
```
python -m src.evaluate --track t08 --pred out/baseline/actions.csv --run-name baseline --out reports/metrics_baseline.json
python -m src.evaluate --track t08 --pred out/poc/actions.csv --run-name poc --out reports/metrics_poc.json
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
```
