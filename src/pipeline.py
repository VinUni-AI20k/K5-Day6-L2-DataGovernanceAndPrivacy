"""PoC pipeline for T08 - Retention & Delete Request Simulator (everything here is MOCK).

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      receive the delete requests + provenance check (manifest.csv sha256)
    02 process   trace lineage, apply the frozen rule order -> dry-run plan (nothing changes yet)
    03 rank      exception queue for the human reviewer (budget B)
    04 review    reviewer decisions -> overrides + audit log; conflicting approvals are blocked
    05 decide    mock deletion (tombstones) + evidence, then GO / HOLD / REWORK with reason_code + owner

Output: out/actions.csv (request_id, artefact_id, action) + out/audit_log.jsonl next to it.
Policy rules live in src/t08_policy.py; the decision criteria are frozen in reports/metric_contract.md.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata

import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.io import sha256_file, write_json
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track
from .t08_mock_store import MockStore
from .t08_policy import ACTIONS, PLAN_COLUMNS, blocked_deletes, build_plan, normalize_requests


def _ascii(value) -> str:
    """Audit entries are kept ASCII-only.

    src/metrics/tracks.py::eval_t08 reads audit_log.jsonl with the platform default encoding, which
    is cp1252 on Windows: a Vietnamese reviewer note stored as UTF-8 can crash the official scorer.
    """
    s = unicodedata.normalize("NFKD", str(value)).replace("đ", "d").replace("Đ", "D")
    return s.encode("ascii", "ignore").decode("ascii")


def _log(ctx: RunContext, actor: str, action: str, item_id: str, **kw) -> None:
    clean = {k: (_ascii(v) if isinstance(v, str) else v) for k, v in kw.items()}
    ctx.audit.log(actor=_ascii(actor), action=action, item_id=_ascii(item_id), **clean)


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    if ctx.track != "t08":
        raise NotImplementedError(f"src/pipeline.py implements T08 only (got {ctx.track}); see docs/tracks/T08.md")
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    graph_path, req_path = ctx.input_dir / "data_graph.json", ctx.input_dir / "requests.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    reqs = json.loads(req_path.read_text(encoding="utf-8"))
    data = {
        "manifest": pd.read_csv(manifest) if manifest.exists() else None,
        "artefacts": graph["artefacts"] if isinstance(graph, dict) else graph,
        "requests": normalize_requests(reqs["requests"] if isinstance(reqs, dict) else reqs),
        # ties review decisions and tombstones to this exact input
        "fingerprint": sha256_file(graph_path)[:16] + "-" + sha256_file(req_path)[:16],
    }
    ctx.stats.update(n_requests=len(data["requests"]), n_artefacts=len(data["artefacts"]))
    _log(ctx, "pipeline", "requests_received", "batch", after={
        "n_requests": len(data["requests"]), "n_artefacts": len(data["artefacts"]), "input_fingerprint": data["fingerprint"]})
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Lineage + policy = the dry-run plan. No state is touched in this step."""
    rows = build_plan(
        data["artefacts"], data["requests"],
        our_acl=str(ctx.param("our_acl", "data-platform")),
        inherit_hold=bool(ctx.param("inherit_hold", True)),
        include_derived_other_subject=bool(ctx.param("include_derived_other_subject", True)),
    )
    df = pd.DataFrame(rows, columns=PLAN_COLUMNS)
    df["item_id"] = df["request_id"] + "|" + df["artefact_id"]
    df["machine_action"] = df["action"]
    df["reviewer"] = ""
    df["reviewer_decision"] = ""
    df.to_csv(ctx.out("dry_run_plan.csv"), index=False)
    for r in df.itertuples(index=False):
        # item_id = artefact_id: this is the key the evaluator uses for audit trace completeness
        _log(ctx, "t08-policy", f"plan:{r.action}", r.artefact_id, after=r.action, reason=r.reason_code,
             request_id=r.request_id, detail=r.reason)
    return df


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Every exception (anything the machine did not mark `delete`) goes to a human.

    Priority = reason class (see REASONS in t08_policy), then earliest deadline.
    """
    budget = int(ctx.param("budget", 100))
    exc = scored[scored["machine_action"] != "delete"].sort_values(["deadline", "request_id", "artefact_id"], kind="mergesort")
    exc = exc.assign(why=exc["reason_code"] + ": " + exc["reason"] + " [" + exc["type"] + "; subjects="
                     + exc["subject_ids"] + "; route=" + exc["owner_role"] + "; deadline=" + exc["deadline"] + "]")
    q = make_review_queue(exc, id_col="item_id", score_col="score", budget=budget, reason_col="why",
                          action_col="action", slice_col="reason_code", evidence_col="uri")
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(q, ctx.out("contact_sheet.html"), image_col=None, title="T08 exception queue (MOCK data)",
                         fields=("rank", "item_id", "suggested_action", "slice", "reason", "evidence_path"))
    ctx.stats.update(n_exceptions=len(exc), n_queued=len(q), review_budget=budget)
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Apply out/review_queue_reviewed.csv if it exists.

    `edit` / `reject` with an `override_value` in {delete, retain_legal_hold, escalate} replaces the
    machine action; `approve` / `escalate` keep it and record who confirmed. Guards:
      - a decision made against a different machine action (stale file) is skipped and logged;
      - an unknown override value, or deleting an artefact that itself carries a legal hold, stops the run;
      - a delete that another request's row still blocks is downgraded to escalate.
    """
    final = scored.copy()
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        rv = load_review_decisions(reviewed_path)
        rv["item_id"] = rv["item_id"].str.strip()
        rv["override_value"] = rv["override_value"].str.strip().str.lower()
        for c in ("reviewer", "review_note"):
            rv[c] = rv[c].map(_ascii).str.strip()
        current = final.set_index("item_id")
        valid, n_stale = [], 0
        for r in rv.itertuples(index=False):
            machine = current.at[r.item_id, "machine_action"] if r.item_id in current.index else None
            if machine is None or (r.suggested_action.strip() and r.suggested_action.strip() != machine):
                n_stale += 1
                _log(ctx, r.reviewer, "review_stale_skipped", r.item_id.split("|")[-1], before=r.suggested_action, after=machine,
                     reason="decision was made against a different plan", request_id=r.item_id.split("|")[0])
                continue
            if r.reviewer_decision in {"edit", "reject"} and r.override_value:
                if r.override_value not in ACTIONS:
                    raise ValueError(f"{reviewed_path}: override_value {r.override_value!r} for {r.item_id} must be one of {ACTIONS}")
                if r.override_value == "delete" and current.at[r.item_id, "reason_code"] == "LEGAL_HOLD":
                    raise ValueError(f"{reviewed_path}: {r.item_id} carries a legal hold and cannot be overridden to delete; "
                                     "release the hold in the source system first")
            valid.append(r)
        valid = pd.DataFrame(valid, columns=rv.columns)
        final = apply_overrides(final, valid, id_col="item_id", value_col="action")   # audit written below, keyed by artefact
        n_over = 0
        for r in valid.itertuples(index=False):
            mask = final["item_id"] == r.item_id
            before, after = current.at[r.item_id, "machine_action"], final.loc[mask, "action"].iloc[0]
            final.loc[mask, ["reviewer", "reviewer_decision"]] = [r.reviewer, r.reviewer_decision]
            if after != before:
                n_over += 1
                final.loc[mask, ["reason_code", "reason"]] = ["REVIEW_OVERRIDE", r.review_note or "reviewer override"]
            _log(ctx, r.reviewer, ("override:" if after != before else "review:") + r.reviewer_decision,
                 current.at[r.item_id, "artefact_id"], before=before, after=after, reason=r.review_note,
                 request_id=current.at[r.item_id, "request_id"])
        ctx.stats.update(n_reviewed=len(valid), n_overrides=n_over, n_stale_reviews=n_stale)
    for rid, aid, blockers in blocked_deletes(final.to_dict("records")):
        mask = (final["request_id"] == rid) & (final["artefact_id"] == aid)
        why = f"delete blocked: {aid} still has an open exception under {'+'.join(blockers)}"
        final.loc[mask, ["action", "reason_code", "reason"]] = ["escalate", "CONFLICTING_ACTIONS", why]
        _log(ctx, "t08-policy", "delete_blocked_conflict", aid, before="delete", after="escalate", reason=why, request_id=rid)
    return final


