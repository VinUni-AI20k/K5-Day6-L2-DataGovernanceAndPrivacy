# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Mọi con số dưới đây lấy từ file do script sinh ra (`out/*/run_info.json`, `out/poc/decision.json`,
> `out/poc/request_summary.csv`, `python -m tools.t08_selfcheck`). **Số chính thức** (`reports/metrics_*.json`,
> `reports/table1_baseline_vs_poc.md`) chỉ sinh được khi giảng viên cài `fixtures/t08_deletion/gt/` — repo học viên
> chạy `src.evaluate` báo *"ground truth file not found"*. Vì vậy Bảng 1 ghi rõ đâu là **tự kiểm** (đáp án nội bộ).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G02 |
| Challenge | T08 · Retention & Delete Request Simulator |
| Thành viên (6) + vai trò | P1. Bui Thanh Tan (Lead/Integrator) · P2. Nguyen Viet Minh Hoang - 2A202603281 (Data & fixtures) · P3. Nhat Nguyen / Edelxz (Core: lineage & policy) · P4. Nguyen Tien Dat / datpro-sudo (Core: review & thực thi) · P5. Nguyen Cong Bao Long (QA/metric + baseline) · P6. NhatNguyen28122003 (Human reviewer + report + slide) |
| Git URL | https://github.com/tantan294/K5-L2-ABC-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | ____ (P1 tạo bằng `make tag-demo`) |
| Tag `final-24h` (commit) | ____ (P1 tạo bằng `make tag-final`) |
| Deadline (giờ VN) | ____ |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? **Chủ thể dữ liệu** (xóa thiếu → bản sao/embedding định danh còn tồn tại, vi phạm quyền xóa); **tổ chức** (xóa nhầm dữ liệu đang bị legal hold → vi phạm nghĩa vụ lưu giữ chứng cứ; xóa dữ liệu của người khác trong artefact chung); **DPO/legal** phải giải trình.
- Điểm nghẽn cụ thể: một người có 14–18 artefact rải qua raw → backup → frame → face_crop → embedding/annotation → training export; xóa theo tên file chỉ chạm raw. Ngoại lệ (legal hold, ACL vendor, origin unknown, artefact nhiều subject) nằm lẫn trong lineage.
- Đầu vào → đầu ra: `data_graph.json` (212 artefact) + `requests.json` (10 yêu cầu) → `actions.csv` (request, artefact, action ∈ delete/retain_legal_hold/escalate) + `review_queue.csv` + `audit_log.jsonl` + `dry_run_diff.csv` + `decision.json`.
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): **HOLD** khi còn ngoại lệ chưa có người ký; **GO** khi mọi ngoại lệ đã được reviewer duyệt → thực thi kế hoạch xóa (mock), mục bị giữ được hẹn kiểm lại khi hết hold. Không có REWORK tự động.
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): (a) legal hold áp cho cả bản sao/dẫn xuất của chính dữ liệu bị giữ (`legal_hold_inherit: true`); (b) artefact nhiều subject phải che/tách, không xóa nguyên khối; (c) `vendor-x` là bên xử lý riêng, nhóm không có quyền xóa thay.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| toàn bộ (không chia split) | 212 artefact · 10 request · 158 cặp trong phạm vi | `fixtures/t08_deletion/` (synthetic: tools/make_fixtures.py seed 42) | CC0-1.0 | có |
| GT ẩn | `gt/gt_actions.csv` — chỉ giảng viên | repo private | — | có |

- Schema & class mapping: artefact = `artefact_id, type, subject_ids, parent_ids, uri, owner, acl, legal_hold, origin_known, created_at, filename`; action ∈ {delete, retain_legal_hold, escalate}. Chi tiết: `reports/t08_exceptions.md`, `reports/t08_interface.md`.
- Seed: 42 · Cách chia split: không chia; evaluator chấm cả 10 request. Tự kiểm bằng đáp án nội bộ 3 request (DR-002, DR-004, DR-008) trong `reports/t08_internal_key.csv`.
- `manifest.csv` verified (sha256): **có** — `python -m tools.verify_manifests` → `14 manifests, 0 failing`. Cần `.gitattributes` `fixtures/** -text` trên Windows, nếu không CRLF làm lệch hash và pipeline dừng ở bước load (đã gặp và sửa, xem §09).
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: không dùng — đề cấm xóa dữ liệu thật trong lab.


## 03 · Research & design

