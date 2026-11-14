# T08 · Data profile (tự sinh bằng tools/t08_profile.py)

- Artefact: **212** · Request: **10**
- Theo type: {'raw_video': 15, 'backup': 15, 'frame': 45, 'face_crop': 45, 'embedding': 45, 'annotation': 45, 'training_export': 2}
- identity_verified=false: []

## Case catalog (ngoại lệ cài sẵn)

| artefact | type | subject_ids | lý do |
|---|---|---|---|
| a0011 | frame | ['subj_00', 'subj_01'] | multi-subject (2) |
| a0014 | annotation | ['subj_00', 'subj_01'] | multi-subject (2) |
| a0043 | raw_video | ['subj_03'] | legal_hold=LH-2026-03 |
| a0067 | frame | ['subj_04', 'subj_05'] | multi-subject (2) |
| a0070 | annotation | ['subj_04', 'subj_05'] | multi-subject (2) |
| a0075 | embedding | ['subj_05'] | origin_known=false |
| a0079 | embedding | ['subj_05'] | origin_known=false |
| a0083 | embedding | ['subj_05'] | origin_known=false |
| a0099 | raw_video | ['subj_07'] | legal_hold=LH-2026-07 |
| a0123 | frame | ['subj_08', 'subj_09'] | multi-subject (2) |
| a0126 | annotation | ['subj_08', 'subj_09'] | multi-subject (2) |
| a0156 | backup | ['subj_11'] | acl=['vendor-x'] |
| a0179 | frame | ['subj_12', 'subj_13'] | multi-subject (2) |
| a0182 | annotation | ['subj_12', 'subj_13'] | multi-subject (2) |
| a0211 | training_export | 10 subjects | multi-subject (10) |
| a0212 | training_export | 9 subjects | multi-subject (9) |

## Cây con của artefact bị legal hold

- a0043 (LH-2026-03): 14 hậu duệ → ['a0044', 'a0045', 'a0046', 'a0047', 'a0048', 'a0049', 'a0050', 'a0051', 'a0052', 'a0053', 'a0054', 'a0055', 'a0056', 'a0211']
- a0099 (LH-2026-07): 15 hậu duệ → ['a0100', 'a0101', 'a0102', 'a0103', 'a0104', 'a0105', 'a0106', 'a0107', 'a0108', 'a0109', 'a0110', 'a0111', 'a0112', 'a0211', 'a0212']

## Số artefact trong phạm vi mỗi request (subject_id ∈ subject_ids)

- DR-001 · subj_01: 17
- DR-002 · subj_03: 15
- DR-003 · subj_04: 16
- DR-004 · subj_05: 18
- DR-005 · subj_07: 16
- DR-006 · subj_08: 14
- DR-007 · subj_09: 17
- DR-008 · subj_11: 15
- DR-009 · subj_12: 15
- DR-010 · subj_14: 15

## Ghi chú kiểm tay 3 case (C2)

- **a0011** (type=frame, subject_ids=['subj_00', 'subj_01'], parent_ids=['a0001'], acl=['data-platform']).
  - cha a0001: type=raw_video, subject_ids=['subj_00'], parent_ids=[], acl=['data-platform']
  - con a0012: type=face_crop, subject_ids=['subj_00'], parent_ids=['a0011'], acl=['data-platform']
  - con a0014: type=annotation, subject_ids=['subj_00', 'subj_01'], parent_ids=['a0011'], acl=['data-platform']
  → frame **dùng chung 2 người**: xoá theo yêu cầu của subj_01 sẽ xoá luôn dữ liệu của subj_00 ⇒ phải `escalate` (R7). Con a0012 (face_crop) chỉ mang subj_00 → không thuộc phạm vi DR-001 (*lineage để TÌM, `subject_ids` để QUYẾT*).
  → Lineage mâu thuẫn (con có subject mà cha không có, trừ export): **4** artefact: ["a0011 (thiếu ở cha: ['subj_01'])", "a0067 (thiếu ở cha: ['subj_05'])", "a0123 (thiếu ở cha: ['subj_09'])", "a0179 (thiếu ở cha: ['subj_13'])"] ⇒ `data-catalog` cần REWORK.
- **a0156** (type=backup, subject_ids=['subj_11'], parent_ids=['a0155'], acl=['vendor-x'], uri=mock://glacier/backup/a0156).
  → backup nằm ở kho có ACL `vendor-x`, đội data-platform **không có quyền xoá** ⇒ `escalate` (R4), cần nhà cung cấp xác nhận xoá.
- **a0211** (training_export, 10 subjects, 12 cha).
  → cha có tổ tiên/bản thân bị legal hold: ['a0106', 'a0046'] (a0046 = face_crop của ['subj_03'], cha raw a0043 giữ LH-2026-03) ⇒ `retain_legal_hold` (R3) ở **mọi** request chạm tới export này, dù R6/R7 cũng khớp — luật đầu tiên khớp thắng.
