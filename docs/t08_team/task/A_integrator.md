# Người A — Lead / Integrator

**Sở hữu:** `configs/lab.yaml` · `src/pipeline.py` · `src/t08/store.py` · tag Git · demo · report 00, 08
**Code mẫu:** [code_mau/src/pipeline.py](code_mau/src/pipeline.py), [code_mau/src/t08/store.py](code_mau/src/t08/store.py)
**Đầu vào từ người khác:** `graph.py`, `policy.py` (B) · `review.py` (D) · test (C)

---

## A1 · Phút 0–10 — Chuẩn bị repo cho cả nhóm

1. Commit fix CRLF (đã có file `.gitattributes` chưa commit):
   ```powershell
   git add .gitattributes
   git commit -m "chore: keep fixture bytes stable on Windows (CRLF)"
   ```
2. Sửa `configs/lab.yaml`:
   ```yaml
   group_id: G07                      # số nhóm thật
   owner: "Ten DPO - Data Protection Officer"
   track_config: tracks/t08.yaml
   track: t08
   input: fixtures/t08_deletion
   output: out/
   seed: 42
   offline: true
   strict_provenance: true
   params:
     dry_run: true                    # A6 sẽ đổi false khi chạy xoá mock
     budget: 100                      # đủ chứa 56 ngoại lệ trong hàng chờ
   ```
3. Tạo `src/t08/__init__.py` (rỗng). Chép thư mục `V:\task` vào repo (ví dụ `docs/t08_team/`) để cả nhóm pull được.
4. Kiểm tra rồi push:
   ```powershell
   .\.venv\Scripts\python.exe -m tools.preflight      # 0 FAIL
   .\.venv\Scripts\python.exe -m pytest -q            # 0 failed
   git add configs/lab.yaml src/t08/__init__.py docs/t08_team
   git commit -m "chore: select track t08, group config"
   git push
   ```
5. Nhắn nhóm: `git pull`.

**Xong khi:** cả 4 máy chạy preflight 0 FAIL.

## A2 · Phút 10–30 — Chủ trì họp chốt chính sách

1. Cả nhóm đọc `00_CHUNG.md` §1–§2 (5 phút).
2. Biểu quyết 4 điểm: (a) legal hold thừa kế cả cây con, (b) artefact chung → escalate, (c) 2 người cùng yêu cầu vẫn escalate, (d) phạm vi = `subject_ids`.
3. Chốt hợp đồng hàm (không ai đổi chữ ký nếu chưa báo):
   ```python
   graph.load_graph(path) -> dict[aid, artefact]
   graph.children_map(arts) -> dict[parent, [child]]
   graph.ancestors(arts, aid) -> set
   graph.scope(arts, children, subject_id) -> sorted list
   graph.lineage_warnings(arts) -> list[dict]
   policy.load_policy(path) -> dict
   policy.decide(aid, arts, req, policy) -> (action, reason_code, rule_id)
   review.build_queue(actions, budget) -> DataFrame (REVIEW_COLUMNS)
   review.render_review_table(queue, path) -> None
   review.apply_review(actions, reviewed, audit) -> DataFrame
   MockStore(state_path).execute(actions, audit, fail_after=None) -> dict
   ```
4. Chốt cột DataFrame `actions` (cột đầu là id):
   `item_id` ("DR-001:a0017") · `request_id` · `artefact_id` · `artefact_type` · `action` · `reason_code` · `rule_id` · `score` · `reviewed_by`
5. C ghi chính sách vào `reports/metric_contract.md` và commit.

## A3 · Phút 30–50 — Khung pipeline chạy được với stub

Mục tiêu: `src.main` **exit 0** trước khi B/D xong, để ai cũng chạy được.

