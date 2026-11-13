"""Budgeted audit oracle: simulates a human inspector who reveals hidden labels
ONLY for the samples you choose to audit, and refuses once the budget is spent.

Example (T12):
    oracle = AuditOracle("fixtures/t12_vendor_batches/gt/hidden_errors.csv",
                         id_col="sample_id", label_col="is_error", group_col="batch_id",
                         budget_per_group=20, audit=ctx.audit)
    labels = oracle.inspect(["V1_0003", "V1_0042"])   # -> {"V1_0003": 0, "V1_0042": 1}
"""
from __future__ import annotations

import csv
from collections import Counter

from .gt_guard import trusted_open
from .review import AuditLog


class BudgetExceededError(RuntimeError):
    pass


class AuditOracle:
    def __init__(self, gt_csv: str, id_col: str, label_col: str, group_col: str | None = None,
                 budget_per_group: int | None = None, total_budget: int | None = None, audit: AuditLog | None = None):
        with trusted_open(gt_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self._label = {r[id_col]: int(r[label_col]) for r in rows}
        self._group = {r[id_col]: r[group_col] for r in rows} if group_col else {}
        self.budget_per_group = budget_per_group
        self.total_budget = total_budget
        self.used: Counter = Counter()
        self.seen: dict[str, int] = {}
        self.audit = audit

    def inspect(self, ids: list[str], actor: str = "auditor") -> dict[str, int]:
        out = {}
        for i in ids:
            if i in self.seen:
                out[i] = self.seen[i]
                continue
            if i not in self._label:
                raise KeyError(f"unknown sample id {i}")
            g = self._group.get(i, "_all")
            if self.budget_per_group is not None and self.used[g] >= self.budget_per_group:
                raise BudgetExceededError(f"audit budget {self.budget_per_group} exhausted for group {g}")
            if self.total_budget is not None and sum(self.used.values()) >= self.total_budget:
                raise BudgetExceededError(f"total audit budget {self.total_budget} exhausted")
            self.used[g] += 1
            self.seen[i] = out[i] = self._label[i]
            if self.audit:
                self.audit.log(actor=actor, action="audit_inspect", item_id=i, after=out[i], reason=f"group={g}")
        return out

    def remaining(self, group: str = "_all") -> int | None:
        return None if self.budget_per_group is None else self.budget_per_group - self.used[group]
