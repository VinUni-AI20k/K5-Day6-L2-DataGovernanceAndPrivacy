"""Build the internal labelling sheet for a track (offline, no ground truth).

The student repo ships no `fixtures/*/gt/`, so the group has no labels to
validate against. This generates the material for labelling a split ourselves:

  * a CSV template, one row per image, with empty label columns;
  * a self-contained HTML sheet (thumbnails embedded as data URIs) with
    dropdowns and an Export CSV button, so a labeller never edits CSV by hand.

Default scope is the `dev` split only — tuning on `eval` is forbidden by the
lab rules, so eval must stay unlabelled until the protocol says otherwise.

Usage:
    python tools/make_label_sheet.py --track t02 --split dev --annotator A
"""
from __future__ import annotations

import argparse
import base64
import html
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFECT_TYPES = ["", "none", "blur", "glare", "dark", "compression"]
SEVERITIES = ["", "0", "1", "2"]
LABEL_COLS = ["defect_type", "severity", "is_defect", "note"]


def thumb_uri(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build_html(df: pd.DataFrame, track_dir: Path, out: Path, annotator: str, track: str) -> None:
    opt = lambda vals: "".join(f'<option value="{v}">{v or "—"}</option>' for v in vals)
    rows = []
    for r in df.itertuples():
        uri = thumb_uri(track_dir / r.path)
        rows.append(f"""
<div class="card" data-id="{html.escape(r.image_id)}">
  <img src="{uri}" alt="{html.escape(r.image_id)}">
  <div class="meta"><b>{html.escape(r.image_id)}</b><br>{r.camera_id} · {r.light} · {r.split}</div>
  <label>loại lỗi <select class="defect">{opt(DEFECT_TYPES)}</select></label>
  <label>mức độ <select class="sev">{opt(SEVERITIES)}</select></label>
  <input class="note" placeholder="ghi chú (tuỳ chọn)">
</div>""")
    out.write_text(f"""<!doctype html><meta charset="utf-8">
<title>Nhãn nội bộ {track} — {html.escape(annotator)}</title>
<style>
 body{{font:14px system-ui,sans-serif;margin:16px;background:#111;color:#eee}}
 h1{{font-size:18px}} .bar{{position:sticky;top:0;background:#111;padding:8px 0;border-bottom:1px solid #333;z-index:9}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin-top:12px}}
 .card{{background:#1c1c1c;border:1px solid #333;border-radius:8px;padding:8px}}
 .card img{{width:100%;border-radius:4px;display:block}}
 .meta{{margin:6px 0;color:#bbb;font-size:12px}}
 label{{display:block;margin:4px 0;font-size:12px}} select,input{{width:100%;padding:4px;background:#222;color:#eee;border:1px solid #444;border-radius:4px}}
 button{{padding:8px 14px;font-size:14px;cursor:pointer}} .done{{outline:2px solid #2d7}}
</style>
<div class="bar">
 <h1>Nhãn nội bộ · {track} · người gán: <b>{html.escape(annotator)}</b></h1>
 <span id="count"></span> &nbsp; <button onclick="exportCsv()">Export CSV</button>
 <p style="color:#999;margin:6px 0 0">Quy ước: <b>none</b> = ảnh dùng được · <b>blur/glare/dark/compression</b> = lỗi.
 Mức độ 0 nhẹ, 1 vừa, 2 nặng. Để trống = chưa gán.</p>
</div>
<div class="grid">{''.join(rows)}</div>
<script>
const cards=[...document.querySelectorAll('.card')];
function refresh(){{
  let n=0; cards.forEach(c=>{{const d=c.querySelector('.defect').value; if(d){{n++;c.classList.add('done')}}else c.classList.remove('done')}});
  document.getElementById('count').textContent=`đã gán ${{n}}/${{cards.length}}`;
}}
cards.forEach(c=>c.addEventListener('change',refresh)); refresh();
function exportCsv(){{
  const esc=v=>`"${{String(v).replace(/"/g,'""')}}"`;
  const head=['image_id','annotator','defect_type','severity','is_defect','note'];
  const lines=[head.join(',')];
  cards.forEach(c=>{{
    const d=c.querySelector('.defect').value, s=c.querySelector('.sev').value, n=c.querySelector('.note').value;
    const isd = d==='' ? '' : (d==='none'?'0':'1');
    lines.push([c.dataset.id,{annotator!r},d,s,isd,n].map(esc).join(','));
  }});
  const b=new Blob([lines.join('\\n')],{{type:'text/csv'}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(b);
  a.download='internal_labels_{annotator}.csv'; a.click();
}}
</script>
""", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", default="t02")
    ap.add_argument("--input", default=None)
    ap.add_argument("--split", default="dev", help="dev | eval | all")
    ap.add_argument("--annotator", default="A")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    track_dir = Path(a.input) if a.input else root / "fixtures" / "t02_raw_qc"

    df = pd.read_csv(track_dir / "images.csv")
    if a.split != "all":
        df = df[df.split == a.split]
    # stratified shuffle so a partially-finished sheet is still balanced
    df = (df.sample(frac=1.0, random_state=a.seed)
            .sort_values(["camera_id", "light"], kind="mergesort")
            .groupby(["camera_id", "light"], group_keys=False).head(len(df))
            .reset_index(drop=True))

    tmpl = df[["image_id", "camera_id", "light", "split"]].copy()
    tmpl["annotator"] = a.annotator
    for c in LABEL_COLS:
        tmpl[c] = ""
    csv_path = root / "reports" / f"internal_labels_{a.track}_{a.annotator}_template.csv"
    tmpl.to_csv(csv_path, index=False, lineterminator="\n")

    html_path = root / "reports" / f"internal_label_sheet_{a.track}_{a.annotator}.html"
    build_html(df, track_dir, html_path, a.annotator, a.track)
    print(f"{len(df)} ảnh (split={a.split})")
    print(f"  template : {csv_path.relative_to(root)}")
    print(f"  sheet    : {html_path.relative_to(root)}  ({html_path.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
