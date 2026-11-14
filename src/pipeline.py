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
from __future__ import annotations

import json
from collections import deque

import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


ACTIONS = ("delete", "retain_legal_hold", "escalate")
DEFAULT_PERMITTED_ACL = ["data-platform"]       # roles our deletion job is allowed to act as

# Columns process() must return (reports/t08_interface.md §1); `score` = review priority (README §4)
PROCESS_COLUMNS = ["request_id", "artefact_id", "action", "key", "subject_id", "type", "reason_code", "reason",
                   "uri", "lineage_depth", "lineage_via", "n_subjects", "held_ancestors", "deadline", "source", "score"]
REVIEW_PRIORITY = {"retain_legal_hold": 2.0, "escalate": 1.0, "delete": 0.0}



# ================================================================ P3 · 01 load
def load(ctx: RunContext) -> dict:
    """Return {"artefacts": {artefact_id: dict}, "requests": [dict], "children": {id: [child ids]}}."""
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    graph = json.loads((ctx.input_dir / "data_graph.json").read_text(encoding="utf-8"))
    requests = json.loads((ctx.input_dir / "requests.json").read_text(encoding="utf-8"))
    arts = {a["artefact_id"]: a for a in graph["artefacts"]}
    if len(arts) != len(graph["artefacts"]):
        raise ValueError("data_graph.json has duplicate artefact_id")
    req_ids = [r["request_id"] for r in requests]
    if len(set(req_ids)) != len(req_ids):
        raise ValueError("requests.json has duplicate request_id")
    ctx.audit.log(actor="pipeline", action="load", item_id="t08_deletion",
                  after={"artefacts": len(arts), "requests": len(requests), "graph_version": graph.get("version")})
    return {"artefacts": arts, "requests": requests, "children": build_children(arts)}


def build_children(arts: dict) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {a: [] for a in arts}
    for aid, a in arts.items():
        for p in a.get("parent_ids") or []:
            if p in children:
                children[p].append(aid)
    for v in children.values():
        v.sort()
    return children


# ================================================================ P3 · 02 process
def trace_lineage(subject: str, arts: dict, children: dict) -> dict[str, dict]:
    """BFS from artefacts tagged `subject` along parent -> child.

    Returns {artefact_id: {"depth", "via", "in_scope"}}; in_scope = the artefact really holds this
    subject's data (subject tag). Descendants that do not (e.g. another person's crop cut from a
    shared frame) are kept only as lineage evidence and are never acted on.
    """
    seeds = sorted(aid for aid, a in arts.items() if subject in (a.get("subject_ids") or []))
    found: dict[str, dict] = {s: {"depth": 0, "via": "subject_tag"} for s in seeds}
    q = deque(seeds)
    while q:
        cur = q.popleft()
        for ch in children.get(cur, []):
            if ch not in found:
                found[ch] = {"depth": found[cur]["depth"] + 1, "via": cur}
                q.append(ch)
    for aid, info in found.items():
        info["in_scope"] = subject in (arts[aid].get("subject_ids") or [])
    return found


def held_ancestors(aid: str, arts: dict, subject: str) -> list[str]:
    """Legal holds on ancestors that hold this subject's own data.
    (Another person's litigation hold must not freeze this subject's unrelated copies.)"""
    out, seen, q = [], set(), deque(arts[aid].get("parent_ids") or [])
    while q:
        p = q.popleft()
        if p in seen or p not in arts:
            continue
        seen.add(p)
        a = arts[p]
        if a.get("legal_hold") and subject in (a.get("subject_ids") or []):
            out.append(f"{p}:{a['legal_hold']}")
        q.extend(a.get("parent_ids") or [])
    return sorted(out)


