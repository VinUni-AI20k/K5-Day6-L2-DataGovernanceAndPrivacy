"""Hàng chờ ngoại lệ + áp quyết định DPO (người D)."""
import html

import pandas as pd

from src.common.review import make_review_queue

PRIORITY = {"IDENTITY_NOT_VERIFIED": 5, "LEGAL_HOLD_ACTIVE": 5, "LEGAL_HOLD_INHERITED": 4, "NO_PERMISSION_ACL": 4,
            "ORIGIN_UNKNOWN": 3, "SHARED_EXPORT_REBUILD": 2, "MULTI_SUBJECT_SHARED": 2}
ACTIONS = {"delete", "retain_legal_hold", "escalate"}


def build_queue(actions: pd.DataFrame, budget: int) -> pd.DataFrame:
    exc = actions[actions.action != "delete"].copy()
    exc["prio"] = exc.reason_code.map(PRIORITY).fillna(1)
    return make_review_queue(exc, id_col="item_id", score_col="prio", budget=budget, reason_col="reason_code",
                             action_col="action", slice_col="artefact_type")


def render_review_table(queue: pd.DataFrame, path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset='utf-8'><title>T08 review queue</title>"
                f"<h1>{html.escape('T08 · Hàng chờ ngoại lệ (DPO duyệt)')}</h1>" + queue.to_html(index=False))


def apply_review(actions: pd.DataFrame, reviewed: pd.DataFrame, audit) -> pd.DataFrame:
    out = actions.copy()
    for r in reviewed.itertuples(index=False):
        m = out.item_id == r.item_id
        if not m.any():
            continue
        aid, req = out.loc[m, "artefact_id"].iloc[0], out.loc[m, "request_id"].iloc[0]
        before = out.loc[m, "action"].iloc[0]
        if r.reviewer_decision == "approve":            # DPO ký đồng ý action máy đề xuất
            out.loc[m, "reviewed_by"] = r.reviewer
            after = before
        elif r.reviewer_decision == "edit":             # DPO đổi action
            after = str(r.override_value).strip().lower()
            if after not in ACTIONS:
                raise ValueError(f"{r.item_id}: override_value phải thuộc {sorted(ACTIONS)}")
            out.loc[m, ["action", "reviewed_by", "rule_id"]] = [after, r.reviewer, "HUMAN_OVERRIDE"]
        else:                                           # reject / escalate / skip: chưa ký
            after = before
        audit.log(actor=r.reviewer, action=f"review:{r.reviewer_decision}", item_id=aid, before=before,
                  after=after, reason=r.review_note, request_id=req)
    return out
