# Slide C · Số liệu: Baseline vs PoC (self-check, seed 42, 158 dòng)

| | Baseline (tên file) | PoC (lineage + R1–R8) |
|---|---|---|
| **Deletion Completeness** | 0.078 (8/102) | **1.000 (102/102)** · CI [0.964, 1.000] |
| **False-delete** (mục tiêu 0) | **2** — xoá raw đang legal hold `a0043`, `a0099` | **0** |
| Exception accuracy | 0 / 56 | 56 / 56 |
| Audit completeness | 10 / 10 | 158 / 158 |
| Latency | 3.07 ms/dòng | 1.19 ms/dòng |

**Ablation:** hold chỉ thừa kế cho backup → **24 dòng bị xoá nhầm** (frame/crop/embedding/annotation của DR-002, DR-005) ⇒ R3 bắt buộc.

**Hai lỗi của baseline:** ① xoá dữ liệu đang legal hold (không đọc `legal_hold`) · ② DR-001 chỉ xoá 1/17, sót backup `a0016` + embedding (không duyệt lineage).

⚠ Chấm trên bộ **self-check C gán tay theo chính sách nhóm**, không phải GT giảng viên — 1.0 nghĩa là code đúng chính sách, chưa chứng minh chính sách đúng luật. Mô phỏng; cần DPO/pháp chế xác nhận.