- **References & vì sao chọn kỹ thuật** (chi tiết + ngày xem ở §11):
  - *GDPR Art. 17(2)–(3)*: quyền xóa áp cho **mọi bản sao/replication**, nên phải duyệt lineage chứ không chỉ raw. Có ngoại lệ (3)(b) nghĩa vụ pháp lý và (3)(e) bảo vệ khiếu kiện, nên `retain_legal_hold` thắng `delete`.
  - *Luật 91/2025/QH15 + NĐ 356/2025/NĐ-CP*: chủ thể tại Việt Nam có quyền yêu cầu xóa, hiệu lực 01/01/2026, có ngoại lệ. NĐ 356 hướng dẫn thi hành (DPO, bên xử lý). Vì vậy nhóm dùng policy theo thứ tự ưu tiên và bắt buộc có người ký.
  - *Data Cards Playbook*: ghi provenance và ngoại lệ thành tài liệu có cấu trúc, áp dụng vào `reports/t08_exceptions.md` và `t08_interface.md`.
  - *California DROP*: một yêu cầu xóa lan tới mọi data broker. Nhóm áp dụng ý tưởng "chuyển tiếp yêu cầu" cho bên thứ ba (`vendor-x`, §07).
- **Data flow:**
  ```
  requests.json ─┐
  data_graph.json┴─► 01 load (sha256 manifest) ─► 02 process: BFS lineage theo subject
     ─► policy: legal hold > hold kế thừa > identity > ACL > origin unknown > multi-subject > delete
     ─► 03 rank: MỌI ngoại lệ vào review_queue.csv + contact_sheet.html (không cắt budget)
     ─► 04 review: P6 ký review_queue_reviewed.csv (approve/edit/escalate/reject) → audit review:*
     ─► 05 decide: dry_run_diff.csv, tombstone mock (idempotent), request_summary.csv, decision.json HOLD/GO
  ```
- **Thành phần offline:** không có model/weights; chỉ Python 3.13 + pandas. Chạy `--offline`, không gọi mạng.
- **Trade-offs:**
  - `legal_hold_inherit=true`: giữ thừa 29 bản sao (có thể xóa sau), đổi lại không có rủi ro xóa nhầm chứng cứ (không phục hồi được). Xem ablation §06.
  - Không có budget B: 56/158 cặp (35%) phải người xem. Tốn công, nhưng false-delete không đảo ngược được.
  - Artefact nhiều subject được `escalate` thay vì xóa: completeness thấp hơn nhưng không xóa dữ liệu của người khác.

## 04 · Baseline vs PoC

- Baseline: `src/baselines/t08_raw_only.py` — xóa raw_video có filename chứa subject, không duyệt lineage, không kiểm ngoại lệ (đề §4). Commit `59afdc6` (P5).
- PoC: `src/pipeline.py` — BFS lineage + policy precedence + review queue + dry-run/tombstone + GO/HOLD. Commits `73eece7` (P3), `398da62`/`d31f355` (P4). Tham số chốt trong `configs/tracks/t08.yaml`: `dry_run: true`, `permitted_acl: [data-platform]`, `legal_hold_inherit: true`.
- Cùng budget / cùng heldout / cùng seed: **xác nhận** — cùng `fixtures/t08_deletion` (sha256 khớp), seed 42, `--offline`, git sha `47fd94e`, cùng ngày 2026-11-14.

**Bảng 1 · Baseline vs PoC** — chưa có `table1_baseline_vs_poc.md` vì cần GT ẩn của giảng viên. Số dưới là **tự kiểm** bằng `python -m tools.t08_selfcheck` trên 3 request có đáp án nội bộ (DR-002, DR-004, DR-008 = 48 cặp), cộng số đếm trên cả 10 request:

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: Deletion Completeness (cặp phải xóa đã xóa / cặp phải xóa), tự kiểm | 2/24 = 0.083 | 24/24 = 1.000 | +0.917; higher = tốt. Wilson 95% CI PoC [0.86, 1.00] |
| False-delete count (tự kiểm 3 request) | 1 (`a0043`) | 0 | mục tiêu 0 |
| False-delete trên cả 10 request (raw đang hold bị xóa) | 2 (`a0043`, `a0099`) | 0 | lower = tốt |
| Hard-slice: Exception handling accuracy (tự kiểm) | 0/24 | 24/24 | N=24 cặp ngoại lệ |
| Cặp trong phạm vi có hành động (10 request) | 10/158 | 158/158 | baseline bỏ sót 148 |
| Review@B / miss / FP | không có review | B = 56 (toàn bộ ngoại lệ), 56/56 đã ký, 0 override | |
| Runtime toàn bộ (10 request) | 0.0113 s (10 dòng) | 0.212 s (158 dòng, gồm review) ≈ 134 ms/100 cặp | AMD64 Family 25, Windows 11, Python 3.13.14 |

