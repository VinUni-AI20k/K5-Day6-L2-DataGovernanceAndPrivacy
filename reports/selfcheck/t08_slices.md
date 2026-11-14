# T08 · Slices, CI, failure cases (tự sinh bằng tools/t08_slices.py)

Chấm trên **bộ self-check** `reports/selfcheck/t08_expected.csv` (158 dòng, C gán tay theo chính sách đã chốt — không phải GT giảng viên). Cùng data, seed 42, `--offline`.

## 1. Phân bố action & Wilson 95% CI

| Run | delete | retain_legal_hold | escalate | Completeness (Wilson CI) | Exception acc (Wilson CI) | False-delete |
|---|---|---|---|---|---|---|
| baseline | 10 | 0 | 0 | 8/102 = 0.078 [0.040, 0.147] | 0/56 = 0.000 [0.000, 0.064] | 2 |
| poc | 102 | 40 | 16 | 102/102 = 1.000 [0.964, 1.000] | 56/56 = 1.000 [0.936, 1.000] | 0 |
| ablation | 126 | 4 | 28 | 102/102 = 1.000 [0.964, 1.000] | 20/56 = 0.357 [0.245, 0.488] | 24 |

## 2. Slice: accuracy theo `artefact_type` (đúng action / số dòng)

| artefact_type | N | baseline | poc | ablation |
|---|---|---|---|---|
| annotation | 33 | 0.000 | 1.000 | 0.818 |
| backup | 10 | 0.000 | 1.000 | 1.000 |
| embedding | 30 | 0.000 | 1.000 | 0.800 |
| face_crop | 30 | 0.000 | 1.000 | 0.800 |
| frame | 33 | 0.000 | 1.000 | 0.818 |
| raw_video | 10 | 0.800 | 1.000 | 1.000 |
| training_export | 12 | 0.000 | 1.000 | 0.000 |

## 3. Slice: accuracy theo `expected_action`

| expected_action | N | baseline | poc | ablation |
|---|---|---|---|---|
| delete | 102 | 0.078 | 1.000 | 1.000 |
| retain_legal_hold | 40 | 0.000 | 1.000 | 0.100 |
| escalate | 16 | 0.000 | 1.000 | 1.000 |

## 4. Ablation `configs/t08_policy_backup_only.yaml` (hold chỉ thừa kế cho backup)

- Xoá nhầm **24** dòng ngoại lệ; theo type: {'frame': 6, 'face_crop': 6, 'embedding': 6, 'annotation': 6}; theo request: {'DR-002': 12, 'DR-005': 12}.
- Kết luận: thừa kế legal hold xuống **toàn bộ cây con** (R3) là cần thiết — chỉ giữ backup thì frame/crop/embedding/annotation sinh ra từ raw bị hold vẫn bị xoá.

## 5. Failure cases (baseline `src.t08.baseline`)

**FC1 — xoá nhầm ngoại lệ legal hold.**
- `out/baseline/actions.csv`: `DR-002,a0043,delete` · `data_graph.json`: type=raw_video, subject_ids=['subj_03'], legal_hold=`LH-2026-03`, filename=`drive_subj_03_003.mp4` → kỳ vọng `retain_legal_hold`.
- `out/baseline/actions.csv`: `DR-005,a0099,delete` · `data_graph.json`: type=raw_video, subject_ids=['subj_07'], legal_hold=`LH-2026-07`, filename=`drive_subj_07_007.mp4` → kỳ vọng `retain_legal_hold`.
- Root cause: baseline chỉ khớp theo tên file raw, **không đọc `legal_hold`** → vi phạm hold, không hoàn tác được.

**FC2 — chỉ xoá raw, bỏ sót lineage (DR-001).** Baseline xoá 1/17 artefact trong phạm vi; còn sót 13 artefact phải xoá: {'frame': 3, 'face_crop': 3, 'embedding': 3, 'annotation': 3, 'backup': 1}.
- Ví dụ: backup ['a0016'] vẫn nằm trong `mock://glacier/backup/a0016`; embedding ['a0019', 'a0023', 'a0027'] còn trong vector-db.
- Root cause: baseline **không duyệt lineage** (cha → backup/frame → crop/embedding/annotation).

## 6. Latency / compute

| Run | runtime_seconds | N dòng | ms / dòng | máy |
|---|---|---|---|---|
| baseline | 0.0307 | 10 | 3.07 | Python 3.12.0, Windows-11-10.0.26200-SP0 |
| poc | 0.1874 | 158 | 1.19 | Python 3.12.0, Windows-11-10.0.26200-SP0 |
| ablation | 0.2347 | 158 | 1.49 | Python 3.12.0, Windows-11-10.0.26200-SP0 |
