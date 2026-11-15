"""Calibrate T02 PoC v1 thresholds on the 56 manual dev labels.

This script is the provenance for the frozen constants in src/poc/t02_v1.py.
It never reads fixtures/*/gt/ and never touches the eval split.

Inputs : fixtures/t02_raw_qc/images.csv, reports/dev_labels.csv
Outputs: reports/t02_calibration.json, reports/t02_calibration.md

Run: python tools/_t02_calibrate.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.poc import t02_v1 as V1  # noqa: E402
from src.poc.t02_v1 import extract, second_highest, second_lowest  # noqa: E402

FIXTURES = ROOT / "fixtures" / "t02_raw_qc"
LABELS = ROOT / "reports" / "dev_labels.csv"
OUT_JSON = ROOT / "reports" / "t02_calibration.json"
OUT_MD = ROOT / "reports" / "t02_calibration.md"

# name -> (ratio column, lower is worse, decimals for lo, decimals for hi)
FEATURES = {
    "dark": ("bright_ratio", True, 3, 3),
    "blur": ("lap_ratio", True, 3, 3),
    "compression": ("block_ratio", False, 2, 2),
    "glare": ("blob", False, 4, 3),
}
FROZEN = {
    "dark": (V1.DARK_LO, V1.DARK_HI),
    "blur": (V1.BLUR_LO, V1.BLUR_HI),
    "compression": (V1.COMP_LO, V1.COMP_HI),
    "glare": (V1.GLARE_LO, V1.GLARE_HI),
}


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def ceil_to(x: float, nd: int) -> float:
    return math.ceil(x * 10**nd - 1e-12) / 10**nd


def floor_to(x: float, nd: int) -> float:
    return math.floor(x * 10**nd + 1e-12) / 10**nd


def round_lo(x: float, lower_is_worse: bool, nd: int) -> float:
    """Round the detection boundary toward the defect side (expand detections)."""
    return ceil_to(x, nd) if lower_is_worse else floor_to(x, nd)


def round_hi(x: float, lower_is_worse: bool, nd: int) -> float:
    """Round the severity-2 boundary toward the clean side (fewer sev-2 calls)."""
    return floor_to(x, nd) if lower_is_worse else ceil_to(x, nd)


def load() -> pd.DataFrame:
    images = pd.read_csv(FIXTURES / "images.csv")
    labels = pd.read_csv(LABELS, dtype=str, keep_default_na=False)
    if len(labels) != 56 or labels["image_id"].nunique() != 56:
        fail(f"expected 56 unique dev labels, got {len(labels)} rows")
    if (labels["is_defect"] == "").any():
        fail("dev_labels.csv still has unlabeled rows")

    raw = extract(images[images["split"] == "dev"].reset_index(drop=True), FIXTURES)
    g = raw.groupby("grp")
    raw["lap_ratio"] = raw["lap"] / g["lap"].transform("max").clip(lower=1e-6)
    raw["bright_ratio"] = raw["bright"] / g["bright"].transform(second_highest).clip(lower=1e-6)
    raw["block_ratio"] = raw["block"] / g["block"].transform(second_lowest).clip(lower=1e-6)

    df = raw.merge(
        labels[["image_id", "defect_type", "severity", "is_defect", "light", "notes"]],
        on="image_id",
        how="left",
    )
    if df[["severity", "is_defect"]].isna().any().any():
        fail("feature/label merge lost rows")
    df["severity"] = df["severity"].astype(int)
    df["is_defect"] = df["is_defect"].astype(int)
    df["type"] = df["defect_type"].replace("", np.nan)
    return df


def fit_lo(df: pd.DataFrame, fallback: dict | None = None) -> tuple[dict, dict]:
    """Midpoint between the clean extreme and the closest *separable* typed positive."""
    clean = df[df["is_defect"] == 0]
    lo, excluded = {}, {}
    for name, (col, lower, _, _) in FEATURES.items():
        pos = df[df["type"] == name]
        if pos.empty:
            if fallback is None:
                fail(f"{name}: no typed positive in training labels")
            lo[name] = fallback[name]
            excluded[name] = {"fallback": True}
            continue
        clean_extreme = clean[col].min() if lower else clean[col].max()

        # A positive on the clean side cannot be separated by this feature.
        if lower:
            ok = pos[pos[col] < clean_extreme]
        else:
            ok = pos[pos[col] > clean_extreme]
        dropped = pos.loc[~pos.index.isin(ok.index), ["image_id", col]].to_dict("records")
        if ok.empty:
            if fallback is None:
                fail(f"{name}: every typed positive overlaps the clean range")
            lo[name] = fallback[name]
            excluded[name] = {"dropped": dropped, "fallback": True}
            continue
        pos_extreme = ok[col].max() if lower else ok[col].min()
        lo[name] = (clean_extreme + pos_extreme) / 2
        excluded[name] = {"dropped": dropped}
    return lo, excluded


def fit_hi(df: pd.DataFrame) -> tuple[dict, dict]:
    """Severity-2 boundary from typed rows only."""
    hi, meta = {}, {}
    for name, (col, lower, _, _) in FEATURES.items():
        sub = df[(df["type"] == name) & (df["severity"] > 0)]
        s1 = sub.loc[sub["severity"] == 1, col]
        s2 = sub.loc[sub["severity"] == 2, col]
        if s2.empty:
            hi[name] = float(s1.min()) / 1.2 if lower else float(s1.max()) * 1.2
            meta[name] = {"rule": "no typed sev2: shrink from sev1 by 1.2x"}
            continue
        if lower:
            gap = float(s2.max()) < float(s1.min())
            if gap:
                hi[name] = math.sqrt(float(s2.max()) * float(s1.min()))
                meta[name] = {"rule": "geometric midpoint (gap)", "gap": True}
            else:
                hi[name] = float(s2.max())
                meta[name] = {"rule": "overlap: max(sev2)", "gap": False}
        else:
            gap = float(s2.min()) > float(s1.max())
            if gap:
                hi[name] = math.sqrt(float(s2.min()) * float(s1.max()))
                meta[name] = {"rule": "geometric midpoint (gap)", "gap": True}
            else:
                hi[name] = float(s2.min())
                meta[name] = {"rule": "overlap: min(sev2)", "gap": False}
    return hi, meta


def scores_with(df: pd.DataFrame, lo: dict, hi: dict) -> pd.DataFrame:
    s = pd.DataFrame(index=df.index)
    s["dark"] = ((lo["dark"] - df["bright_ratio"]) / (lo["dark"] - hi["dark"])).clip(lower=0)
    s["blur"] = ((lo["blur"] - df["lap_ratio"]) / (lo["blur"] - hi["blur"])).clip(lower=0)
    s["compression"] = ((df["block_ratio"] - lo["compression"]) / (hi["compression"] - lo["compression"])).clip(lower=0)
    s["glare"] = (
        np.log10(df["blob"].clip(lower=1e-9) / lo["glare"]) / np.log10(hi["glare"] / lo["glare"])
    ).clip(lower=0)
    return s


def main() -> None:
    df = load()
    clean = df[df["is_defect"] == 0]
    defects = df[df["is_defect"] == 1]
    typed = df[df["type"].notna()]

    lo_exact, excluded = fit_lo(df)
    hi_exact, hi_meta = fit_hi(df)

    rows = []
    for name, (col, lower, dlo, dhi) in FEATURES.items():
        lo_frozen = round_lo(lo_exact[name], lower, dlo)
        hi_frozen = round_hi(hi_exact[name], lower, dhi)
        if abs(lo_frozen - FROZEN[name][0]) > 1e-12 or abs(hi_frozen - FROZEN[name][1]) > 1e-12:
            fail(
                f"{name}: src/poc/t02_v1.py has ({FROZEN[name][0]}, {FROZEN[name][1]}) "
                f"but labels calibrate to ({lo_frozen}, {hi_frozen}); update the module deliberately"
            )
        pos = df[df["type"] == name]
        ce = clean[col].min() if lower else clean[col].max()
        pe = pos[col].max() if lower else pos[col].min()
        rows.append(
            {
                "feature": name,
                "column": col,
                "lower_is_worse": lower,
                "clean_extreme": float(ce),
                "closest_typed_positive": float(pe),
                "lo_exact": float(lo_exact[name]),
                "lo_frozen": lo_frozen,
                "hi_exact": float(hi_exact[name]),
                "hi_frozen": hi_frozen,
                "excluded": excluded[name],
                "severity_rule": hi_meta[name],
            }
        )

    # in-sample behaviour of the frozen constants
    sc = scores_with(df, {k: FROZEN[k][0] for k in FROZEN}, {k: FROZEN[k][1] for k in FROZEN})
    pred_score = sc.max(axis=1)
    fired = sc > 0
    pred_type = pd.Series("none", index=df.index)
    for t in V1.TYPE_PRIORITY:
        pred_type = pred_type.mask(fired[t] & (pred_type == "none"), t)

    clean_flagged = df.index[(df["is_defect"] == 0) & (pred_score > 0)]
    defects_missed = df.index[(df["is_defect"] == 1) & (pred_score == 0)]
    typed_defects = df[(df["is_defect"] == 1) & df["type"].notna()]
    type_ok = int((typed_defects["type"] == pred_type.loc[typed_defects.index]).sum())

    # severity accuracy on typed rows (severity is NOT part of the T02 metric)
    sev_ok = 0
    for i, r in typed.iterrows():
        t = r["type"]
        if t == "none":
            sev_ok += int(pred_type.loc[i] == "none")
            continue
        if pred_type.loc[i] != t:
            continue
        if t == "dark":
            s = 2 if r["bright_ratio"] <= FROZEN["dark"][1] else 1
        elif t == "blur":
            s = 2 if r["lap_ratio"] <= FROZEN["blur"][1] else 1
        elif t == "compression":
            s = 2 if r["block_ratio"] >= FROZEN["compression"][1] else 1
        else:
            s = 2 if r["blob"] >= FROZEN["glare"][1] else 1
        sev_ok += int(s == r["severity"])

    # leave-one-group-out: recalibrate lo without the held-out group
    folds = []
    for grp in sorted(df["grp"].unique()):
        train = df[df["grp"] != grp]
        test = df[df["grp"] == grp]
        flo, fex = fit_lo(train, fallback=lo_exact)
        fsc = scores_with(test, flo, hi_exact)
        fscore = fsc.max(axis=1)
        fp = int(((test["is_defect"] == 0) & (fscore > 0)).sum())
        fn = int(((test["is_defect"] == 1) & (fscore == 0)).sum())
        folds.append(
            {
                "group": grp,
                "n": len(test),
                "fp": fp,
                "fn": fn,
                "lo": {k: round(float(v), 4) for k, v in flo.items()},
                "fallback": {k: bool(v.get("fallback")) for k, v in fex.items()},
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "labels_file": str(LABELS.relative_to(ROOT)),
        "labels_sha256": hashlib.sha256(LABELS.read_bytes()).hexdigest(),
        "n_images": int(len(df)),
        "n_clean": int(len(clean)),
        "n_defect": int(len(defects)),
        "n_typed_defect": int(len(typed_defects)),
        "n_type_unknown_defect": int(len(defects) - len(typed_defects)),
        "features": rows,
        "in_sample": {
            "clean_flagged": [df.loc[i, "image_id"] for i in clean_flagged],
            "defects_missed": [df.loc[i, "image_id"] for i in defects_missed],
            "n_positive_score_defects": int(((df["is_defect"] == 1) & (pred_score > 0)).sum()),
            "type_accuracy_typed_defects": type_ok / len(typed_defects),
            "type_correct": type_ok,
            "type_n": int(len(typed_defects)),
            "severity_accuracy_typed_rows": sev_ok / len(typed),
            "severity_correct": sev_ok,
            "severity_n": int(len(typed)),
        },
        "cv": {
            "protocol": "leave-one-group-out, lo refit without the held-out group",
            "folds": folds,
            "fp_total": int(sum(f["fp"] for f in folds)),
            "fn_total": int(sum(f["fn"] for f in folds)),
            "clean_total": int(len(clean)),
            "defect_total": int(len(defects)),
        },
        "frozen_constants": {
            k: {"lo": FROZEN[k][0], "hi": FROZEN[k][1]} for k in FEATURES
        },
        "notes": [
            "19 defects have severity but no defect_type; they are used for binary evaluation only, "
            "not for fitting type/severity thresholds.",
            "img_11_0 and img_12_1 are severity 1 but all four features sit at the group baseline; kept as given, flagged for review.",
            "severity/action is not part of the T02 metric and its accuracy is reported only as a sanity check.",
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ----- markdown ---------------------------------------------------------
    lines = [
        "# T02 — Calibration trên 56 nhãn dev",
        "",
        f"- Thời điểm: `{payload['generated_at']}`",
        f"- Nhãn: `{payload['labels_file']}`, SHA-256 `{payload['labels_sha256'][:16]}…`",
        f"- {payload['n_clean']} clean / {payload['n_defect']} defect "
        f"({payload['n_typed_defect']} defect có type, {payload['n_type_unknown_defect']} chỉ có severity)",
        "- Tất cả 56 nhãn được dùng để đo binary; 15 typed defects dùng để fit ngưỡng type/severity.",
        "",
        "## Ngưỡng",
        "",
        "| feature | ratio | clean extreme | typed positive gần nhất | lo exact | lo frozen | hi exact | hi frozen |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['feature']} | `{r['column']}` | {r['clean_extreme']:.5g} | "
            f"{r['closest_typed_positive']:.5g} | {r['lo_exact']:.5g} | **{r['lo_frozen']:.5g}** | "
            f"{r['hi_exact']:.5g} | **{r['hi_frozen']:.5g}** |"
        )

    lines += [
        "",
        "Quy tắc: `lo` = midpoint giữa clean extreme và positive typed gần nhất, làm tròn "
        "*về phía defect* (feature càng thấp càng xấu: lên; càng cao càng xấu: xuống); "
        "`hi` làm tròn *về phía clean* (ngược lại). Positive nằm ngoài khoảng tách được "
        "ghi nhận riêng (blur: `img_08_2`).",
        "",
        "## Kết quả in-sample (ngưỡng frozen)",
        "",
        f"- Clean bị flag: **{len(payload['in_sample']['clean_flagged'])}/{payload['n_clean']}**",
        f"- Defect bị bỏ: **{len(payload['in_sample']['defects_missed'])}/{payload['n_defect']}** "
        f"({', '.join(payload['in_sample']['defects_missed'])})",
        f"- Defect có score > 0: **{payload['in_sample']['n_positive_score_defects']}/{payload['n_defect']}**",
        f"- Type accuracy trên defect có type: "
        f"**{payload['in_sample']['type_correct']}/{payload['in_sample']['type_n']}** "
        f"= {payload['in_sample']['type_accuracy_typed_defects']:.3f}",
        f"- Severity accuracy trên row có type: "
        f"**{payload['in_sample']['severity_correct']}/{payload['in_sample']['severity_n']}** "
        f"= {payload['in_sample']['severity_accuracy_typed_rows']:.3f} "
        "(không nằm trong metric T02)",
        "",
        "## Leave-one-group-out",
        "",
        f"- Tổng out-of-fold: **{payload['cv']['fp_total']}/{payload['cv']['clean_total']} clean bị flag**, "
        f"**{payload['cv']['fn_total']}/{payload['cv']['defect_total']} defect bị bỏ**.",
        "- `lo` blur thay đổi mạnh khi fold chứa `img_00_0` hoặc `img_09_0` bị giữ lại "
        "(xem bảng folds trong JSON): biên clean-vs-blur rất hẹp, đây là điểm yếu đã biết.",
        "",
        "## Ghi chú nhãn",
        "",
        "- `img_11_0`, `img_12_1`: severity 1 nhưng cả 4 feature đều ở mức tham chiếu nhóm; "
        "giữ nguyên nhãn người dùng, cần xem lại.",
        "- 19 defect chỉ có severity, không có type → không dùng để fit ngưỡng type/severity; "
        "vẫn được dùng để kiểm tra binary recall.",
        "",
        "**Freeze:** các hằng số trong `src/poc/t02_v1.py` khớp bảng trên; "
        "eval không được đọc để chỉnh ngưỡng.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    for r in rows:
        print(
            f"  {r['feature']:11s} lo={r['lo_frozen']:<7g} hi={r['hi_frozen']:<7g} "
            f"excluded={r['excluded'].get('dropped', [])}"
        )
    print(
        f"in-sample: clean flagged {len(payload['in_sample']['clean_flagged'])}/{payload['n_clean']}, "
        f"defects missed {len(payload['in_sample']['defects_missed'])}/{payload['n_defect']}, "
        f"type {payload['in_sample']['type_correct']}/{payload['in_sample']['type_n']}"
    )
    print(
        f"LOSO: FP {payload['cv']['fp_total']}/{payload['cv']['clean_total']}, "
        f"FN {payload['cv']['fn_total']}/{payload['cv']['defect_total']}"
    )


if __name__ == "__main__":
    main()
