# Slide · Thuật toán (người B)

## Tìm đúng dữ liệu của một người — rồi mới quyết định

```
raw_video (subj_01) ──► backup
        └──► frame ──► face_crop · embedding · annotation
                └──► training_export (9–10 người)

frame a0011 = subj_00 + subj_01   ← dữ liệu CHUNG
   └──► face_crop a0012 = CHỈ subj_00   ← duyệt mù cây con sẽ xoá nhầm
```

**Lineage để TÌM · `subject_ids` để QUYẾT** → 158 dòng cho 10 yêu cầu

## 8 luật — luật đầu tiên khớp thắng

| | Điều kiện | → |
|---|---|---|
| R1 | chưa xác minh danh tính | escalate |
| R2 | đang legal hold | **giữ** |
| R3 | tổ tiên đang legal hold | **giữ** |
| R4 | không có quyền (vendor) | escalate |
| R5 | không rõ nguồn gốc | escalate |
| R6 | training export | escalate (rebuild) |
| R7 | chung nhiều người | escalate (redact) |
| R8 | còn lại | **xoá** |

**Kết quả:** 102 xoá · 40 giữ · 16 escalate — baseline (xoá theo filename) xoá cả 2 video đang legal hold.
**Nguyên tắc:** xoá không hoàn tác được → phân vân thì để người duyệt.
