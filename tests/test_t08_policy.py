"""Người B · test engine chính sách: mỗi loại ngoại lệ + delete thường."""
import json
from collections import Counter

import pytest

from src.t08 import graph, policy

FIX = "fixtures/t08_deletion"


@pytest.fixture(scope="module")
def env():
    arts = graph.load_graph(f"{FIX}/data_graph.json")
    return arts, graph.children_map(arts), policy.load_policy("configs/t08_policy.yaml")


REQ = {"request_id": "DR-X", "subject_id": "subj_x", "identity_verified": True}


@pytest.mark.parametrize("aid,action,code", [
    ("a0043", "retain_legal_hold", "LEGAL_HOLD_ACTIVE"),
    ("a0045", "retain_legal_hold", "LEGAL_HOLD_INHERITED"),   # frame con của raw bị hold
    ("a0156", "escalate", "NO_PERMISSION_ACL"),
    ("a0075", "escalate", "ORIGIN_UNKNOWN"),
    ("a0011", "escalate", "MULTI_SUBJECT_SHARED"),
    ("a0017", "delete", "ERASURE_REQUEST"),
])
def test_rules(env, aid, action, code):
    arts, _, pol = env
    got = policy.decide(aid, arts, REQ, pol)
    assert got[:2] == (action, code)


def test_identity_rule_has_top_priority(env):
    arts, _, pol = env
    assert policy.decide("a0017", arts, {**REQ, "identity_verified": False}, pol)[1] == "IDENTITY_NOT_VERIFIED"


def test_scope_uses_subject_ids(env):
    arts, ch, _ = env
    s = graph.scope(arts, ch, "subj_01")
    assert len(s) == 17 and "a0011" in s and "a0012" not in s   # a0012 = crop của subj_00


def test_lineage_warnings_found(env):
    arts, _, _ = env
    assert {w["artefact_id"] for w in graph.lineage_warnings(arts)} == {"a0011", "a0067", "a0123", "a0179"}


@pytest.mark.parametrize("path,expected", [
    ("configs/t08_policy.yaml", {"delete": 102, "retain_legal_hold": 40, "escalate": 16}),
    ("configs/t08_policy_backup_only.yaml", {"delete": 126, "retain_legal_hold": 4, "escalate": 28}),  # ablation
])
def test_action_counts_main_vs_ablation(env, path, expected):
    arts, ch, _ = env
    pol = policy.load_policy(path)
    reqs = json.loads(open(f"{FIX}/requests.json", encoding="utf-8").read())
    got = Counter(policy.decide(aid, arts, r, pol)[0] for r in reqs for aid in graph.scope(arts, ch, r["subject_id"]))
    assert dict(got) == expected


def test_bad_policy_yaml_fails_loudly(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("rules:\n  - {id: R1, when: typo_condition, action: delete, reason_code: X, source: x}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        policy.load_policy(bad)
