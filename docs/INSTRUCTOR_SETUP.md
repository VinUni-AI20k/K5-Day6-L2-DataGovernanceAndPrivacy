# Instructor / TA setup — gói offline P0–P6

Mục tiêu: lớp chạy được **hoàn toàn offline** trên CPU; Internet chậm không cản tiến độ.

## P0 · `py_env/` (tất cả nhóm)

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
# Wheelhouse cho máy không mạng:
.venv/bin/pip download -r requirements.txt -d wheelhouse/
# Trên máy học viên:  pip install --no-index --find-links wheelhouse -r requirements.txt
```

## Fixtures synthetic (đã commit sẵn — mọi track)

`fixtures/` được sinh bởi `python -m tools.make_fixtures` (deterministic, seed 42; sinh lại cho ra hash giống hệt **với cùng phiên bản Pillow/OpenCV** — bản commit dùng Pillow 13 / OpenCV 5.0; phiên bản khác chỉ đổi byte JPEG và `t13 pool_features.csv`, GT không đổi).
Ground truth nằm trong `fixtures/<track>/gt/`. Nếu muốn **hidden eval** riêng: đổi seed trong `tools/make_fixtures.py`
(ví dụ cộng 1000 vào mọi `default_rng(...)`), sinh ra thư mục khác, giữ kín và chấm bằng
`python -m src.evaluate --track tXX --gt <hidden>/gt/<file> --pred <out của nhóm>`. Cấu trúc file y hệt nên pipeline của nhóm chạy được ngay.

Mapping với gói trong handout:

| Gói | Track | Có sẵn trong repo | Bổ sung tuỳ chọn |
|---|---|---|---|
| P1 `driving_small/` | T01–03, T05, T10, T13 | `fixtures/t01,t02,t03,t05,t10,t13` | `data/real/bdd/` (240 ảnh BDD100K + weather/timeofday/scene + boxes) |
| P2 `sensors_small/` | T04 | `fixtures/t04_sensor_sync` (+ `shock/` clock reset) | — |
| P3 `labels_small/` | T06, T11, T14 | `fixtures/t06,t11,t14` | `data/real/coco/` (150 ảnh COCO val2017 + boxes), `data/real/bdd/detections.csv` |
| P4 `privacy_safe/` | T07–09 | `fixtures/t07,t08,t09` (mặt/biển số synthetic) | `data/real/plates/` (60 ảnh biển số thật, CC BY 4.0) |
| P5 `vendor_batches/` | T12 | `fixtures/t12_vendor_batches` (5×100) | `python -m tools.make_fixtures --tracks t12 --t12-size 1000` |
| P6 `models_optional/` | T07, T14 | — | MediaPipe face `.tflite`, YOLO nano weights — tải trước, ghi checksum + license |

## Dữ liệu thật từ Hugging Face (chạy TRƯỚC buổi học)

```bash
cp .env.example .env        # điền HF_TOKEN=<read token của bạn>  (.env đã được gitignore)
make real-data              # = python -m tools.download_real_samples   (~2 phút, ~80 MB index BDD + ảnh)
make verify                 # kiểm tra sha256 mọi manifest
```

| Pack | Repo HF | License (kiểm tra lại trước khi dùng ngoài lớp) |
|---|---|---|
| `bdd/` | `dgural/bdd100k` (FiftyOne export của BDD100K val) | BDD100K License — non-commercial research/education |
| `coco/` | `LibreYOLO/coco-val2017-mini500` | Annotations CC BY 4.0; ảnh theo license Flickr từng ảnh (cột `license_id`) |
| `plates/` | `keremberke/license-plate-object-detection` (test split) | CC BY 4.0 (Roboflow Universe) |

Tuỳ chọn: `--bdd-n`, `--coco-n`, `--plates-n`, `--max-side` (mặc định 640 px; handout cho phép ≤1024), `--packs bdd coco`.
Script tải theo stratified sampling (ưu tiên foggy / tunnel / gas station / parking lot, cân bằng weather × timeofday).

Phân phối cho lớp: nén `data/real/` và chép qua USB/LAN nội bộ. **Không** đưa lên repo công khai hay cloud:
gói này có người và biển số thật. Học viên dùng `data/real/` để mở rộng/khám phá; chấm điểm chính trên fixtures.

## Preflight 5 phút trước lớp (tắt Wi-Fi)

```bash
make preflight      # Python, packages, fixture hashes, offline guard, data/real, không lộ token
make test
make baseline TRACK=t11 && make eval-baseline TRACK=t11
```

## Trong lớp: shock test gợi ý

| Input bất ngờ | Cách tạo |
|---|---|
| missing file | xoá 1 ảnh trong bản copy fixture → `src.main` phải fail rõ (manifest check) |
| corrupt JSON | cắt nửa `releases/candidates/r03/annotations.json` (T06) hoặc 1 case (T09) |
| clock reset | `fixtures/t04_sensor_sync/shock/` |
| risk slice | chỉ đưa ảnh `condition=dark` (T07) / batch `b5_dusk_far_peds` (T10) |
| network | chạy với `--offline` khi pipeline cố tải model |

## Sau lớp (+24h)

```bash
git clone <repo nhóm> && cd <repo> && git checkout final-24h
make setup && ./run.sh            # run + evaluate + pytest
git shortlog -sne --all           # đối chiếu reports/team_contributions.csv
```
