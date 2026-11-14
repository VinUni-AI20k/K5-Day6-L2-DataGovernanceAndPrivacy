# 02 · Data & provenance — phần do B viết *(gửi C ghép vào mục 02)*

## Schema dùng trong thuật toán (`fixtures/t08_deletion/data_graph.json`)

| Trường | Kiểu | Dùng ở đâu |
|---|---|---|
| `artefact_id` | str | khoá, cột `artefact_id` trong `actions.csv` |
| `type` | raw_video / backup / frame / face_crop / embedding / annotation / training_export | R6 (export), ablation R3 (backup) |
| `subject_ids` | list[str] | **quyết định phạm vi** (`graph.scope`), R7 |
| `parent_ids` | list[str] | duyệt lineage (`children_map`, `ancestors`), R3, `lineage_warnings` |
| `legal_hold` | str hoặc null | R2, R3 |
| `acl` | list[str] | R4 |
| `origin_known` | bool | R5 |
| `filename` | str (chỉ raw/backup) | chỉ baseline dùng |

`requests.json`: `request_id`, `subject_id`, `deadline`, `identity_verified` (R1).

## Cấu trúc đồ thị (đếm bằng `graph.load_graph`)
212 artefact: 15 raw_video (gốc, không có cha) → mỗi raw có 1 backup + 3 frame → mỗi frame có 1 face_crop, 1 embedding, 1 annotation; thêm 2 training_export gộp 9–10 người. Mỗi request có 14–18 artefact trong phạm vi, tổng **158 dòng**.

## Kiểm tra nhất quán catalog (`graph.lineage_warnings`)
4 artefact chứa một subject mà không cha nào chứa: `a0011` (subj_01), `a0067` (subj_05), `a0123` (subj_09), `a0179` (subj_13).
Nghĩa là raw video của người kia **thực ra cũng có** người này nhưng catalog không ghi → pipeline báo **REWORK scope `data-catalog`** thay vì âm thầm tin catalog.

## Vì sao không chia dev / eval
Chỉ có 10 request trên 1 đồ thị; thuật toán là luật cố định (không học tham số), nên không có gì để "tune". Toàn bộ luật được chốt và commit (`configs/t08_policy.yaml`) trước khi chạy đánh giá.
