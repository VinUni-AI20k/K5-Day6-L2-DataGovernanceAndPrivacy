# 06 · Result slices (phần C — QA / metric)

> Nguồn: `reports/selfcheck/t08_slices.md` (sinh bằng `python -m tools.t08_slices`), chấm trên self-check, seed 42.

**Slice theo `expected_action`** (accuracy = đúng action / N)

| Slice | N | Baseline | PoC | Ablation | Ghi chú |
|---|---|---|---|---|---|
| delete | 102 | 0.078 | 1.000 | 1.000 | baseline chỉ xoá raw |
| retain_legal_hold | 40 | 0.000 | 1.000 | 0.100 | ablation mất thừa kế hold |
| escalate | 16 | 0.000 | 1.000 | 1.000 | |

**Slice theo `artefact_type`**

| Slice | N | Baseline | PoC | Ablation | Ghi chú |
|---|---|---|---|---|---|
| raw_video | 10 | 0.800 | 1.000 | 1.000 | baseline sai 2 raw bị hold |
| backup | 10 | 0.000 | 1.000 | 1.000 | |
| frame | 33 | 0.000 | 1.000 | 0.818 | |
| face_crop | 30 | 0.000 | 1.000 | 0.800 | |
| embedding | 30 | 0.000 | 1.000 | 0.800 | |
| annotation | 33 | 0.000 | 1.000 | 0.818 | |
| training_export | 12 | 0.000 | 1.000 | 0.000 | export là hậu duệ crop bị hold |

- **Failure case 1 — xoá nhầm ngoại lệ (baseline).** `out/baseline/actions.csv` có `DR-002,a0043,delete`; trong `data_graph.json` `a0043` là raw_video của subj_03 với `legal_hold = LH-2026-03` (tương tự `DR-005,a0099,delete`, `LH-2026-07`). **Root cause:** baseline chỉ khớp tên file, không đọc `legal_hold` → xoá dữ liệu đang bị giữ pháp lý, không hoàn tác được. PoC: R2 → `retain_legal_hold`, có test `test_legal_hold_never_deleted`.
- **Failure case 2 — chỉ xoá raw, bỏ sót lineage (baseline, DR-001).** Baseline xoá 1/17 artefact trong phạm vi; còn sót 13 artefact phải xoá (3 frame · 3 face_crop · 3 embedding · 3 annotation · 1 backup), ví dụ backup `a0016` ở `mock://glacier/backup/a0016`, embedding `a0019/a0023/a0027` trong vector-db. **Root cause:** không duyệt `parent_ids` → Completeness 8/102. PoC: `graph.scope` duyệt cây.
- **Latency / compute** (Windows 11, Python 3.12.0, AMD64): PoC 0.1874 s / 158 dòng = **1.19 ms/dòng**; baseline 0.0307 s / 10 dòng; ablation 0.2347 s / 158 dòng.
