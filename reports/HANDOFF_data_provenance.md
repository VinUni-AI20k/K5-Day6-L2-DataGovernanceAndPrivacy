# Bàn giao từ Data & Provenance → cả nhóm (T02)

Người viết: Thành viên 2 (Soraxolo). Nhánh: `feat/t02-data-provenance`.

Đọc mục 1 trước khi viết `src/pipeline.py`. Hai ràng buộc ở đó đến từ dữ liệu,
không phải ý kiến, và nếu bỏ qua thì phải viết lại thuật toán.

Đề xuất phân việc ở mục 3 là **đề xuất**, Lead/Integrator chốt lại.

---

## 1. Hai ràng buộc với thuật toán

### 1.1 `cam_A/night` không có mẫu nào ở `dev`

Số ảnh theo tầng:

| camera | light | dev | eval |
|---|---|---:|---:|
| cam_A | day | 24 | 20 |
| cam_A | dusk | 12 | **0** |
| cam_A | night | **0** | 8 |
| cam_B | day | 12 | **0** |
| cam_B | dusk | 4 | 4 |
| cam_B | night | 4 | 8 |

Quy tắc 1 của lab: chỉ được chỉnh ngưỡng trên `dev`. Nên **không thể** hiệu chỉnh
ngưỡng riêng cho `cam_A/night`, mà tầng đó chiếm 8/40 ảnh eval (20%).

Hệ quả: đừng chuẩn hoá theo cặp `(camera_id, light)`. Chuẩn hoá theo riêng
`camera_id` thì an toàn — cả `cam_A` và `cam_B` đều có mặt ở hai split.
Chuẩn hoá theo riêng `light` cũng chạy được nhưng `night` chỉ có 4 ảnh dev.

Có một cách nữa không phụ thuộc split: chuẩn hoá **trong từng cảnh gốc**
(`img_NN` có 4 biến thể), so các biến thể với nhau. Cách này không cần mẫu dev
cho tầng nào cả, nhưng giả định mỗi cảnh có ít nhất một biến thể sạch.

### 1.2 Ngưỡng toàn cục sẽ báo nhầm có hệ thống

Độ nét trung vị (Laplacian variance):

| camera | day | dusk | night |
|---|---:|---:|---:|
| cam_A | 944 | 777 | **1578** |
| cam_B | **236** | 174 | 350 |

Hai điều ngược trực giác:

- `cam_B` mềm hơn `cam_A` gấp 4 lần ở ảnh ban ngày. Đó là quang học camera,
  không phải lỗi ảnh. Một ngưỡng chung sẽ quét gần hết `cam_B` vào hàng đợi.
- Ảnh đêm của `cam_A` **nét hơn** ảnh ngày (1578 so với 944). Nên "tối = lỗi" là sai.

Đây đúng là hai trong ba failure mode mà `docs/tracks/T02.md` mục 5 bắt phải phân tích,
nên chúng vừa là bẫy vừa là điểm.

---

## 2. Trạng thái dữ liệu

| Hạng mục | Kết quả |
|---|---|
| Hash manifest | khớp hết (`verify_manifest` 0 problem) |
| Schema `images.csv` | đủ cột, không null, `image_id` không trùng |
| Rò rỉ split | không — 24 cảnh gốc, không cảnh nào ở cả hai split |
| Phân tầng | lệch, xem mục 1.1 |
| Nhãn | **chưa có ai gán** |

Chạy lại kiểm tra: `python tools/data_audit.py --track t02 --out reports/data_audit_t02.md`

### Lỗi đã sửa: CRLF làm hỏng hash

`images.csv` bị hash trong `manifest.csv` và có 97 dòng. Máy nào đặt
`core.autocrlf=true` (mặc định trên Windows) sẽ checkout ra file dài thêm đúng
97 byte → sha256 lệch → `strict_provenance` dừng pipeline với **exit 2**.
Repo trước đó không có `.gitattributes`. Nhánh này thêm vào, đánh dấu
`fixtures/**` là `-text`.

**Nếu bạn đã clone trước khi có nhánh này và đang bị exit 2:**

```bash
git rm --cached -r . && git reset --hard
```

---

## 3. Việc còn lại (đề xuất)

| Ai | Việc | Chặn ai |
|---|---|---|
| **TV2** (xong) | `.gitattributes`, audit, protocol + công cụ nhãn | — |
| **TV2 + TV4** | Gán nhãn 56 ảnh `dev`, hai người độc lập, chạy `merge_internal_labels.py` | chặn TV3 và TV4 |
| **TV1** Lead | Điền `group_id` + `owner` trong `configs/lab.yaml`; merge nhánh này | chặn mọi run |
| **TV3** Algorithm | `src/pipeline.py`: `process()` theo ràng buộc mục 1, trả cột `image_id` + `score` | — |
| **TV3** | Baseline: một ngưỡng Laplacian toàn cục (`src/examples/` đã có bản random) | — |
| **TV4** QA | Thêm test cho `process()`; chốt `reports/metric_contract.md` | cần nhãn |
| **TV5** Review | Contact sheet 20 ảnh, vòng override, `audit_log.jsonl`, `group_report.md` | cần pipeline chạy |

### Thứ tự khoá nhau

```
merge nhánh này  ->  TV1 điền lab.yaml  ->  TV3 viết process()  ->  TV5 review loop
                 \
                  ->  TV2+TV4 gán nhãn  ->  chốt ngưỡng  ->  TV4 đo baseline vs PoC
```

Gán nhãn và viết `process()` chạy song song được. Nhưng **chốt ngưỡng phải đợi nhãn**,
nên bắt đầu gán sớm.

---

## 4. Cách gán nhãn

```bash
xdg-open reports/internal_label_sheet_t02_A.html     # người thứ hai mở bản _B
```

Không có file HTML thì sinh lại:

```bash
python tools/make_label_sheet.py --track t02 --split dev --annotator A
```

Gán hết 56 ảnh → **Export CSV** → đổi tên thành `reports/internal_labels_t02_A.csv`
(và `_B.csv`) → chạy:

```bash
python tools/merge_internal_labels.py
```

Hai quy ước dễ lệch nhau nhất, chốt trước khi gán:

1. **Ảnh đêm nhìn rõ nội dung vẫn là `none`**, không phải `dark`.
2. **Ảnh `cam_B` so với `cam_B` khác**, không so với `cam_A`.

Chi tiết ở `reports/internal_label_protocol.md`. Không gán split `eval` —
gán rồi chỉnh ngưỡng theo đó là vi phạm quy tắc 1.
