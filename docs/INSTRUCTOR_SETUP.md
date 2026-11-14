# Instructor / TA setup - T14 (offline)

Mục tiêu: lớp chạy được **hoàn toàn offline** trên CPU.

## Môi trường

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
# Wheelhouse cho máy không mạng:
.venv/bin/pip download -r requirements.txt -d wheelhouse/
# Trên máy học viên:  pip install --no-index --find-links wheelhouse -r requirements.txt
```

## Fixture và ground truth

Repo học viên chỉ chứa **input** `fixtures/t14_auto_annotation/`. Ground truth (`gt/gt_boxes.csv`), generator và hidden eval
nằm ở **repo private của giảng viên**, chép đè (overlay) khi cần chấm:

```bash
git clone <repo học viên> lab && git clone <repo private giảng viên> lab-instructor
lab-instructor/install.sh lab          # chép gt/ + generator vào lab/ (các path này đã gitignore)
cd lab && pytest -q                    # chạy đủ test, kể cả test cần GT
```

GT guard trong `src.main` chỉ là kiểm tra trung thực (chặn `open()` trong cùng process), không phải ranh giới bảo mật.
Điểm chính thức **chỉ** lấy trên hidden eval nhóm chưa từng có:

```bash
python -m src.evaluate --track t14 --gt hidden_eval/t14_auto_annotation/gt/gt_boxes.csv --pred out/poc/predictions.csv
```

## Model tuỳ chọn

`models_optional/`: YOLO nano weights (hoặc model khác nhóm dùng) - tải trước, ghi checksum + license + version.

## CVAT (human QC)

Điền `CVAT_HOST`, `CVAT_ORG`, `CVAT_PAT` trong `.env` (đã gitignore). Hướng dẫn: `docs/HUONG_DAN_GAN_NHAN_CVAT.md`.

## Preflight 5 phút trước lớp (tắt Wi-Fi)

```bash
make preflight
make test
make baseline && make eval-baseline
```

## Shock test gợi ý

| Input bất ngờ | Cách tạo |
|---|---|
| missing file | xoá 1 ảnh trong bản copy fixture -> `src.main` phải fail rõ (manifest check) |
| network | chạy với `--offline` khi pipeline cố tải model |

## Sau lớp (+24h)

```bash
git clone <repo nhóm> && cd <repo> && git checkout final-24h
make setup && ./run.sh            # run + evaluate + pytest
git shortlog -sne --all           # đối chiếu reports/team_contributions.csv
```
