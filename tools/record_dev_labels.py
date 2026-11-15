"""Record manual dev labels for T02 (Raw QC Triage).

The dev set is human-labeled. This tool never reads fixtures/*/gt/.

Usage:
    python tools/record_dev_labels.py --init
    python tools/record_dev_labels.py --labels "img_07_2=blur/2; img_07_3=none/0"
    python tools/record_dev_labels.py --file reports/labels_batch_2.txt
    python tools/record_dev_labels.py --status
    python tools/record_dev_labels.py --status --folder 2

Label syntax (one per line, ';' also separates entries):
    img_07_2 = blur / 2
    img_08_1 = none / 0
    img_08_3 = none / 0 *hn        # hard negative (clean but looks defective)
    img_09_1 = dark / 1  # goc toi, mat chi tiet vung toi

Aliases: jpg|jpeg -> compression; clean|ok|sharp -> none.
Rule: none <=> severity 0; defect <=> severity 1..2.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "t02_raw_qc"
CSV_PATH = ROOT / "reports" / "dev_labels.csv"

COLUMNS = [
    "image_id",
    "group_id",
    "camera_id",
    "light",
    "split",
    "label_folder",
    "defect_type",
    "severity",
    "is_defect",
    "hard_negative",
    "labeler",
    "notes",
    "labeled_at",
]

DEFECTS = {"none", "blur", "glare", "dark", "compression"}
ALIASES = {
    "clean": "none",
    "ok": "none",
    "sharp": "none",
    "jpg": "compression",
    "jpeg": "compression",
}

# Folder assignment shared by the team (from the GitHub outimages/dev_images tree).
FOLDERS = {
    "1": [
        "img_00_0", "img_00_1", "img_00_2", "img_00_3",
        "img_02_0", "img_02_1", "img_02_2", "img_02_3",
        "img_04_0", "img_04_1", "img_04_2", "img_04_3",
        "img_07_0", "img_07_1",
    ],
    "2": [
        "img_07_2", "img_07_3",
        "img_08_0", "img_08_1", "img_08_2", "img_08_3",
        "img_09_0", "img_09_1", "img_09_2", "img_09_3",
        "img_10_0", "img_10_1", "img_10_2", "img_10_3",
    ],
    "3": [
        "img_18_2", "img_18_3",
        "img_20_0", "img_20_1", "img_20_2", "img_20_3",
        "img_21_0", "img_21_1", "img_21_2", "img_21_3",
        "img_22_0", "img_22_1", "img_22_2", "img_22_3",
    ],
    "4": [
        "img_11_0", "img_11_1", "img_11_2", "img_11_3",
        "img_12_0", "img_12_1", "img_12_2", "img_12_3",
        "img_14_0", "img_14_1", "img_14_2", "img_14_3",
        "img_18_0", "img_18_1",
    ],
}

ENTRY_RE = re.compile(
    r"^(?P<image_id>[A-Za-z0-9_]+)\s*=\s*"
    r"(?P<defect>[A-Za-z?]+)\s*/\s*(?P<severity>[0-9]+)"
    r"\s*(?P<hn>\*?hn)?\s*"
    r"(?:#\s*(?P<note>.*))?$"
)


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def build_template() -> pd.DataFrame:
    images = pd.read_csv(FIXTURES / "images.csv")
    manifest = pd.read_csv(FIXTURES / "manifest.csv")
    manifest = manifest[["file_id", "group_id"]].rename(columns={"file_id": "image_id"})
    dev = images[images["split"] == "dev"].merge(manifest, on="image_id", how="left")

    if dev["group_id"].isna().any():
        fail("missing group_id for some dev images in manifest.csv")

    folder_of = {img: folder for folder, ids in FOLDERS.items() for img in ids}
    return pd.DataFrame(
        {
            "image_id": dev["image_id"],
            "group_id": dev["group_id"],
            "camera_id": dev["camera_id"],
            "light": dev["light"],
            "split": dev["split"],
            "label_folder": dev["image_id"].map(folder_of).fillna(""),
            "defect_type": "",
            "severity": "",
            "is_defect": "",
            "hard_negative": "",
            "labeler": "",
            "notes": "",
            "labeled_at": "",
        }
    )[COLUMNS]


def load_or_init() -> pd.DataFrame:
    if not CSV_PATH.exists():
        df = build_template()
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
        print(f"created {CSV_PATH} ({len(df)} dev rows, labels empty)")
        return df
    df = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        fail(f"{CSV_PATH} is missing columns: {missing}")
    df = df[COLUMNS]
    # Backfill label_folder for rows created before a folder was added to FOLDERS.
    folder_of = {img: folder for folder, ids in FOLDERS.items() for img in ids}
    blank = df["label_folder"] == ""
    df.loc[blank, "label_folder"] = df.loc[blank, "image_id"].map(folder_of).fillna("")
    return df


def parse_entries(text: str) -> list[dict]:
    # '#' starts a comment only outside an entry; entries split on newline or ';'
    entries = []
    errors = []
    for raw_line in text.splitlines() or [text]:
        for chunk in raw_line.split(";"):
            line = chunk.strip()
            if not line or line.startswith("#"):
                continue
            m = ENTRY_RE.match(line)
            if not m:
                errors.append(f"cannot parse: {line!r}")
                continue
            image_id = m["image_id"]
            raw_defect = m["defect"].lower()
            if raw_defect in {"?", "unknown", "unk"}:
                defect = ""  # severity known, defect type not provided
            else:
                defect = ALIASES.get(raw_defect, raw_defect)
            severity = int(m["severity"])
            hard_negative = bool(m["hn"])
            note = (m["note"] or "").strip()

            if defect and defect not in DEFECTS:
                errors.append(f"{image_id}: unknown defect_type {m['defect']!r}")
                continue
            if severity not in (0, 1, 2):
                errors.append(f"{image_id}: severity must be 0, 1 or 2 (got {severity})")
                continue
            if defect == "" and severity == 0:
                errors.append(f"{image_id}: severity 0 requires defect_type none (use none/0)")
                continue
            if defect == "none" and severity != 0:
                errors.append(f"{image_id}: none requires severity 0")
                continue
            if defect not in ("", "none") and severity == 0:
                errors.append(f"{image_id}: {defect} requires severity 1 or 2")
                continue
            if hard_negative and defect != "none":
                errors.append(f"{image_id}: *hn is only valid for none/0")
                continue

            entries.append(
                {
                    "image_id": image_id,
                    "defect_type": defect,
                    "severity": str(severity),
                    "is_defect": "0" if defect == "none" else "1",
                    "hard_negative": "1" if hard_negative else "0",
                    "notes": note,
                }
            )
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
    return entries


def record(entries: list[dict], labeler: str, overwrite: bool) -> None:
    df = load_or_init()
    known = set(df["image_id"])
    seen = set()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for e in entries:
        image_id = e["image_id"]
        if image_id in seen:
            fail(f"{image_id}: duplicate entry in this batch")
        seen.add(image_id)
        if image_id not in known:
            fail(f"{image_id}: not a dev image in fixtures/t02_raw_qc/images.csv")

        row = df.index[df["image_id"] == image_id][0]
        previous = df.at[row, "defect_type"]
        previous_known = df.at[row, "is_defect"] != ""
        if previous_known and not overwrite:
            same = (
                previous == e["defect_type"]
                and df.at[row, "severity"] == e["severity"]
                and df.at[row, "hard_negative"] == e["hard_negative"]
            )
            if same:
                print(f"skip {image_id}: already recorded with the same label")
                continue
            fail(
                f"{image_id}: already labeled "
                f"{previous or '?'}/{df.at[row, 'severity']} by {df.at[row, 'labeler'] or '?'}; "
                "pass --overwrite to replace"
            )

        for key, value in e.items():
            df.at[row, key] = value
        df.at[row, "labeler"] = labeler
        df.at[row, "labeled_at"] = now

    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    print(f"\nrecorded {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} -> {CSV_PATH}")
    summarize(df)


def summarize(df: pd.DataFrame) -> None:
    labeled = df["is_defect"] != ""
    total = len(df)
    print(f"labeled: {labeled.sum()}/{total} | remaining: {(~labeled).sum()}")

    if labeled.any():
        sub = df[labeled].copy()
        sub["type_shown"] = sub["defect_type"].replace("", "?")
        print("\nby defect_type (\"?\" = severity-only, type not provided):")
        counts = sub.groupby(["type_shown", "severity"]).size()
        for (defect, severity), n in counts.items():
            print(f"  {defect:>11} / {severity}: {n}")
        print("\nby label_folder:")
        for folder, n in sub.groupby("label_folder").size().items():
            print(f"  folder {folder or '?':>2}: {n}")
        typed = sub["defect_type"] != ""
        print(f"\ntype known: {typed.sum()}/{len(sub)} | severity-only: {(~typed).sum()}")
    else:
        print("\nby label_folder (all pending):")
        for folder, n in df.groupby("label_folder").size().items():
            print(f"  folder {folder or '?':>2}: {n}")

    remaining = df.loc[~labeled, "image_id"].tolist()
    if remaining:
        shown = ", ".join(remaining[:20])
        more = f" ... (+{len(remaining) - 20})" if len(remaining) > 20 else ""
        print(f"\npending image_ids: {shown}{more}")


def status(folder: str | None) -> None:
    df = load_or_init()
    if folder:
        if folder not in FOLDERS:
            fail(f"unknown label folder {folder!r}; known: {sorted(FOLDERS)}")
        df = df[df["label_folder"] == folder]
        print(f"folder {folder}: scope limited to {len(df)} images\n")
    summarize(df)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--init", action="store_true", help="create reports/dev_labels.csv from dev metadata")
    ap.add_argument("--labels", help="inline batch, e.g. 'img_07_2=blur/2; img_07_3=none/0'")
    ap.add_argument("--file", type=Path, help="read a batch from a text file (same syntax)")
    ap.add_argument("--status", action="store_true", help="show coverage and label distribution")
    ap.add_argument("--folder", help="restrict --status to one label folder (e.g. 2)")
    ap.add_argument("--labeler", default="user", help="labeler name recorded in the CSV (default: user)")
    ap.add_argument("--overwrite", action="store_true", help="replace an existing different label")
    args = ap.parse_args()

    if args.status and not (args.labels or args.file):
        status(args.folder)
        return 0
    if args.init:
        df = load_or_init()
        summarize(df)
        return 0

    text = args.labels or ""
    if args.file:
        if not args.file.exists():
            fail(f"labels file not found: {args.file}")
        text += "\n" + args.file.read_text(encoding="utf-8-sig")
    if not text.strip():
        ap.print_help()
        return 2

    record(parse_entries(text), args.labeler, args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
