"""Build web/public/queue.json + web/public/img/ from a finished PoC run (queue to be reviewed online).

    python -m tools.t14_build_web [--run out/poc] [--input fixtures/t14_auto_annotation] [--web web/public]

Only images that appear in the review queue are copied. No ground truth is read.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd
import yaml


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="out/poc")
    ap.add_argument("--input", default="fixtures/t14_auto_annotation")
    ap.add_argument("--web", default="web/public")
    a = ap.parse_args()
    run, fx, web = Path(a.run), Path(a.input), Path(a.web)
    q = pd.read_csv(run / "review_queue.csv", dtype=str).fillna("")
    boxes = pd.read_csv(run / "boxes_all.csv").set_index("box_id", drop=False)
    classes = list(yaml.safe_load((fx / "taxonomy.yaml").read_text(encoding="utf-8"))["classes"].values())
    (web / "img").mkdir(parents=True, exist_ok=True)
    items = []
    for r in q.itertuples(index=False):
        me = boxes.loc[r.item_id]
        img = Path(me["path"]).name
        shutil.copyfile(fx / me["path"], web / "img" / img)
        others = boxes[(boxes.image_id == me["image_id"]) & (boxes.box_id != r.item_id)]
        items.append({
            "rank": int(r.rank), "item_id": r.item_id, "score": r.score, "reason": r.reason,
            "suggested_action": r.suggested_action, "slice": r.slice, "evidence_path": r.evidence_path,
            "image": f"img/{img}", "width": int(me["width"]), "height": int(me["height"]),
            "target": {k: (round(float(me[k]), 2) if k != "class" else me[k]) for k in ("x", "y", "w", "h", "class", "conf")},
            "others": [{"x": round(float(o.x), 2), "y": round(float(o.y), 2), "w": round(float(o.w), 2),
                        "h": round(float(o.h), 2), "class": o["class"]} for _, o in others.iterrows()],
        })
    (web / "queue.json").write_text(json.dumps({"classes": classes, "items": items}, ensure_ascii=False), encoding="utf-8")
    print(f"{len(items)} items, {len(set(i['image'] for i in items))} images -> {web}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
