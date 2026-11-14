"""T08 · Retention & Delete Request Simulator — PoC pipeline (group G02).

    python -m src.main --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42

5 steps (lab contract) and owners — column contract in reports/t08_interface.md:
    01 load      data_graph.json + requests.json, verify manifest sha256                  [P3]
    02 process   per request: subject's artefacts + BFS lineage, then the frozen policy:  [P3]
                     legal hold > identity > permission > unknown origin > multi-subject > delete
    03 rank      review queue = every exception (no budget cut: false deletes are final)  [P4]
    04 review    apply out/review_queue_reviewed.csv (approve / edit / escalate / reject) [P4]
    05 decide    dry-run diff, mock delete (tombstones, idempotent), GO/HOLD               [P4]

Everything is mock: "deleting" only writes a tombstone file. No real data is ever deleted.
Policy parameters are frozen in configs/tracks/t08.yaml (see reports/metric_contract.md).
Rules: never read fixtures/*/gt/ (GT guard), no network, seed via ctx.rng.
"""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .common.contact_sheet import render_contact_sheet
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


# ================================================================ P4 · 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Every exception (score > 0) goes to a human: legal hold first, then escalations, earliest deadline first.
    Budget = all exceptions (false deletes are irreversible, so no top-B cut)."""
    cand = scored[scored.score > 0].sort_values(["deadline", "key"], kind="mergesort")
    cand = cand.assign(review_reason=cand.reason_code + ": " + cand.reason)
    q = make_review_queue(cand, id_col="key", score_col="score", budget=len(cand), reason_col="review_reason",
                          action_col="action", slice_col="type", evidence_col="uri")
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(q, ctx.out("contact_sheet.html"), image_col=None,
                         title="T08 · delete-request exceptions — reviewer sign-off")
    ctx.stats["n_review_queue"] = len(q)
    return q


# ================================================================ P4 · 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Apply out/review_queue_reviewed.csv (or params.review_file) if present; audit every change.

    approve -> keep suggested action · edit + override_value ∈ ACTIONS -> new action
    escalate / reject -> escalate (a reject never turns into a delete) · skip -> unchanged, still pending
    """
    final = scored.copy()
    final["reviewer"] = ""
    final["review_note"] = ""
    path = Path(ctx.param("review_file") or ctx.output_dir / "review_queue_reviewed.csv")
    if not path.exists():
        ctx.stats["n_reviewed"] = 0
        return final
    reviewed = load_review_decisions(path)
    unknown = sorted(set(reviewed.item_id) - set(final.key))
    if unknown:
        raise ValueError(f"review rows not in this run's (request, artefact) scope: {unknown[:5]}")
    reviewed = reviewed[reviewed.reviewer_decision != "skip"]
    for r in reviewed.itertuples(index=False):
        m = final.key == r.item_id
        before = final.loc[m, "action"].iloc[0]
        after = reviewed_action(r.reviewer_decision, r.override_value, before, r.item_id)
        final.loc[m, ["action", "reviewer", "review_note", "source"]] = [after, r.reviewer, r.review_note, "human"]
        req_id, aid = r.item_id.split(":", 1)
        ctx.audit.log(actor=r.reviewer, action=f"review:{r.reviewer_decision}", item_id=aid, before=before,
                      after=after, reason=r.review_note, request_id=req_id, reviewed_at=r.reviewed_at)
    ctx.stats["n_reviewed"] = len(reviewed)
    return final


def reviewed_action(decision: str, override_value: str, before: str, item_id: str) -> str:
    """approve keeps the suggestion; reject/escalate send it up (never delete); edit sets override_value."""
    if decision == "approve":
        return before
    if decision in ("reject", "escalate"):
        return "escalate"
    value = str(override_value).strip().lower()
    if value not in ACTIONS:
        raise ValueError(f"override_value {override_value!r} for {item_id} must be one of {ACTIONS}")
    return value


