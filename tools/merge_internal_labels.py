"""Measure agreement between two internal annotators and build the adjudication list.

Implements step 3 of `reports/internal_label_protocol.md`:
  * Cohen's kappa on `is_defect` (the binary the primary metric depends on);
  * raw agreement on `defect_type`;
  * the list of images the two annotators disagree on, for joint adjudication;
  * a merged file where agreed rows are filled in and disagreements left blank.

Usage:
    python tools/merge_internal_labels.py --a reports/internal_labels_t02_A.csv \
                                          --b reports/internal_labels_t02_B.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

KAPPA_MIN = 0.70
AGREE_MIN = 0.70


def cohen_kappa(a: pd.Series, b: pd.Series) -> float | None:
    """Unweighted Cohen's kappa for two aligned categorical series."""
    n = len(a)
    if n == 0:
        return None
    po = float((a.values == b.values).mean())
    cats = sorted(set(a) | set(b))
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else None
    return (po - pe) / (1 - pe)


def load(path: Path, who: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    need = {"image_id", "defect_type", "is_defect"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"{path}: thiếu cột {sorted(missing)}")
    blank = df[df.defect_type == ""]
    if len(blank):
        raise SystemExit(f"{path}: còn {len(blank)} ảnh chưa gán nhãn "
                         f"(ví dụ {list(blank.image_id.head(3))}) — gán hết rồi hãy chạy lại")
    if df.image_id.duplicated().any():
        raise SystemExit(f"{path}: có image_id trùng")
    return df.set_index("image_id").add_suffix(f"_{who}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="reports/internal_labels_t02_A.csv")
    ap.add_argument("--b", default="reports/internal_labels_t02_B.csv")
    ap.add_argument("--out", default="reports/internal_labels_t02_merged.csv")
    ap.add_argument("--disagree", default="reports/internal_labels_t02_disagreements.csv")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]

    A, B = load(root / args.a, "A"), load(root / args.b, "B")
    only_a, only_b = A.index.difference(B.index), B.index.difference(A.index)
    if len(only_a) or len(only_b):
        print(f"CẢNH BÁO: chỉ A có {len(only_a)} ảnh, chỉ B có {len(only_b)} ảnh — so trên phần chung")
    m = A.join(B, how="inner")
    n = len(m)

    k = cohen_kappa(m.is_defect_A, m.is_defect_B)
    agree_type = float((m.defect_type_A == m.defect_type_B).mean())
    agree_bin = float((m.is_defect_A == m.is_defect_B).mean())

    print(f"N chung = {n}")
    print(f"  đồng thuận is_defect   : {agree_bin:.3f}")
    print(f"  Cohen's kappa is_defect: {k:.3f}" if k is not None else "  Cohen's kappa: không tính được")
    print(f"  đồng thuận defect_type : {agree_type:.3f}")
    fails = []
    if k is not None and k < KAPPA_MIN:
        fails.append(f"kappa {k:.3f} < {KAPPA_MIN}")
    if agree_type < AGREE_MIN:
        fails.append(f"đồng thuận defect_type {agree_type:.3f} < {AGREE_MIN}")
    print("  -> ĐẠT ngưỡng protocol" if not fails else "  -> CHƯA ĐẠT: " + "; ".join(fails))

    print("\nMa trận chéo defect_type (hàng = A, cột = B):")
    print(pd.crosstab(m.defect_type_A, m.defect_type_B).to_string())

    dis = m[(m.defect_type_A != m.defect_type_B) | (m.is_defect_A != m.is_defect_B)]
    cols = [c for c in ["defect_type_A", "severity_A", "defect_type_B", "severity_B"] if c in dis.columns]
    dis[cols].to_csv(root / args.disagree, lineterminator="\n")
    print(f"\n{len(dis)} ảnh lệch nhau -> {args.disagree} (hai người xem lại cùng nhau, chốt một nhãn)")

    merged = pd.DataFrame(index=m.index)
    same = m.defect_type_A == m.defect_type_B
    merged["defect_type"] = m.defect_type_A.where(same, "")
    if "severity_A" in m.columns:
        sev_same = same & (m.severity_A == m.severity_B)
        merged["severity"] = m.severity_A.where(sev_same, "")
    merged["is_defect"] = m.is_defect_A.where(m.is_defect_A == m.is_defect_B, "")
    merged["status"] = ["agreed" if s else "NEEDS_ADJUDICATION" for s in same]
    merged["note"] = ""
    merged.to_csv(root / args.out, lineterminator="\n")
    print(f"{int(same.sum())}/{n} ảnh thống nhất -> {args.out}")
    print("Điền nốt các dòng NEEDS_ADJUDICATION rồi lưu thành reports/internal_labels_t02_final.csv")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
