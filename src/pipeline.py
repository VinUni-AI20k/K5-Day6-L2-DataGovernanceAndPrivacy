"""YOUR PoC PIPELINE — this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   your algorithm / model (the research part)
    03 rank      prioritise for a fixed review budget B
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

Required output: out/<pred_file> with the columns listed for your track in
docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
    python -m src.evaluate --track tXX --pred out/<pred_file>

Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
no network calls; fail loudly on missing models instead of downloading.
See src/examples/random_baseline.py for a minimal end-to-end wiring example.
"""
import cv2
import numpy as np
import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track

COLS = ["image_id", "x", "y", "w", "h"]


# ---------------------------------------------------------------- detectors (classical, offline)
def detect_plates(bgr: np.ndarray) -> list[dict]:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    white = ((hsv[..., 2] > 170) & (hsv[..., 1] < 70)).astype(np.uint8)
    dark = (gray < 90).astype(np.uint8)
    blob = cv2.morphologyEx(white | dark, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(blob, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if not (10 <= w <= 90 and 4 <= h <= 30) or not (1.8 <= w / h <= 7):
            continue
        roi_w = white[y:y + h, x:x + w].mean()
        roi_d = dark[y:y + h, x:x + w].mean()
        if roi_w < 0.35 or roi_d < 0.05 or a / (w * h) < 0.6:
            continue
        conf = float(min(1.0, roi_w * 1.2) * min(1.0, w / 24) * (1.0 if roi_d > 0.12 else 0.7))
        out.append(dict(type="plate", x=int(x), y=int(y), w=int(w), h=int(h), conf=round(conf, 3)))
    return out


def detect_faces(bgr: np.ndarray) -> list[dict]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
    spots = (bh > 18).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(spots, 8)
    eyes = [(cen[i], st[i]) for i in range(1, n) if 1 <= st[i][4] <= 40 and st[i][2] <= 8 and st[i][3] <= 8]
    found = []
    for i, (c1, s1) in enumerate(eyes):
        for c2, s2 in eyes[i + 1:]:
            dx, dy = abs(c1[0] - c2[0]), abs(c1[1] - c2[1])
            if dy > 2 or not (2.5 <= dx <= 24):
                continue
            mx, my = int((c1[0] + c2[0]) / 2), int((c1[1] + c2[1]) / 2)
            mask = np.zeros((H + 2, W + 2), np.uint8)
            tmp = bgr.copy()
            cv2.floodFill(tmp, mask, (mx, my), (0, 0, 0), (14, 14, 14), (14, 14, 14), 4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
            m = cv2.morphologyEx(mask[1:-1, 1:-1], cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            ys, xs = np.nonzero(m)
            if len(xs) == 0:
                continue
            x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
            w, h = x1 - x0 + 1, y1 - y0 + 1
            if not (5 <= w <= 70 and 5 <= h <= 80) or not (0.6 <= w / h <= 1.3):
                continue
            if dx > 0.9 * w:
                continue
            fill = len(xs) / (w * h)
            conf = float(np.clip(1.0 - abs(fill - 0.78) * 2.5, 0.2, 1.0))
            if min(w, h) < 10:
                conf *= 0.7
            found.append(dict(type="face", x=int(x0), y=int(y0), w=int(w), h=int(h), conf=round(conf, 3)))
    return _nms(found)


def _nms(dets: list[dict], thr: float = 0.4) -> list[dict]:
    keep: list[dict] = []
    for d in sorted(dets, key=lambda d: -d["conf"]):
        if all(_iou(d, k) < thr for k in keep):
            keep.append(d)
    return keep


def _iou(a: dict, b: dict) -> float:
    ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    inter = ix * iy
    return inter / (a["w"] * a["h"] + b["w"] * b["h"] - inter + 1e-9)


def detect(bgr: np.ndarray) -> list[dict]:
    return detect_faces(bgr) + detect_plates(bgr)


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    imgs = pd.read_csv(ctx.input_dir / "images.csv")
    s = ctx.param("run_split")           # None = all images; "dev" while tuning
    return {"images": imgs[imgs.split == s] if s else imgs}


def pad_box(x, y, w, h, ratio, W, H):
    px, py = w * ratio, h * ratio
    x0, y0 = max(0, int(x - px)), max(0, int(y - py))
    x1, y1 = min(W, int(x + w + px + 0.999)), min(H, int(y + h + py + 0.999))
    return x0, y0, x1 - x0, y1 - y0


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    ratio = float(ctx.param("padding_ratio", 0.25))
    min_conf = float(ctx.param("min_conf", 0.25))
    rows = []
    for r in data["images"].itertuples():
        im = cv2.imread(str(ctx.input_dir / r.path))
        if im is None:
            raise FileNotFoundError(f"cannot read image {r.path}")
        H, W = im.shape[:2]
        for k, d in enumerate(detect(im)):
            if d["conf"] < min_conf:
                continue
            x, y, w, h = pad_box(d["x"], d["y"], d["w"], d["h"], ratio, W, H)
            rows.append(dict(image_id=r.image_id, x=x, y=y, w=w, h=h, item_id=f"{r.image_id}#{k}",
                             type=d["type"], conf=d["conf"], score=round(1 - d["conf"], 4),
                             reason=f"{d['type']} conf={d['conf']}", path=r.path))
    return pd.DataFrame(rows, columns=COLS + ["item_id", "type", "conf", "score", "reason", "path"])


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    q = make_review_queue(scored, id_col="item_id", score_col="score", budget=int(ctx.param("budget", 15)),
                          reason_col="reason", slice_col="type", evidence_col="path")
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(q, ctx.out("contact_sheet.html"), image_root=ctx.input_dir, title="T07 redaction review queue")
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """approve/skip keep the box, reject removes it, edit replaces it with override_value 'x,y,w,h'."""
    final = scored.copy()
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    ctx.stats["n_reviewed"] = 0
    if not reviewed_path.exists():
        return final
    rv = load_review_decisions(reviewed_path)
    ctx.stats["n_reviewed"] = len(rv)
    for r in rv.itertuples(index=False):
        m = final.item_id == r.item_id
        if not m.any():
            continue
        before = final.loc[m, COLS[1:]].iloc[0].tolist()
        if r.reviewer_decision == "reject":
            final = final[~m]
            ctx.audit.log(actor=r.reviewer, action="override:reject", item_id=r.item_id, before=before, after=None, reason=r.review_note)
        elif r.reviewer_decision == "edit" and str(r.override_value).strip():
            x, y, w, h = [int(float(v)) for v in str(r.override_value).replace(";", ",").split(",")]
            final.loc[m, COLS[1:]] = [x, y, w, h]
            ctx.audit.log(actor=r.reviewer, action="override:edit", item_id=r.item_id, before=before, after=[x, y, w, h], reason=r.review_note)
        else:
            ctx.audit.log(actor=r.reviewer, action=f"review:{r.reviewer_decision}", item_id=r.item_id, reason=r.review_note)
    return final


def _export_images(ctx: RunContext, final: pd.DataFrame, imgs: pd.DataFrame) -> None:
    for r in imgs.itertuples():
        im = cv2.imread(str(ctx.input_dir / r.path))
        for b in final[final.image_id == r.image_id].itertuples():
            roi = im[b.y:b.y + b.h, b.x:b.x + b.w]
            k = max(3, (min(b.w, b.h) // 2) | 1)
            im[b.y:b.y + b.h, b.x:b.x + b.w] = cv2.GaussianBlur(roi, (k, k), 0)
        cv2.imwrite(str(ctx.out(f"redacted/{r.image_id}.jpg")), im)


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    owner = ctx.config.get("owner", "TODO-owner")
    if ctx.stats.get("n_reviewed", 0) == 0:
        return Decision(status="HOLD", reason_code="REVIEW_PENDING", owner=owner, scope=ctx.track,
                        reason="Queue not yet reviewed by a human; do not release redacted set")
    if len(final) and float(final.conf.mean()) < float(ctx.param("min_mean_conf", 0.6)):
        return Decision(status="REWORK", reason_code="LOW_DETECTOR_CONFIDENCE", owner=owner, scope=ctx.track,
                        reason="Mean detector confidence below frozen threshold")
    return Decision(status="GO", reason_code="REVIEWED_QUEUE_OK", owner=owner, scope=ctx.track,
                    reason="Queue reviewed with audit log; output is redacted/pseudonymised, not anonymised")


def run(ctx: RunContext) -> None:
    if ctx.track != "t07":
        raise NotImplementedError(f"src/pipeline.py implements only t07 (got {ctx.track})")
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(data["images"])
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    spec = get_track(ctx.track)
    final[COLS + [c for c in final.columns if c not in COLS]].to_csv(ctx.out(spec.pred_file), index=False)
    _export_images(ctx, final, data["images"])
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
