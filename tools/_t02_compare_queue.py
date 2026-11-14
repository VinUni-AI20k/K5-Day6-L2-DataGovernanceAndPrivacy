"""Compare baseline vs PoC v0 review queues on the eval split (no GT).

There is no fixtures/t02_raw_qc/gt/ locally, so this is NOT Recall/Precision.
It only answers: how much does the PoC change the top-B review queue?

Run: python tools/_t02_compare_queue.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.poc.t02_v0 import (  # noqa: E402
    BLUR_HI,
    BLUR_LO,
    COMP_HI,
    COMP_LO,
    DARK_HI,
    DARK_LO,
    GLARE_HI,
    GLARE_LO,
    extract,
    score_frame,
)
BASE = ROOT / "out" / "baseline" / "ranked_review.csv"
POC = ROOT / "out" / "poc_v0" / "ranked_review.csv"
IMAGES = ROOT / "fixtures" / "t02_raw_qc" / "images.csv"
OUT_MD = ROOT / "reports" / "queue_compare_eval.md"
OUT_JSON = ROOT / "reports" / "queue_compare_eval.json"
B = 20


def ranked(df: pd.DataFrame, score_col: str = "score") -> pd.DataFrame:
    """One canonical order: score desc, image_id asc (deterministic tie-break)."""
    out = df.sort_values([score_col, "image_id"], ascending=[False, True], kind="mergesort")
    return out.reset_index(drop=True)


def top_set(df: pd.DataFrame, k: int, score_col: str = "score") -> set[str]:
    return set(ranked(df, score_col).head(k)["image_id"])


def boundary_tie(df: pd.DataFrame, k: int, score_col: str = "score") -> tuple[float, int]:
    """Score at rank k and how many images share it (1 = no tie)."""
    r = ranked(df, score_col)
    cut = float(r.loc[k - 1, score_col])
    return cut, int((r[score_col] == cut).sum())


def main() -> None:
    images = pd.read_csv(IMAGES)
    eval_ids = set(images.loc[images["split"] == "eval", "image_id"])
    base = pd.read_csv(BASE)
    poc = pd.read_csv(POC)
    base = base[base["image_id"].isin(eval_ids)].copy()
    poc = poc[poc["image_id"].isin(eval_ids)].copy()

    m = base[["image_id", "score", "pred_defect_type"]].merge(
        poc[["image_id", "score", "pred_defect_type", "pred_severity"]],
        on="image_id", suffixes=("_base", "_poc"),
    )
    if len(m) != len(eval_ids):
        raise SystemExit(f"expected {len(eval_ids)} eval images, got {len(m)}")

    rho = spearmanr(m["score_base"], m["score_poc"]).statistic

    bt20, pt20 = top_set(base, B), top_set(poc, B)
    inter20 = bt20 & pt20
    bt10, pt10 = top_set(base, 10), top_set(poc, 10)
    inter10 = bt10 & pt10

    base_flag = set(base.loc[base["pred_defect_type"] != "none", "image_id"])
    poc_flag = set(poc.loc[poc["pred_defect_type"] != "none", "image_id"])

    m = ranked(m, "score_poc")
    m["rank_poc"] = range(1, len(m) + 1)
    m["in_base20"] = m["image_id"].isin(bt20)

    # the same order must produce the table rows and the set used for overlap
    assert set(m.head(B)["image_id"]) == pt20, "PoC queue table and overlap set disagree"
    base_ranked = ranked(base)
    base_ranked["rank_base"] = range(1, len(base_ranked) + 1)
    assert set(base_ranked.head(B)["image_id"]) == bt20, "baseline queue table and overlap set disagree"

    poc_cut, poc_tie_n = boundary_tie(poc, B)
    base_cut, base_tie_n = boundary_tie(base, B)

    # PoC queue
    lines = [
        "# T02 — So sánh queue baseline vs PoC v0 (40 ảnh eval)",
        "",
        "**Không có GT**: đây là so sánh queue, không phải Recall/Precision. "
        "Không dùng kết quả này để chỉnh threshold.",
        "",
        f"Baseline: `lap < 800` (score = 1000/(lap+1e-5)). "
        f"PoC v0: 4 feature group-relative, ngưỡng sơ bộ từ 14 nhãn dev.",
        "",
        "Thứ tự xếp hạng dùng chung cho mọi bảng và mọi tập top-B: "
        "`score` giảm dần, hoà thì `image_id` tăng dần. Tie-break chỉ để kết quả "
        "tái lập được, không mang ý nghĩa chất lượng.",
        "",
        "## Tóm tắt",
        "",
        "| Chỉ số | Baseline | PoC v0 |",
        "|---|---:|---:|",
        f"| Số ảnh bị flag | {len(base_flag)}/{len(eval_ids)} | {len(poc_flag)}/{len(eval_ids)} |",
        f"| Overlap@10 | — | {len(inter10)}/10 |",
        f"| Overlap@{B} | — | {len(inter20)}/{B} |",
        f"| Overlap tập bị flag (score > 0) | — | {len(base_flag & poc_flag)}/"
        f"{len(base_flag | poc_flag)} (Jaccard {len(base_flag & poc_flag) / len(base_flag | poc_flag):.3f}) |",
        f"| Jaccard@{B} | — | {len(inter20) / len(bt20 | pt20):.3f} |",
        f"| Spearman ρ (40 ảnh) | — | {rho:.3f} |",
        "",
        f"**{B - len(inter20)} ảnh vào top-{B} của PoC** (baseline không có): "
        + ", ".join(sorted(pt20 - bt20)),
        "",
        f"**{B - len(inter20)} ảnh rời top-{B}** (baseline có, PoC không): "
        + ", ".join(sorted(bt20 - pt20)),
        "",
        f"**Tie ở biên top-{B}:** baseline score rank {B} = {base_cut:.4f} "
        f"({base_tie_n} ảnh cùng score); PoC score rank {B} = {poc_cut:.4f} "
        f"({poc_tie_n} ảnh cùng score). "
        + (
            f"PoC có {poc_tie_n} ảnh score {poc_cut:.3f} tranh 1 slot cuối → "
            "slot 20 chỉ là ảnh thắng tie-break theo `image_id`, không phải ảnh "
            "suspicious hơn. Mọi so sánh nên đọc top-19 (các ảnh score > 0) "
            "hoặc dùng overlap không phụ thuộc tie."
            if poc_tie_n > 1
            else "Không có tie ở biên."
        ),
        "",
        "## PoC v0 — top 20",
        "",
        "| rank | image_id | score | type | sev | baseline score | baseline top-20 |",
        "|---:|---|---:|---|---:|---:|:---:|",
    ]
    for r in m.head(B).itertuples():
        lines.append(
            f"| {r.rank_poc} | {r.image_id} | {r.score_poc:.3f} | {r.pred_defect_type_poc} | "
            f"{r.pred_severity} | {r.score_base:.2f} | {'✓' if r.in_base20 else ''} |"
        )

    lines += [
        "",
        f"## Baseline — top {B} nhưng không nằm trong PoC top-{B}",
        "",
        "| base rank | image_id | baseline score | PoC score | PoC type |",
        "|---:|---|---:|---:|---|",
    ]
    left = base_ranked[base_ranked["image_id"].isin(bt20 - pt20)]
    poc_map = poc.set_index("image_id")
    for r in left.itertuples():
        p = poc_map.loc[r.image_id]
        lines.append(
            f"| {r.rank_base} | {r.image_id} | {r.score:.2f} | {p['score']:.3f} | {p['pred_defect_type']} |"
        )

    # ----- why the queue moved ---------------------------------------------
    moved_in, moved_out = sorted(pt20 - bt20), sorted(bt20 - pt20)
    all_imgs = pd.read_csv(IMAGES)
    sc = score_frame(extract(all_imgs, ROOT / "fixtures" / "t02_raw_qc")).set_index("image_id")
    light = all_imgs.set_index("image_id")["light"]
    margins = pd.DataFrame(
        {
            "dark": (DARK_LO - sc["bright_ratio"]) / (DARK_LO - DARK_HI),
            "blur": (BLUR_LO - sc["lap_ratio"]) / (BLUR_LO - BLUR_HI),
            "compression": (sc["block_ratio"] - COMP_LO) / (COMP_HI - COMP_LO),
            "glare": np.log10(sc["blob"].clip(lower=1e-9) / GLARE_LO)
            / np.log10(GLARE_HI / GLARE_LO),
        }
    ).clip(lower=0)

    lines += [
        "",
        f"## Vì sao {len(moved_in) + len(moved_out)} ảnh đổi chỗ",
        "",
        "| image_id | light | hướng | PoC score | type | lap_ratio | bright_ratio "
        "| block_ratio | blob % | feature áp đảo |",
        "|---|---|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for direction, ids in (("vào", moved_in), ("rời", moved_out)):
        for iid in ids:
            r, mg = sc.loc[iid], margins.loc[iid]
            top = mg.idxmax()
            top_txt = f"{top} ({mg[top]:.2f})" if mg.max() > 0 else "— (score 0)"
            lines.append(
                f"| {iid} | {light.loc[iid]} | {direction} | {r['score']:.3f} | "
                f"{r['pred_defect_type']} | {r['lap_ratio']:.3f} | {r['bright_ratio']:.3f} | "
                f"{r['block_ratio']:.2f} | {100 * r['blob']:.3f} | {top_txt} |"
            )

    g53 = sc.loc["img_05_3"]
    c132, c013 = sc.loc["img_13_2"], sc.loc["img_01_3"]
    n192 = sc.loc["img_19_2"]
    lines += [
        "",
        "- `img_05_3` (day): glare, blob chiếm "
        f"{100 * g53['blob']:.2f}% diện tích — "
        f"{g53['blob'] / GLARE_LO:.0f}× ngưỡng `lo` = {GLARE_LO}. `lap` = {g53['lap']:.0f} "
        "vẫn cao nên baseline coi là ảnh nét; đây là loại lỗi baseline không có feature.",
        f"- `img_13_2` và `img_01_3` (night): compression, `block_ratio` = "
        f"{c132['block_ratio']:.2f} / {c013['block_ratio']:.2f}, vượt `hi` = {COMP_HI} "
        "→ severity 2. Baseline xếp hai ảnh này ở nửa dưới vì `lap` cao.",
        "- Ba ảnh rời queue (`img_03_0`, `img_06_0` night; `img_15_0` dusk) "
        "đều có PoC score = 0: `lap` thấp do cảnh thiếu tương phản chứ không phải blur, "
        "và không feature nào vượt ngưỡng. Đây đúng là kiểu false alarm của baseline.",
        f"- `img_19_2` (day) là ca sát ngưỡng: `block_ratio` = {n192['block_ratio']:.2f} "
        f"(lo = {COMP_LO}), blob = {100 * n192['blob']:.3f}% (lo = {100 * GLARE_LO:.2f}%) "
        "→ lọt qua mọi ngưỡng. Cần nhãn eval mới biết đây là miss hay đúng là clean.",
        "- `img_01_0` không thực sự \"được thăng hạng\": score = 0, chỉ lấp slot 20 "
        "sau khi hết ảnh suspicious (xem tie ở trên).",
        "",
        "**Chưa có nhãn eval**, nên các nhận xét trên chỉ giải thích *vì sao queue đổi*, "
        "không khẳng định ảnh nào bị bỏ sót hay báo nhầm.",
        "",
    ]

    types = ["blur", "dark", "glare", "compression", "none"]
    base_top = base[base["image_id"].isin(bt20)]
    poc_top = poc[poc["image_id"].isin(pt20)]

    def dist(df: pd.DataFrame) -> dict[str, int]:
        vc = df["pred_defect_type"].value_counts()
        return {t: int(vc.get(t, 0)) for t in types}

    bd, pd_ = dist(base_top), dist(poc_top)
    lines += [
        "## Phân bố type trong top-20",
        "",
        "| type | baseline | PoC v0 |",
        "|---|---:|---:|",
        *[f"| {t} | {bd[t]} | {pd_[t]} |" for t in types],
        "",
        "Baseline chỉ có một score Laplacian nên type dự đoán chỉ là `blur`/`none`; "
        "PoC phân bổ queue sang nhiều loại lỗi hơn. Không có GT nên chưa biết phân bổ nào đúng hơn.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    payload = {
        "n_eval": len(eval_ids),
        "baseline_flagged": len(base_flag),
        "poc_flagged": len(poc_flag),
        "overlap_at_10": len(inter10),
        "overlap_at_20": len(inter20),
        "jaccard_at_20": len(inter20) / len(bt20 | pt20),
        "overlap_flagged": len(base_flag & poc_flag),
        "jaccard_flagged": len(base_flag & poc_flag) / len(base_flag | poc_flag),
        "spearman_rho": float(rho),
        "poc_top20_added": sorted(pt20 - bt20),
        "baseline_top20_dropped": sorted(bt20 - pt20),
        "tie_at_20": {
            "baseline_score": base_cut,
            "baseline_n_at_cut": base_tie_n,
            "poc_score": poc_cut,
            "poc_n_at_cut": poc_tie_n,
        },
        "type_distribution_top20": {"baseline": bd, "poc": pd_},
        "ranking_order": "score desc, image_id asc",
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_JSON}")
    print(f"overlap@10={len(inter10)}/10  overlap@20={len(inter20)}/20  rho={rho:.3f}")


if __name__ == "__main__":
    main()