# ---------------------------------------------------------------- 05 decide (execute + decision)
def execute(ctx: RunContext, data: dict, final: pd.DataFrame) -> dict:
    """Mock deletion + evidence. With params.dry_run=true nothing is tombstoned."""
    dry = bool(ctx.param("dry_run", True))
    deletes = final[final["action"] == "delete"]
    lines = sorted(final["request_id"] + "|" + final["artefact_id"] + "|" + final["action"])
    ev = {
        "mode": "dry_run" if dry else "mock_delete",
        "note": "MOCK - no real data is deleted in this lab",
        "input_fingerprint": data["fingerprint"],
        "plan_sha256": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
        "n_pairs": int(len(final)),
        "n_delete_pairs": int(len(deletes)),
        "n_delete_artefacts": int(deletes["artefact_id"].nunique()),
        "newly_deleted": 0, "newly_linked": 0, "noop": 0,
        "residual_must_delete": [], "deleted_but_no_longer_planned": [],
    }
    deleted: set[str] = set()
    if not dry:
        store = MockStore(ctx.out("mock_store_state.json"), data["fingerprint"])
        for rid, grp in deletes.groupby("request_id", sort=True):
            for aid in grp["artefact_id"]:
                outcome = store.delete(aid, rid)
                ev["newly_deleted" if outcome == "new" else "newly_linked" if outcome == "linked" else "noop"] += 1
                if outcome != "noop":
                    _log(ctx, "t08-executor", "mock_delete" if outcome == "new" else "mock_delete_already_gone", aid,
                         before="present" if outcome == "new" else "tombstoned", after="tombstoned", request_id=rid)
            store.save()            # checkpoint per request: an interrupted job resumes without redoing work
        store.save()
        deleted = store.deleted
        planned = set(deletes["artefact_id"])
        ev["residual_must_delete"] = sorted(planned - deleted)            # must be empty after execution
        ev["deleted_but_no_longer_planned"] = sorted(deleted - planned)   # irreversible mistake if not empty
    ev["tombstones_total"] = len(deleted)
    ev["changed_state"] = bool(ev["newly_deleted"] or ev["newly_linked"])
    write_json(ctx.out("deletion_evidence.json"), ev)
    _summarize(ctx, data, final, deleted).to_csv(ctx.out("request_summary.csv"), index=False)
    ctx.stats["evidence"] = ev
    ctx.stats.update(n_delete=int((final["action"] == "delete").sum()),
                     n_retain_legal_hold=int((final["action"] == "retain_legal_hold").sum()),
                     n_escalate=int((final["action"] == "escalate").sum()))
    return ev


