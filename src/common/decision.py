"""Release decision record: GO / HOLD / REWORK (or track-specific equivalents).

A decision without `reason_code`, `owner` and evidence is not accepted by the rubric.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .io import write_json

# Canonical statuses + track-specific aliases (mapped for reporting only).
CANONICAL = {"GO", "HOLD", "REWORK"}
ALIASES = {
    "PASS": "GO", "ACCEPT": "GO", "KEEP": "GO", "RELEASE": "GO",
    "BLOCK": "HOLD", "ESCALATE": "HOLD",
    "RECAPTURE": "REWORK", "REJECT": "REWORK", "FIX": "REWORK",
}


def canonical_status(status: str) -> str:
    s = status.strip().upper()
    if s in CANONICAL:
        return s
    if s in ALIASES:
        return ALIASES[s]
    raise ValueError(f"unknown decision status {status!r}; use GO/HOLD/REWORK or one of {sorted(ALIASES)}")


@dataclass
class Decision:
    status: str                 # e.g. GO / HOLD / REWORK / PASS / ACCEPT / RECAPTURE
    reason_code: str            # short machine code, e.g. "PRIMARY_BELOW_THRESHOLD"
    reason: str                 # one human sentence
    owner: str                  # who signs off (name/role) — mandatory
    scope: str = ""             # batch/release/request id this decision is about
    evidence: list[str] = field(default_factory=list)   # paths to files backing the decision
    metrics: dict = field(default_factory=dict)          # snapshot of key numbers
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def __post_init__(self):
        canonical_status(self.status)
        if not self.owner.strip():
            raise ValueError("Decision.owner is mandatory")
        if not self.reason_code.strip():
            raise ValueError("Decision.reason_code is mandatory")

    @property
    def canonical(self) -> str:
        return canonical_status(self.status)


DECISION_LOG_COLUMNS = ["ts", "scope", "status", "canonical", "reason_code", "reason", "owner", "evidence"]


def write_decision(decision: Decision, json_path: str | Path, log_csv: str | Path | None = None) -> None:
    """Write decision JSON and append one row to the decision log CSV."""
    payload = asdict(decision) | {"canonical": decision.canonical}
    write_json(json_path, payload)
    if log_csv:
        p = Path(log_csv)
        p.parent.mkdir(parents=True, exist_ok=True)
        new = not p.exists() or p.stat().st_size == 0
        with open(p, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=DECISION_LOG_COLUMNS)
            if new:
                w.writeheader()
            w.writerow(
                {
                    "ts": decision.ts,
                    "scope": decision.scope,
                    "status": decision.status,
                    "canonical": decision.canonical,
                    "reason_code": decision.reason_code,
                    "reason": decision.reason,
                    "owner": decision.owner,
                    "evidence": ";".join(decision.evidence),
                }
            )
