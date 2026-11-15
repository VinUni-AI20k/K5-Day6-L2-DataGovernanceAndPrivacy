"""Tạo contact sheet CHỈ gồm ảnh split=dev (không điểm, không gợi ý) + mẫu dev_labels.csv để tự gán nhãn.

    python -m tools.t02_make_dev_sheet                 # -> out/dev_sheet.html, labels/dev_labels.csv
Ảnh eval KHÔNG bao giờ được đưa vào sheet (quy tắc: không xem/gán nhãn/tune trên eval).
Điền labels/dev_labels.csv: is_defect = 0/1, defect_type = none|blur|dark|glare|compression.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.common.contact_sheet import render_contact_sheet
from src.common.review import make_review_queue

TYPES = "none|blur|dark|glare|compression"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="fixtures/t02_raw_qc")
    ap.add_argument("--out-html", default="out/dev_sheet.html")
    ap.add_argument("--labels", default="labels/dev_labels.csv")
    ap.add_argument("--force", action="store_true", help="ghi đè dev_labels.csv đã có (mặc định: không đụng)")
    a = ap.parse_args(argv)

    images = pd.read_csv(Path(a.input) / "images.csv")
    dev = images[images["split"] == "dev"].sort_values("image_id").reset_index(drop=True)
    assert (dev["split"] == "dev").all() and len(dev) > 0
    dev = dev.assign(score=0.0, reason="", slice=dev["camera_id"].astype(str) + "/" + dev["light"].astype(str))
    q = make_review_queue(dev, "image_id", "score", len(dev), slice_col="slice", evidence_col="path", ascending=True)
    render_contact_sheet(q, a.out_html, image_root=a.input, fields=("item_id", "slice"),
                         title=f"T02 dev ({len(dev)} ảnh) · gán nhãn: {TYPES}", thumb_width=300)
    lab = Path(a.labels)
    lab.parent.mkdir(parents=True, exist_ok=True)
    if lab.exists() and not a.force:
        print(f"[dev-sheet] giữ nguyên {lab} (đã tồn tại, dùng --force để tạo lại)")
    else:
        pd.DataFrame({"image_id": dev["image_id"], "is_defect": "", "defect_type": ""}).to_csv(lab, index=False)
        print(f"[dev-sheet] tạo mẫu nhãn {lab} ({len(dev)} dòng)")
    print(f"[dev-sheet] mở {a.out_html} bằng trình duyệt; {len(dev)} ảnh dev, không có ảnh eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
