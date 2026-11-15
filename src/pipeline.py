"""YOUR PoC PIPELINE (T13 - Active Learning & Rare Case Miner) - this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load     input + provenance check (manifest.csv)
    02 process  novelty (kNN) + rarity (KMeans) + junk filter + k-center greedy with hard dedupe
    03 rank     top-K review queue (K = budget = 20)
    04 review   apply reviewer overrides, then re-select final top-K
    05 decide   GO / HOLD / REWORK with reason_code + owner, based on evidence

Required output: out/<pred_file> (T13: out/selected.csv) = exactly K rows, column `image_id` (+ optional `rank`).

Rules: never read fixtures/*/gt/; seed everything via ctx.rng; no network calls.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track

ID = "image_id"
NON_FEATURE_COLS = {ID, "id", "file_name", "path", "split", "label", "gt", "rank"}


# ---------------------------------------------------------------- helpers
def _minmax(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    rng = x.max() - x.min()
    return (x - x.min()) / rng if rng > 1e-12 else np.zeros_like(x)


def _robust_z(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    if mad <= 1e-8:
        return np.zeros_like(x)
    return 0.6745 * (x - med) / mad


def _find_col(df: pd.DataFrame, prefixes: tuple[str, ...]) -> str | None:
    for p in prefixes:
        for c in df.columns:
            if c == p or c.startswith(p):
                if pd.api.types.is_numeric_dtype(df[c]):
                    return c
    return None


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")

    data: dict = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}

    # pool features / embeddings
    for name in ("pool_features.csv", "features.csv"):
        p = ctx.input_dir / name
        if p.exists():
            feats = pd.read_csv(p)
            break
    else:
        raise FileNotFoundError("pool_features.csv not found in input directory.")

    # normalise the id column to `image_id`
    if ID not in feats.columns:
        first = "id" if "id" in feats.columns else feats.columns[0]
        feats = feats.rename(columns={first: ID})
    feats[ID] = feats[ID].astype(str)

    # images.csv gives the image `path` (needed for the contact sheet)
    imgs_path = ctx.input_dir / "images.csv"
    if imgs_path.exists():
        imgs = pd.read_csv(imgs_path)
        imgs[ID] = imgs[ID].astype(str)
        if "path" in imgs.columns and "path" not in feats.columns:
            feats = feats.merge(imgs[[ID, "path"]], on=ID, how="left")
    data["features"] = feats
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    df = data.get("features")
    if df is None or df.empty:
        raise ValueError("Feature data is missing or empty.")
    df = df.reset_index(drop=True)
    n = len(df)

    numeric = [c for c in df.columns if c not in NON_FEATURE_COLS and pd.api.types.is_numeric_dtype(df[c])]
    emb_cols = [c for c in numeric if c.startswith("emb_")]
    if not emb_cols:
        emb_cols = numeric  # fallback: no embedding columns found
    if not emb_cols:
        raise ValueError("No numeric feature columns found.")

    # Embedding space is used ONLY for novelty / rarity / dedupe (avoid brightness bias).
    X = StandardScaler().fit_transform(df[emb_cols].values)

    # 1. Novelty = mean distance to k nearest neighbours
    k = int(ctx.param("knn", 5))
    nn = NearestNeighbors(n_neighbors=min(k + 1, n)).fit(X)
    dists, _ = nn.kneighbors(X)
    if dists.shape[1] > 1:
        novelty = dists[:, 1:].mean(axis=1)
        nn1 = dists[:, 1]
    else:
        novelty = np.zeros(n)
        nn1 = np.zeros(n)

    # 2. Rarity = 1 - relative size of KMeans cluster
    n_clusters = max(1, min(int(ctx.param("n_clusters", 10)), n))
    seed_val = int(ctx.rng.integers(0, 10000))
    labels = KMeans(n_clusters=n_clusters, random_state=seed_val, n_init=10).fit_predict(X)
    counts = np.bincount(labels)
    rarity = 1.0 - counts[labels] / n

    # 3. Junk = isolated singletons in embedding space OR extreme noise in cheap features
    junk_z = float(ctx.param("junk_z", 3.0))
    noise_z = float(ctx.param("noise_z", 3.5))
    nov_z = _robust_z(novelty)
    is_junk = nov_z > junk_z
    edge_col = _find_col(df, ("edge_density",))
    if edge_col is not None:
        is_junk = is_junk | (_robust_z(df[edge_col].values) > noise_z)

    # 4. Dark bias guard (failure mode: "only very dark images")
    bright_col = _find_col(df, ("brightness_mean", "brightness"))
    if bright_col is not None:
        b = df[bright_col].values
        is_dark = b <= np.quantile(b, float(ctx.param("dark_quantile", 0.25)))
    else:
        is_dark = np.zeros(n, dtype=bool)
    dark_cap = math.ceil(float(ctx.param("dark_cap", 0.6)) * int(ctx.param("budget", 20)))

    # 5. Base score on a common 0-1 scale: "hybrid" | "novelty" | "diversity"
    mode = ctx.param("mode", "hybrid")
    nov_n, rar_n = _minmax(novelty), _minmax(rarity)
    if mode == "novelty":
        base = nov_n
    elif mode == "diversity":
        base = rar_n
    else:
        base = 0.5 * nov_n + 0.5 * rar_n
    base = base.copy()
    base[is_junk] -= 10.0  # junk can never win on score

    # 6. Greedy k-center selection with HARD dedupe + dark cap + junk exclusion
    lam = float(ctx.param("lambda", 0.5))
    budget = min(int(ctx.param("budget", 20)), n)
    tau_param = ctx.param("dedupe_tau", None)
    tau = float(tau_param) if tau_param is not None else float(np.quantile(nn1, float(ctx.param("dedupe_q", 0.10))))

    selected: list[int] = []
    relaxed: set[int] = set()
    chosen = np.zeros(n, dtype=bool)
    min_d = np.full(n, np.inf)
    dark_count = 0

    while len(selected) < budget:
        # constraint levels: 0 = all rules, 1 = drop dedupe+dark cap, 2 = also allow junk
        pick = None
        for level in range(3):
            avail = ~chosen
            if level < 2:
                avail &= ~is_junk
            if level == 0:
                if selected:
                    avail &= min_d > tau
                if dark_count >= dark_cap:
                    avail &= ~is_dark
            if avail.any():
                idx = np.flatnonzero(avail)
                if selected:
                    d = min_d[idx]
                    d = d / (d.max() + 1e-9)
                    g = base[idx] + lam * d
                else:
                    g = base[idx]
                pick = int(idx[np.argmax(g)])
                if level > 0:
                    relaxed.add(pick)
                break
        if pick is None:
            break
        selected.append(pick)
        chosen[pick] = True
        dark_count += int(is_dark[pick])
        min_d = np.minimum(min_d, np.linalg.norm(X - X[pick], axis=1))
        min_d[pick] = 0.0

    # 7. Final scores: selected items on top (in greedy order), the rest by base score
    scores = base - base.min()
    for r, idx in enumerate(selected):
        scores[idx] = 1000.0 + (len(selected) - r)

    sel_rank = np.full(n, -1, dtype=int)
    is_selected = np.zeros(n, dtype=bool)
    for r, idx in enumerate(selected, start=1):
        sel_rank[idx] = r
        is_selected[idx] = True

    # near-duplicate flag among the K (closest other selected item is within tau)
    near_dup_sel = 0
    if len(selected) > 1:
        S = X[selected]
        pd_ = np.linalg.norm(S[:, None, :] - S[None, :, :], axis=2)
        np.fill_diagonal(pd_, np.inf)
        near_dup_sel = int((pd_.min(axis=1) <= tau).sum())

    # 8. Explainable reasons
    med_nov = np.median(novelty)
    mad_nov = np.median(np.abs(novelty - med_nov))
    reasons = []
    for i in range(n):
        parts = ["selected_by_greedy"] if is_selected[i] else []
        if novelty[i] > med_nov + mad_nov:
            parts.append("high_novelty")
        if rarity[i] > 0.5:
            parts.append("rare_cluster")
        if is_dark[i]:
            parts.append("dark")
        if is_junk[i]:
            parts.append("junk_flagged")
        if i in relaxed:
            parts.append("constraint_relaxed")
        if not is_selected[i] and not is_junk[i] and min_d[i] <= tau:
            parts.append("near_duplicate_of_selected")
        reasons.append(",".join(parts) if parts else "not_selected")

    out = df.copy()
    out["score"] = scores
    out["novelty"] = novelty
    out["rarity"] = rarity
    out["is_junk"] = is_junk
    out["is_dark"] = is_dark
    out["reason"] = reasons
    out["is_selected"] = is_selected
    out["selection_rank"] = sel_rank

    ctx.stats["dedupe_tau"] = round(tau, 4)
    ctx.stats["n_dark_selected"] = int(is_dark[selected].sum()) if selected else 0
    ctx.stats["n_near_dup_selected"] = near_dup_sel
    ctx.stats["n_relaxed"] = len(relaxed)
    return out


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Create the top-K review queue (K = budget)."""
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): missing score column.")

    q = make_review_queue(
        scored,
        id_col=ID,
        score_col="score",
        budget=budget,
        reason_col="reason",
        evidence_col="path" if "path" in scored.columns else None,
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Apply reviewer decisions from out/review_queue_reviewed.csv (if present), then re-select top-K.

    common.review.apply_overrides only changes a value column for `edit`/`reject` rows that carry an
    override_value, so a plain `reject` would do nothing there. T13 needs "reject -> drop from K and
    refill", so decisions are applied here and every change is written to the audit log.
      approve  -> keep in K (highest priority)
      reject   -> removed from K, replaced by the next best clean candidate
      edit / escalate / skip -> no change to the selection (still logged)
    """
    final = scored.copy()
    final[ID] = final[ID].astype(str)
    final["reviewer_decision"] = ""
    final["reviewer"] = ""
    final["review_note"] = ""

    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)  # validates decisions + mandatory reviewer
        ctx.stats["n_reviewed"] = len(reviewed)
        ctx.stats["n_rejected"] = int((reviewed["reviewer_decision"] == "reject").sum())
        for r in reviewed.itertuples(index=False):
            mask = final[ID] == str(r.item_id)
            if not mask.any():
                continue
            was_selected = bool(final.loc[mask, "is_selected"].iloc[0])
            final.loc[mask, "reviewer_decision"] = r.reviewer_decision
            final.loc[mask, "reviewer"] = r.reviewer
            final.loc[mask, "review_note"] = r.review_note
            ctx.audit.log(
                actor=r.reviewer,
                action=f"review:{r.reviewer_decision}",
                item_id=str(r.item_id),
                before={"is_selected": was_selected},
                after={"decision": r.reviewer_decision},
                reason=r.review_note,
            )

    # priority: approved > originally selected > other clean candidates > junk/near-dup; rejected excluded
    dec = final["reviewer_decision"].values
    clean = (~final["is_junk"].astype(bool)) & (~final["reason"].astype(str).str.contains("near_duplicate_of_selected"))
    prio = np.where(final["is_selected"].astype(bool), 2, np.where(clean, 1, 0))
    prio = np.where(dec == "approve", 3, prio)
    prio = np.where(dec == "reject", -1, prio)
    final["_prio"] = prio

    final = final.sort_values(["_prio", "score"], ascending=False, kind="mergesort").reset_index(drop=True)
    budget = min(int(ctx.param("budget", 20)), int((final["_prio"] >= 0).sum()))
    final["is_selected"] = False
    final["selection_rank"] = -1
    final.loc[: budget - 1, "is_selected"] = True
    final.loc[: budget - 1, "selection_rank"] = np.arange(1, budget + 1)
    return final.drop(columns="_prio")


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    budget = int(ctx.param("budget", 20))
    sel = final[final["is_selected"]] if "is_selected" in final.columns else final.iloc[0:0]
    n_junk = int(sel["is_junk"].sum()) if "is_junk" in sel.columns else 0
    n_dup = int(ctx.stats.get("n_near_dup_selected", 0))
    n_dark = int(ctx.stats.get("n_dark_selected", 0))
    reviewed = "n_reviewed" in ctx.stats

    if len(final) == 0:
        status, code, reason = "HOLD", "EMPTY_POOL", "Feature pool is empty or unavailable."
    elif len(sel) < budget:
        status, code = "REWORK", "UNDERFILLED_SELECTION"
        reason = f"Only {len(sel)}/{budget} items selected."
    elif n_junk > 0:
        status, code = "REWORK", "JUNK_IN_SELECTION"
        reason = f"{n_junk} junk-flagged item(s) in the selected K."
    elif n_dup > 0:
        status, code = "REWORK", "NEAR_DUPLICATE_IN_SELECTION"
        reason = f"{n_dup} near-duplicate item(s) in the selected K."
    elif not reviewed:
        status, code = "HOLD", "PENDING_HUMAN_REVIEW"
        reason = "Selection is clean but no human review has been applied yet."
    else:
        status, code = "GO", "REVIEWED_OK"
        reason = (f"K={budget} selected, no junk/near-duplicates, review applied "
                  f"(rejected+replaced: {int(ctx.stats.get('n_rejected', 0))}, dark items in K: {n_dark}).")

    return Decision(
        status=status,
        reason_code=code,
        reason=reason,
        owner=ctx.config.get("owner", "T13-ActiveLearningTeam"),
        scope=ctx.track,
    )


# ---------------------------------------------------------------- export
def export_selected(ctx: RunContext, final: pd.DataFrame, spec) -> None:
    """out/<pred_file>: exactly K rows, columns image_id (+ rank)."""
    sel = final[final["is_selected"]].sort_values("selection_rank")
    out = pd.DataFrame({ID: sel[ID].values, "rank": np.arange(1, len(sel) + 1)})
    missing = [c for c in spec.pred_columns if c not in out.columns]
    if missing:
        raise ValueError(f"pred columns {missing} not produced; check TRACKS['t13'].pred_columns")
    out = out[list(spec.pred_columns) + [c for c in out.columns if c not in spec.pred_columns]]
    out.to_csv(ctx.out(spec.pred_file), index=False)
    # full scored pool kept separately for failure-mode analysis
    final.to_csv(ctx.out("scored_all.csv"), index=False)


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)

    data = load(ctx)                      # 01
    scored = process(ctx, data)           # 02
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)             # 03
    final = review(ctx, scored, queue)    # 04

    export_selected(ctx, final, spec)

    write_decision(                       # 05
        decide(ctx, final),
        ctx.out("decision.json"),
        ctx.out("decision_log.csv"),
    )

    if "evidence_path" in queue.columns and queue["evidence_path"].astype(str).str.strip().ne("").any():
        render_contact_sheet(
            queue,
            ctx.out("contact_sheet.html"),
            image_root=ctx.input_dir,
            title="T13 - Active Learning & Rare Case Miner",
        )
