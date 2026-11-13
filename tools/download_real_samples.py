"""Instructor/TA prep: download SMALL real samples from Hugging Face into data/real/ (gitignored).

    cp .env.example .env            # put HF_TOKEN=... (read token) — never commit it
    python -m tools.download_real_samples                       # all packs, default sizes
    python -m tools.download_real_samples --packs bdd --bdd-n 240 --max-side 640

Packs (each gets images/, CSV metadata, manifest.csv with source + license + sha256):
  bdd     dgural/bdd100k (BDD100K val, FiftyOne export): weather / timeofday / scene + boxes
          -> P1 driving_small (T01 T02 T03 T05 T10 T13) and P3 boxes (T11 T14)
  coco    LibreYOLO/coco-val2017-mini500 (COCO val2017 subset, annotations CC BY 4.0)
          -> P3 labels_small (T06 T11 T14)
  plates  keremberke/license-plate-object-detection (Roboflow, CC BY 4.0) test split
          -> P4 privacy (T07 plate slice)

WARNING: these are REAL images (real people, real plates). Keep them local; never push
data/real/ to a public repo or cloud. Check each dataset's license before any reuse.
Run this BEFORE class; the lab itself must run offline.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402

from src.common.manifest import build_manifest, write_manifest  # noqa: E402

BDD_REPO = "dgural/bdd100k"
COCO_REPO = "LibreYOLO/coco-val2017-mini500"
PLATES_REPO = "keremberke/license-plate-object-detection"
BDD_LICENSE = "BDD100K License — non-commercial research/education only (https://doc.bdd100k.com/license.html)"
COCO_ANN_LICENSE = "COCO annotations CC BY 4.0; image license per Flickr id (see license_id column)"
PLATES_LICENSE = "CC BY 4.0 (Roboflow Universe: augmented-startups/vehicle-registration-plates-trudk)"


def load_token() -> str | None:
    tok = os.environ.get("HF_TOKEN")
    env = ROOT / ".env"
    if not tok and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("HF_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return tok


def _hf():
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        sys.exit("pip install huggingface_hub  (only needed for this prep script)")
    return hf_hub_download


def resize_save(src_bytes_or_path, dst: Path, max_side: int) -> tuple[int, int, float]:
    img = Image.open(io.BytesIO(src_bytes_or_path) if isinstance(src_bytes_or_path, bytes) else src_bytes_or_path).convert("RGB")
    scale = min(1.0, max_side / max(img.size))
    if scale < 1.0:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, format="JPEG", quality=90)
    return img.width, img.height, scale


# ----------------------------------------------------------------------------- BDD
def pick_bdd(samples: list[dict], n: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    lab = lambda s, k: (s.get(k) or {}).get("label", "undefined")  # noqa: E731
    order = rng.permutation(len(samples))
    chosen, seen = [], set()

    def take(s):
        if s["filepath"] not in seen and len(chosen) < n:
            seen.add(s["filepath"])
            chosen.append(s)

    # 1) rare scenarios first (real long-tail): fog, tunnel, gas station, parking lot, snowy night
    caps = {("weather", "foggy"): 13, ("scene", "tunnel"): 10, ("scene", "gas stations"): 7, ("scene", "parking lot"): 10}
    for (k, v), cap in caps.items():
        for i in order:
            if sum(1 for c in chosen if lab(c, k) == v) >= cap:
                break
            if lab(samples[i], k) == v:
                take(samples[i])
    # 2) round-robin over weather x timeofday cells for balance
    cells = defaultdict(list)
    for i in order:
        s = samples[i]
        cells[(lab(s, "weather"), lab(s, "timeofday"))].append(s)
    for keys in ([k for k in sorted(cells) if "undefined" not in k], sorted(cells)):  # 'undefined' only as fallback
        while len(chosen) < n and any(cells[k] for k in keys):
            for k in keys:
                if cells[k]:
                    take(cells[k].pop())
    return chosen


def download_bdd(out: Path, n: int, max_side: int, seed: int, token: str | None, workers: int) -> None:
    hf = _hf()
    print(f"[bdd] fetching index samples.json from {BDD_REPO} (~71 MB, cached after first time)")
    samples = json.load(open(hf(BDD_REPO, "samples.json", repo_type="dataset", token=token)))["samples"]
    chosen = pick_bdd(samples, n, seed)
    d = out / "bdd"
    (d / "images").mkdir(parents=True, exist_ok=True)

    def one(s):
        fid = Path(s["filepath"]).stem
        p = hf(BDD_REPO, s["filepath"], repo_type="dataset", token=token)
        W0, H0 = s["metadata"]["width"], s["metadata"]["height"]
        w, h, _ = resize_save(p, d / "images" / f"{fid}.jpg", max_side)
        dets = []
        for det in (s.get("detections") or {}).get("detections", []):
            bx, by, bw, bh = det["bounding_box"]  # FiftyOne relative [x, y, w, h]
            dets.append({"file_id": fid, "class": det["label"], "x": round(bx * w, 2), "y": round(by * h, 2), "w": round(bw * w, 2),
                         "h": round(bh * h, 2), "occluded": int(bool(det.get("occluded"))), "truncated": int(bool(det.get("truncated")))})
        cnt = Counter(x["class"] for x in dets)
        meta = {"file_id": fid, "path": f"images/{fid}.jpg", "width": w, "height": h, "orig_width": W0, "orig_height": H0,
                "weather": (s.get("weather") or {}).get("label", "undefined"), "timeofday": (s.get("timeofday") or {}).get("label", "undefined"),
                "scene": (s.get("scene") or {}).get("label", "undefined"),
                **{f"n_{c.replace(' ', '_')}": cnt.get(c, 0) for c in ["car", "pedestrian", "rider", "bicycle", "motorcycle", "truck", "bus", "traffic light", "traffic sign"]}}
        return meta, dets

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, chosen))
    meta = pd.DataFrame([m for m, _ in res]).sort_values("file_id")
    dets = pd.DataFrame([x for _, ds in res for x in ds])
    meta.to_csv(d / "metadata.csv", index=False)
    dets.to_csv(d / "detections.csv", index=False)
    write_manifest(build_manifest(d, list(meta.path), f"hf:{BDD_REPO} (BDD100K val)", BDD_LICENSE), d / "manifest.csv")
    print(f"[bdd] {len(meta)} images -> {d}")
    print("      weather:", meta.weather.value_counts().to_dict())
    print("      timeofday:", meta.timeofday.value_counts().to_dict())
    print("      scene:", meta.scene.value_counts().to_dict())


# ----------------------------------------------------------------------------- COCO
COCO_KEEP = {"person", "bicycle", "car", "motorcycle", "bus", "truck", "traffic light", "stop sign", "dog"}


def download_coco(out: Path, n: int, max_side: int, seed: int, token: str | None, workers: int) -> None:
    hf = _hf()
    ann = json.load(open(hf(COCO_REPO, "annotations/instances_val2017_mini500.json", repo_type="dataset", token=token)))
    cats = {c["id"]: c["name"] for c in ann["categories"]}
    keep_ids = {k for k, v in cats.items() if v in COCO_KEEP}
    by_img = defaultdict(list)
    for a in ann["annotations"]:
        by_img[a["image_id"]].append(a)
    rng = np.random.default_rng(seed)
    road = [im for im in ann["images"] if any(a["category_id"] in keep_ids and a["category_id"] != 1 for a in by_img[im["id"]])]
    other = [im for im in ann["images"] if im not in road]
    rng.shuffle(road)
    rng.shuffle(other)
    chosen = (road + other)[:n]
    d = out / "coco"
    lic = {l["id"]: l.get("name", "") for l in ann.get("licenses", [])}

    def one(im):
        p = hf(COCO_REPO, f"images/val2017/{im['file_name']}", repo_type="dataset", token=token)
        w, h, sc = resize_save(p, d / "images" / im["file_name"], max_side)
        boxes = [{"image_id": im["id"], "file_name": im["file_name"], "ann_id": a["id"], "class": cats[a["category_id"]], "category_id": a["category_id"],
                  "x": round(a["bbox"][0] * sc, 2), "y": round(a["bbox"][1] * sc, 2), "w": round(a["bbox"][2] * sc, 2), "h": round(a["bbox"][3] * sc, 2),
                  "iscrowd": a.get("iscrowd", 0)} for a in by_img[im["id"]]]
        return {**im, "width": w, "height": h, "scale": sc, "license_name": lic.get(im.get("license"), "")}, boxes

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, chosen))
    imgs = [i for i, _ in res]
    boxes = pd.DataFrame([b for _, bs in res for b in bs])
    subset = {"info": {"description": f"subset of {COCO_REPO}, rescaled to max_side={max_side}"}, "licenses": ann.get("licenses", []),
              "categories": ann["categories"], "images": [{k: v for k, v in i.items() if k not in ("scale", "license_name")} for i in imgs],
              "annotations": [{"id": int(b.ann_id), "image_id": int(b.image_id), "category_id": int(b.category_id), "bbox": [b.x, b.y, b.w, b.h],
                               "area": round(b.w * b.h, 2), "iscrowd": int(b.iscrowd)} for b in boxes.itertuples()]}
    (d / "annotations_subset.json").write_text(json.dumps(subset))
    boxes.to_csv(d / "boxes.csv", index=False)
    pd.DataFrame([{"image_id": i["id"], "file_name": i["file_name"], "width": i["width"], "height": i["height"], "license_id": i.get("license"),
                   "license_name": i["license_name"]} for i in imgs]).to_csv(d / "images.csv", index=False)
    write_manifest(build_manifest(d, [f"images/{i['file_name']}" for i in imgs], f"hf:{COCO_REPO}", COCO_ANN_LICENSE), d / "manifest.csv")
    print(f"[coco] {len(imgs)} images, {len(boxes)} boxes -> {d}")


# ----------------------------------------------------------------------------- plates
def download_plates(out: Path, n: int, max_side: int, seed: int, token: str | None, workers: int) -> None:
    hf = _hf()
    zp = hf(PLATES_REPO, "data/test.zip", repo_type="dataset", token=token)
    z = zipfile.ZipFile(zp)
    ann_name = [x for x in z.namelist() if x.endswith("_annotations.coco.json")][0]
    ann = json.loads(z.read(ann_name))
    by_img = defaultdict(list)
    for a in ann["annotations"]:
        by_img[a["image_id"]].append(a)
    rng = np.random.default_rng(seed)
    imgs = [im for im in ann["images"] if by_img[im["id"]]]
    rng.shuffle(imgs)
    chosen = imgs[:n]
    prefix = str(Path(ann_name).parent)
    d = out / "plates"
    rows, meta = [], []
    for k, im in enumerate(chosen):
        member = f"{prefix}/{im['file_name']}" if prefix not in ("", ".") else im["file_name"]
        fid = f"plate_{k:03d}"
        w, h, sc = resize_save(z.read(member), d / "images" / f"{fid}.jpg", max_side)
        meta.append({"image_id": fid, "path": f"images/{fid}.jpg", "width": w, "height": h, "orig_file": im["file_name"]})
        for j, a in enumerate(by_img[im["id"]]):
            x, y, bw, bh = a["bbox"]
            rows.append({"image_id": fid, "region_id": f"{fid}_r{j}", "type": "plate", "x": round(x * sc, 2), "y": round(y * sc, 2),
                         "w": round(bw * sc, 2), "h": round(bh * sc, 2), "must_redact": 1})
    pd.DataFrame(meta).to_csv(d / "images.csv", index=False)
    pd.DataFrame(rows).to_csv(d / "plate_regions.csv", index=False)
    write_manifest(build_manifest(d, [m["path"] for m in meta], f"hf:{PLATES_REPO} (test split)", PLATES_LICENSE), d / "manifest.csv")
    print(f"[plates] {len(meta)} images, {len(rows)} plate regions -> {d}")


README = """# data/real — REAL samples (local only, gitignored)

