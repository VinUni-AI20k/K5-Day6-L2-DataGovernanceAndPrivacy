"""Ground-truth guard: the pipeline (src.main) must never read fixtures/*/gt/.

Only src.evaluate (and the controlled AuditOracle for T12-style audits) may.
Enabled by default in src.main; disable with --allow-gt-read (and explain why in the report).
"""
from __future__ import annotations

import builtins
import io
import os
from pathlib import Path

_original_open = builtins.open
_enabled = False


class GroundTruthAccessError(PermissionError):
    pass


def _is_gt(path) -> bool:
    try:
        p = Path(os.fspath(path)).resolve()
    except TypeError:
        return False
    parts = p.parts
    return "gt" in parts and "fixtures" in parts and parts.index("gt") > parts.index("fixtures")


def _guarded_open(file, *args, **kwargs):  # type: ignore[no-untyped-def]
    if isinstance(file, (str, bytes, os.PathLike)) and _is_gt(file):
        raise GroundTruthAccessError(
            f"Pipeline tried to read ground truth: {file}. GT is only for src.evaluate. "
            "Use the dev split / your own labels, or the AuditOracle for budgeted audits."
        )
    return _original_open(file, *args, **kwargs)


def enable_gt_guard() -> None:
    global _enabled
    builtins.open = _guarded_open
    io.open = _guarded_open
    _enabled = True


def disable_gt_guard() -> None:
    global _enabled
    builtins.open = _original_open
    io.open = _original_open
    _enabled = False


def trusted_open(file, *args, **kwargs):
    """Bypass the guard — ONLY for audit oracles that enforce a budget."""
    return _original_open(file, *args, **kwargs)
