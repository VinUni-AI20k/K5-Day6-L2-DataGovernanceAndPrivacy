"""Nam: trạng thái mock bền vững, log trước/sau và chống thực hiện lặp."""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile

import pandas as pd
from ..common.context import RunContext
from .input_data import load_input
from .lineage import find_related
from .policy import ACTIONS, propose_action


def atomic_json(path: Path, value: dict) -> None:
    # Ghi file mới rồi replace: tránh state JSON bị ghi dở khi job gián đoạn.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def execution_lock(path: Path):
    # Không cho hai executor cùng đọc state cũ rồi ghi đè lẫn nhau.
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError("Execution is locked. If a process crashed, confirm it stopped before removing .execution.lock") from exc
    try:
        with stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def execute_mock(ctx: RunContext, final: pd.DataFrame) -> pd.DataFrame:
    dry_run = ctx.param("dry_run", True)
    if not isinstance(dry_run, bool):
        raise ValueError("params.dry_run must be true or false")
    actor = ctx.param("actor", "data-platform")
    data = load_input(ctx.input_dir)
    related = {r["request_id"]: {a["artefact_id"]: a for a in find_related(r, data["artefacts"])}
               for r in data["requests"]}
    requests = {r["request_id"]: r for r in data["requests"]}
    if final.item_id.duplicated().any() or not set(final.action).issubset(ACTIONS):
        raise ValueError("Duplicate item_id or invalid final action")
    # Revalidate delete ở ranh giới thực hiện, không tin action CSV đơn thuần.
    for row in final.itertuples(index=False):
        if row.request_id not in requests or row.artefact_id not in related[row.request_id]:
            raise ValueError("Final action outside request scope")
        if row.item_id != row.request_id + "::" + row.artefact_id:
            raise ValueError("Invalid composite item_id")
        base = propose_action(requests[row.request_id], related[row.request_id][row.artefact_id], actor)
        if row.action == "delete" and base["action"] != "delete":
            raise ValueError(f"Executor policy blocks {row.item_id}")
        if base["action"] == "retain_legal_hold" and row.action != base["action"]:
            raise ValueError("Executor cannot release active legal hold")
    blocked = set(final.loc[final.action != "delete", "artefact_id"])
    result = final.copy()
    statuses = []
    state_path = ctx.out("mock_state.json")
    with execution_lock(ctx.out(".execution.lock")):
        state = {"schema": 1, "input_hash": data["input_hash"], "deleted": {}}
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("schema") != 1 or state.get("input_hash") != data["input_hash"] or not isinstance(state.get("deleted"), dict):
                raise ValueError("Mock state belongs to different input or is invalid; use another output folder")
        for row in result.itertuples(index=False):
            extra = dict(request_id=row.request_id, composite_id=row.item_id,
                         plan_hash=ctx.stats["plan_hash"], dry_run=dry_run)
            if row.action == "retain_legal_hold":
                status = "retained"
            elif row.action == "escalate":
                status = "escalated"
            elif row.artefact_id in blocked:
                status = "blocked_conflicting_request"
            elif not bool(row.execution_approved) or not str(row.reviewer).strip():
                status = "pending_approval"
            elif dry_run:
                status = "planned_delete"
            elif row.artefact_id in state["deleted"]:
                # Sau crash giữa ghi state và audit completed, lần chạy lại
                # ghi already_deleted để đối soát mà không lặp tác động.
                status = "already_deleted"
            else:
                ctx.audit.log(actor=actor, action="mock_delete_intent", item_id=row.artefact_id,
                              before="present", after="delete_pending", **extra)
                state["deleted"][row.artefact_id] = {"first_request": row.request_id,
                                                     "reviewer": row.reviewer,
                                                     "plan_hash": ctx.stats["plan_hash"]}
                atomic_json(state_path, state)
                status = "deleted"
            ctx.audit.log(actor=actor, action="execution:" + status, item_id=row.artefact_id,
                          after=row.action, reason=row.reason_code, **extra)
            statuses.append(status)
    result["execution_status"] = statuses
    result[["request_id", "artefact_id", "action", "execution_status", "reviewer"]].to_csv(
        ctx.out("execution_evidence.csv"), index=False)
    ctx.stats["execution_counts"] = result.execution_status.value_counts().to_dict()
    return result
