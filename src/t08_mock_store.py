"""Mock artefact store for T08. NOTHING REAL IS DELETED.

A "deletion" is a tombstone written to a JSON state file in the run's output folder. The state
is what makes the executor idempotent and resumable: deleting an artefact that is already
tombstoned is a no-op, so a second run (or a run resumed after an interruption) changes nothing.
"""
from __future__ import annotations

from pathlib import Path

from .common.io import read_json, write_json


class MockStore:
    def __init__(self, path: str | Path, fingerprint: str):
        self.path = Path(path)
        self.fingerprint = fingerprint
        self.tombstones: dict[str, list[str]] = {}       # artefact_id -> request ids that deleted it
        if self.path.exists():
            state = read_json(self.path)
            if state.get("input_fingerprint") != fingerprint:
                raise ValueError(
                    f"{self.path} was written for a different input (fingerprint "
                    f"{state.get('input_fingerprint')} != {fingerprint}). Use a clean --output folder."
                )
            self.tombstones = {k: list(v) for k, v in (state.get("tombstones") or {}).items()}

    @property
    def deleted(self) -> set[str]:
        return set(self.tombstones)

    def delete(self, artefact_id: str, request_id: str) -> str:
        """'new' = tombstoned now; 'linked' = already gone, request recorded; 'noop' = nothing to do."""
        if artefact_id not in self.tombstones:
            self.tombstones[artefact_id] = [request_id]
            return "new"
        if request_id not in self.tombstones[artefact_id]:
            self.tombstones[artefact_id] = sorted(self.tombstones[artefact_id] + [request_id])
            return "linked"
        return "noop"

    def save(self) -> Path:
        # No timestamps on purpose: identical plans must give byte-identical state files.
        return write_json(self.path, {
            "note": "MOCK tombstones - no real data is deleted in this lab",
            "input_fingerprint": self.fingerprint,
            "tombstones": {k: self.tombstones[k] for k in sorted(self.tombstones)},
        })