## 05 · Evaluation protocol

- Công thức (xem `reports/metric_contract.md`): đơn vị là cặp `(request_id, artefact_id)`, khớp chính xác theo khóa.
  - **Completeness** = #cặp GT `delete` mà nhóm `delete` / #cặp GT `delete`.
  - **False-delete** = #cặp GT `retain_legal_hold`/`escalate` bị nhóm `delete` + #`delete` cho cặp không có trong GT.
  - **Exception accuracy** = #cặp ngoại lệ đúng action / #cặp ngoại lệ.
  - **Audit completeness** = #hành động có `item_id` trong `audit_log.jsonl` / #hành động.
- Threshold / budget: không có threshold số. Policy precedence và `legal_hold_inherit` được chốt ngày 2026-11-14, trước khi chạy eval. Budget B = mọi ngoại lệ (56), không cắt top-B vì xóa nhầm không đảo ngược được.
- Độ bất định: N nhỏ (10 request, 158 cặp; tự kiểm 48 cặp). Nhóm dùng Wilson 95% CI cho tỉ lệ, báo false-delete bằng số đếm tuyệt đối, kèm bảng từng request (`out/poc/request_summary.csv`). Đáp án nội bộ do chính nhóm soạn, nên chỉ kiểm được "code đúng ý nhóm", không kiểm được "ý nhóm đúng đề".
- Lệnh evaluate (giảng viên chạy khi có GT):
  ```bash
  python -m src.evaluate --track t08 --pred out/baseline/actions.csv --run-name baseline --out reports/metrics_baseline.json
  python -m src.evaluate --track t08 --pred out/poc/actions.csv --run-name poc --out reports/metrics_poc.json
  python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md
  ```

## 06 · Result slices

| Slice (10 request) | N cặp | Baseline có hành động | PoC: delete / retain / escalate | Ghi chú |
|---|---|---|---|---|
| raw_video | 10 | 10 (đều `delete`) | 8 / 2 / 0 | 2 raw đang legal hold |
| backup (`mock://glacier/`) | 10 | 0 | 7 / 2 / 1 | `a0156` ACL vendor-x |
| frame | 33 | 0 | 21 / 6 / 6 | 6 frame chung 2 người |
| face_crop | 30 | 0 | 24 / 6 / 0 | |
| embedding (`mock://vector-db/`) | 30 | 0 | 21 / 6 / 3 | 3 embedding origin unknown |
| annotation | 33 | 0 | 21 / 6 / 6 | |
| training_export | 12 | 0 | 0 / 3 / 9 | 9–10 subject / file → retrain/unlearning |
| **Tổng** | **158** | **10** | **102 / 31 / 25** | |
| Ablation `legal_hold_inherit=false` | 158 | — | 128 / 2 / 28 | tự kiểm: false-delete 13, exception acc 10/24 |

- **Failure case 1 — Xóa nhầm dữ liệu thuộc ngoại lệ.**
  - Baseline xóa `a0043` (`drive_subj_03_003.mp4`, `legal_hold: LH-2026-03`, DR-002) và `a0099` (`drive_subj_07_007.mp4`, `LH-2026-07`, DR-005). Bằng chứng: `out/baseline/actions.csv` dòng 3 và 6.
  - **Root cause:** baseline không đọc trường `legal_hold`.
  - **PoC:** xét `legal_hold` đầu tiên nên ra `retain_legal_hold`. Với `legal_hold_inherit=true`, PoC giữ cả **29 bản sao/dẫn xuất** (14 của subj_03, 15 của subj_07).
  - Ablation tắt kế thừa: tự kiểm false-delete = 13 trên riêng DR-002.
- **Failure case 2 — Chỉ xóa raw, giữ bản sao + embedding định danh.**
  - Baseline chỉ chạm **10/158** cặp, bỏ sót 148: toàn bộ 10 backup (`mock://glacier/backup/…`), 30 embedding (`mock://vector-db/embedding/…`), 30 face_crop, 33 frame, 33 annotation, 12 training export.
  - Ví dụ DR-008 (subj_11): xóa `a0155` raw nhưng `a0156` backup và các embedding `a0159, a0163, a0167` còn nguyên.
  - **Root cause:** không duyệt `parent_ids` / không tra theo `subject_ids`.
  - **PoC:** BFS lineage nên 158/158 cặp có hành động. Con lệch subject (`a0012` chỉ của subj_00) được log `lineage_out_of_scope` và không bị xóa.
