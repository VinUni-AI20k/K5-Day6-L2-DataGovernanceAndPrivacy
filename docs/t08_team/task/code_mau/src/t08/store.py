"""Kho mock (người A): chỉ ghi trạng thái 'đã xoá' vào JSON. Idempotent + resume được."""
import json
from datetime import datetime, timezone
from pathlib import Path


class MockStore:
    def __init__(self, state_path):
        self.path = Path(state_path)
        self.state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"deleted": {}}

    def _save(self):
        self.path.write_text(json.dumps(self.state, indent=1, sort_keys=True), encoding="utf-8")

    def execute(self, actions, audit, fail_after=None) -> dict:
        n_new = n_skip = 0
        for r in actions[actions.action == "delete"].itertuples(index=False):
            if r.artefact_id in self.state["deleted"]:
                n_skip += 1
                audit.log(actor="mock-store", action="delete_skipped_already_deleted", item_id=r.artefact_id,
                          request_id=r.request_id)
                continue
            if fail_after is not None and n_new >= fail_after:
                raise RuntimeError(f"simulated crash after {n_new} deletes")
            self.state["deleted"][r.artefact_id] = {"request_id": r.request_id,
                                                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self._save()  # lưu sau MỖI lần xoá -> bị ngắt giữa chừng vẫn resume được
            n_new += 1
            audit.log(actor="mock-store", action="delete", item_id=r.artefact_id, before="present",
                      after="deleted", reason=r.reason_code, request_id=r.request_id)
        return {"deleted_new": n_new, "skipped_already_deleted": n_skip}