# ================================================================ P4 · 05 decide (+ mock delete)
def execute(ctx: RunContext, final: pd.DataFrame) -> dict:
    """Dry-run diff always. With dry_run=false write tombstones; artefacts already tombstoned are
    skipped, so re-running (or resuming an interrupted job) never deletes twice."""
    dry = bool(ctx.param("dry_run", True))
    store_path = Path(ctx.param("mock_store") or ctx.output_dir / "mock_store_tombstones.json")
    store = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else {}
    diff, new, already = [], 0, 0
    for r in final.itertuples(index=False):
        status = "kept"
        if r.action == "delete":
            if r.artefact_id in store:
                status, already = "already_deleted", already + 1
            elif dry:
                status = "would_delete"
            else:
                store[r.artefact_id] = {"request_id": r.request_id, "uri": r.uri,
                                        "deleted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                status, new = "deleted_mock", new + 1
                store_path.parent.mkdir(parents=True, exist_ok=True)   # persist each delete -> resumable
                store_path.write_text(json.dumps(dict(sorted(store.items())), indent=1), encoding="utf-8")
        diff.append({"request_id": r.request_id, "artefact_id": r.artefact_id, "type": r.type, "action": r.action,
                     "status": status, "reason_code": r.reason_code})
        ctx.audit.log(actor=r.reviewer or "pipeline", action=r.action, item_id=r.artefact_id,
                      reason=f"{r.reason_code}: {r.reason}", request_id=r.request_id, status=status,
                      dry_run=dry, uri=r.uri, lineage_via=r.lineage_via)
    pd.DataFrame(diff).to_csv(ctx.out("dry_run_diff.csv"), index=False)
    ctx.stats.update({"dry_run": dry, "new_deletes": new, "already_deleted": already})
    return {"dry_run": dry, "new": new, "already": already}


def request_summary(ctx: RunContext, final: pd.DataFrame) -> pd.DataFrame:
    """Per-request SLA view: counts per action, unreviewed exceptions, days to deadline."""
    now = datetime.now(timezone.utc)
    rows = []
    for rid, sub in final.groupby("request_id", sort=True):
        dl = sub.deadline.iloc[0]
        pending = int(((sub.action != "delete") & (sub.reviewer == "")).sum())
        rows.append({
            "request_id": rid, "subject_id": sub.subject_id.iloc[0], "n_artefacts": len(sub),
            **{f"n_{a}": int((sub.action == a).sum()) for a in ACTIONS},
            "pending_review": pending, "deadline": dl,
            "days_to_deadline": round((datetime.fromisoformat(dl) - now).total_seconds() / 86400, 1) if dl else None,
            "status": "BLOCKED_REVIEW" if pending else ("PARTIAL_RETAINED" if (sub.action != "delete").any() else "COMPLETE"),
        })
    df = pd.DataFrame(rows)
    df.to_csv(ctx.out("request_summary.csv"), index=False)
    return df


def decide(ctx: RunContext, final: pd.DataFrame, summary: pd.DataFrame, exec_info: dict) -> Decision:
    """HOLD while exceptions are unreviewed, GO when all are signed off; reason_code + owner."""
    owner = ctx.config.get("owner", "TODO-owner")
    pending = int(summary.pending_review.sum())
    metrics = {"n_rows": len(final), **{f"n_{a}": int((final.action == a).sum()) for a in ACTIONS},
               "pending_review": pending, **exec_info}
    ev = [str(ctx.out(f)) for f in ("actions.csv", "dry_run_diff.csv", "review_queue.csv", "request_summary.csv",
                                    "audit_log.jsonl")]
    scope = "t08:" + ",".join(summary.request_id)
    if pending:
        return Decision("HOLD", "EXCEPTIONS_PENDING_REVIEW",
                        f"{pending} exception(s) need a human sign-off before the deletion plan can be closed",
                        owner, scope=scope, evidence=ev, metrics=metrics)
    return Decision("GO", "DELETION_PLAN_APPROVED",
                    "all exceptions signed off; execute delete plan, retained items re-checked when holds lift",
                    owner, scope=scope, evidence=ev, metrics=metrics)


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    if spec.track != "t08":
        raise NotImplementedError(f"group G02 pipeline implements t08 only (got {spec.track})")
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final = final.sort_values(["request_id", "artefact_id"], kind="mergesort").reset_index(drop=True)
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    exec_info = execute(ctx, final)
    summary = request_summary(ctx, final)
    write_decision(decide(ctx, final, summary, exec_info), ctx.out("decision.json"), ctx.out("decision_log.csv"))
