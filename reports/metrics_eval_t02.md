# T02 — Ket qua chinh thuc tren 40 nhan eval

- Thoi diem: `2026-11-14T11:06:05+00:00`
- GT: `reports\eval_gt_from_Evalimg.txt.csv` (tu `Downloads/Evalimg.txt`), SHA-256 `3441d4937bc453e3…`
- 17 clean / 23 defect (tong 40)
- Budget: B=20 (50% cua 40)
- Nguong da **freeze truoc** tren 56 nhan dev; **khong doc** `fixtures/*/gt/`, **khong chinh** tren eval.

## Tong ket chinh thuc

| Model | Recall@20 | Precision@20 | Defect-type accuracy | False alarm @20 |
|---|---:|---:|---:|---:|
| PoC v1 | 0.8696 (20/23) | 1.0000 (20/20) | 0.8696 | 0/17 |
| Baseline (lap<760) | 0.8696 (20/23) | 1.0000 (20/20) | 0.3043 | 0/17 |

## Theo loai loi (type accuracy denominator = 23 defect)

| Slice | PoC recall@20 | Baseline recall@20 |
|---|---:|---:|
| defect=blur | 0.714 | 1.000 |
| defect=blur glare | 1.000 | 1.000 |
| defect=compression | 0.875 | 0.750 |
| defect=dark | 1.000 | 1.000 |
| defect=glare | 1.000 | 0.500 |

## Theo anh sang (false alarm @20)

| Slice | PoC FA | Baseline FA |
|---|---:|---:|
| light=day | 0.000 | 0.000 |
| light=dusk | 0.000 | 0.000 |
| light=night | 0.000 | 0.000 |

## Dinh dang GT nhap vao (Evalimg.txt)

- 40 dong, tab-separated: `image_id\ttype\t\tseverity`
- 2 dong multi-label: `img_03_2` (blur glare/1), `img_06_3` (blur glare/2)
- `eval_t02` so sanh chuoi `defect_type` chinh xac, nen multi-label duoc dem la sai neu pred chi la 1 loai.

## Ket luan

- PoC v1 va baseline bang nhau tren Recall@20 (20/23 = 87.0%) va Precision@20 (20/20 = 100%), false alarm = 0 tren tat ca slice.
- PoC v1 thang xac nhat tren defect-type accuracy (87.0% vs 30.4%), nhan dang duoc compression/glare/dark thay bao het la blur.
- Freeze da duoc toan toan: khong chinh nguong nao sau khi nhan eval.