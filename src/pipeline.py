"""Offline T02 image triage with staged, auditable human review."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import brightness_stats, jpeg_blockiness, laplacian_variance, load_rgb, local_glare_stats
from .common.io import sha256_text
from .common.manifest import verify_manifest
from .common.review import AuditLog, T02_REASON_CODES, T02_REVIEW_COLUMNS, load_t02_review_decisions, write_review_queue
from .metrics.tracks import get_track

_REVIEW_FILES = {
    "qc": ("review_queue.csv", "contact_sheet.html", "review_queue_reviewed.csv", "QC review queue"),
    "senior_qc": ("senior_review_queue.csv", "senior_contact_sheet.html", "senior_review_queue_reviewed.csv", "Senior QC review queue"),
    "domain_owner": ("domain_owner_review_queue.csv", "domain_owner_contact_sheet.html", "domain_owner_review_queue_reviewed.csv", "Domain owner review queue"),
}
_FEATURES = ("blur", "dark", "glare", "compression")


def load(ctx: RunContext) -> dict:
    """Verify provenance and load T02 metadata without touching ground truth."""
    manifest = ctx.input_dir / "manifest.csv"
    images_path = ctx.input_dir / "images.csv"
    if not images_path.exists():
        raise FileNotFoundError(f"T02 metadata not found: {images_path}")
    # Read identifiers and metadata as strings to preserve values such as IDs
    # with leading zeroes and to avoid accidental type inference by pandas.
    images = pd.read_csv(images_path, dtype={"image_id": str, "path": str, "camera_id": str, "light": str, "split": str})
    required = ["image_id", "path", "camera_id", "light", "split"]
    missing = [c for c in required if c not in images.columns]
    if missing:
        raise ValueError(f"{images_path} missing required columns {missing}")
    images["image_id"] = images["image_id"].fillna("").astype(str).str.strip()
    images["path"] = images["path"].fillna("").astype(str).str.strip()
    if (images.image_id == "").any():
        raise ValueError(f"{images_path} contains an empty image_id")
    duplicate_ids = sorted(images.loc[images.image_id.duplicated(keep=False), "image_id"].unique().tolist())
    if duplicate_ids:
        raise ValueError(f"{images_path} contains duplicate image_id values: {duplicate_ids}")
    missing_paths = images[images.path == ""]
    if len(missing_paths):
        raise ValueError(f"images have missing paths: {missing_paths.image_id.tolist()}")

    manifest_df = pd.read_csv(manifest, dtype=str) if manifest.exists() else None
    # Check both file hashes and that each image referenced by metadata is
    # included in the provenance manifest before processing it.
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if manifest_df is not None and "path" in manifest_df.columns:
        listed_paths = set(manifest_df["path"].fillna("").astype(str))
        unlisted = sorted(set(images.path.astype(str)) - listed_paths)
        problems.extend({"problem": "metadata_path_not_in_manifest", "path": path} for path in unlisted)
    if problems:
        by_path = dict(zip(images.path, images.image_id))
        details = []
        for p in problems[:8]:
            path = p.get("path", "")
            image_id = by_path.get(path)
            details.append(f"image_id={image_id!r} path={path!r}: {p.get('problem')}" if image_id else str(p))
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=details)
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems): {details[:3]}")
    return {"manifest": manifest_df, "images": images}


def _image_path(ctx: RunContext, row: pd.Series) -> Path:
    root = ctx.input_dir.resolve()
    candidate = Path(str(row["path"]))
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        # Reject paths that escape the input folder, even when they use '..'
        # or resolve through symlinks.
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"image path escapes input folder for image_id={row.get('image_id', '')!r}: {row['path']!r}") from None
    return resolved


def _measure_images(ctx: RunContext, images: pd.DataFrame, include_extra: bool = True) -> pd.DataFrame:
    rows = []
    for row in images.itertuples(index=False):
        rec = pd.Series(row._asdict())
        image_path = _image_path(ctx, rec)
        if not image_path.is_file():
            raise FileNotFoundError(f"missing image for image_id={rec.image_id!r} path={str(image_path)!r}")
        try:
            img = load_rgb(image_path)
            lap = laplacian_variance(img)
            values = {
                "image_id": str(rec.image_id), "path": str(rec.path), "camera_id": str(rec.camera_id),
                "light": str(rec.light), "split": str(rec.split), "laplacian_variance": lap,
            }
            if include_extra:
                values.update(brightness_stats(img))
                values.update({f"glare_{k}": v for k, v in local_glare_stats(img).items()})
                values["jpeg_blockiness"] = jpeg_blockiness(img)
        except Exception as exc:
            raise ValueError(f"cannot read/process image_id={rec.image_id!r} path={str(image_path)!r}: {exc}") from exc
        rows.append(values)
    measured = pd.DataFrame(rows)
    numeric = measured.select_dtypes(include=[np.number])
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        bad = measured.loc[~np.isfinite(numeric).all(axis=1), "image_id"].tolist()
        raise ValueError(f"non-finite image features for image_id values {bad}")
    return measured


def _tail_risk(values: pd.Series, dev: pd.Series, direction: str) -> tuple[np.ndarray, dict]:
    """Scale a dev-calibrated tail beyond its quartile to [0,1]."""
    vals = values.to_numpy(dtype=float)
    refs = dev.to_numpy(dtype=float)
    if not len(refs):
        raise ValueError("T02 normalization requires at least one dev image")
    if direction == "low":
        threshold = float(np.quantile(refs, 0.25))
        floor = float(np.min(refs))
        span = threshold - floor
        risk = (vals < threshold).astype(float) if span <= 1e-12 else np.clip((threshold - vals) / span, 0.0, 1.0)
    else:
        threshold = float(np.quantile(refs, 0.75))
        ceiling = float(np.max(refs))
        span = ceiling - threshold
        risk = (vals > threshold).astype(float) if span <= 1e-12 else np.clip((vals - threshold) / span, 0.0, 1.0)
    return risk, {"direction": direction, "threshold_q25_or_q75": threshold, "dev_min": float(np.min(refs)),
                  "dev_max": float(np.max(refs)), "dev_n": int(len(refs))}


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Score all input images using interpretable, dev-normalized signals."""
    started = time.perf_counter()
    measured = _measure_images(ctx, data["images"], include_extra=True)
    dev = measured[measured.split == str(ctx.param("dev_split", "dev"))]
    if dev.empty:
        raise ValueError(f"no dev images found for normalization split {ctx.param('dev_split', 'dev')!r}")
    specs = {
        "blur": ("laplacian_variance", "low"),
        "dark": ("frac_dark", "high"),
        "glare": ("glare_local_saturated_max", "high"),
        "compression": ("jpeg_blockiness", "high"),
    }
    norms = {}
    for name, (column, direction) in specs.items():
        measured[f"risk_{name}"], norms[name] = _tail_risk(measured[column], dev[column], direction)
    weights = {"blur": 0.35, "dark": 0.20, "glare": 0.30, "compression": 0.15}
    measured["score"] = sum(measured[f"risk_{name}"] * weight for name, weight in weights.items())
    measured["score"] = measured["score"].astype(float)
    risk_columns = [f"risk_{name}" for name in _FEATURES]
    winner = measured[risk_columns].to_numpy().argmax(axis=1)
    measured["pred_defect_type"] = [
        _FEATURES[i] if measured[risk_columns].iloc[j, i] > 0 else "none" for j, i in enumerate(winner)
    ]
    measured["reason"] = [
        "; ".join(f"{name}={measured.iloc[j][f'risk_{name}']:.3f}" for name in _FEATURES
                   if measured.iloc[j][f"risk_{name}"] > 0) or "no feature exceeded dev tail"
        for j in range(len(measured))
    ]
    measured["pred_action"] = np.where(measured["score"] > 0, "REVIEW", "KEEP")
    if not np.isfinite(measured.score.to_numpy(dtype=float)).all():
        raise ValueError("T02 generated non-finite ranking scores")
    ctx.stats["normalization"] = norms
    ctx.stats["feature_weights"] = weights
    ctx.stats["process_seconds"] = round(time.perf_counter() - started, 4)
    ctx.stats["process_ms_per_image"] = round(ctx.stats["process_seconds"] * 1000 / len(measured), 3)
    return measured