1. Mở `src/pipeline.py`, thay toàn bộ bằng khung sau (stub: mọi artefact có subject → delete):
   ```python
   import json
   import pandas as pd
   from .common.decision import Decision, write_decision
   from .common.manifest import verify_manifest

   COLS = ["item_id", "request_id", "artefact_id", "artefact_type", "action",
           "reason_code", "rule_id", "score", "reviewed_by"]

   def load(ctx):
       problems = verify_manifest(ctx.input_dir / "manifest.csv")
       if problems:
           raise ValueError(f"provenance check failed: {problems[:3]}")
       arts = json.loads((ctx.input_dir / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]
       return {"requests": json.loads((ctx.input_dir / "requests.json").read_text(encoding="utf-8")),
               "arts": {a["artefact_id"]: a for a in arts}}

   def run(ctx):
       if ctx.track != "t08":
           raise NotImplementedError(f"this group pipeline only implements t08, got {ctx.track}")
       data = load(ctx)
       rows = [{"item_id": f"{r['request_id']}:{aid}", "request_id": r["request_id"], "artefact_id": aid,
                "artefact_type": a["type"], "action": "delete", "reason_code": "STUB", "rule_id": "STUB",
                "score": 0, "reviewed_by": ""}
               for r in data["requests"] for aid, a in sorted(data["arts"].items())
               if r["subject_id"] in a["subject_ids"]]
       pd.DataFrame(rows, columns=COLS).to_csv(ctx.out("actions.csv"), index=False)
       write_decision(Decision("HOLD", "STUB", "pipeline stub", ctx.config["owner"], "t08-all"),
                      ctx.out("decision.json"), ctx.out("decision_log.csv"))
   ```
   > ⚠ Dòng `if ctx.track != "t08": raise NotImplementedError` là **bắt buộc**: test có sẵn
   > `tests/test_cli.py::test_template_pipeline_fails_clearly_not_silently` chạy pipeline với T02 và chờ exit 3.
   > Thiếu dòng này → pytest đỏ (đã gặp khi chạy thử).
2. Chạy:
   ```powershell
   .\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t08 --output out/poc --run-name poc --offline --seed 42
   ```
3. Kiểm: exit 0, `out/poc/actions.csv` có 158 dòng.
4. Commit `feat(pipeline): t08 skeleton with stub policy`, push.

## A4 · Phút 50–90 — Nối module thật của B và D + audit "plan"

Khi B push `graph.py`/`policy.py` và D push `review.py`:
1. Thay `src/pipeline.py` bằng bản [code_mau/src/pipeline.py](code_mau/src/pipeline.py). Các phần chính:
   - `load()`: kiểm manifest → đọc requests + graph (`graph.load_graph`) + policy (`policy.load_policy("configs/t08_policy.yaml")`).
   - `process()`: với mỗi request, `graph.scope(...)` → `policy.decide(...)` cho từng artefact →
     1 dòng `actions` + **1 dòng audit `plan:<action>` với `item_id=artefact_id`** (bắt buộc cho metric Audit completeness).
     Ghi `deletion_plan.csv` (đây là **dry-run**: kế hoạch, chưa xoá gì).
   - `run()`: `review.build_queue` → `review_queue.csv` + `review_queue.html`; nếu có `review_queue_reviewed.csv` → `review.apply_review`; ghi `actions.csv`.
2. Chạy lại, kiểm:
   ```powershell
   .\.venv\Scripts\python.exe -c "import pandas as pd; a=pd.read_csv('out/poc/actions.csv'); print(len(a), a.action.value_counts().to_dict())"
   ```
   Kỳ vọng: `158 {'delete': 102, 'retain_legal_hold': 40, 'escalate': 16}`; `review_queue.csv` 56 dòng.
3. Commit `feat(pipeline): wire lineage, policy and review queue`.

## A5 · Phút 90–120 — `src/t08/store.py`: kho mock idempotent + resume