def _summarize(ctx: RunContext, data: dict, final: pd.DataFrame, deleted: set[str]) -> pd.DataFrame:
    """Per-request status board (SLA view). `as_of` is a param so the output never depends on the clock."""
    reqs = data["requests"]
    as_of = ctx.param("as_of") or max((str(r.get("received_at", "")) for r in reqs), default="")
    rows = []
    for rq in reqs:
        sub = final[final["request_id"] == rq["request_id"]]
        own = sub[sub["reason_code"] != "DERIVED_OTHER_SUBJECT"]
        n = {a: int((sub["action"] == a).sum()) for a in ACTIONS}
        emb_left = own[(own["type"] == "embedding") & (own["action"] != "delete")]
        try:
            days = (pd.Timestamp(rq["deadline"]) - pd.Timestamp(as_of)).days
        except (KeyError, ValueError, TypeError):
            days = None
        status = "NO_DATA_FOUND" if sub.empty else "COMPLETED" if n["delete"] == len(sub) else "PARTIAL_EXCEPTIONS_OPEN"
        rows.append({
            "request_id": rq["request_id"], "subject_id": rq["subject_id"], "received_at": rq.get("received_at", ""),
            "deadline": rq.get("deadline", ""), "days_to_deadline": days,
            "sla": "" if days is None else "OVERDUE" if days < 0 else "DUE_SOON" if days <= 7 else "ON_TRACK",
            "n_pairs": len(sub), "n_delete": n["delete"], "n_retain_legal_hold": n["retain_legal_hold"],
            "n_escalate": n["escalate"], "n_tombstoned": int(sub["artefact_id"].isin(deleted).sum()),
            "n_embeddings_not_deleted": len(emb_left), "status": status,
        })
    return pd.DataFrame(rows)