def process_baseline(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Global Laplacian threshold baseline calibrated only on dev images."""
    started = time.perf_counter()
    measured = _measure_images(ctx, data["images"], include_extra=False)
    dev = measured[measured.split == str(ctx.param("dev_split", "dev"))]
    if dev.empty:
        raise ValueError(f"no dev images found for baseline threshold split {ctx.param('dev_split', 'dev')!r}")
    threshold = float(np.quantile(dev.laplacian_variance.to_numpy(dtype=float), float(ctx.param("baseline_quantile", 0.25))))
    span = max(threshold - float(dev.laplacian_variance.min()), 1e-12)
    measured["score"] = np.clip((threshold - measured.laplacian_variance) / span, 0.0, 1.0)
    measured["pred_defect_type"] = np.where(measured.laplacian_variance < threshold, "blur", "none")
    measured["reason"] = np.where(measured.laplacian_variance < threshold,
                                   f"global Laplacian below dev q{ctx.param('baseline_quantile', 0.25):g} threshold {threshold:.3f}",
                                   "Laplacian above dev threshold")
    measured["pred_action"] = np.where(measured["score"] > 0, "REVIEW", "KEEP")
    if not np.isfinite(measured.score.to_numpy(dtype=float)).all():
        raise ValueError("T02 baseline generated non-finite ranking scores")
    ctx.stats["baseline_laplacian_threshold"] = threshold
    ctx.stats["baseline_dev_n"] = int(len(dev))
    ctx.stats["process_seconds"] = round(time.perf_counter() - started, 4)
    ctx.stats["process_ms_per_image"] = round(ctx.stats["process_seconds"] * 1000 / len(measured), 3)
    return measured


def _queue_id(stage: str, queue: pd.DataFrame, parent: str = "") -> str:
    context = []
    for row in queue.to_dict(orient="records"):
        context.append({key: str(row.get(key, "")) for key in
                        ("image_id", "score", "reason", "light", "camera_id", "evidence_path", "review_history")})
    canonical = json.dumps({"stage": stage, "parent": parent, "items": context}, separators=(",", ":"), ensure_ascii=False)
    return f"t02-{stage}-{sha256_text(canonical)[:12]}"


def _stage_queue(base: pd.DataFrame, stage: str, parent_queue_id: str = "") -> pd.DataFrame:
    q = base.copy().reset_index(drop=True)
    q["rank"] = range(1, len(q) + 1)
    q["item_id"] = q["image_id"].astype(str)
    q["review_stage"] = stage
    q["queue_id"] = _queue_id(stage, q, parent_queue_id)
    q.attrs["queue_id"] = q["queue_id"].iloc[0] if len(q) else _queue_id(stage, q, parent_queue_id)
    if "review_history" not in q:
        q["review_history"] = ""
    for col in ["reviewer", "action", "review_reason_codes", "review_note", "reviewed_at", "review_session_seconds"]:
        q[col] = ""
    return q


def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Rank all 96 images, then create the evaluator-aligned top-20 eval queue."""
    if "image_id" not in scored or "score" not in scored:
        raise ValueError("T02 rank() requires image_id and score columns")
    if scored.image_id.astype(str).duplicated().any():
        dup = sorted(scored.loc[scored.image_id.astype(str).duplicated(keep=False), "image_id"].astype(str).unique())
        raise ValueError(f"T02 rank() refuses duplicate image_id values: {dup}")
    scores = pd.to_numeric(scored.score, errors="coerce")
    if scores.isna().any() or not np.isfinite(scores.to_numpy(dtype=float)).all():
        raise ValueError("T02 rank() requires one finite numeric score per image")
    budget = int(ctx.param("budget", 20))
    if budget <= 0:
        raise ValueError(f"T02 review budget must be positive; got {budget}")
    eval_split = str(ctx.param("eval_split", "eval"))
    pool = scored[scored.split.astype(str) == eval_split] if "split" in scored else scored
    if len(pool) < budget:
        raise ValueError(f"T02 eval split {eval_split!r} has {len(pool)} images, fewer than review budget {budget}")
    ordered = pool.sort_values("score", ascending=False, kind="mergesort").head(budget).reset_index(drop=True)
    if "path" in ordered:
        ordered["evidence_path"] = ordered["path"]
    queue = _stage_queue(ordered, "qc")
    ctx.stats["ranked_n"] = int(len(scored))
    ctx.stats["queue_n"] = int(len(queue))
    ctx.stats["eval_split"] = eval_split
    ctx.stats["queue_id"] = str(queue.queue_id.iloc[0]) if len(queue) else _queue_id("qc", queue)
    return queue


def _queue_for_stage(queue: pd.DataFrame, stage: str, parent_queue_id: str = "") -> pd.DataFrame:
    base_columns = [c for c in ["image_id", "score", "reason", "light", "camera_id", "evidence_path", "review_history"] if c in queue]
    base = queue[base_columns].copy()
    return _stage_queue(base, stage, parent_queue_id)


def _audit_decisions(ctx: RunContext, reviewed: pd.DataFrame, stage: str, queue_id: str) -> None:
    audit = ctx.audit or AuditLog(ctx.out("audit_log.jsonl"))
    history = audit.read()
    for row in reviewed.to_dict(orient="records"):
        item_id = str(row["image_id"])
        after = {
            "action": row["action"], "review_reason_codes": row["review_reason_codes"],
            "review_note": row["review_note"], "reviewed_at": row["reviewed_at"],
            "review_session_seconds": float(row["review_session_seconds"]),
        }
        prior = next((ev for ev in reversed(history)
                      if ev.get("action") in {"review_decision", "review_override"}
                      and ev.get("item_id") == item_id
                      and ev.get("extra", {}).get("review_stage") == stage
                      and ev.get("extra", {}).get("queue_id") == queue_id), None)
        same = bool(prior and prior.get("actor") == row["reviewer"] and prior.get("after") == after)
        if same:
            continue
        audit.log(
            actor=row["reviewer"], action="review_override" if prior else "review_decision", item_id=item_id,
            before=prior.get("after") if prior else None, after=after, reason=row["review_note"],
            review_stage=stage, queue_id=queue_id, review_reason_codes=row["review_reason_codes"],
        )
        history = audit.read()


def _history_text(prior: pd.Series, parent_stage: str) -> str:
    return json.dumps([{
        "stage": parent_stage, "reviewer": prior["reviewer"], "action": prior["action"],
        "review_reason_codes": prior["review_reason_codes"], "review_note": prior["review_note"],
        "reviewed_at": prior["reviewed_at"],
    }], ensure_ascii=False, separators=(",", ":"))


def _render_stage(ctx: RunContext, queue: pd.DataFrame, stage: str) -> None:
    csv_name, html_name, export_name, title = _REVIEW_FILES[stage]
    write_review_queue(queue[T02_REVIEW_COLUMNS], ctx.out(csv_name))
    render_contact_sheet(
        queue[T02_REVIEW_COLUMNS], ctx.out(html_name), image_col="evidence_path", image_root=ctx.input_dir,
        title=title, fields=("review_stage", "queue_id", "rank", "image_id", "score", "reason", "light", "camera_id", "review_history"),
        decision_options=("", "KEEP", "RECAPTURE", "HOLD"), decision_col="action",
        reason_codes_col="review_reason_codes", export_filename=export_name,
        session_duration_col="review_session_seconds", reason_codes_allowed=T02_REASON_CODES,
    )


def _read_stage(ctx: RunContext, queue: pd.DataFrame, stage: str) -> pd.DataFrame:
    _, _, reviewed_name, _ = _REVIEW_FILES[stage]
    path = ctx.output_dir / reviewed_name
    queue_id = str(queue.queue_id.iloc[0]) if len(queue) else str(queue.attrs.get("queue_id") or _queue_id(stage, queue))
    if not path.exists():
        return pd.DataFrame(columns=T02_REVIEW_COLUMNS)
    reviewed = load_t02_review_decisions(path, stage, queue_id, queue.image_id.astype(str).tolist())
    _audit_decisions(ctx, reviewed, stage, queue_id)
    return reviewed


def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Import QC decisions and create separate escalation queues by review level."""
    audit_path = ctx.audit.path if ctx.audit is not None else ctx.out("audit_log.jsonl")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.touch(exist_ok=True)
    qc_queue = queue.copy()
    _render_stage(ctx, qc_queue, "qc")
    qc = _read_stage(ctx, qc_queue, "qc")
    qc_map = {str(r.image_id): r for r in qc.itertuples(index=False)}
    senior_rows = []
    for row in qc_queue.itertuples(index=False):
        decision = qc_map.get(str(row.image_id))
        if decision and decision.action == "HOLD":
            record = {c: getattr(row, c) for c in ["image_id", "score", "reason", "light", "camera_id", "evidence_path"]}
            record["review_history"] = _history_text(pd.Series(decision._asdict()), "qc")
            senior_rows.append(record)
    senior_base = pd.DataFrame(senior_rows, columns=["image_id", "score", "reason", "light", "camera_id", "evidence_path", "review_history"])
    senior_queue = _queue_for_stage(senior_base, "senior_qc", str(qc_queue.queue_id.iloc[0]) if len(qc_queue) else "")
    _render_stage(ctx, senior_queue, "senior_qc")
    senior = _read_stage(ctx, senior_queue, "senior_qc")
    senior_map = {str(r.image_id): r for r in senior.itertuples(index=False)}
    owner_rows = []
    for row in senior_queue.itertuples(index=False):
        decision = senior_map.get(str(row.image_id))
        if decision and decision.action == "HOLD":
            record = {c: getattr(row, c) for c in ["image_id", "score", "reason", "light", "camera_id", "evidence_path"]}
            previous = json.loads(str(row.review_history)) if str(row.review_history) else []
            previous.append({
                "stage": "senior_qc", "reviewer": decision.reviewer, "action": decision.action,
                "review_reason_codes": decision.review_reason_codes, "review_note": decision.review_note,
                "reviewed_at": decision.reviewed_at,
            })
            record["review_history"] = json.dumps(previous, ensure_ascii=False, separators=(",", ":"))
            owner_rows.append(record)
    owner_base = pd.DataFrame(owner_rows, columns=["image_id", "score", "reason", "light", "camera_id", "evidence_path", "review_history"])
    owner_queue = _queue_for_stage(owner_base, "domain_owner", str(senior_queue.queue_id.iloc[0]) if len(senior_queue) else "")
    _render_stage(ctx, owner_queue, "domain_owner")
    owner = _read_stage(ctx, owner_queue, "domain_owner")
    ctx.stats["review_counts"] = {"qc": len(qc), "senior_qc": len(senior), "domain_owner": len(owner)}
    ctx.stats["review_session_seconds"] = float(sum(pd.to_numeric(x.review_session_seconds, errors="coerce").fillna(0).sum()
                                                        for x in (qc, senior, owner)))
    return {"qc": qc, "senior_qc": senior, "domain_owner": owner,
            "queues": {"qc": qc_queue, "senior_qc": senior_queue, "domain_owner": owner_queue}}


def _write_t02_decision(ctx: RunContext, decision: Decision) -> None:
    log_path = ctx.out("decision_log.csv")
    signature = [decision.scope, decision.status, decision.canonical, decision.reason_code, decision.reason,
                 decision.owner, ";".join(decision.evidence)]
    if log_path.exists() and log_path.stat().st_size:
        existing = pd.read_csv(log_path, dtype=str).fillna("")
        if len(existing):
            last = existing.iloc[-1]
            old = [last.get("scope", ""), last.get("status", ""), last.get("canonical", ""), last.get("reason_code", ""),
                   last.get("reason", ""), last.get("owner", ""), last.get("evidence", "")]
            if old == signature:
                decision.ts = str(last["ts"])
                write_decision(decision, ctx.out("decision.json"), None)
                return
    write_decision(decision, ctx.out("decision.json"), log_path)


def decide(ctx: RunContext, scored: pd.DataFrame, reviewed: dict[str, pd.DataFrame]) -> Decision:
    qc_queue = reviewed["queues"]["qc"]
    decisions: dict[str, tuple[str, str]] = {}
    for stage in ("qc", "senior_qc", "domain_owner"):
        rows = reviewed[stage]
        for r in rows.itertuples(index=False):
            decisions[str(r.image_id)] = (str(r.action), stage)
    outcomes = [decisions.get(str(image_id), ("PENDING", ""))[0] for image_id in qc_queue.image_id]
    unresolved = sum(x in {"PENDING", "HOLD"} for x in outcomes)
    recaptures = sum(x == "RECAPTURE" for x in outcomes)
    if unresolved:
        status, reason_code = "HOLD", "REVIEW_PENDING"
        reason = f"{unresolved} of {len(outcomes)} images in the eval top-{len(outcomes)} queue remain unresolved or on HOLD."
    elif recaptures:
        status, reason_code = "REWORK", "QUEUE_RECAPTURE_REQUIRED"
        reason = f"{recaptures} of {len(outcomes)} images in the eval top-{len(outcomes)} queue were marked RECAPTURE."
    else:
        status, reason_code = "GO", "QUEUE_ALL_KEPT"
        reason = f"All {len(outcomes)} images in the eval top-{len(outcomes)} review queue were marked KEEP."
    reason += f" This decision applies to the eval top-{len(outcomes)} review queue only; it does not approve release of the full batch."
    owner = str(ctx.config.get("owner", "TODO: owner"))
    if "TODO" in owner.upper() or "G00" in str(ctx.config.get("group_id", "")).upper():
        reason += " The sample owner/group configuration is still provisional."
    return Decision(
        status=status, reason_code=reason_code, reason=reason, owner=owner,
        scope=f"{ctx.track}:eval-top-{len(outcomes)}:{str(qc_queue.queue_id.iloc[0]) if len(qc_queue) else 'empty'}",
        evidence=[str(ctx.out("ranked_review.csv")), str(ctx.out("review_queue.csv")), str(ctx.out("audit_log.jsonl"))],
        metrics={"queue_size": len(outcomes), "unresolved": unresolved, "recapture": recaptures, "keep": outcomes.count("KEEP")},
    )


def _run(ctx: RunContext, baseline: bool = False) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process_baseline(ctx, data) if baseline else process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    pred_columns = ["image_id", "score", "pred_defect_type", "pred_action", "reason"]
    scored = scored.sort_values("score", ascending=False, kind="mergesort").reset_index(drop=True)
    scored[pred_columns].to_csv(ctx.out(spec.pred_file), index=False)
    scored[["image_id", "score", "pred_defect_type", "pred_action", "reason", "light", "camera_id", "split"]].to_csv(
        ctx.out("ranked_review.csv"), index=False
    )
    imported = review(ctx, scored, queue)
    _write_t02_decision(ctx, decide(ctx, scored, imported))


def run(ctx: RunContext) -> None:
    _run(ctx, baseline=False)
