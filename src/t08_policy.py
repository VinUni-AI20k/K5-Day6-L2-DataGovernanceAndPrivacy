"""T08 deletion policy: lineage traversal + rule precedence. Pure functions, no I/O.

Scope of a request = every artefact tagged with the requester, plus everything derived from
those artefacts. Each in-scope (request, artefact) pair gets exactly one action; the first
matching rule wins. The rule order is frozen in reports/metric_contract.md.

The policy never auto-deletes an artefact that carries an exception: only a human reviewer
can turn an `escalate` into a `delete` (see review() in src/pipeline.py).
"""
from __future__ import annotations

from collections import defaultdict

ACTIONS = ("delete", "retain_legal_hold", "escalate")

# reason_code -> (review priority, higher = review first; role that handles the exception)
REASONS: dict[str, tuple[float, str]] = {
    "MULTI_SUBJECT_ALL_REQUESTED": (0.95, "dpo"),   # a human can unblock the deletion right now
    "CONFLICTING_ACTIONS": (0.92, "dpo"),
    "NO_PERMISSION": (0.90, "vendor-manager"),      # copy outside our control: longest lead time
    "UNKNOWN_ORIGIN": (0.85, "data-steward"),
    "BROKEN_LINEAGE": (0.85, "data-steward"),
    "IDENTITY_NOT_VERIFIED": (0.80, "dpo"),
    "MULTI_SUBJECT": (0.70, "dpo"),
    "PARTIAL_LEGAL_HOLD": (0.60, "legal"),
    "LEGAL_HOLD_INHERITED": (0.50, "legal"),        # rests on assumption A1, needs legal confirmation
    "LEGAL_HOLD": (0.30, "legal"),
    "DERIVED_OTHER_SUBJECT": (0.20, "dpo"),
    "REVIEW_OVERRIDE": (0.0, ""),
    "OK_DELETE": (0.0, ""),
}

# Exceptions about the *requester* (not about the artefact itself). They never argue for keeping
# the artefact, so they must not block another request's legitimate delete of the same artefact.
NON_BLOCKING = frozenset({"IDENTITY_NOT_VERIFIED", "DERIVED_OTHER_SUBJECT"})

PLAN_COLUMNS = ["request_id", "artefact_id", "action", "reason_code", "reason", "type",
                "subject_ids", "uri", "owner_role", "deadline", "score"]


def build_index(artefacts: list[dict]) -> tuple[dict, dict]:
    """Return (by_id, children). Duplicate ids are a data error: fail loudly, never guess."""
    by_id: dict[str, dict] = {}
    for a in artefacts:
        aid = a.get("artefact_id")
        if not aid:
            raise ValueError(f"artefact without artefact_id: {a}")
        if aid in by_id:
            raise ValueError(f"duplicate artefact_id {aid!r} in data graph")
        by_id[aid] = a
    children: dict[str, list[str]] = defaultdict(list)
    for a in artefacts:
        for p in a.get("parent_ids") or []:
            children[p].append(a["artefact_id"])
    return by_id, children