def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Criteria frozen in reports/metric_contract.md (REWORK > HOLD > GO)."""
    ev = ctx.stats.get("evidence") or {}
    logged = {e.get("item_id") for e in ctx.audit.read()}
    problems = []
    if final.duplicated(["request_id", "artefact_id"]).any():
        problems.append("duplicate (request_id, artefact_id) rows")
    if not final["action"].isin(ACTIONS).all():
        problems.append("action outside the contract")
    no_audit = sorted(set(final["artefact_id"]) - logged)
    if no_audit:
        problems.append(f"{len(no_audit)} artefacts without an audit entry")
    if ev.get("residual_must_delete"):
        problems.append(f"{len(ev['residual_must_delete'])} planned deletes still present after execution")
    if ev.get("deleted_but_no_longer_planned"):
        problems.append(f"{len(ev['deleted_but_no_longer_planned'])} tombstoned artefacts are no longer planned as delete")
    exc = final[final["machine_action"] != "delete"]
    pending = exc[exc["reviewer_decision"].isin(["", "skip"])]
    conflicts = int((final["reason_code"] == "CONFLICTING_ACTIONS").sum())
    budget = int(ctx.param("budget", 100))
    counts = {a: int((final["action"] == a).sum()) for a in ACTIONS}
    tail = f"{counts['delete']} delete, {counts['retain_legal_hold']} retain_legal_hold, {counts['escalate']} escalate"
    if problems:
        status, code, why = "REWORK", "INTEGRITY_CHECK_FAILED", "; ".join(problems)
    elif len(exc) > budget:
        status, code, why = "HOLD", "REVIEW_BUDGET_EXCEEDED", f"{len(exc)} exceptions exceed review budget B={budget}"
    elif len(pending):
        status, code, why = "HOLD", "EXCEPTIONS_PENDING_REVIEW", f"{len(pending)} of {len(exc)} exception pairs have no reviewer decision ({tail})"
    elif conflicts:
        status, code, why = "HOLD", "CONFLICTING_ACTIONS", f"{conflicts} approved deletes are blocked by another request's open exception"
    elif ev.get("mode") != "mock_delete":
        status, code, why = "HOLD", "DRY_RUN_ONLY", f"plan reviewed but not executed (dry_run=true): {tail}"
    else:
        status, code, why = "GO", "PLAN_EXECUTED_EXCEPTIONS_TRACKED", (
            f"all {len(exc)} exception pairs reviewed; {ev.get('tombstones_total')} artefacts mock-deleted, residual 0; "
            f"open items tracked with an owner ({tail})")
    return Decision(
        status=status, reason_code=code, reason=why, owner=ctx.config.get("owner", "TODO-owner"), scope=ctx.track,
        evidence=[str(ctx.out(f)) for f in ("actions.csv", "audit_log.jsonl", "deletion_evidence.json",
                                             "request_summary.csv", "review_queue.csv")],
        metrics={"n_pairs": int(len(final)), **{f"n_{a}": c for a, c in counts.items()}, "n_exceptions": int(len(exc)),
                 "n_pending_review": int(len(pending)), "n_conflicts": conflicts, "mode": ev.get("mode"),
                 "newly_deleted": ev.get("newly_deleted"), "tombstones_total": ev.get("tombstones_total"),
                 "plan_sha256": ev.get("plan_sha256")},
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)                           # 01 receive requests
    scored = process(ctx, data)                # 02 lineage + dry-run plan
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)                  # 03 exception queue
    final = review(ctx, scored, queue)         # 04 human approval
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    execute(ctx, data, final)                  # 05 mock delete + evidence
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
