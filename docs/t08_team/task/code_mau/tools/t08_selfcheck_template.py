"""Người C · tạo KHUNG bộ tự kiểm (self-check) — C tự điền cột expected_action bằng tay.

Chạy:  .\\.venv\\Scripts\\python.exe -m tools.t08_selfcheck_template
Ra:    reports/selfcheck/t08_expected_TODO.csv  (expected_action để trống)
C mở bằng Excel, điền expected_action theo chính sách ĐÃ CHỐT + case catalog,
lưu thành reports/selfcheck/t08_expected.csv và commit TRƯỚC khi chạy PoC lên nó.

KHÔNG đặt file vào fixtures/t08_deletion/gt/: GT guard chặn đọc, và tests/conftest.py
sẽ báo "instructor overlay is incomplete" làm pytest dừng.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path("fixtures/t08_deletion")
OUT = Path("reports/selfcheck/t08_expected_TODO.csv")


def main():
    arts = json.loads((ROOT / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]
    reqs = json.loads((ROOT / "requests.json").read_text(encoding="utf-8"))
    rows = []
    for r in reqs:
        for a in sorted(arts, key=lambda x: x["artefact_id"]):
            if r["subject_id"] in a["subject_ids"]:
                rows.append({"request_id": r["request_id"], "artefact_id": a["artefact_id"], "type": a["type"],
                             "n_subjects": len(a["subject_ids"]), "legal_hold": a.get("legal_hold") or "",
                             "acl": ";".join(a["acl"]), "origin_known": a.get("origin_known", True),
                             "parent_ids": ";".join(a["parent_ids"]), "expected_action": "", "label_note": ""})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(rows)} rows) — điền expected_action ∈ {{delete, retain_legal_hold, escalate}}")


if __name__ == "__main__":
    main()
