"""Dev-only evaluation of T02 PoC v1 against the frozen baseline.

Scope
-----
* Reads fixtures/t02_raw_qc/images.csv and the 56 manual dev labels in
  reports/dev_labels.csv.  It never reads fixtures/*/gt/ and never touches the
  40 eval labels (which are not available locally).
* B=28 is 50% of the 56 dev images, matching the eval budget B=20/40.
  B=20 (the official eval budget) is reported as a secondary view.
* Type accuracy is computed only on the 15 defective dev rows that have a
  defect_type; the 19 severity-only defects are used for binary metrics only.

Outputs
-------
reports/t02_dev_eval.json
reports/t02_dev_eval.md

Run: python tools/_t02_dev_eval.py
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

FIXTURES = ROOT / "fixtures" / "t02_raw_qc"
LABELS = ROOT / "reports" / "dev_labels.csv"
POC_PRED = ROOT / "out" / "poc_v1" / "ranked_review.csv"
BASE_PRED = ROOT / "out" / "baseline" / "ranked_review.csv"
OUT_JSON = ROOT / "reports" / "t02_dev_eval.json"
OUT_MD = ROOT / "reports" / "t02_dev_eval.md"

BUDGETS = (20, 28)
PRIMARY_B = 28
TIE = ("score", "image_id")


def fail(msg: str) -> None:
    raise SystemExit(f"ERROR: {msg}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ranked(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    return df.sort_values(
        [score_col, "image_id"], ascending=[False, True], kind="mergesort"
    )


def average_precision(df: pd.DataFrame, score_col: str) -> float:
    ordered = ranked(df, score_col)
    y = ordered["is_defect"].to_numpy(dtype=int)
    positives = int(y.sum())
    if positives == 0:
        return float("nan")
    hits = 0
    total = 0.0
    for rank, value in enumerate(y, start=1):
        if value:
            hits += 1
            total += hits / rank
    return total / positives


def at_budget(df: pd.DataFrame, score_col: str, budget: int) -> dict:
    top = ranked(df, score_col).head(budget)
    tp = int(top["is_defect"].sum())
    n_defect = int(df["is_defect"].sum())
    return {
        "budget": budget,
        "tp": tp,
        "n": int(len(top)),
        "recall_den": n_defect,
        "precision_den": int(len(top)),
        "recall": tp / n_defect if n_defect else None,
        "precision": tp / len(top) if len(top) else None,
        "false_alarms": top.loc[top["is_defect"] == 0, "image_id"].tolist(),
        "missed": ranked(df, score_col)
        .iloc[budget:]
        .loc[lambda d: d["is_defect"] == 1, "image_id"]
        .tolist(),
    }


def threshold_metrics(df: pd.DataFrame, flag_col: str) -> dict:
    flagged = df[flag_col].to_numpy(dtype=bool)
    positive = df["is_defect"].to_numpy(dtype=int) == 1
    tp = int((flagged & positive).sum())
    fp = int((flagged & ~positive).sum())
    fn = int((~flagged & positive).sum())
    tn = int((~flagged & ~positive).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n_flagged": int(flagged.sum()),
        "false_alarms": df.loc[flagged & ~positive, "image_id"].tolist(),
        "missed": df.loc[~flagged & positive, "image_id"].tolist(),
    }


def label_short(row: pd.Series) -> str:
    defect = row["defect_type"] if row["defect_type"] else "?"
    return f"{row['image_id']} ({defect}/{row['severity']})"


def slice_at_budget(df: pd.DataFrame, score_col: str, dim: str, budget: int) -> list[dict]:
    top = set(ranked(df, score_col).head(budget)["image_id"])
    rows = []
    for value, sub in df.groupby(dim, sort=True):
        defects = sub[sub["is_defect"] == 1]
        clean = sub[sub["is_defect"] == 0]
        hit = int(defects["image_id"].isin(top).sum())
        false_alarm = int(clean["image_id"].isin(top).sum())
        rows.append(
            {
                "slice": f"{dim}={value}",
                "n": int(len(sub)),
                "defects": int(len(defects)),
                "clean": int(len(clean)),
                "recall": hit / len(defects) if len(defects) else None,
                "recall_num": hit,
                "recall_den": int(len(defects)),
                "false_alarm": false_alarm / len(clean) if len(clean) else None,
                "false_alarm_num": false_alarm,
                "false_alarm_den": int(len(clean)),
            }
        )
    return rows


def type_metrics(df: pd.DataFrame, type_col: str) -> dict:
    typed = df[(df["is_defect"] == 1) & (df["defect_type"] != "")]
    correct = int((typed["defect_type"] == typed[type_col]).sum())
    types = ["none", "blur", "compression", "dark", "glare"]
    confusion = {gt: {pred: 0 for pred in types} for gt in types}
    for _, r in typed.iterrows():
        confusion[r["defect_type"]][r[type_col]] += 1
    wrong = [
        {
            "image_id": r["image_id"],
            "gt_type": r["defect_type"],
            "gt_severity": int(r["severity"]),
            "pred_type": r[type_col],
        }
        for _, r in typed[typed["defect_type"] != typed[type_col]].iterrows()
    ]
    return {
        "correct": correct,
        "n": int(len(typed)),
        "accuracy": correct / len(typed) if len(typed) else None,
        "confusion": confusion,
        "wrong": wrong,
    }


def predicted_severity(row: pd.Series) -> int | None:
    """Mirror t02_v1.score_frame's severity rule (sanity check only)."""
    defect = row["defect_type"]
    if defect == "none":
        return 0
    if row["poc_type"] == "none":
        return 0
    if row["poc_type"] != defect:
        return None
    if defect == "dark":
        return 2 if row["bright_ratio"] <= V1.DARK_HI else 1
    if defect == "blur":
        return 2 if row["lap_ratio"] <= V1.BLUR_HI else 1
    if defect == "compression":
        return 2 if row["block_ratio"] >= V1.COMP_HI else 1
    return 2 if row["blob"] >= V1.GLARE_HI else 1


