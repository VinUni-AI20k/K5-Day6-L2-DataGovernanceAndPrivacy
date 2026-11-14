# T08 · Baseline vs PoC + ablation (P5 · QA / metric)

> Cùng data (`fixtures/t08_deletion`, sha256 khớp manifest), cùng seed 42, chạy `--offline`, ngày 2026-11-14.
> **Số chính thức** (`reports/metrics_*.json`, `table1_baseline_vs_poc.md`) chỉ sinh được khi giảng viên cài
> `gt/` — repo học viên chạy `src.evaluate` sẽ exit 2. Bảng dưới là **tự kiểm** bằng đáp án nội bộ
> `reports/t08_internal_key.csv` (DR-002, DR-004, DR-008; 48 cặp) qua `python -m tools.t08_selfcheck`.

## 1. Lệnh tái lập

```bash
python -m src.main --config configs/lab.yaml --pipeline src.baselines.t08_raw_only --output out/baseline --run-name baseline --offline --seed 42
python -m src.main --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42
# ablation: cùng config nhưng params.legal_hold_inherit: false
python -m src.main --config <lab_ablation.yaml> --output out/ablation_no_inherit --run-name ablation_no_inherit --offline --seed 42
python -m tools.t08_selfcheck --pred out/<run>/actions.csv
```

## 2. Baseline vs PoC (tự kiểm, 3 request)

| Metric (unit) | Baseline (raw theo tên file) | PoC (`legal_hold_inherit: true`) | Ghi chú |
|---|---|---|---|
| Deletion Completeness (cặp phải xóa đã xóa / cặp phải xóa) | **2/24** (0.083) | **24/24** (1.000) | higher = tốt |
| False-delete count | **1** (`a0043`, raw đang `LH-2026-03`) | **0** | mục tiêu 0 |
| Exception handling accuracy | 0/24 | 24/24 | baseline không sinh dòng ngoại lệ nào |
| Exact match (cả 3 action) | 2/48 | 48/48 | |
| Runtime toàn bộ 10 request | 0.014 s (10 dòng) | 0.134 s (158 dòng) ≈ 85 ms / 100 cặp | CPU laptop, Python 3.13, Windows 11 |

Trên **cả 10 request** (không có đáp án, chỉ đếm): baseline sinh 10 dòng (chỉ `raw_video`) trên 158 cặp trong phạm vi;
xóa nhầm **2** raw đang legal hold (`a0043`, `a0099`). PoC: 102 `delete` · 31 `retain_legal_hold` · 25 `escalate`.

| Loại artefact | Cặp trong phạm vi | Baseline có hành động | PoC có hành động |
|---|---|---|---|
| raw_video | 10 | 10 | 10 |
| backup | 10 | 0 | 10 |
| frame | 33 | 0 | 33 |
| face_crop | 30 | 0 | 30 |
| embedding | 30 | 0 | 30 |
| annotation | 33 | 0 | 33 |
| training_export | 12 | 0 | 12 |

## 3. Ablation: kế thừa legal hold cho bản sao

| | `legal_hold_inherit: true` (PoC, đã chốt) | `legal_hold_inherit: false` |
|---|---|---|
| delete / retain / escalate | 102 / 31 / 25 | 128 / 2 / 28 |
| Self-check completeness | 24/24 | 24/24 |
| Self-check false-delete | 0 | **13** |
| Self-check exception accuracy | 24/24 | 10/24 |

29 cặp đổi hành động, tất cả thuộc **DR-002** (subj_03, raw `a0043`) và **DR-005** (subj_07, raw `a0099`):
backup, frame, face_crop, embedding, annotation chuyển `retain_legal_hold → delete`; training export chuyển
`retain_legal_hold → escalate`.

**Đọc kết quả trung thực:** đáp án nội bộ được soạn theo giả định “hold áp cho cả bản sao”, nên con số
false-delete 13 của ablation là **hệ quả của giả định**, không phải bằng chứng độc lập. Nếu GT ẩn chỉ giữ đúng
artefact có cờ `legal_hold`, PoC sẽ mất ~26 cặp completeness ở DR-002/DR-005 nhưng vẫn false-delete = 0;
ngược lại ablation sẽ xóa nhầm 26 bản sao chứng cứ. Nhóm chọn `true` vì xóa nhầm không phục hồi được còn giữ thừa
thì xóa sau khi hết hold được (đề: “hẹn xóa khi hết hold”). Cần DPO/legal xác nhận.

## 4. Giới hạn

- N nhỏ (3 request có đáp án nội bộ, 48 cặp) → không suy rộng; Wilson 95% CI cho 24/24 là [0.86, 1.00].
- Đáp án nội bộ do cùng nhóm soạn → kiểm được *code làm đúng ý nhóm*, không kiểm được *ý nhóm đúng đề*.
- Runtime đo 1 lần trên máy cá nhân; đã có trong `out/*/run_info.json`.
