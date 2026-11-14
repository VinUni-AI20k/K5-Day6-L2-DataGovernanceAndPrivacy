# Người B — Core algorithm (lineage + chính sách + baseline)

**Sở hữu:** `src/t08/graph.py` · `src/t08/policy.py` · `src/t08/baseline.py` · `configs/t08_policy.yaml` · `tests/test_t08_policy.py` · report 03
**Code mẫu:** [code_mau/src/t08/](code_mau/src/t08/) · [code_mau/configs/t08_policy.yaml](code_mau/configs/t08_policy.yaml) · [code_mau/tests/test_t08_policy.py](code_mau/tests/test_t08_policy.py)
**Đầu vào:** case catalog của C (C2) · nguồn luật của D (D2)

---

## B1 · Phút 0–10 — Setup
```powershell
git pull
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
git checkout -b b/algorithm
```

## B2 · Phút 10–30 — Soạn `configs/t08_policy.yaml`

1. Chép [code_mau/configs/t08_policy.yaml](code_mau/configs/t08_policy.yaml). Mỗi luật có 5 khoá:
   `id` · `when` (tên điều kiện trong `policy.py`) · `action` · `reason_code` · `source` (căn cứ, D bổ sung).
2. Thứ tự dòng = độ ưu tiên: R1 identity → R2 legal hold → R3 hold thừa kế → R4 ACL → R5 origin → R6 export → R7 multi-subject → R8 delete.
3. Ghi đầu file: `TEACHING EXAMPLE, not legal advice`.
4. Đưa cả nhóm duyệt trong buổi họp A2 → commit `feat(t08): policy rules v1 (frozen)`.

## B3 · Phút 30–45 — `src/t08/graph.py`

Chép [code_mau/src/t08/graph.py](code_mau/src/t08/graph.py), hiểu từng hàm:
| Hàm | Làm gì |
|---|---|
| `load_graph(path)` | đọc JSON → dict `artefact_id → artefact` |
| `children_map(arts)` | đảo `parent_ids` → `parent → [con]` (để BFS xuống) |
| `ancestors(arts, aid)` | đi ngược `parent_ids` tới gốc (dùng cho luật R3) |
| `scope(arts, children, subject_id)` | BFS từ mọi artefact có subject, **chỉ giữ con có subject** |
| `lineage_warnings(arts)` | con có subject mà không cha nào có → catalog thiếu (REWORK) |

Tự kiểm nhanh:
```powershell
.\.venv\Scripts\python.exe -c "from src.t08 import graph as g; a=g.load_graph('fixtures/t08_deletion/data_graph.json'); s=g.scope(a,g.children_map(a),'subj_01'); print(len(s),'a0011' in s,'a0012' in s); print([w['artefact_id'] for w in g.lineage_warnings(a)])"
```
Kỳ vọng: `17 True False` và `['a0011', 'a0067', 'a0123', 'a0179']`.
(`a0012` là crop **của subj_00** nằm dưới frame chung `a0011` — duyệt cây mù sẽ xoá nhầm nó.)

Commit `feat(t08): lineage graph + scope`.

## B4 · Phút 45–50 — Baseline `src/t08/baseline.py`

Đề: *"Xoá một bản raw theo filename, không tìm derived/backup."*
1. Chép [code_mau/src/t08/baseline.py](code_mau/src/t08/baseline.py): với mỗi request, xoá `raw_video` có `filename` bắt đầu bằng `drive_<subject_id>_`. Ghi `actions.csv` + audit + `decision.json`.
2. Chạy:
   ```powershell
   .\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t08 --pipeline src.t08.baseline --output out/baseline --run-name baseline --offline --seed 42
   ```
   Kỳ vọng: exit 0, `out/baseline/actions.csv` 10 dòng `delete` — **có cả `a0043` và `a0099` đang legal hold** (đây là failure mode 1 để C phân tích).
3. Commit `feat(t08): filename-only baseline`. Báo C.

## B5 · Phút 50–90 — `src/t08/policy.py`

1. Chép [code_mau/src/t08/policy.py](code_mau/src/t08/policy.py):
   - `CONDITIONS`: dict tên điều kiện → hàm `(artefact, arts, request) -> bool`.
   - `load_policy()`: đọc YAML, **báo lỗi nếu `when`/`action` không hợp lệ** (gõ sai YAML → fail rõ, không im lặng).
   - `decide()`: duyệt luật theo thứ tự, luật đầu tiên khớp → `(action, reason_code, rule_id)`.
2. Tự kiểm:
   ```powershell
   .\.venv\Scripts\python.exe -c "from src.t08 import graph as g, policy as p; a=g.load_graph('fixtures/t08_deletion/data_graph.json'); pol=p.load_policy('configs/t08_policy.yaml'); r={'identity_verified':True}; [print(x, p.decide(x,a,r,pol)) for x in ['a0043','a0045','a0156','a0075','a0011','a0211','a0017']]"
   ```
   Kỳ vọng: a0043 `LEGAL_HOLD_ACTIVE` · a0045 `LEGAL_HOLD_INHERITED` · a0156 `NO_PERMISSION_ACL` · a0075 `ORIGIN_UNKNOWN` · a0011 `MULTI_SUBJECT_SHARED` · a0211 `LEGAL_HOLD_INHERITED` (export là hậu duệ của crop bị hold) · a0017 `delete`.
3. Commit `feat(t08): policy engine`, push, báo A nối vào pipeline.

## B6 · Phút 90–145 — Test module + hỗ trợ ablation

1. Chép [code_mau/tests/test_t08_policy.py](code_mau/tests/test_t08_policy.py): 6 case luật + identity ưu tiên + scope + lineage warnings.
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q tests/test_t08_policy.py
   ```
2. Tạo biến thể cho ablation (C chạy): `configs/t08_policy_backup_only.yaml` — copy file chính, đổi R3 thành điều kiện mới `ancestor_legal_hold_backup` (chỉ áp cho `type == "backup"`), thêm điều kiện đó vào `CONDITIONS`. Kết quả mong đợi: 126 delete / 4 retain / 28 escalate. **Không** dùng biến thể này làm kết quả chính.
3. Commit `test(t08): policy rules` · `feat(t08): ablation policy variant`.

## B7 · Phút 145–170 — Report + hỗ trợ bug
- Report mục **03 Research & design**: data flow (load → scope → decide → review → store), vì sao BFS + lọc `subject_ids`, thứ tự ưu tiên luật, trade-off (giữ cả cây hold → completeness thấp hơn nhưng false-delete = 0), offline, references (GDPR Art.17, Luật 91/2025, NĐ 356/2025).
- Viết phần "thuật toán" cho mục 02 (C chủ trì mục 02).
- 1 slide thuật toán (sơ đồ cây + 8 luật).

## Câu hỏi debate nên tập
- Vì sao lọc theo `subject_ids` thay vì xoá cả cây con? (a0011 → a0012 của người khác)
- Vì sao hold thừa kế cả cây con, kể cả training export?
- a0067 thuộc 2 người đều yêu cầu xoá — sao không xoá luôn? (request độc lập theo thời gian, idempotent, DPO quyết)
- Nếu catalog thiếu subject ở raw (`lineage_warnings`) thì kết quả có tin được không?

**Commit gợi ý:** `feat(t08): policy rules v1` · `feat(t08): lineage graph` · `feat(t08): baseline` · `feat(t08): policy engine` · `test(t08): policy rules`