def severity_sanity(df: pd.DataFrame) -> dict:
    """Severity accuracy on typed rows; NOT part of the official T02 metric."""
    typed = df[df["defect_type"] != ""].copy()
    correct = sum(
        int(predicted_severity(r) == r["severity"]) for _, r in typed.iterrows()
    )
    defects = typed[typed["is_defect"] == 1]
    defect_correct = sum(
        int(predicted_severity(r) == r["severity"]) for _, r in defects.iterrows()
    )
    return {
        "typed_rows_correct": correct,
        "typed_rows_n": int(len(typed)),
        "typed_defects_correct": defect_correct,
        "typed_defects_n": int(len(defects)),
    }


def baseline_threshold_provenance(df: pd.DataFrame) -> dict:
    flagged = df[df["base_flag"]]
    unflagged = df[~df["base_flag"]]
    t_low = float(flagged["lap"].max())
    t_high = float(unflagged["lap"].min())
    at_800 = df["lap"] < 800.0
    extra = df[at_800 & ~df["base_flag"]]
    tp800 = int((at_800 & (df["is_defect"] == 1)).sum())
    fp800 = int((at_800 & (df["is_defect"] == 0)).sum())
    return {
        "threshold": 760.0,
        "same_decisions_interval": [t_low, t_high],
        "interval_note": f"any T in ({t_low:g}, {t_high:g}] gives the same flagged set",
        "old_threshold": 800.0,
        "old_tp": tp800,
        "old_fp": fp800,
        "old_extra_flagged": extra[["image_id", "lap", "light", "camera_id"]].to_dict("records"),
    }


def load() -> pd.DataFrame:
    images = pd.read_csv(FIXTURES / "images.csv")
    labels = pd.read_csv(LABELS, dtype=str, keep_default_na=False)
    if len(labels) != 56 or labels["image_id"].nunique() != 56:
        fail(f"expected 56 unique dev labels, got {len(labels)} rows")
    if (labels["is_defect"] == "").any():
        fail("dev_labels.csv still has unlabeled rows")

    dev = images[images["split"] == "dev"].copy()
    if len(dev) != 56:
        fail(f"expected 56 dev images, got {len(dev)}")

    features = pd.read_csv(ROOT / "tools" / "_t02_features_grp.csv")
    features = features[["image_id", "lap_ratio", "bright_ratio", "block_ratio", "blob"]]

    poc = pd.read_csv(POC_PRED).rename(
        columns={
            "score": "poc_score",
            "pred_defect_type": "poc_type",
            "pred_severity": "poc_severity",
        }
    )
    base = pd.read_csv(BASE_PRED).rename(
        columns={
            "score": "base_score",
            "pred_defect_type": "base_type",
        }
    )

    label_cols = ["image_id", "defect_type", "severity", "is_defect", "notes"]
    df = (
        dev.merge(labels[label_cols], on="image_id", how="left")
        .merge(features, on="image_id", how="left")
        .merge(poc[["image_id", "poc_score", "poc_type", "poc_severity"]], on="image_id", how="left")
        .merge(base[["image_id", "lap", "base_score", "base_type"]], on="image_id", how="left")
    )
    if df[["is_defect", "poc_score", "base_score", "lap_ratio"]].isna().any().any():
        fail("merge lost rows or predictions")
    df["is_defect"] = df["is_defect"].astype(int)
    df["severity"] = df["severity"].astype(int)
    df["poc_flag"] = df["poc_type"] != "none"
    df["base_flag"] = df["base_type"] != "none"
    if len(df) != 56:
        fail(f"expected 56 dev rows after merge, got {len(df)}")
    return df


