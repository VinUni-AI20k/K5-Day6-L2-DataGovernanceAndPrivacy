"""Offline HTML contact sheet for human review (no server, no CDN).

Each card shows image(s) + fields + a decision dropdown + note box.
The "Export decisions CSV" button downloads a file with the REVIEW_COLUMNS
schema, which `review.load_review_decisions` can read back.
"""
from __future__ import annotations

import base64
import html
import io
import json
import os
from pathlib import Path
from typing import Iterable

import pandas as pd
from PIL import Image, ImageDraw

DECISIONS = ["", "approve", "reject", "edit", "escalate", "skip"]


def _thumb_data_uri(path: str | Path, width: int, boxes: list[dict] | None = None) -> str:
    """Return base64 JPEG thumbnail (optionally with boxes drawn: dicts x,y,w,h,label,color in source px)."""
    img = Image.open(path).convert("RGB")
    if boxes:
        d = ImageDraw.Draw(img)
        for b in boxes:
            x, y, w, h = float(b["x"]), float(b["y"]), float(b["w"]), float(b["h"])
            color = b.get("color", "red")
            d.rectangle([x, y, x + w, y + h], outline=color, width=max(2, img.width // 300))
            if b.get("label"):
                d.text((x + 2, max(0, y - 12)), str(b["label"]), fill=color)
    scale = width / img.width
    img = img.resize((width, max(1, int(img.height * scale))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def render_contact_sheet(
    queue: pd.DataFrame,
    out_html: str | Path,
    image_col: str | None = "evidence_path",
    before_image_col: str | None = None,
    fields: Iterable[str] = ("rank", "item_id", "score", "reason", "suggested_action", "slice"),
    title: str = "Review queue",
    image_root: str | Path | None = None,
    thumb_width: int = 280,
    boxes_by_item: dict[str, list[dict]] | None = None,
    embed: bool = True,
) -> Path:
    """Write a self-contained review page.

    queue          : DataFrame (usually the review_queue.csv rows)
    image_col      : column with image path (after / current)
    before_image_col: optional column with original image path (before/after grid)
    image_root     : base folder for relative image paths
    boxes_by_item  : optional {item_id: [box dicts]} drawn on the 'after' image
    embed          : True = base64 thumbnails (portable single file)
    """
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    root = Path(image_root) if image_root else Path(".")
    fields = list(fields)
    cards = []
    for _, row in queue.iterrows():
        imgs = []
        for col, label in ((before_image_col, "before"), (image_col, "after" if before_image_col else "")):
            if not col or col not in row or pd.isna(row[col]) or str(row[col]) == "":
                continue
            p = Path(str(row[col]))
            p = p if p.is_absolute() else root / p
            if not p.exists():
                imgs.append(f'<div class="missing">missing: {html.escape(str(p))}</div>')
                continue
            boxes = (boxes_by_item or {}).get(str(row.get("item_id", ""))) if label != "before" else None
            src = _thumb_data_uri(p, thumb_width, boxes) if embed else os.path.relpath(p, out_html.parent)
            cap = f"<figcaption>{label}</figcaption>" if label else ""
            imgs.append(f'<figure><img src="{src}" width="{thumb_width}">{cap}</figure>')
        meta = "".join(
            f"<div><b>{html.escape(f)}</b>: {html.escape(str(row[f]))}</div>" for f in fields if f in row
        )
        opts = "".join(f'<option value="{d}">{d or "— decision —"}</option>' for d in DECISIONS)
        item_id = html.escape(str(row.get("item_id", "")))
        cards.append(
            f'<div class="card" data-item="{item_id}" data-rank="{html.escape(str(row.get("rank", "")))}" '
            f'data-score="{html.escape(str(row.get("score", "")))}">'
            f'<div class="imgs">{"".join(imgs)}</div><div class="meta">{meta}</div>'
            f'<select class="dec">{opts}</select>'
            f'<input class="ov" placeholder="override value (optional)">'
            f'<input class="note" placeholder="reason / note"></div>'
        )
    rows_json = json.dumps(queue.astype(str).to_dict(orient="records"))
    page = _TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__CARDS__", "\n".join(cards))
    page = page.replace("__ROWS__", rows_json).replace("__N__", str(len(queue)))
    out_html.write_text(page, encoding="utf-8")
    return out_html


_TEMPLATE = """<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
body{font-family:system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}
header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.grid{display:flex;flex-wrap:wrap;gap:12px}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:8px;width:min(100%,620px)}
.imgs{display:flex;gap:6px;flex-wrap:wrap} figure{margin:0} figcaption{font-size:11px;color:#666}
.meta{font-size:12px;margin:6px 0;word-break:break-all}
select,input{font-size:12px;margin:2px 0;width:100%;box-sizing:border-box}
.missing{color:#b00;font-size:12px}
button{padding:6px 12px}
</style></head><body>
<header><h2 style="margin:0">__TITLE__</h2><span>N = __N__</span>
<label>Reviewer (bắt buộc): <input id="reviewer" style="width:180px"></label>
<button onclick="exportCsv()">Export decisions CSV</button></header>
<div class="grid">__CARDS__</div>
<script>
const ROWS = __ROWS__;
const COLS = ["rank","item_id","score","reason","suggested_action","slice","evidence_path",
              "reviewer","reviewer_decision","override_value","review_note","reviewed_at"];
function esc(v){v = (v===undefined||v===null)?"":String(v); return /[",\\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;}
function exportCsv(){
  const reviewer = document.getElementById('reviewer').value.trim();
  if(!reviewer){alert('Nhập tên reviewer trước khi export'); return;}
  const now = new Date().toISOString();
  const cards = document.querySelectorAll('.card');
  const lines = [COLS.join(',')];
  cards.forEach((c,i)=>{
    const r = Object.assign({}, ROWS[i]);
    const dec = c.querySelector('.dec').value;
    r.reviewer = dec ? reviewer : ''; r.reviewer_decision = dec;
    r.override_value = c.querySelector('.ov').value; r.review_note = c.querySelector('.note').value;
    r.reviewed_at = dec ? now : '';
    lines.push(COLS.map(k=>esc(r[k])).join(','));
  });
  const blob = new Blob([lines.join('\\n')+'\\n'], {type:'text/csv'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'review_queue_reviewed.csv'; a.click();
}
</script></body></html>
"""