1. Chép [code_mau/src/t08/store.py](code_mau/src/t08/store.py). Ý chính:
   - Trạng thái lưu ở `out/poc/mock_store_state.json`: `{"deleted": {artefact_id: {request_id, ts}}}`.
   - `execute()` chỉ xử lý dòng `action == "delete"`; artefact đã có trong state → **bỏ qua** + log `delete_skipped_already_deleted` (idempotent).
   - Lưu file **sau mỗi lần xoá** → bị ngắt giữa chừng thì lần sau chạy tiếp (resume).
   - `fail_after=N` để giả lập crash (C dùng trong test).
2. Trong `run()`: chỉ gọi store khi `dry_run` = false:
   ```python
   if not ctx.param("dry_run", True):
       ctx.stats["store"] = MockStore(ctx.out("mock_store_state.json")).execute(actions, ctx.audit)
   ```
3. Thử: đổi `params.dry_run: false` trong `lab.yaml`, chạy 2 lần → `run_info.json` lần 1 `deleted_new: 102`, lần 2 `deleted_new: 0, skipped_already_deleted: 102`.
4. Commit `feat(t08): idempotent MockStore with resume`.

## A6 · Phút 120–145 — Quyết định từng request

1. Hàm `decide_requests()` trong code mẫu:
   - còn ngoại lệ `reviewed_by == ""` → **HOLD** `PENDING_DPO_REVIEW`
   - đã ký hết nhưng có `retain_legal_hold` → **HOLD** `LEGAL_HOLD_ACTIVE`
   - còn lại → **GO** `ERASURE_COMPLETE` / `ERASURE_DONE_EXCEPTIONS_SIGNED`
   - `graph.lineage_warnings` khác rỗng → **REWORK** scope `data-catalog`
   - tổng: `decision.json` (GO nếu 10/10 GO, ngược lại HOLD `OPEN_REQUESTS`)
2. Mỗi quyết định ghi `out/poc/decisions/<request>.json` + 1 dòng `decision_log.csv` (`write_decision` tự làm).
3. Phối hợp D chạy vòng duyệt (D5). Kỳ vọng sau khi D ký 2 dòng DR-006: **DR-006 GO**, còn lại HOLD, `data-catalog` REWORK.
4. Commit `feat(t08): per-request GO/HOLD/REWORK decisions`.

## A7 · Phút 145–170 — Clean start + kiểm tra toàn bộ

```powershell
Remove-Item -Recurse -Force out
.\.venv\Scripts\python.exe -m src.main --offline --seed 42                       # dùng lab.yaml, phải exit 0
.\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t08 --pipeline src.t08.baseline --output out/baseline --run-name baseline --offline --seed 42
.\.venv\Scripts\python.exe -m pytest -q                                          # 0 failed
```
Nhớ: chép lại `review_queue_reviewed.csv` của D vào `out/poc/` sau khi xoá `out/` (hoặc lưu bản gốc ở `reports/`). Sửa bug cùng cả nhóm.

## A8 · Phút 170–180 — Freeze demo
```powershell
git pull; .\.venv\Scripts\python.exe -m pytest -q
git tag -a demo-180m -m "Demo freeze at minute 180"
git push origin demo-180m
```

## Demo 3 phút (180–240)
1. Chạy lệnh PoC (exit 0, ~0.2 s).
2. Mở `out/poc/actions.csv` → lọc DR-002: toàn `retain_legal_hold`.
3. Mở `review_queue.html` → dòng DR-006 đã ký → `decision_log.csv`: DR-006 GO.
4. Chạy lại lần 2 → `deleted_new: 0` (idempotent).

## A9 · +24h
- Demo resume: chạy store với `fail_after=5` rồi chạy lại.
- Report mục 00 (Group ID, 4 thành viên + vai, Git URL, SHA 2 tag) + 08 (lệnh tái lập, test).
- `git tag -a final-24h -m "Final submission"` + push.

**Commit gợi ý:** `chore: t08 config + gitattributes` · `feat(pipeline): t08 skeleton` · `feat(pipeline): wire modules` · `feat(t08): MockStore` · `feat(t08): per-request decisions`
