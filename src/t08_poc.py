"""T08 dry-run deletion decisions for the mock artefact graph."""
from __future__ import annotations

import csv
import json

from .common.context import RunContext
from .pipeline import load


def has_legal_hold(item: dict, subject: str, by_id: dict[str, dict]) -> bool:
    pending = [item["artefact_id"]]
    seen = set()

    while pending:
        artefact_id = pending.pop()
        if artefact_id in seen:
            continue

        seen.add(artefact_id)
        node = by_id[artefact_id]
        if node["legal_hold"] and subject in node["subject_ids"]:
            return True

        pending.extend(node["parent_ids"])

    return False


def run(ctx: RunContext) -> None:
    load(ctx)  # Verify the input manifest.
    graph = json.loads(
        (ctx.input_dir / "data_graph.json").read_text(encoding="utf-8")
    )
    requests = json.loads(
        (ctx.input_dir / "requests.json").read_text(encoding="utf-8")
    )
    artefacts = graph["artefacts"]
    by_id = {item["artefact_id"]: item for item in artefacts}

    with ctx.out("actions.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["request_id", "artefact_id", "action"])

        for request in requests:
            subject = request["subject_id"]
            request_id = request["request_id"]

            for item in artefacts:
                if subject not in item["subject_ids"]:
                    continue

                if has_legal_hold(item, subject, by_id):
                    action, reason = "retain_legal_hold", "Legal hold on artefact or ancestor"
                elif not request["identity_verified"]:
                    action, reason = "escalate", "Identity unverified"
                elif not item["origin_known"]:
                    action, reason = "escalate", "Unknown origin"
                elif "data-platform" not in item["acl"]:
                    action, reason = "escalate", "Missing deletion permission"
                elif len(item["subject_ids"]) > 1:
                    action, reason = "escalate", "Shared artefact"
                else:
                    action, reason = "delete", "Eligible for mock deletion"

                artefact_id = item["artefact_id"]
                writer.writerow([request_id, artefact_id, action])
                ctx.audit.log(
                    "pipeline", action, artefact_id,
                    reason=reason, request_id=request_id,
                )
