"""Dev-proxy metrics for the T02 Laplacian baseline.

No official gt/ exists in this repo, so this builds a proxy GT from the manual
labels in reports/dev_labels.csv and calls the official eval_t02() with B=7
(50% of the 14 labeled images, matching the eval budget B=20/40).

Reads:  out/baseline/ranked_review.csv, reports/dev_labels.csv
Writes: reports/_dev_gt_proxy.csv, reports/metrics_baseline_dev.json,
        reports/baseline_dev.md

Run: python tools/_t02_baseline_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.report import MetricResult, write_metrics  # noqa: E402
from src.metrics.tracks import eval_t02  # noqa: E402

PRED = ROOT / "out" / "baseline" / "ranked_review.csv"
LABELS = ROOT / "reports" / "dev_labels.csv"
PROXY_GT = ROOT / "reports" / "_dev_gt_proxy.csv"
OUT_MD = ROOT / "reports" / "baseline_dev.md"
OUT_JSON = ROOT / "reports" / "metrics_baseline_dev.json"
B = 7  # 50% of 14 labeled images (eval uses 20/40)
THRESHOLD = 800.0


def fmt(v) -> str:
    if v is None or pd.isna(v):
        return "n/a"
    return f"{float(v):.4f}"


def main() -> None:
    pred = pd.read_csv(PRED)
    lab = pd.read_csv(LABELS, dtype=str, keep_default_na=False)
    lab = lab[lab["defect_type"] != ""].copy()
    if lab.empty:
        raise SystemExit("no labels in reports/dev_labels.csv")

    lab["is_defect"] = lab["is_defect"].astype(int)
    lab["severity"] = lab["severity"].astype(int)
    gt = lab[["image_id", "split", "light", "defect_type", "severity", "is_defect"]]
    gt.to_csv(PROXY_GT, index=False)

    ev = eval_t02(PROXY_GT, PRED, {"budget": B, "split": "dev"})

    # ----- ranking table ----------------------------------------------------
    m = lab.merge(pred[["image_id", "lap", "score", "pred_defect_type"]], on="image_id")
    m = m.sort_values("score", ascending=False, kind="mergesort").reset_index(drop=True)
    m["rank"] = range(1, len(m) + 1)
    m["top"] = m["rank"] <= B
    m["gt"] = m["defect_type"] + "/" + m["severity"].astype(str)

    # ----- threshold-free average precision --------------------------------
    y = m["is_defect"].astype(int).to_numpy()
    n_pos = int(y.sum())
    ap = 0.0
    hit = 0
    prev_recall = 0.0
    for k in range(1, len(y) + 1):
        hit += int(y[k - 1])
        precision_k = hit / k
        recall_k = hit / n_pos if n_pos else 0.0
        ap += precision_k * (recall_k - prev_recall)
        prev_recall = recall_k
    ap_metric = MetricResult(
        name="Average Precision", value=ap, direction="higher", unit="fraction", n=len(y)
    )

    # ----- binary confusion at the frozen threshold -------------------------
    flagged = m["pred_defect_type"] != "none"
    tp = int((flagged & (m["is_defect"] == 1)).sum())
    fp = int((flagged & (m["is_defect"] == 0)).sum())
    fn = int((~flagged & (m["is_defect"] == 1)).sum())
    tn = int((~flagged & (m["is_defect"] == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec and (prec + rec) else None

    # ----- markdown ---------------------------------------------------------
    lines = [
        "# T02 baseline — dev proxy",
        "",
        "**Baseline:** một ngưỡng Laplacian toàn ảnh duy nhất.",
        "`score = 1000 / (lap + 1e-5)`, `pred_defect_type = blur` nếu `lap < 800`.",
        "",
        "**Phạm vi:** 14 ảnh dev đã label (folder 2, 4 nhóm), 8 defect / 6 clean. "
        f"B = {B} = 50% của 14, tương ứng B = 20/40 của eval. "
        "Đây là proxy, **không phải** metric chính thức: repo không có `fixtures/t02_raw_qc/gt/`.",
        "",
        f"Ngưỡng `T = {THRESHOLD:.0f}` chốt trên chính 14 nhãn này; mọi T trong (745, 876] "
        "cho cùng quyết định. Chưa có nhóm đêm và chưa có nhãn glare → kết quả lạc quan.",
        "",
        "## Ranking",
        "",
        "| rank | image_id | light | GT | lap | score | top-B | pred |",
        "|---:|---|---|---|---:|---:|:---:|---|",
    ]
    for r in m.itertuples():
        lines.append(
            f"| {r.rank} | {r.image_id} | {r.light} | {r.gt} | {r.lap:.1f} | "
            f"{r.score:.2f} | {'✓' if r.top else ''} | {r.pred_defect_type} |"
        )

    lines += [
        "",
        "## Metrics (official `eval_t02`, proxy GT)",
        "",
        "| Metric | Value | num/den | N |",
        "|---|---:|---:|---:|",
    ]
    for x in ev.metrics + [ap_metric]:
        frac = (
            f"{x.numerator:g}/{x.denominator:g}"
            if x.numerator is not None and x.denominator is not None
            else ""
        )
        name = x.name + (f" [{x.slice}]" if x.slice not in ("", "all") else "")
        lines.append(f"| {name} | {fmt(x.value)} | {frac} | {x.n or ''} |")

    lines += [
        "",
        f"## Binary confusion at `lap < {THRESHOLD:.0f}`",
        "",
        "| TP | FP | FN | TN | Precision | Recall | F1 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {tp} | {fp} | {fn} | {tn} | {fmt(prec)} | {fmt(rec)} | {fmt(f1)} |",
        "",
        "**Đọc kết quả:** baseline bắt 3 ảnh dark vì `lap` thấp (do thiếu tương phản), "
        "không phải vì nhận ra dark. False alarm duy nhất là `img_09_0` (clean nhưng mềm). "
        "Top-7 bỏ sót `img_08_2` (blur/1) và `img_10_2` (compression/2). "
        "Vì vậy con số này không chứng minh baseline tốt — nó chỉ cho thấy tập 14 ảnh "
        "chưa có nhóm đêm/glare, nơi baseline được dự đoán sẽ sụp.",
        "",
        f"Files: `{PRED.relative_to(ROOT)}`, `{OUT_JSON.relative_to(ROOT)}`.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    write_metrics(
        OUT_JSON,
        run_name="baseline_dev_proxy",
        track="t02",
        metrics=ev.metrics + [ap_metric],
        seed=42,
        config={"budget": B, "split": "dev", "threshold_lap": THRESHOLD,
                "note": "proxy GT from reports/dev_labels.csv; not official eval"},
        n_items=len(m),
    )
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_JSON}")
    print(f"  Average Precision: {fmt(ap)}")
    for x in ev.metrics:
        if x.primary or x.name.startswith("Defect Recall") or x.name.startswith("Precision"):
            print(f"  {x.name}: {fmt(x.value)} ({x.numerator}/{x.denominator})")


if __name__ == "__main__":
    main()
