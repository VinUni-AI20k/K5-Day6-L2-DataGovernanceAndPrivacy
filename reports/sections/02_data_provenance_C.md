# 02 · Data & provenance (phần C — Data & fixtures)

> Nguồn số liệu: `reports/t08_data_profile.md` (sinh bằng `python -m tools.t08_profile`), `fixtures/t08_deletion/manifest.csv`.

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| eval (toàn bộ, không chia) | 10 request · 212 artefact · 158 cặp (request, artefact) trong phạm vi | `fixtures/t08_deletion/` — `synthetic:tools/make_fixtures.py (seed 42)` | CC0-1.0 (synthetic, generated for AI20K Day06) | Có — không chứa người thật |

- **Schema:**
  - `requests.json`: `request_id`, `subject_id`, `deadline` (+30 ngày), `identity_verified` (cả 10 = true).
  - `data_graph.json`: 212 artefact = 15 `raw_video` · 15 `backup` · 45 `frame` · 45 `face_crop` · 45 `embedding` · 45 `annotation` · 2 `training_export`; trường quyết định: `subject_ids`, `parent_ids`, `legal_hold`, `acl`, `origin_known`.
  - Nhãn action: `delete` / `retain_legal_hold` / `escalate`.
- **Seed:** 42. **Không chia dev/eval:** chỉ có 10 request; chính sách là luật (R1–R8), không có tham số học/tune; luật được chốt ở phút 30 trước khi nhìn kết quả chấm → toàn bộ 158 cặp là tập đánh giá.
- **`manifest.csv` verified (sha256): có** — `python -m tools.verify_manifests` → `OK fixtures\t08_deletion\manifest.csv`. Sai hash → `src.main` exit 2 (có test `test_tampered_input_fails`).
- **Case catalog** (16 artefact ngoại lệ cài sẵn): 2 raw bị legal hold (`a0043` LH-2026-03 → 14 hậu duệ; `a0099` LH-2026-07 → 15 hậu duệ), 1 backup ACL `vendor-x` (`a0156`), 3 embedding `origin_known=false` (`a0075/a0079/a0083`), 8 frame/annotation dùng chung 2 người, 2 training export (10 và 9 người). Lineage mâu thuẫn ở 4 frame (`a0011, a0067, a0123, a0179`: con có subject mà cha không có) → `data-catalog` REWORK.
- **Dữ liệu thật & GT:** không dùng dữ liệu thật. Repo học viên không có `fixtures/t08_deletion/gt/` → nhóm dùng **bộ self-check** `reports/selfcheck/t08_expected.csv` (158 dòng = 102 delete · 40 retain_legal_hold · 16 escalate), do C gán tay theo chính sách đã chốt + case catalog, **độc lập với người viết luật (B)** và commit trước khi chạy PoC lên nó (commit `data(t08): hand-labelled self-check set (frozen)`).
