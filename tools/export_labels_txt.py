"""Export folder-2 dev labels as a Notepad-friendly table (table only, no prose).

Writes the same table to:
    reports/folder2_labels.txt
    reports/dev_labels_56.txt

Run: python tools/export_labels_txt.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "reports" / "dev_labels.csv"
OUT_DIR = ROOT / "reports"

W_ID, W_TYPE, W_SEV, W_DEF = 10, 13, 9, 10
HEADER = (
    f"{'image_id':<{W_ID}}{'defect_type':<{W_TYPE}}"
    f"{'severity':^{W_SEV}}{'is_defect':^{W_DEF}}"
)
RULE = "-" * len(HEADER)


def row_text(r: pd.Series) -> str:
    return (
        f"{r['image_id']:<{W_ID}}{r['defect_type']:<{W_TYPE}}"
        f"{r['severity']:^{W_SEV}}{r['is_defect']:^{W_DEF}}"
    )


def main() -> None:
    df = pd.read_csv(CSV, dtype=str, keep_default_na=False)
    folder2 = df[df["label_folder"] == "2"]
    lines = [HEADER, RULE]
    lines += [row_text(r) for _, r in folder2.iterrows()]
    lines += [RULE]
    text = "\r\n".join(lines) + "\r\n"

    for name in ("folder2_labels.txt", "dev_labels_56.txt"):
        path = OUT_DIR / name
        path.write_text(text, encoding="utf-8-sig", newline="")
        print(f"saved {path}")


if __name__ == "__main__":
    main()