def classify(art: dict, subject: str, request: dict, permitted_acl: list[str], hold_inherit: bool,
             inherited_holds: list[str]) -> tuple[str, str, str]:
    """Frozen precedence -> (action, reason_code, reason). See reports/t08_interface.md §2."""
    if art.get("legal_hold"):
        return ("retain_legal_hold", "LEGAL_HOLD",
                f"legal hold {art['legal_hold']} (GDPR Art.17(3) / Luật 91/2025 exception): retain, delete when lifted")
    if hold_inherit and inherited_holds:
        return ("retain_legal_hold", "LEGAL_HOLD_INHERITED",
                f"copy/derivative of held data {inherited_holds}: retain, delete when lifted")
    if not request.get("identity_verified", False):
        return "escalate", "IDENTITY_NOT_VERIFIED", "requester identity not verified"
    acl = art.get("acl") or []
    if not set(acl) & set(permitted_acl):
        return "escalate", "NO_DELETE_PERMISSION", f"acl={acl} outside our permission {permitted_acl}: ask the data owner"
    if not art.get("origin_known", True):
        return "escalate", "UNKNOWN_ORIGIN", "origin unknown: cannot prove what it contains or who else is in it"
    others = [s for s in (art.get("subject_ids") or []) if s != subject]
    if others:
        what = "training export (retrain/unlearning needed)" if art.get("type") == "training_export" else "shared artefact"
        return "escalate", "MULTI_SUBJECT", f"{what} also contains {len(others)} other subject(s): redact/split, not delete"
    return "delete", "SUBJECT_DATA", "only this subject's data, no exception"


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """One row per (request, in-scope artefact) with PROCESS_COLUMNS."""
    arts, children = data["artefacts"], data["children"]
    permitted = list(ctx.param("permitted_acl", DEFAULT_PERMITTED_ACL))
    hold_inherit = bool(ctx.param("legal_hold_inherit", True))
    rows = []
    for req in data["requests"]:
        subject = req["subject_id"]
        lineage = trace_lineage(subject, arts, children)
        n_scope = sum(1 for v in lineage.values() if v["in_scope"])
        ctx.audit.log(actor="pipeline", action="request_received", item_id=req["request_id"],
                      after={"subject_id": subject, "deadline": req.get("deadline"), "lineage_nodes": len(lineage),
                             "in_scope": n_scope}, reason="delete request intake + lineage trace")
        if n_scope == 0:
            ctx.audit.log(actor="pipeline", action="request_no_data", item_id=req["request_id"],
                          reason=f"no artefact tagged {subject}")
        for aid, info in sorted(lineage.items()):
            a = arts[aid]
            if not info["in_scope"]:
                ctx.audit.log(actor="pipeline", action="lineage_out_of_scope", item_id=aid,
                              reason=f"{req['request_id']}: derived via {info['via']} but not tagged {subject}")
                continue
            inh = held_ancestors(aid, arts, subject)
            action, code, reason = classify(a, subject, req, permitted, hold_inherit, inh)
            rows.append({
                "request_id": req["request_id"], "artefact_id": aid, "action": action,
                "key": f"{req['request_id']}:{aid}", "subject_id": subject, "type": a.get("type"),
                "reason_code": code, "reason": reason, "uri": a.get("uri"), "lineage_depth": info["depth"],
                "lineage_via": info["via"], "n_subjects": len(a.get("subject_ids") or []),
                "held_ancestors": ";".join(inh), "deadline": req.get("deadline"), "source": "pipeline",
                "score": REVIEW_PRIORITY[action],
            })
    df = pd.DataFrame(rows, columns=PROCESS_COLUMNS)
    if df.empty:
        raise ValueError("no artefacts in scope for any request")
    ctx.stats["n_requests"] = len(data["requests"])
    ctx.stats["action_counts"] = df.action.value_counts().to_dict()
    return df


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Default: top-B by `score`. Adapt id/score/reason columns to your track."""
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first), "
                         "or adapt rank() to your track")
    q = make_review_queue(scored, id_col=scored.columns[0], score_col="score", budget=budget,
                          reason_col="reason" if "reason" in scored.columns else None)
    write_review_queue(q, ctx.out("review_queue.csv"))
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """If a reviewed queue exists (out/review_queue_reviewed.csv), apply it. Otherwise pass through.

    TODO: decide what an `edit` / `reject` means for your track and apply it
    (e.g. via common.review.apply_overrides), logging every change to ctx.audit.
    """
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        # TODO: apply overrides
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    # TODO: replace with your policy (thresholds frozen BEFORE looking at eval results)
    return Decision(status="HOLD", reason_code="POLICY_NOT_IMPLEMENTED", reason="Decision policy not implemented yet",
                    owner=ctx.config.get("owner", "TODO-owner"), scope=ctx.track)


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
