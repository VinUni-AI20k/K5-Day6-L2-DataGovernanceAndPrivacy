"""PoC Pipeline for T13: Active Learning & Rare Case Miner.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   density-weighted novelty scoring + junk filter + diversity selection
    03 rank      prioritise top K=20 candidate queue + offline HTML contact sheet
    04 review    human-in-the-loop: load reviewed queue, apply overrides, audit log
    05 decide    GO / HOLD / REWORK decision with reason_code + owner, write outputs

Required output: out/selected.csv (image_id, rank)
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    """Load inputs with provenance verification."""
    if ctx.track != "t13":
        spec = get_track(ctx.track)
        raise NotImplementedError(
            f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
            f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
        )

    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")

    images_path = ctx.input_dir / "images.csv"
    features_path = ctx.input_dir / "pool_features.csv"
    if not images_path.exists():
        raise FileNotFoundError(f"Missing {images_path}")
    if not features_path.exists():
        raise FileNotFoundError(f"Missing {features_path}")

    images = pd.read_csv(images_path)
    features = pd.read_csv(features_path)

    # Merge metadata with features
    df = images.merge(features, on="image_id", how="inner")
    return {"df": df, "manifest": pd.read_csv(manifest) if manifest.exists() else None}


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Active learning selection:

    1. Junk filtering (abnormal edge density, collapsed variance/contrast).
    2. Density-weighted novelty: kNN distance in embedding space (outlier score).
    3. Diversity & redundancy suppression: Greedy Maximal Marginal Relevance (MMR)
       to avoid selecting near-duplicate / burst frames of the same scene.
    """
    df = data["df"].copy()
    k_target = int(ctx.param("k", 20))

    # 1. Feature preparation
    emb_cols = [c for c in df.columns if c.startswith("emb_")]
    if not emb_cols:
        raise ValueError("pool_features.csv must contain embedding columns emb_00..")

    emb_matrix = df[emb_cols].to_numpy(dtype=np.float32)

    # L2 normalize embeddings for cosine distance
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    emb_normed = emb_matrix / norms

    # 2. Junk heuristic filter
    # Junk frames: degenerate edge density, near-zero brightness std (collapsed contrast)
    is_junk = (
        (df["edge_density"] < 0.004)
        | (df["edge_density"] > 0.09)
        | (df["brightness_std"] < 12.0)
    )

    # 3. Density-based Novelty estimation (kNN distance)
    # Common scenes (day driving, standard night) form dense clusters.
    # Rare cases are isolated or in sparse regions.
    n_neighbors = min(10, len(df) - 1)
    nn = NearestNeighbors(n_neighbors=n_neighbors, metric="cosine")
    nn.fit(emb_normed)
    distances, _ = nn.kneighbors(emb_normed)

    # Mean distance to k nearest neighbors (higher = more novel / lower density)
    novelty_score = distances[:, 1:].mean(axis=1)

    # Penalize detected junk
    novelty_score[is_junk] = -1.0

    df["novelty_score"] = novelty_score
    df["is_suspect_junk"] = is_junk

    # 4. Diversity-aware Greedy Selection (MMR)
    # Pick top K items balancing novelty vs distance to already selected items
    selected_indices: list[int] = []
    remaining_indices = list(np.where(~is_junk)[0])

    # If not enough non-junk, allow all
    if len(remaining_indices) < k_target:
        remaining_indices = list(range(len(df)))

    # Sort candidates by initial novelty
    remaining_indices.sort(key=lambda idx: df.loc[idx, "novelty_score"], reverse=True)

    # Pick the highest novelty item first
    first_pick = remaining_indices.pop(0)
    selected_indices.append(first_pick)

    # Redundancy penalty coefficient lambda
    redundancy_penalty_weight = float(ctx.param("redundancy_penalty", 0.65))

    while len(selected_indices) < k_target and remaining_indices:
        selected_embs = emb_normed[selected_indices]
        candidate_embs = emb_normed[remaining_indices]

        # Cosine similarity between remaining candidates and already selected items
        # candidate_embs: (N_rem, D), selected_embs: (N_sel, D)
        sim_matrix = np.dot(candidate_embs, selected_embs.T)
        max_sim_to_selected = sim_matrix.max(axis=1)

        # Candidates' base novelty
        cand_novelty = np.array([df.loc[idx, "novelty_score"] for idx in remaining_indices])

        # MMR score: Novelty - lambda * max_similarity_to_selected
        mmr_scores = cand_novelty - (redundancy_penalty_weight * max_sim_to_selected)

        best_cand_pos = int(np.argmax(mmr_scores))
        chosen_idx = remaining_indices.pop(best_cand_pos)
        selected_indices.append(chosen_idx)

    # Assign rank and selection flags
    df["score"] = df["novelty_score"]
    df["is_selected"] = False
    df.loc[selected_indices, "is_selected"] = True

    # Order dataframe so selected items are at top with their ranks
    selected_df = df.loc[selected_indices].copy()
    selected_df["rank"] = range(1, len(selected_df) + 1)
    selected_df["reason"] = "novelty_diversity_mmr"
    selected_df["suggested_action"] = "LABEL"

    unselected_df = df.loc[~df.index.isin(selected_indices)].copy()
    unselected_df["rank"] = range(len(selected_df) + 1, len(df) + 1)
    unselected_df["reason"] = "pool_unselected"
    unselected_df["suggested_action"] = "SKIP"

    result = pd.concat([selected_df, unselected_df], ignore_index=True)
    return result


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Form the review queue for the top K=20 selected candidates and render contact sheet."""
    k_target = int(ctx.param("k", 20))
    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=k_target,
        reason_col="reason",
        action_col="suggested_action",
        evidence_col="path" if "path" in scored.columns else None,
    )
    write_review_queue(q, ctx.out("review_queue.csv"))

    # Render offline contact sheet HTML for Human-in-the-loop review
    if "path" in scored.columns:
        render_contact_sheet(
            q,
            ctx.out("contact_sheet.html"),
            image_root=ctx.input_dir,
            title=f"T13 Active Learning Queue (Top-{k_target})",
        )
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Human-in-the-loop: if out/review_queue_reviewed.csv exists, apply overrides."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)

        for _, row in reviewed.iterrows():
            item_id = row["item_id"]
            decision = row["reviewer_decision"]
            reviewer = row["reviewer"]
            note = row["review_note"]

            ctx.audit.log(
                actor=reviewer,
                action=f"review_{decision}",
                item_id=item_id,
                before={"suggested": "LABEL"},
                after={"decision": decision, "note": note},
            )

            # If rejected by reviewer, mark not selected and demote rank
            if decision == "reject":
                scored.loc[scored["image_id"] == item_id, "is_selected"] = False
                scored.loc[scored["image_id"] == item_id, "score"] = -999.0

        # Re-sort so selected items remain at top
        scored = scored.sort_values(
            by=["is_selected", "score"], ascending=[False, False], kind="mergesort"
        ).reset_index(drop=True)
        scored["rank"] = range(1, len(scored) + 1)

    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Governance decision policy for release of mined active learning batch."""
    k_target = int(ctx.param("k", 20))
    selected = final[final["is_selected"]].head(k_target)

    owner = ctx.config.get("owner", "Nguyen Hoang Dieu")
    n_selected = len(selected)

    if n_selected < k_target:
        return Decision(
            status="HOLD",
            reason_code="INSUFFICIENT_SAMPLES",
            reason=f"Selected only {n_selected}/{k_target} samples",
            owner=owner,
            scope=ctx.track,
        )

    # Check for potential junk risk in selected set
    junk_risk = int(selected["is_suspect_junk"].sum()) if "is_suspect_junk" in selected.columns else 0
    if junk_risk > 3:
        return Decision(
            status="REWORK",
            reason_code="HIGH_JUNK_RISK",
            reason=f"{junk_risk} selected samples flagged with junk risk",
            owner=owner,
            scope=ctx.track,
        )

    return Decision(
        status="GO",
        reason_code="RARE_CASES_MINED",
        reason=f"Successfully mined {n_selected} diverse, high-novelty candidate samples for annotation",
        owner=owner,
        scope=ctx.track,
        evidence=[str(ctx.out("selected.csv")), str(ctx.out("review_queue.csv"))],
    )


def run(ctx: RunContext) -> None:
    """Execute complete 5-step contract."""
    spec = get_track(ctx.track)
    k_target = int(ctx.param("k", 20))

    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)

    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)

    # Extract top-K selected images for output contract: out/selected.csv
    selected_out = (
        final[final["is_selected"]].head(k_target)[["image_id", "rank"]].copy()
    )
    if len(selected_out) < k_target:
        # Fallback to top scored if needed
        selected_out = final.head(k_target)[["image_id", "rank"]].copy()

    selected_out.to_csv(ctx.out(spec.pred_file), index=False)

    decision = decide(ctx, final)
    write_decision(decision, ctx.out("decision.json"), ctx.out("decision_log.csv"))