- **Phát hiện thêm khi duyệt (P6):** `a0044` backup có `created_at 2026-01-10`, sớm hơn raw cha `a0043` (`2026-04-21`). Metadata lineage không nhất quán, đã ghi vào review note.
- Latency: PoC 0.212 s / 158 cặp (≈1.3 ms/cặp), baseline 0.011 s; AMD64 Family 25, Windows 11, Python 3.13.14.

## 07 · Human & decision

- **Review queue:** `out/poc/review_queue.csv` + `contact_sheet.html`. B = **56** (31 retain + 25 escalate). Ưu tiên legal hold (score 2) trước escalate (score 1), cùng mức thì theo deadline.
- **Người duyệt:** P6 · `NhatNguyen28122003 (P6 - human reviewer)`, 2026-11-14. Bằng chứng: `reports/review_queue.csv`, `reports/audit_review_entries.jsonl` (56 dòng `review:*`), `reports/decision_log.csv`.

| Request | Artefact | Ngoại lệ | Quyết định P6 | Hành động cuối | Lý do |
|---|---|---|---|---|---|
| DR-002 | `a0043` raw | LEGAL_HOLD `LH-2026-03` | approve | retain_legal_hold | GDPR 17(3)(e)/Luật 91; hẹn xóa khi gỡ hold; cần legal xác nhận hold còn hiệu lực |
| DR-002 | 14 dẫn xuất `a0044–a0056`, `a0211` | LEGAL_HOLD_INHERITED | approve ×14 | retain_legal_hold | bản sao chứng cứ; `a0044` ngày tạo lệch |
| DR-005 | `a0099` raw | LEGAL_HOLD `LH-2026-07` | approve | retain_legal_hold | như trên |
| DR-005 | 15 dẫn xuất `a0100–a0112`, `a0211`, `a0212` | LEGAL_HOLD_INHERITED | approve ×15 | retain_legal_hold | export: khi hết hold phải retrain/unlearning |
| DR-008 | `a0156` backup | NO_DELETE_PERMISSION (vendor-x) | **escalate** | escalate | chuyển yêu cầu sang vendor-x, hạn 2026-12-08 (kiểu DROP) |
| DR-004 | `a0075`, `a0079`, `a0083` | UNKNOWN_ORIGIN | **escalate** ×3 | escalate | data owner xác minh nguồn trong 7 ngày |
| DR-001 / DR-009 | `a0011`,`a0014` / `a0179`,`a0182` | MULTI_SUBJECT (người kia không yêu cầu) | approve ×4 | escalate | che/cắt phần của người yêu cầu |
| DR-003+004 / DR-006+007 | `a0067`,`a0070` / `a0123`,`a0126` | MULTI_SUBJECT (**cả 2** đều yêu cầu) | approve ×8 | escalate | gộp 2 yêu cầu rồi mới xóa |
| 7 request | `a0211` / `a0212` export | MULTI_SUBJECT export | approve ×9 | escalate | export mới + unlearning; bản gốc chứa subj_03/07 đang hold, nên không sửa bản gốc |

Tổng: 52 approve + 4 escalate, 0 edit, 0 reject.

- **Override + audit log:** mỗi dòng review ghi `actor`, `action = review:<decision>`, `before/after`, `reason`, `reviewed_at`. `reject`/`escalate` không bao giờ thành `delete`.
- **Decision log:**

| ts (UTC) | status | reason_code | owner |
|---|---|---|---|
| 2026-11-14T14:49:35 | **HOLD** | `EXCEPTIONS_PENDING_REVIEW` (56 chờ ký) | NhatNguyen28122003 - P6 |
| 2026-11-14T14:50:52 | **GO** | `DELETION_PLAN_APPROVED` | NhatNguyen28122003 - P6 |
| 2026-11-14T14:50:54 | GO | lần chạy kiểm idempotency | NhatNguyen28122003 - P6 |

- **Khi nào HOLD:** còn ≥1 ngoại lệ chưa ký thì HOLD và không xóa gì. GO chỉ phê duyệt kế hoạch:
  - 102 cặp delete được xóa mock.
  - 31 cặp giữ đến khi legal gỡ hold.
  - 25 cặp escalate chờ vendor-x, data owner, ML owner phản hồi trước deadline.
