"""Dựng ảnh minh hoạ failure case của baseline T02 (chỉ trên split dev, không đọc ground truth).

    python -m src.main --track t02 --pipeline src.baseline_t02 --output out/baseline --run-name baseline --offline --seed 42
    python -m tools.baseline_failure_cases            # ghi reports/failure_cases/*.png + failure_cases.csv

Danh sách ảnh ở dưới do người phân tích xem bằng mắt (ảnh dev) rồi chọn; ghi chú `verdict` là nhận định thị giác,
KHÔNG phải nhãn chính thức của giảng viên. Hạng (rank) là hạng của ảnh trong split dev theo điểm baseline.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw

INPUT = Path("fixtures/t02_raw_qc")

CASES = {
    # failure mode -> [(image_id, nhận định thị giác của người phân tích)]
    "glare_missed": [("img_22_3", "glare lớn phủ vùng phải"), ("img_02_2", "glare cục bộ ở xe giữa"),
                     ("img_20_3", "glare cục bộ ở xe trái"), ("img_18_2", "glare ở đèn pha xe (ảnh đêm)")],
    "camB_false_alarm": [("img_12_0", "sạch (cam_B, dusk)"), ("img_09_0", "sạch (cam_B, day)"),
                         ("img_21_0", "sạch (cam_B, day)"), ("img_00_0", "sạch (cam_B, day)")],
}


def tile(image_id: str, caption: str) -> Image.Image:
    t = Image.open(INPUT / "images" / f"{image_id}.jpg").convert("RGB")
    out = Image.new("RGB", (t.width, t.height + 30), "white")
    out.paste(t, (0, 30))
    d = ImageDraw.Draw(out)
    d.text((3, 2), caption.split("\n")[0], fill="black")
    d.text((3, 15), caption.split("\n")[1], fill="black")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", type=Path, default=Path("out/baseline/ranked_review.csv"))
    ap.add_argument("--out", type=Path, default=Path("reports/failure_cases"))
    a = ap.parse_args(argv)

    pred = pd.read_csv(a.pred)
    dev = pred[pred.split == "dev"].copy()
    dev["dev_rank"] = dev.score.rank(ascending=False, method="first").astype(int)
    info = dev.set_index("image_id")
    a.out.mkdir(parents=True, exist_ok=True)

    rows = []
    for mode, items in CASES.items():
        tiles = []
        for image_id, verdict in items:
            r = info.loc[image_id]
            rows.append({"failure_mode": mode, "image_id": image_id, "camera_id": r.camera_id, "light": r.light,
                         "lap_var": round(float(r.lap_var), 1), "baseline_dev_rank_of_%d" % len(dev): int(r.dev_rank),
                         "in_top20_of_dev": bool(r.dev_rank <= 20), "verdict": verdict})
            tiles.append(tile(image_id, f"{image_id}  {verdict}\nrank {int(r.dev_rank)}/{len(dev)}  lap_var={r.lap_var:.0f}  {r.camera_id}/{r.light}"))
        sheet = Image.new("RGB", (sum(t.width for t in tiles), tiles[0].height), "white")
        x = 0
        for t in tiles:
            sheet.paste(t, (x, 0)); x += t.width
        sheet.save(a.out / f"{mode}.png")
    table = pd.DataFrame(rows)
    table.to_csv(a.out / "failure_cases.csv", index=False)
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