Generated by `python -m tools.download_real_samples` (seed {seed}, max_side {max_side}).

| Pack | Source | License | Use in tracks |
|---|---|---|---|
| `bdd/` | `{bdd}` (BDD100K val) | {bdd_lic} | T01 T02 T03 T05 T10 T13 (metadata: weather/timeofday/scene), T11 T14 (boxes) |
| `coco/` | `{coco}` | {coco_lic} | T06 T11 T14 |
| `plates/` | `{plates}` | {plates_lic} | T07 (plate slice) |

**Rules**
- Contains real people and real licence plates. Do **not** commit, upload to cloud, or share outside the class.
- Real data has **no hidden eval GT prepared by the instructor**: if you use it, define your own GT protocol
  (e.g. inject defects with `src/common/corruptions.py` and log them in a manifest) and say so in the report.
- Synthetic fixtures in `fixtures/` remain the graded, reproducible baseline.
- Verify licenses yourself before reuse outside this lab.
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packs", nargs="*", default=["bdd", "coco", "plates"], choices=["bdd", "coco", "plates"])
    ap.add_argument("--out", default=str(ROOT / "data" / "real"))
    ap.add_argument("--bdd-n", type=int, default=240)
    ap.add_argument("--coco-n", type=int, default=150)
    ap.add_argument("--plates-n", type=int, default=60)
    ap.add_argument("--max-side", type=int, default=640, help="resize longest side (lab spec: <=1024)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    token = load_token()
    print("[hf] token:", "found (env/.env)" if token else "not set — trying anonymous access to public datasets")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if "bdd" in a.packs:
        download_bdd(out, a.bdd_n, a.max_side, a.seed, token, a.workers)
    if "coco" in a.packs:
        download_coco(out, a.coco_n, a.max_side, a.seed, token, a.workers)
    if "plates" in a.packs:
        download_plates(out, a.plates_n, a.max_side, a.seed, token, a.workers)
    (out / "README.md").write_text(README.format(seed=a.seed, max_side=a.max_side, bdd=BDD_REPO, coco=COCO_REPO, plates=PLATES_REPO,
                                                 bdd_lic=BDD_LICENSE, coco_lic=COCO_ANN_LICENSE, plates_lic=PLATES_LICENSE), encoding="utf-8")
    print("done ->", out)


if __name__ == "__main__":
    main()
