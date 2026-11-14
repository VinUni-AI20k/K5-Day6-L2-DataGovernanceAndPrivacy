"""Human-in-the-loop helpers: review queue, overrides, audit log.

Workflow used by every track:
  1. pipeline scores items  -> make_review_queue(...)  -> reports/review_queue.csv
  2. a human fills `reviewer`, `reviewer_decision`, `override_value`, `review_note`
     (in a spreadsheet, or via the HTML contact sheet "Export CSV" button)
  3. load_review_decisions(...) + apply_overrides(...) -> final outputs
  4. every change is appended to an AuditLog (JSONL) with who/when/why
"""
from __future__ import annotations

import getpass
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

REVIEW_COLUMNS = [
    "rank",
    "item_id",
    "score",
    "reason",
    "suggested_action",
    "slice",
    "evidence_path",
    "reviewer",
    "reviewer_decision",
    "override_value",
    "review_note",
    "reviewed_at",
]

# Keep this list small and explicit; extend per track in your config if needed.
DEFAULT_ALLOWED_DECISIONS = {"approve", "reject", "edit", "escalate", "skip"}

T02_STAGES = ("qc", "senior_qc", "domain_owner")
T02_ACTIONS = {"KEEP", "RECAPTURE", "HOLD"}
T02_REASON_CODES = {
    "blur", "glare", "dark", "compression", "insufficient_evidence", "other", "no_defect"
}
T02_REVIEW_COLUMNS = [
    "review_stage", "queue_id", "rank", "image_id", "score", "reason", "light", "camera_id",
    "evidence_path", "review_history", "reviewer", "action", "review_reason_codes", "review_note",
    "reviewed_at", "review_session_seconds",
]


def make_review_queue(
    df: pd.DataFrame,
    id_col: str,
    score_col: str,
    budget: int,
    reason_col: str | None = None,
    action_col: str | None = None,
    slice_col: str | None = None,
    evidence_col: str | None = None,
    ascending: bool = False,
) -> pd.DataFrame:
    """Top-`budget` items by score (default: highest score first = most suspicious)."""
    ranked = df.sort_values(score_col, ascending=ascending, kind="mergesort").head(int(budget)).reset_index(drop=True)
    q = pd.DataFrame(
        {
            "rank": range(1, len(ranked) + 1),
            "item_id": ranked[id_col].astype(str),
            "score": ranked[score_col].astype(float).round(6),
            "reason": ranked[reason_col] if reason_col else "",
            "suggested_action": ranked[action_col] if action_col else "",
            "slice": ranked[slice_col] if slice_col else "",
            "evidence_path": ranked[evidence_col] if evidence_col else "",
        }
    )
    for c in ["reviewer", "reviewer_decision", "override_value", "review_note", "reviewed_at"]:
        q[c] = ""
    return q[REVIEW_COLUMNS]