- **So với California DROP:** DROP gửi một yêu cầu xóa tới mọi data broker. Ở đây tương tự là `a0156` (vendor-x): nhóm không xóa được, phải chuyển tiếp yêu cầu và theo dõi xác nhận.

## 08 · Reproduce & tests

```bash
python -m tools.verify_manifests
python -m src.main --config configs/lab.yaml --pipeline src.baselines.t08_raw_only --output out/baseline --run-name baseline --offline --seed 42
python -m src.main --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42      # lần 1: HOLD
cp reports/review_queue.csv out/poc/review_queue_reviewed.csv
python -m src.main --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42      # lần 2: GO
pytest -q
```

- `pytest -q`: **54 passed, 39 skipped in 6.69s**; `tests/test_t08_pipeline.py`: 7 passed. Chạy 2 lần cho `actions.csv` giống hệt.
- Máy: AMD64 Family 25, Windows 11, Python 3.13.14 · git sha `47fd94e`.

## 09 · Limitations & ethics

- Dữ liệu synthetic (CC0), không có người thật, không xóa dữ liệu thật.
- Data không có ngày hết hạn hold, nội dung ticket legal hay hợp đồng vendor-x. Nếu GT ẩn không coi bản sao là bị hold, PoC mất ~26 cặp completeness (false-delete vẫn 0).
- 35% cặp phải người duyệt. Ở scale 10× (~560 ngoại lệ) cần duyệt theo cụm hold và có SLA.
- **Không tuyên bố "đạt GDPR / luật Việt Nam"**, chỉ nói có xử lý ngoại lệ theo tinh thần GDPR Art. 17(3) / Luật 91/2025. Bốn giả định cần DPO/legal xác nhận:
  - (a) hold kế thừa sang bản sao;
  - (b) artefact nhiều người thì che/tách thay vì xóa;
  - (c) vendor-x là bên xử lý, phải nhận yêu cầu chuyển tiếp;
  - (d) export đã dùng để train có cần unlearning không.
- Cải tiến: tự mở lại request khi gỡ hold, stub thông báo vendor-x, duyệt theo cụm, demo `dry_run: false`.

## 10 · Team contribution

| Học viên | Git author | Vai trò | Commit | Trình bày? |
|---|---|---|---|---|
| P1 Bui Thanh Tan | tantan294 | Lead / Integrator | `d12b691`, `d9ca826` | có |
| P2 Nguyen Viet Minh Hoang (2A202603281) | hoanghamhok | Data & fixtures | `f7a517c`, `76b93d1`, `822693a` | |
| P3 Nhat Nguyen | Edelxz | Core: lineage + policy | `73eece7` | |
| P4 Nguyen Tien Dat | datpro-sudo | Core: review + thực thi | `398da62`, `d31f355` | |
| P5 Nguyen Cong Bao Long | NguyenCongBaoLong | QA/metric + baseline + ablation | `59afdc6` | |
| P6 NhatNguyen28122003 | NhatNguyen28122003 | Human reviewer + report + slide | (commit P6) | có |

## 11 · References

| URL | Ngày xem | Ý nghĩa |
|---|---|---|
| https://gdpr-info.eu/art-17-gdpr/ | 2026-11-14 | Quyền xóa áp cả bản sao; ngoại lệ (3)(b), (3)(e) → căn cứ `retain_legal_hold` |
| https://thuvienphapluat.vn/van-ban/Bo-may-hanh-chinh/Law-91-2025-QH15-Personal-Data-Protection-665440.aspx | 2026-11-14 | Luật 91/2025/QH15, hiệu lực 01/01/2026: quyền yêu cầu xóa, có ngoại lệ |
| https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Nghi-dinh-356-2025-ND-CP-huong-dan-Luat-Bao-ve-du-lieu-ca-nhan-687428.aspx | 2026-11-14 | NĐ 356/2025 hướng dẫn Luật 91, thay NĐ 13/2023 |
| https://www.cppa.ca.gov/data_brokers/ | 2026-11-14 | California DROP: một yêu cầu xóa tới mọi data broker |
| https://sites.research.google/datacardsplaybook/ | 2026-11-14 | Khung tài liệu dữ liệu có cấu trúc → `t08_exceptions.md` |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật. *(tag do P1 tạo)*
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics (tự kiểm), 2 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên. *(P6 cần commit phần này)*