def main() -> None:
    df = load()
    clean = df[df["is_defect"] == 0]
    defects = df[df["is_defect"] == 1]
    typed_defects = defects[defects["defect_type"] != ""]

    models = {}
    for name, score_col, flag_col, type_col in [
        ("baseline", "base_score", "base_flag", "base_type"),
        ("poc_v1", "poc_score", "poc_flag", "poc_type"),
    ]:
        models[name] = {
            "average_precision": average_precision(df, score_col),
            "at_budget": {str(b): at_budget(df, score_col, b) for b in BUDGETS},
            "threshold": threshold_metrics(df, flag_col),
            "type": type_metrics(df, type_col),
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "scope": "56 labelled dev images; eval split (40 images) not scored",
        "labels_file": str(LABELS.relative_to(ROOT)),
        "labels_sha256": sha256(LABELS),
        "poc_pipeline": "src/poc/t02_v1.py",
        "poc_pipeline_sha256": sha256(ROOT / "src" / "poc" / "t02_v1.py"),
        "baseline_pipeline": "src/baselines/t02_laplacian.py",
        "baseline_pipeline_sha256": sha256(ROOT / "src" / "baselines" / "t02_laplacian.py"),
        "n_dev": int(len(df)),
        "n_eval_unscored": int((pd.read_csv(FIXTURES / "images.csv")["split"] == "eval").sum()),
        "n_clean": int(len(clean)),
        "n_defect": int(len(defects)),
        "n_typed_defect": int(len(typed_defects)),
        "n_type_unknown_defect": int(len(defects) - len(typed_defects)),
        "primary_budget": PRIMARY_B,
        "budgets": list(BUDGETS),
        "models": models,
        "slices": {
            "light": {
                name: slice_at_budget(df, score_col, "light", PRIMARY_B)
                for name, score_col in [("baseline", "base_score"), ("poc_v1", "poc_score")]
            },
            "camera_id": {
                name: slice_at_budget(df, score_col, "camera_id", PRIMARY_B)
                for name, score_col in [("baseline", "base_score"), ("poc_v1", "poc_score")]
            },
        },
        "severity_sanity": severity_sanity(df),
        "baseline_threshold": baseline_threshold_provenance(df),
        "frozen_constants": {
            "dark": {"lo": V1.DARK_LO, "hi": V1.DARK_HI},
            "blur": {"lo": V1.BLUR_LO, "hi": V1.BLUR_HI},
            "compression": {"lo": V1.COMP_LO, "hi": V1.COMP_HI},
            "glare": {"lo": V1.GLARE_LO, "hi": V1.GLARE_HI},
        },
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    b = models["baseline"]
    p = models["poc_v1"]
    b28, b20 = b["at_budget"]["28"], b["at_budget"]["20"]
    p28, p20 = p["at_budget"]["28"], p["at_budget"]["20"]
    bt, pt = b["threshold"], p["threshold"]
    btype, ptype = b["type"], p["type"]

    def pct(value):
        return "n/a" if value is None else f"{100 * value:.1f}%"

    def metric_row(label, bv, pv, fmt="pct"):
        if fmt == "pct":
            return f"| {label} | {pct(bv)} | {pct(pv)} |"
        return f"| {label} | {bv} | {pv} |"

    lines = [
        "# T02 — Dev evaluation: baseline vs PoC v1 (56 nhãn tay)",
        "",
        "**Phạm vi:** 56/56 ảnh `dev` có nhãn tay trong `reports/dev_labels.csv`; "
        "không đọc `fixtures/*/gt/`, không chấm 40 ảnh `eval` (chưa có nhãn). "
        "Đây là proxy dev, **không phải** metric chính thức.",
        "",
        f"- Clean: **{len(clean)}** · Defect: **{len(defects)}** "
        f"({len(typed_defects)} defect có type, {len(defects) - len(typed_defects)} chỉ có severity).",
        f"- Budget chính trên dev: **B={PRIMARY_B}** = 50% của 56, tương ứng B=20/40 của eval. "
        f"B=20 cũng được báo để so sánh trực tiếp với budget chính thức.",
        f"- Tie-break: `score` giảm dần, `image_id` tăng dần (giống file dự đoán).",
        "- Type accuracy chỉ tính **15 defect có type**; 19 defect severity-only không có type nên "
        "không thể chấm type.",
        "",
        "## 1. Freeze / provenance",
        "",
        f"- Labels SHA-256: `{payload['labels_sha256'][:16]}…`",
        f"- Pipeline `src/poc/t02_v1.py` SHA-256: `{payload['poc_pipeline_sha256'][:16]}…`",
        f"- Baseline `src/baselines/t02_laplacian.py` SHA-256: `{payload['baseline_pipeline_sha256'][:16]}…`",
        f"- PoC thresholds: dark `{V1.DARK_LO:g}/{V1.DARK_HI:g}`, "
        f"blur `{V1.BLUR_LO:g}/{V1.BLUR_HI:g}`, "
        f"compression `{V1.COMP_LO:g}/{V1.COMP_HI:g}`, "
        f"glare `{V1.GLARE_LO:g}/{V1.GLARE_HI:g}`.",
        f"- Baseline: `lap < 760` (re-freeze trên 56 nhãn dev; mọi T trong "
        f"`({payload['baseline_threshold']['same_decisions_interval'][0]:g}, "
        f"{payload['baseline_threshold']['same_decisions_interval'][1]:g}]` cho cùng quyết định).",
        "",
        "## 2. Ranking quality",
        "",
        "| Metric | Baseline (`lap<760`) | PoC v1 |",
        "|---|---:|---:|",
        f"| Average Precision (56 ảnh) | {b['average_precision']:.4f} | {p['average_precision']:.4f} |",
        metric_row(f"Recall@{p28['budget']} (50% dev)", b28["recall"], p28["recall"]),
        metric_row(f"Precision@{p28['budget']}", b28["precision"], p28["precision"]),
        metric_row(f"Recall@{p20['budget']} (budget official)", b20["recall"], p20["recall"]),
        metric_row(f"Precision@{p20['budget']}", b20["precision"], p20["precision"]),
        "",
        f"Ở B={PRIMARY_B}: baseline đúng **{b28['tp']}/{b28['n']}** slot, PoC đúng "
        f"**{p28['tp']}/{p28['n']}** slot. Baseline có {len(b28['false_alarms'])} ảnh clean "
        f"trong top-{PRIMARY_B} (`{', '.join(b28['false_alarms']) or '—'}`); PoC có "
        f"{len(p28['false_alarms'])}.",
        "",
        f"Ở B={p20['budget']}: baseline **{b20['tp']}/{b20['n']}**, PoC **{p20['tp']}/{p20['n']}**.",
        "",
        "AP là metric phụ (không nằm trong `eval_t02` chính thức); Recall@B/Precision@B mới là "
        "metric chính. AP dùng cùng tie-break `score` giảm dần, `image_id` tăng dần.",
        "",
        "## 3. Threshold (flagged set)",
        "",
        "| Metric | Baseline | PoC v1 |",
        "|---|---:|---:|",
        f"| TP / FP / FN / TN | {bt['tp']} / {bt['fp']} / {bt['fn']} / {bt['tn']} | "
        f"{pt['tp']} / {pt['fp']} / {pt['fn']} / {pt['tn']} |",
        f"| Precision | {pct(bt['precision'])} | {pct(pt['precision'])} |",
        f"| Recall | {pct(bt['recall'])} | {pct(pt['recall'])} |",
        f"| F1 | {pct(bt['f1'])} | {pct(pt['f1'])} |",
        f"| Số ảnh bị flag | {bt['n_flagged']}/56 | {pt['n_flagged']}/56 |",
        "",
        f"- Baseline false alarm: `{', '.join(bt['false_alarms']) or '—'}`.",
        f"- Baseline miss: `{', '.join(bt['missed']) or '—'}`.",
        f"- PoC false alarm: `{', '.join(pt['false_alarms']) or '—'}`.",
        f"- PoC miss: `{', '.join(pt['missed']) or '—'}` "
        "(cả hai đều là nhãn severity-only, feature-neutral; xem mục 7).",
        "",
    ]

    if payload["baseline_threshold"]["old_threshold"]:
        old = payload["baseline_threshold"]
        extra = ", ".join(
            f"`{r['image_id']}` (lap={r['lap']:g}, {r['light']})" for r in old["old_extra_flagged"]
        )
        lines += [
            f"- Baseline cũ `T=800` sẽ flag thêm **{len(old['old_extra_flagged'])} clean** "
            f"({extra}) mà không thêm TP nào: TP/FP = **{old['old_tp']}/{old['old_fp']}** "
            f"so với **{bt['tp']}/{bt['fp']}** ở T=760. Vì ranking score là monotonic theo `lap`, "
            "thay đổi này **không đổi Recall@B/Precision@B**.",
            "",
        ]

    lines += [
        "## 4. Type accuracy (15 defect có type)",
        "",
        "| Model | Đúng | Accuracy |",
        "|---|---:|---:|",
        f"| Baseline | {btype['correct']}/{btype['n']} | {pct(btype['accuracy'])} |",
        f"| PoC v1 | {ptype['correct']}/{ptype['n']} | {pct(ptype['accuracy'])} |",
        "",
        "PoC confusion (hàng = GT, cột = dự đoán):",
        "",
        "| GT \\ Pred | none | blur | compression | dark | glare |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for gt in ["blur", "compression", "dark", "glare"]:
        row = ptype["confusion"][gt]
        lines.append(
            f"| {gt} | {row['none']} | {row['blur']} | {row['compression']} | "
            f"{row['dark']} | {row['glare']} |"
        )
    if ptype["wrong"]:
        lines += [
            "",
            "PoC type sai:",
            "",
            *[
                f"- `{w['image_id']}`: GT `{w['gt_type']}/{w['gt_severity']}` → "
                f"pred `{w['pred_type']}`."
                for w in ptype["wrong"]
            ],
        ]
    lines += [
        "",
        f"Severity sanity (không nằm trong metric T02): PoC đúng "
        f"**{payload['severity_sanity']['typed_defects_correct']}/"
        f"{payload['severity_sanity']['typed_defects_n']}** severity trên defect có type; "
        f"**{payload['severity_sanity']['typed_rows_correct']}/"
        f"{payload['severity_sanity']['typed_rows_n']}** trên toàn bộ row có type.",
        "",
        "## 5. Slice theo `light` ở B=28",
        "",
        "| Slice | n (defect/clean) | Baseline recall | Baseline FA | PoC recall | PoC FA |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for bslice, pslice in zip(
        payload["slices"]["light"]["baseline"], payload["slices"]["light"]["poc_v1"]
    ):
        lines.append(
            f"| {bslice['slice']} | {bslice['n']} ({bslice['defects']}/{bslice['clean']}) | "
            f"{bslice['recall_num']}/{bslice['recall_den']} ({pct(bslice['recall'])}) | "
            f"{bslice['false_alarm_num']}/{bslice['false_alarm_den']} | "
            f"{pslice['recall_num']}/{pslice['recall_den']} ({pct(pslice['recall'])}) | "
            f"{pslice['false_alarm_num']}/{pslice['false_alarm_den']} |"
        )
    lines += [
        "",
        "## 6. Slice theo `camera_id` ở B=28",
        "",
        "| Slice | n (defect/clean) | Baseline recall | Baseline FA | PoC recall | PoC FA |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for bslice, pslice in zip(
        payload["slices"]["camera_id"]["baseline"], payload["slices"]["camera_id"]["poc_v1"]
    ):
        lines.append(
            f"| {bslice['slice']} | {bslice['n']} ({bslice['defects']}/{bslice['clean']}) | "
            f"{bslice['recall_num']}/{bslice['recall_den']} ({pct(bslice['recall'])}) | "
            f"{bslice['false_alarm_num']}/{bslice['false_alarm_den']} | "
            f"{pslice['recall_num']}/{pslice['recall_den']} ({pct(pslice['recall'])}) | "
            f"{pslice['false_alarm_num']}/{pslice['false_alarm_den']} |"
        )

    label_of = dict(zip(df["image_id"], df.apply(label_short, axis=1)))
    lines += [
        "",
        "## 7. Danh sách lỗi / ghi chú",
        "",
        f"**PoC top-{PRIMARY_B} bỏ sót:** "
        + (", ".join(f"`{label_of[i]}`" for i in p28["missed"]) or "—")
        + ".",
        "",
        f"**Baseline top-{PRIMARY_B} bỏ sót:** "
        + (", ".join(f"`{label_of[i]}`" for i in b28["missed"]) or "—")
        + ".",
        "",
        "- `img_11_0` và `img_12_1` được label severity 1 nhưng cả 4 feature đều ở mức "
        "tham chiếu nhóm (sạch hoàn hảo). Giữ nguyên nhãn người dùng, không tự sửa; "
        "đây là 2 FN duy nhất ở ngưỡng của PoC. Cần xem lại ảnh/nhãn.",
        "- `img_08_2` (GT `blur/1`) bị PoC dự đoán `compression`: `block_ratio` vượt "
        "ngưỡng compression trong khi `lap_ratio` không tách được khỏi clean. Đây là "
        "type error duy nhất của PoC.",
        "- Glare: baseline bỏ `img_02_2` (glare/1) ngoài top-28 và bỏ cả `img_20_3`, "
        "`img_22_3`; PoC đưa 4 ảnh glare vào top-28. Đây là gain chính về recall/type.",
        "- `camera_id`: baseline false alarm `img_09_0` (cam_B, clean, lap=187) vì quang học "
        "mềm; PoC không flag ảnh này. Ở chiều ngược lại, top-28 của PoC chỉ có 10/15 defect "
        "cam_B (baseline 14/15) vì 4 defect cam_B có score thấp (0.005–0.089) bị đẩy ra "
        "khỏi budget; baseline bắt chúng nhờ `lap` thấp, nhưng đồng thời tạo false alarm.",
        "",
        "## 8. Kết luận dev",
        "",
        f"- PoC v1 tăng Recall@{PRIMARY_B} từ **{b28['tp']}/{b28['recall_den']}** "
        f"lên **{p28['tp']}/{p28['recall_den']}**, Precision@{PRIMARY_B} từ "
        f"**{pct(b28['precision'])}** lên **{pct(p28['precision'])}**; AP từ "
        f"**{b['average_precision']:.4f}** lên **{p['average_precision']:.4f}**.",
        f"- Ở ngưỡng flag: PoC **{pt['tp']} TP / {pt['fp']} FP / {pt['fn']} FN** so với "
        f"baseline **{bt['tp']} TP / {bt['fp']} FP / {bt['fn']} FN**.",
        f"- Type accuracy tăng từ **{btype['correct']}/{btype['n']}** lên "
        f"**{ptype['correct']}/{ptype['n']}**.",
        "- **Chưa có kết luận eval.** 40 nhãn eval chưa có; khi có, chỉ chấm bằng pipeline "
        "đã freeze này, không chỉnh ngưỡng.",
        "",
        "## 9. Tái lập",
        "",
        "```powershell",
        r".\.venv\Scripts\python.exe tools\_t02_calibrate.py",
        r".\.venv\Scripts\python.exe tools\_t02_dev_eval.py",
        r".\.venv\Scripts\python.exe -m src.main --track t02 --input fixtures/t02_raw_qc "
        "--output out/poc_v1 --run-name poc_v1 --pipeline src.poc.t02_v1 --offline",
        r".\.venv\Scripts\python.exe -m src.main --track t02 --input fixtures/t02_raw_qc "
        "--output out/baseline --run-name baseline --pipeline src.baselines.t02_laplacian --offline",
        "```",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    print(
        f"baseline: AP={b['average_precision']:.4f} R@28={b28['tp']}/{b28['recall_den']} "
        f"P@28={b28['precision']:.4f} | poc: AP={p['average_precision']:.4f} "
        f"R@28={p28['tp']}/{p28['recall_den']} P@28={p28['precision']:.4f}"
    )
    print(
        f"type: baseline {btype['correct']}/{btype['n']}, poc {ptype['correct']}/{ptype['n']} | "
        f"threshold: baseline {bt['tp']}/{bt['fp']}/{bt['fn']}, poc {pt['tp']}/{pt['fp']}/{pt['fn']}"
    )


if __name__ == "__main__":
    main()