def write_review_queue(q: pd.DataFrame, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    q.to_csv(p, index=False)
    return p


def load_review_decisions(path: str | Path, allowed: Iterable[str] = DEFAULT_ALLOWED_DECISIONS) -> pd.DataFrame:
    """Load a reviewed queue; only rows with a decision are returned. Validates values."""
    q = pd.read_csv(path, dtype=str).fillna("")
    missing = [c for c in REVIEW_COLUMNS if c not in q.columns]
    if missing:
        raise ValueError(f"review file {path} missing columns: {missing}")
    done = q[q["reviewer_decision"].str.strip() != ""].copy()
    bad = sorted(set(done["reviewer_decision"].str.strip().str.lower()) - set(allowed))
    if bad:
        raise ValueError(f"unknown reviewer_decision values {bad}; allowed={sorted(allowed)}")
    no_owner = done[done["reviewer"].str.strip() == ""]
    if len(no_owner):
        raise ValueError(f"{len(no_owner)} reviewed rows have no `reviewer` (owner is mandatory)")
    done["reviewer_decision"] = done["reviewer_decision"].str.strip().str.lower()
    return done


def load_t02_review_decisions(
    path: str | Path,
    expected_stage: str,
    expected_queue_id: str,
    expected_item_ids: Iterable[str],
) -> pd.DataFrame:
    """Validate and normalize one stage-specific T02 review export."""
    if expected_stage not in T02_STAGES:
        raise ValueError(f"unsupported T02 review stage {expected_stage!r}")
    q = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in T02_REVIEW_COLUMNS if c not in q.columns]
    if missing:
        raise ValueError(f"review file {path} missing required T02 columns: {missing}")
    expected = {str(x) for x in expected_item_ids}
    for row_num, row in q.iterrows():
        line = row_num + 2
        stage = row["review_stage"].strip()
        queue_id = row["queue_id"].strip()
        item_id = row["image_id"].strip()
        if stage != expected_stage:
            raise ValueError(f"review file {path} row {line}: stage {stage!r} does not match {expected_stage!r}")
        if queue_id != expected_queue_id:
            raise ValueError(f"review file {path} row {line}: queue_id {queue_id!r} does not match {expected_queue_id!r}")
        if not item_id:
            raise ValueError(f"review file {path} row {line}: missing image_id")
        if item_id not in expected:
            raise ValueError(f"review file {path} row {line}: image_id {item_id!r} is not in this queue")
    dup = q[q["image_id"].duplicated(keep=False)]
    if len(dup):
        raise ValueError(f"review file {path} has duplicate image_id values: {sorted(dup.image_id.unique().tolist())}")

    done = q[q["action"].str.strip() != ""].copy()
    done["action"] = done["action"].str.strip().str.upper()
    bad_actions = sorted(set(done["action"]) - T02_ACTIONS)
    if bad_actions:
        raise ValueError(f"review file {path} has invalid action(s) {bad_actions}; use KEEP/RECAPTURE/HOLD")
    for row_num, row in done.iterrows():
        line = row_num + 2
        reviewer = row["reviewer"].strip()
        note = row["review_note"].strip()
        codes = [part.strip().lower().replace(" ", "_") for part in row["review_reason_codes"].split(";") if part.strip()]
        if not reviewer:
            raise ValueError(f"review file {path} row {line}: reviewer is required")
        if not codes:
            raise ValueError(f"review file {path} row {line}: at least one review_reason_code is required")
        unknown = sorted(set(codes) - T02_REASON_CODES)
        if unknown:
            raise ValueError(f"review file {path} row {line}: invalid review_reason_code(s) {unknown}")
        if len(codes) != len(set(codes)):
            raise ValueError(f"review file {path} row {line}: duplicate review_reason_code")
        if "no_defect" in codes and row["action"] != "KEEP":
            raise ValueError(f"review file {path} row {line}: no_defect is valid only with KEEP")
        if row["action"] in {"HOLD", "RECAPTURE"} and not note:
            raise ValueError(f"review file {path} row {line}: review_note is required for {row['action']}")
        reviewed_at = row["reviewed_at"].strip()
        if not reviewed_at:
            raise ValueError(f"review file {path} row {line}: reviewed_at is required")
        try:
            parsed_at = datetime.fromisoformat(reviewed_at[:-1] + "+00:00" if reviewed_at.endswith("Z") else reviewed_at)
        except ValueError:
            raise ValueError(f"review file {path} row {line}: reviewed_at must be an ISO-8601 timestamp with timezone") from None
        if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
            raise ValueError(f"review file {path} row {line}: reviewed_at must be an ISO-8601 timestamp with timezone")
        try:
            duration = float(row["review_session_seconds"])
        except (TypeError, ValueError):
            raise ValueError(f"review file {path} row {line}: review_session_seconds must be a non-negative number") from None
        if not math.isfinite(duration) or duration < 0:
            raise ValueError(f"review file {path} row {line}: review_session_seconds must be a non-negative number")
        done.at[row_num, "reviewer"] = reviewer
        done.at[row_num, "review_note"] = note
        done.at[row_num, "review_reason_codes"] = ";".join(codes)
        done.at[row_num, "review_session_seconds"] = str(duration)
    return done.reset_index(drop=True)


def apply_overrides(
    pred: pd.DataFrame,
    reviewed: pd.DataFrame,
    id_col: str,
    value_col: str,
    audit: "AuditLog | None" = None,
) -> pd.DataFrame:
    """Apply `override_value` for rows whose decision is `edit` (or `reject` with a value).

    Returns a copy of `pred`. Raw predictions are never modified in place —
    keep both files so the diff is auditable.
    """
    out = pred.copy()
    out[id_col] = out[id_col].astype(str)
    idx = out.set_index(id_col).index
    for r in reviewed.itertuples(index=False):
        if r.reviewer_decision in {"edit", "reject"} and str(r.override_value) != "":
            if r.item_id not in idx:
                continue
            mask = out[id_col] == r.item_id
            before = out.loc[mask, value_col].tolist()
            out.loc[mask, value_col] = r.override_value
            if audit:
                audit.log(
                    actor=r.reviewer,
                    action=f"override:{r.reviewer_decision}",
                    item_id=r.item_id,
                    before=before[0] if len(before) == 1 else before,
                    after=r.override_value,
                    reason=r.review_note,
                )
    return out


@dataclass
class AuditEvent:
    ts: str
    actor: str
    action: str
    item_id: str
    before: object = None
    after: object = None
    reason: str = ""
    extra: dict = field(default_factory=dict)


class AuditLog:
    """Append-only JSONL audit log. Never delete or rewrite lines."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, actor: str | None, action: str, item_id: str = "", before=None, after=None, reason: str = "", **extra) -> AuditEvent:
        ev = AuditEvent(
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            actor=actor or getpass.getuser(),
            action=action,
            item_id=str(item_id),
            before=before,
            after=after,
            reason=reason,
            extra=extra,
        )
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(ev), ensure_ascii=False, default=str) + "\n")
        return ev

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
