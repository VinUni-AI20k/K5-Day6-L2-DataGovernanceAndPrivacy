# T08 · Delete Request Simulator — G02 (5 slide)

---

## Slide 1 · Vấn đề: "xóa tôi đi" không phải xóa 1 file

- 10 yêu cầu xóa (DR-001…DR-010), 212 artefact mock, **158 cặp (request, artefact)** trong phạm vi.
- Mỗi người có **14–18 artefact**: raw → backup → frame → face_crop → embedding / annotation → training export.
- Hai kiểu sai bắt buộc phân tích:
  1. **Xóa nhầm** dữ liệu đang bị legal hold / không có quyền / có người khác.
  2. **Xóa thiếu**: xóa raw nhưng bản sao + embedding định danh vẫn còn.
- Sai → chủ thể dữ liệu vẫn bị nhận diện; tổ chức mất chứng cứ pháp lý; DPO phải giải trình.

*Speaker note:* nhấn mạnh 1 người = trung bình 16 artefact, baseline chỉ thấy 1.

---

## Slide 2 · Baseline vs PoC (2 failure case)

| | Baseline (raw theo filename) | PoC (lineage + policy + người duyệt) |
|---|---|---|
| Cặp có hành động | **10 / 158** | **158 / 158** |
| Raw đang legal hold bị xóa | **2** (`a0043` LH-2026-03, `a0099` LH-2026-07) | **0** |
| Completeness (tự kiểm 3 request) | 2/24 | 24/24 |
| Backup + embedding bị bỏ sót | 10 backup `mock://glacier/` + 30 embedding `mock://vector-db/` | 0 |

- **Failure 1** root cause: không đọc `legal_hold` → PoC `retain_legal_hold` + giữ cả **29 bản sao** của dữ liệu đang hold.
- **Failure 2** root cause: không duyệt lineage / không tra theo subject → PoC BFS `parent_ids` theo `subject_ids`.
- Số tự kiểm (đáp án nội bộ), số chính thức cần GT của giảng viên.

---

## Slide 3 · Người thật ký duyệt: 56 ngoại lệ

Policy: **legal hold > hold kế thừa > identity > ACL > origin unknown > nhiều subject > delete**

| Ngoại lệ | Số | Quyết định P6 |
|---|---|---|
| Legal hold + bản sao (DR-002, DR-005) | 31 | approve → giữ, hẹn xóa khi legal gỡ hold |
| `a0156` backup do vendor-x giữ | 1 | **escalate** → chuyển yêu cầu sang vendor-x |
| 3 embedding không rõ nguồn (DR-004) | 3 | **escalate** → data owner xác minh trong 7 ngày |
| Frame/annotation chung 2 người | 12 | approve escalate → che/tách |
| Training export 9–10 người | 9 | approve escalate → export mới + đánh giá unlearning |

- Reviewer phát hiện thêm: frame `a0067`/`a0123` có **cả 2 người cùng yêu cầu xóa** → gộp yêu cầu; export `a0211`/`a0212` chứa subj_03/07 đang hold → **không sửa bản gốc**.
- `decision.json`: **HOLD** (56 chờ ký) → **GO** (0 chờ), owner = P6; 56 dòng `review:*` trong `audit_log.jsonl`.

---

## Slide 4 · "Đạt GDPR chưa?" — Không tuyên bố vậy

- Chỉ nói: **có xử lý ngoại lệ theo tinh thần** GDPR Art. 17(3) (nghĩa vụ pháp lý, khiếu kiện) và Luật 91/2025/QH15 + NĐ 356/2025.
- 4 giả định **cần DPO/legal xác nhận**: hold áp cả bản sao · artefact nhiều người thì che/tách · vendor-x phải nhận chuyển tiếp · export đã train cần unlearning hay không.
- **So với California DROP:** DROP = một yêu cầu tới **mọi data broker**. Ở đây tương tự là `a0156` (vendor-x): mình **không xóa được**, phải chuyển yêu cầu và theo dõi xác nhận — không được báo "đã xóa xong".
- Data không ghi ngày hết hạn hold → reviewer chưa kiểm được hold còn hiệu lực.

---

## Slide 5 · Giới hạn & bước tiếp theo

- 35% cặp (56/158) phải người duyệt → scale 10× cần duyệt theo cụm (1 quyết định / 1 hold) + SLA.
- Ablation `legal_hold_inherit=false`: 128 delete, tự kiểm false-delete 13 → nhóm chọn giữ thừa (xóa sau được) hơn xóa nhầm (không phục hồi).
- Tái lập: `python -m src.main --config configs/lab.yaml --output out/poc --offline --seed 42` · `pytest -q` → 54 passed, 39 skipped · chạy 2 lần cho kết quả giống hệt.
- Tiếp theo: tự mở lại request khi gỡ hold · stub thông báo vendor-x · demo `dry_run: false` với tombstone + resume.
