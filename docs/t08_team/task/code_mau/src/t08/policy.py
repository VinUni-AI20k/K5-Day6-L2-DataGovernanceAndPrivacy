"""Engine chính sách T08 (người B): luật đầu tiên khớp thắng."""
from pathlib import Path

import yaml

from .graph import ancestors

# Tên điều kiện khớp với khoá `when:` trong configs/t08_policy.yaml
CONDITIONS = {
    "identity_not_verified": lambda a, arts, req: not req.get("identity_verified", False),
    "legal_hold": lambda a, arts, req: bool(a.get("legal_hold")),
    "ancestor_legal_hold": lambda a, arts, req: any(arts[p].get("legal_hold") for p in ancestors(arts, a["artefact_id"])),
    "no_permission": lambda a, arts, req: "data-platform" not in a.get("acl", []),
    "origin_unknown": lambda a, arts, req: not a.get("origin_known", True),
    "training_export": lambda a, arts, req: a["type"] == "training_export",
    "multi_subject": lambda a, arts, req: len(a["subject_ids"]) > 1,
    "always": lambda a, arts, req: True,
}
ACTIONS = {"delete", "retain_legal_hold", "escalate"}


def load_policy(path) -> dict:
    pol = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for r in pol["rules"]:
        if r["when"] not in CONDITIONS or r["action"] not in ACTIONS:
            raise ValueError(f"bad rule {r}")
    return pol


def decide(aid, arts, req, policy) -> tuple:
    a = arts[aid]
    for r in policy["rules"]:
        if CONDITIONS[r["when"]](a, arts, req):
            return r["action"], r["reason_code"], r["id"]
    raise ValueError(f"no rule matched {aid}")
