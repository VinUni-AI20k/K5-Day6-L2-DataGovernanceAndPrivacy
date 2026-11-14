"""Người C · QA — slice theo artefact_type, Wilson CI, ablation, 2 failure case, latency (C7).

Chạy (sau khi đã có out/baseline, out/poc, tuỳ chọn out/ablation):
    .\\.venv\\Scripts\\python.exe -m tools.t08_slices
Ra:  reports/selfcheck/t08_slices.md (UTF-8)

Chấm trên bộ self-check reports/selfcheck/t08_expected.csv (C gán tay, KHÔNG phải GT giảng viên).
Không đọc fixtures/*/gt/.
"""
import json
from pathlib import Path

import pandas as pd

from src.metrics import wilson_ci

FIX = Path("fixtures/t08_deletion")
GT = Path("reports/selfcheck/t08_expected.csv")
OUT = Path("reports/selfcheck/t08_slices.md")
RUNS = ["baseline", "poc", "ablation"]
ACTIONS = ["delete", "retain_legal_hold", "escalate"]


def _merge(gt, run):
    pred = pd.read_csv(Path("out") / run / "actions.csv")[["request_id", "artefact_id", "action"]]
    m = gt.merge(pred, on=["request_id", "artefact_id"], how="left")
    m["action"] = m.action.fillna("(missing)")
    m["ok"] = m.action == m.expected_action
    return pred, m


def _ci(k, n):
    lo, hi = wilson_ci(int(k), int(n))
    return f"{k}/{n} = {k / n:.3f} [{lo:.3f}, {hi:.3f}]" if n else "n/a"


def main():
    gt = pd.read_csv(GT)
    arts = {a["artefact_id"]: a for a in json.loads((FIX / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]}
    runs = [r for r in RUNS if (Path("out") / r / "actions.csv").exists()]
    L = ["# T08 · Slices, CI, failure cases (tự sinh bằng tools/t08_slices.py)\n",
         f"Chấm trên **bộ self-check** `{GT.as_posix()}` (158 dòng, C gán tay theo chính sách đã chốt — "
         "không phải GT giảng viên). Cùng data, seed 42, `--offline`.\n"]
    merged = {r: _merge(gt, r) for r in runs}

    # 1. Phân bố action + Wilson CI
    L += ["## 1. Phân bố action & Wilson 95% CI\n",
          "| Run | delete | retain_legal_hold | escalate | Completeness (Wilson CI) | Exception acc (Wilson CI) | False-delete |",
          "|---|---|---|---|---|---|---|"]
    for r, (pred, m) in merged.items():
        vc = pred.action.value_counts()
        must, exc = m[m.expected_action == "delete"], m[m.expected_action != "delete"]
        keys = set(zip(gt.request_id, gt.artefact_id))
        stray = sum((a == "delete") and (k not in keys) for a, k in zip(pred.action, zip(pred.request_id, pred.artefact_id)))
        fd = int((exc.action == "delete").sum()) + stray
        L.append(f"| {r} | {vc.get('delete', 0)} | {vc.get('retain_legal_hold', 0)} | {vc.get('escalate', 0)} | "
                 f"{_ci(int((must.action == 'delete').sum()), len(must))} | {_ci(int(exc.ok.sum()), len(exc))} | {fd} |")

    # 2. Slice theo artefact_type
    L += ["\n## 2. Slice: accuracy theo `artefact_type` (đúng action / số dòng)\n",
          "| artefact_type | N | " + " | ".join(runs) + " |", "|---|---|" + "---|" * len(runs)]
    for t, g in gt.groupby("type"):
        cells = []
        for r in runs:
            mm = merged[r][1]
            sub = mm[mm.type == t]
            cells.append(f"{sub.ok.mean():.3f}")
        L.append(f"| {t} | {len(g)} | " + " | ".join(cells) + " |")

    # 3. Slice theo expected_action
    L += ["\n## 3. Slice: accuracy theo `expected_action`\n",
          "| expected_action | N | " + " | ".join(runs) + " |", "|---|---|" + "---|" * len(runs)]
    for e in ACTIONS:
        n = int((gt.expected_action == e).sum())
        L.append(f"| {e} | {n} | " + " | ".join(
            f"{merged[r][1][merged[r][1].expected_action == e].ok.mean():.3f}" for r in runs) + " |")

    # 4. Ablation: dòng bị xoá nhầm
    if "ablation" in merged:
        m = merged["ablation"][1]
        bad = m[(m.expected_action != "delete") & (m.action == "delete")]
        L += ["\n## 4. Ablation `configs/t08_policy_backup_only.yaml` (hold chỉ thừa kế cho backup)\n",
              f"- Xoá nhầm **{len(bad)}** dòng ngoại lệ; theo type: {bad.type.value_counts().to_dict()}; "
              f"theo request: {bad.request_id.value_counts().sort_index().to_dict()}.",
              "- Kết luận: thừa kế legal hold xuống **toàn bộ cây con** (R3) là cần thiết — chỉ giữ backup thì "
              "frame/crop/embedding/annotation sinh ra từ raw bị hold vẫn bị xoá."]

    # 5. Failure cases của baseline
    if "baseline" in merged:
        pred, m = merged["baseline"]
        L += ["\n## 5. Failure cases (baseline `src.t08.baseline`)\n"]
        fd = m[(m.expected_action != "delete") & (m.action == "delete")]
        L.append("**FC1 — xoá nhầm ngoại lệ legal hold.**")
        for x in fd.itertuples():
            a = arts[x.artefact_id]
            L.append(f"- `out/baseline/actions.csv`: `{x.request_id},{x.artefact_id},delete` · `data_graph.json`: "
                     f"type={a['type']}, subject_ids={a['subject_ids']}, legal_hold=`{a['legal_hold']}`, "
                     f"filename=`{a.get('filename')}` → kỳ vọng `{x.expected_action}`.")
        L.append("- Root cause: baseline chỉ khớp theo tên file raw, **không đọc `legal_hold`** → vi phạm hold, "
                 "không hoàn tác được.\n")
        d1 = m[m.request_id == "DR-001"]
        miss = d1[(d1.expected_action == "delete") & (d1.action != "delete")]
        L.append(f"**FC2 — chỉ xoá raw, bỏ sót lineage (DR-001).** Baseline xoá "
                 f"{int((d1.action == 'delete').sum())}/{len(d1)} artefact trong phạm vi; còn sót "
                 f"{len(miss)} artefact phải xoá: {miss.type.value_counts().to_dict()}.")
        bk = miss[miss.type == "backup"].artefact_id.tolist()
        L.append(f"- Ví dụ: backup {bk} vẫn nằm trong `{arts[bk[0]]['uri'] if bk else ''}`; "
                 f"embedding {miss[miss.type == 'embedding'].artefact_id.tolist()} còn trong vector-db.")
        L.append("- Root cause: baseline **không duyệt lineage** (cha → backup/frame → crop/embedding/annotation).")

    # 6. Latency
    L += ["\n## 6. Latency / compute\n", "| Run | runtime_seconds | N dòng | ms / dòng | máy |", "|---|---|---|---|---|"]
    for r in runs:
        info = json.loads((Path("out") / r / "run_info.json").read_text(encoding="utf-8"))
        n = info.get("stats", {}).get("n_items") or len(merged[r][0])
        mach = info.get("machine", {})
        L.append(f"| {r} | {info['runtime_seconds']} | {n} | {1000 * info['runtime_seconds'] / n:.2f} | "
                 f"Python {mach.get('python')}, {mach.get('platform')} |")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(L)} lines)")


if __name__ == "__main__":
    main()