def descendants(root_ids, children: dict) -> set[str]:
    """Everything derived from `root_ids` (any depth). Safe on cycles."""
    seen: set[str] = set()
    stack = list(root_ids)
    while stack:
        for c in children.get(stack.pop(), []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


def hold_status(aid: str, by_id: dict, memo: dict) -> tuple[str | None, list[str]]:
    """(state, hold ids) where state is
        'direct'  - the artefact itself carries a legal hold
        'full'    - every parent is held (derived only from held data)
        'partial' - only some of its sources are held (e.g. a multi-source export)
        None      - no hold anywhere in its ancestry
    """
    if aid in memo:
        return memo[aid]
    memo[aid] = (None, [])                      # cycle guard
    a = by_id[aid]
    if a.get("legal_hold"):
        memo[aid] = ("direct", [str(a["legal_hold"])])
        return memo[aid]
    states = [hold_status(p, by_id, memo) for p in (a.get("parent_ids") or []) if p in by_id]
    holds = sorted({h for _, hs in states for h in hs})
    if states and all(s in ("direct", "full") for s, _ in states):
        memo[aid] = ("full", holds)
    elif any(s for s, _ in states):
        memo[aid] = ("partial", holds)
    return memo[aid]


def decide_action(a: dict, request: dict, by_id: dict, hold=(None, ()), verified_subjects=frozenset(),
                  our_acl: str = "data-platform") -> tuple[str, str, str]:
    """(action, reason_code, reason) for one (request, artefact) pair. First matching rule wins."""
    sid = request["subject_id"]
    subjects = list(a.get("subject_ids") or [])
    state, holds = hold
    if state == "direct":
        return "retain_legal_hold", "LEGAL_HOLD", f"legal hold {holds[0]} on this artefact; delete when the hold is released"
    if state == "full":
        return "retain_legal_hold", "LEGAL_HOLD_INHERITED", f"derived only from data under legal hold {'+'.join(holds)}"
    if state == "partial":
        return "escalate", "PARTIAL_LEGAL_HOLD", (f"some sources are under legal hold {'+'.join(holds)}; "
                                                  f"{len(subjects)} subject(s) in this artefact")
    if request.get("identity_verified") is not True:
        return "escalate", "IDENTITY_NOT_VERIFIED", "requester identity is not verified"
    acl = list(a.get("acl") or [])
    if our_acl not in acl:
        return "escalate", "NO_PERMISSION", f"acl={'+'.join(map(str, acl)) or 'none'} does not include {our_acl}"
    if a.get("origin_known") is not True:
        return "escalate", "UNKNOWN_ORIGIN", "origin_known is not true: provenance must be traced first"
    missing = [p for p in (a.get("parent_ids") or []) if p not in by_id]
    if missing:
        return "escalate", "BROKEN_LINEAGE", f"parent(s) not in graph: {'+'.join(missing)}"
    if sid not in subjects:
        return "escalate", "DERIVED_OTHER_SUBJECT", (f"derived from an artefact of {sid} but tagged "
                                                     f"{'+'.join(subjects) or 'nobody'}: check the subject tag")
    if len(subjects) > 1:
        others = [s for s in subjects if s != sid]
        waiting = [s for s in others if s not in verified_subjects]
        if not waiting:
            return "escalate", "MULTI_SUBJECT_ALL_REQUESTED", (f"shared with {'+'.join(others)}; every subject has a "
                                                               "verified delete request: confirm, then delete")
        return "escalate", "MULTI_SUBJECT", (f"shared with {'+'.join(others)}; {len(waiting)} of them did not "
                                             "request deletion: redact the requester instead of deleting")
    return "delete", "OK_DELETE", "single-subject artefact of the requester, no exception"


def normalize_requests(requests: list[dict]) -> list[dict]:
    """Sorted by request_id; exact duplicates collapse, contradictory duplicates fail loudly."""
    seen: dict[str, dict] = {}
    for rq in requests:
        rid, sid = rq.get("request_id"), rq.get("subject_id")
        if not rid or not sid:
            raise ValueError(f"request without request_id/subject_id: {rq}")
        if rid in seen:
            if seen[rid]["subject_id"] != sid:
                raise ValueError(f"request_id {rid!r} appears twice with different subjects")
            continue
        seen[rid] = rq
    return [seen[k] for k in sorted(seen)]


def build_plan(artefacts: list[dict], requests: list[dict], our_acl: str = "data-platform",
               inherit_hold: bool = True, include_derived_other_subject: bool = True) -> list[dict]:
    """Dry-run plan: one row per in-scope (request, artefact) pair, deterministic order."""
    by_id, children = build_index(artefacts)
    requests = normalize_requests(requests)
    verified = frozenset(r["subject_id"] for r in requests if r.get("identity_verified") is True)
    memo: dict = {}
    rows = []
    for rq in requests:
        sid = rq["subject_id"]
        own = {aid for aid, a in by_id.items() if sid in (a.get("subject_ids") or [])}
        scope = own | descendants(own, children) if include_derived_other_subject else own
        for aid in sorted(scope):
            a = by_id[aid]
            hold = hold_status(aid, by_id, memo)
            if not inherit_hold and hold[0] != "direct":
                hold = (None, [])
            action, code, why = decide_action(a, rq, by_id, hold, verified, our_acl)
            score, role = REASONS[code]
            rows.append({
                "request_id": rq["request_id"], "artefact_id": aid, "action": action, "reason_code": code,
                "reason": why, "type": a.get("type", ""), "subject_ids": "+".join(a.get("subject_ids") or []),
                "uri": a.get("uri", ""), "owner_role": role, "deadline": rq.get("deadline", ""), "score": score,
            })
    return rows


def blocked_deletes(rows: list[dict]) -> list[tuple[str, str, list[str]]]:
    """Delete rows whose artefact still has an open artefact-level exception under another request.

    Deleting is physical and irreversible, so one request's `delete` must not destroy an artefact
    that another request's row says to keep or escalate (e.g. a reviewer approved only one side of
    a shared frame). Returns (request_id, artefact_id, blocking request ids).
    """
    blockers: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r["action"] != "delete" and r["reason_code"] not in NON_BLOCKING:
            blockers[r["artefact_id"]].append(r["request_id"])
    return [(r["request_id"], r["artefact_id"], sorted(blockers[r["artefact_id"]]))
            for r in rows if r["action"] == "delete" and r["artefact_id"] in blockers]
