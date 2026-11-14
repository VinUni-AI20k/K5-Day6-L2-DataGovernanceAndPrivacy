"""Chạy thử thuật toán T02 trên ẢNH THẬT trong fixtures/t02_raw_qc. Không đọc gt/.

Cách chạy (từ thư mục gốc repo):
  .\\.venv\\Scripts\\python.exe tools\\t02_try.py               # PoC
  .\\.venv\\Scripts\\python.exe tools\\t02_try.py --baseline    # baseline
Kết quả:
  out/try_<poc|baseline>.csv          bảng điểm 96 ảnh
  out/try_<poc|baseline>_top20.html   mở bằng Chrome để NHÌN 20 ảnh bị lọc ra
Nếu có data/gold_dev.csv (nhóm tự gán nhãn ảnh dev) -> in thêm Recall/Precision trên dev.
"""
import argparse
import html
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import t02_qc as q  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--input", default="fixtures/t02_raw_qc")
ap.add_argument("--baseline", action="store_true")
ap.add_argument("--top", type=int, default=20)
ap.add_argument("--gold", default="data/gold_dev.csv")
a = ap.parse_args()

inp = Path(a.input)
df = q.load_inputs(inp)
ranked = q.run_baseline(df, inp) if a.baseline else q.run_poc(df, inp)
out = q.to_output(ranked)
name = "baseline" if a.baseline else "poc"

Path("out").mkdir(exist_ok=True)
out.to_csv(f"out/try_{name}.csv", index=False)

# ---------------------------------------------------------------- in ra màn hình
cols = ["image_id", "score", "pred_defect_type", "pred_action", "camera_id", "light", "split"]
print(f"== {name.upper()}: {len(out)} ảnh, top {a.top} nghi lỗi nhất ==")
print(out.head(a.top)[cols].round(2).to_string(index=False))

print("\n== Tỉ lệ bị báo RECAPTURE theo nhóm (soi failure mode: night, cam_B) ==")
rate = (out.assign(flag=out.pred_action == "RECAPTURE")
           .groupby(["camera_id", "light"])["flag"].agg(["sum", "count", "mean"]))
rate.columns = ["bi_bao", "tong", "ti_le"]
print(rate.round(2).to_string())

# ---------------------------------------------------------------- tự chấm trên gold dev
gold_path = Path(a.gold)
if gold_path.exists():
    gold = pd.read_csv(gold_path)
    gold["is_defect"] = gold["defect_type"].astype(str).str.lower() != "none"
    dev = out[out["image_id"].isin(gold["image_id"])].reset_index(drop=True)
    dev = dev.merge(gold[["image_id", "defect_type", "is_defect"]], on="image_id")
    n_def = int(dev["is_defect"].sum())
    k = min(a.top, len(dev))
    hit = int(dev.head(k)["is_defect"].sum())
    print(f"\n== Tự chấm trên gold dev ({len(dev)} ảnh đã gán nhãn, {n_def} ảnh lỗi) ==")
    print(f"Recall@{k}    = {hit}/{n_def} = {hit / n_def:.2f}" if n_def else "Gold không có ảnh lỗi nào")
    print(f"Precision@{k} = {hit}/{k} = {hit / k:.2f}")
    flagged = dev[dev.pred_action == "RECAPTURE"]
    if len(flagged):
        acc = (flagged["pred_defect_type"] == flagged["defect_type"]).mean()
        print(f"Đoán đúng loại lỗi (trên ảnh bị báo) = {acc:.2f}")
else:
    print(f"\n(Chưa có {gold_path} -> bỏ qua phần tự chấm. Gán nhãn vài ảnh dev để có số.)")

# ---------------------------------------------------------------- HTML xem bằng mắt
html_path = Path(f"out/try_{name}_top{a.top}.html")
cards = []
for i, r in enumerate(out.head(a.top).itertuples(index=False), 1):
    src = os.path.relpath(inp / r.path, html_path.parent).replace("\\", "/")
    color = "#c0392b" if r.pred_action == "RECAPTURE" else "#27ae60"
    cards.append(
        f'<div class="c"><img src="{html.escape(src)}" loading="lazy">'
        f'<div><b>#{i} {html.escape(str(r.image_id))}</b> · score {r.score:.2f}</div>'
        f'<div style="color:{color}"><b>{r.pred_action}</b> · {r.pred_defect_type}</div>'
        f'<div class="m">{r.camera_id} · {r.light} · {r.split}</div></div>')
html_path.write_text(
    "<!doctype html><meta charset='utf-8'><title>T02 " + name + "</title>"
    "<style>body{font-family:sans-serif;margin:16px}"
    ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}"
    ".c{border:1px solid #ccc;border-radius:8px;padding:8px;font-size:14px}"
    ".c img{width:100%;display:block;border-radius:4px;margin-bottom:6px}.m{color:#777}</style>"
    f"<h2>T02 {name.upper()} · top {a.top} ảnh nghi lỗi nhất / {len(out)}</h2>"
    "<p>Nhìn từng ảnh: máy nói đúng hay sai? Ghi lại ảnh máy sai để làm failure case.</p>"
    f"<div class='g'>{''.join(cards)}</div>", encoding="utf-8")

print(f"\nĐã lưu: out/try_{name}.csv")
print(f"Mở bằng Chrome để xem ảnh: {html_path}")
