"""Render an offline PNG contact sheet for manual dev labeling (T02).

Captions show only image_id, so the sheet does not leak feature-based guesses.

Usage:
    python tools/_t02_label_sheet.py --folder 2
    python tools/_t02_label_sheet.py --ids img_07_2,img_07_3 --out reports/sheet.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "t02_raw_qc"

FOLDERS = {
    "2": [
        "img_07_2", "img_07_3",
        "img_08_0", "img_08_1", "img_08_2", "img_08_3",
        "img_09_0", "img_09_1", "img_09_2", "img_09_3",
        "img_10_0", "img_10_1", "img_10_2", "img_10_3",
    ],
}


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(str(Path(r"C:\Windows\Fonts") / name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default="2", help="label folder id (known: 2)")
    ap.add_argument("--ids", help="comma-separated image_ids (overrides --folder)")
    ap.add_argument("--out", type=Path, help="output PNG path")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--width", type=int, default=480, help="thumbnail width in px")
    args = ap.parse_args()

    if args.ids:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]
        stem = "custom"
    else:
        if args.folder not in FOLDERS:
            print(f"ERROR: folder {args.folder!r} mapping unknown; pass --ids")
            return 1
        ids = FOLDERS[args.folder]
        stem = f"folder_{args.folder}"

    out = args.out or ROOT / "reports" / f"dev_label_sheet_{stem}.png"
    paths = [FIXTURES / "images" / f"{image_id}.jpg" for image_id in ids]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print("ERROR: missing local images:\n  " + "\n  ".join(missing))
        return 1

    first = Image.open(paths[0])
    thumb_h = round(args.width * first.height / first.width)
    pad = 10
    caption_h = 30
    header_h = 44
    rows = (len(ids) + args.cols - 1) // args.cols
    cell_w = args.width + pad
    cell_h = thumb_h + caption_h + pad

    canvas = Image.new("RGB", (args.cols * cell_w + pad, header_h + rows * cell_h + pad), "white")
    draw = ImageDraw.Draw(canvas)
    f_head = font(22)
    f_cap = font(18)
    title = f"T02 dev label sheet - {stem} ({len(ids)} images)"
    draw.text((pad + 2, 10), title, fill="black", font=f_head)

    for i, (image_id, path) in enumerate(zip(ids, paths)):
        img = Image.open(path).convert("RGB").resize((args.width, thumb_h), Image.LANCZOS)
        x = pad + (i % args.cols) * cell_w
        y = header_h + (i // args.cols) * cell_h
        canvas.paste(img, (x, y))
        draw.rectangle([x, y, x + args.width - 1, y + thumb_h - 1], outline="#bbbbbb")
        draw.text((x + 2, y + thumb_h + 5), image_id, fill="black", font=f_cap)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"saved {out} ({canvas.width}x{canvas.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
