# Người D — Human review + pháp lý + report + slides

**Sở hữu:** `src/t08/review.py` · vòng duyệt DPO (`out/poc/review_queue_reviewed.csv`) · `source` trong `configs/t08_policy.yaml` · `reports/group_report.md` (chủ trì) · `demo/`
**Code mẫu:** [code_mau/src/t08/review.py](code_mau/src/t08/review.py)

---

## D1 · Phút 0–10 — Setup
```powershell
git pull
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
git checkout -b d/review-report
```

## D2 · Phút 10–50 — Tra nguồn luật cho từng luật (song song khi người khác code)

Điền bảng, gửi B điền khoá `source` trong YAML:
| Luật | Căn cứ gợi ý | Cần ghi |
|---|---|---|
| R1 identity | GDPR Art.12(6) — được yêu cầu thêm thông tin xác minh | |
| R2/R3 legal hold | GDPR Art.17(3)(e) — thiết lập/bảo vệ yêu cầu pháp lý; ngoại lệ quyền xoá trong Luật 91/2025 | hẹn xoá khi hết hold |
| R4 ACL | chính sách nội bộ; vendor là bên xử lý → yêu cầu vendor xoá (GDPR Art.28, 17(2)) | |
| R5 origin | GDPR Art.5(2) trách nhiệm giải trình | |
| R6 export | GDPR Art.17(2) — thông báo bên nhận; rebuild export | |
| R7 multi-subject | quyền của người khác (GDPR Art.15(4) tương tự) → redact thay vì xoá | |
| R8 delete | GDPR Art.17(1); Luật 91/2025; NĐ 356/2025 | |
So sánh: California **DROP** (một yêu cầu xoá gửi tới mọi data broker). Ghi rõ: *tài liệu học tập, không phải tư vấn pháp lý*.

## D3 · Phút 30–50 — Report mục 01 Problem statement
- Ai gửi yêu cầu, hạn 30 ngày, dữ liệu nằm rải ở raw/backup/frame/crop/embedding/export.
- Hai rủi ro ngược chiều: **xoá thiếu** (vi phạm quyền xoá) vs **xoá nhầm** (huỷ bằng chứng đang legal hold, xoá dữ liệu người khác).
- Mục tiêu đo: Completeness cao, False-delete = 0, mọi hành động có audit.

## D4 · Phút 50–90 — `src/t08/review.py`

Chép [code_mau/src/t08/review.py](code_mau/src/t08/review.py), hiểu từng hàm:
| Hàm | Làm gì |
|---|---|
| `build_queue(actions, budget)` | lấy các dòng **không phải delete** (56 ngoại lệ), xếp ưu tiên: identity/legal hold (5) > hold thừa kế, ACL (4) > origin (3) > export, multi-subject (2); dùng `make_review_queue` có sẵn → đúng `REVIEW_COLUMNS` |
| `render_review_table(queue, path)` | HTML offline để DPO xem (`review_queue.html`) |
| `apply_review(actions, reviewed, audit)` | áp quyết định DPO, mỗi dòng 1 audit `review:<quyết định>` với `item_id=artefact_id` |

Ý nghĩa quyết định của reviewer:
| `reviewer_decision` | Tác dụng |
|---|---|
| `approve` | DPO **ký** action máy đề xuất → điền `reviewed_by` |
| `edit` + `override_value` | đổi action (chỉ nhận `delete / retain_legal_hold / escalate`), `rule_id = HUMAN_OVERRIDE` |
| `reject` / `escalate` / `skip` | chưa ký → request vẫn HOLD |

Tự kiểm sau khi A nối:
```powershell
.\.venv\Scripts\python.exe -c "import pandas as pd; q=pd.read_csv('out/poc/review_queue.csv'); print(len(q)); print(q.reason.value_counts())"
```
Kỳ vọng 56 dòng. Commit `feat(t08): review queue + apply review`.

## D5 · Phút 90–145 — Vòng duyệt thật (bạn đóng vai DPO)

1. A chạy PoC → mở `out/poc/review_queue.html` (trình duyệt) hoặc `review_queue.csv` (Excel).
2. Điền cho **ít nhất 2 dòng DR-006** (`DR-006:a0123`, `DR-006:a0126`):
   - `reviewer` = tên bạn (bắt buộc, thiếu → pipeline báo lỗi)
   - `reviewer_decision` = `approve`
   - `review_note` = "frame/annotation chung subj_08+09: giữ escalate, chuyển redact"
   - `reviewed_at` = thời điểm
3. Duyệt thêm vài dòng khác để có bằng chứng (ví dụ `DR-008:a0156` → `approve`, note "yêu cầu vendor-x xoá theo hợp đồng").
4. Lưu thành **`out/poc/review_queue_reviewed.csv`** (giữ nguyên tên cột, UTF-8). Lưu thêm 1 bản ở `reports/review_queue_reviewed.csv` (vì `out/` bị xoá khi clean start).
5. A chạy lại → kiểm:
   - `decision_log.csv`: **DR-006 GO** `ERASURE_DONE_EXCEPTIONS_SIGNED`, các request khác HOLD.
   - `audit_log.jsonl` có dòng `review:approve` với tên bạn.

> ⚠ **Không** dùng `edit` để chuyển ngoại lệ thành `delete` trong lần chạy được chấm
> (ví dụ a0067 → delete): nếu giáo viên coi đó là ngoại lệ thì thành **false-delete**.
> Muốn minh hoạ override kiểu này → chạy riêng vào `out/override_demo/` và mô tả trong report mục 07.

Commit file reviewed: `data(t08): DPO review round 1`.

## D6 · Phút 145–170 — Report mục 07 + 09
- **07 Human & decision:** bảng `request → artefact → ngoại lệ → người duyệt → hành động & log` (lấy từ `review_queue_reviewed.csv` + `decision_log.csv`); giải thích GO/HOLD/REWORK; ai là owner.
- **09 Limitations & ethics:** dữ liệu mock; self-check do nhóm tự gán; chính sách cần DPO/pháp chế xác nhận; hold thừa kế làm completeness thấp hơn; không tuyên bố "đạt GDPR".

## D7 · Phút 170–180 — Slides (3–5, trong `demo/`)
1. Vấn đề (2 rủi ro: xoá thiếu / xoá nhầm)
2. Thuật toán (slide của B: cây + 8 luật)
3. Kết quả (slide của C: bảng baseline vs PoC, 2 failure case)
4. Human review + quyết định (DR-006 GO, DR-002 HOLD legal hold, data-catalog REWORK)
5. Giới hạn + bước tiếp

## D8 · +24h — SLA + hoàn thiện report
- `sla.csv` / `sla.html`: mỗi request: `received_at`, `deadline`, trạng thái, số ngày còn lại; `notifications.jsonl` (stub, không gửi thật) cho request HOLD gần hạn.
- Report mục 01, 07, 09, 11 (References) + gộp toàn bộ `group_report.md`, kiểm mỗi mục có chủ.
- Copy `review_queue.csv`, `review_queue_reviewed.csv`, `decision_log.csv` vào `reports/`.

## Câu hỏi debate nên tập
- Khi nào được từ chối xoá? (legal hold — phải ghi reason_code + căn cứ + hẹn xoá khi hết hold)
- DPO duyệt sai thì sao? (audit ghi ai/khi nào/trước-sau → truy được trách nhiệm, sửa bằng lần duyệt mới)
- Vì sao không tuyên bố "đạt GDPR"?

**Commit gợi ý:** `docs: legal sources` · `feat(t08): review queue` · `data(t08): DPO review` · `docs: report 01/07/09` · `docs: demo slides`
