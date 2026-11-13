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
