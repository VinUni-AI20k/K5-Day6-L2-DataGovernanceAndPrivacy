"""T08 policy rules on small hand-built graphs (no fixture, no I/O)."""
import random

import pytest

from src.t08_policy import ACTIONS, blocked_deletes, build_plan, descendants, build_index


def A(i, typ, subj, parents=(), hold=None, origin=True, acl=("data-platform",)):
    return {"artefact_id": i, "type": typ, "subject_ids": list(subj), "parent_ids": list(parents),
            "legal_hold": hold, "origin_known": origin, "acl": list(acl), "uri": f"mock://{typ}/{i}"}


def R(rid, subj, verified=True):
    return {"request_id": rid, "subject_id": subj, "identity_verified": verified, "deadline": "2026-12-01T09:00:00+07:00"}


def plan(graph, requests, **kw):
    return {(r["request_id"], r["artefact_id"]): r for r in build_plan(graph, requests, **kw)}


def chain(prefix, subj, hold=None):
    """raw -> backup, raw -> frame -> crop -> embedding, frame -> annotation"""
    return [A(f"{prefix}1", "raw_video", [subj], hold=hold), A(f"{prefix}2", "backup", [subj], [f"{prefix}1"]),
            A(f"{prefix}3", "frame", [subj], [f"{prefix}1"]), A(f"{prefix}4", "face_crop", [subj], [f"{prefix}3"]),
            A(f"{prefix}5", "embedding", [subj], [f"{prefix}4"]), A(f"{prefix}6", "annotation", [subj], [f"{prefix}3"])]


# ------------------------------------------------------------------ success path
def test_full_lineage_is_deleted_including_backup_and_embedding():
    p = plan(chain("a", "s1") + chain("b", "s2"), [R("R1", "s1")])
    assert {k[1] for k, r in p.items() if r["action"] == "delete"} == {"a1", "a2", "a3", "a4", "a5", "a6"}
    assert not any(k[1].startswith("b") for k in p)          # the other subject's data is untouched


def test_every_action_is_in_the_contract_and_keys_are_unique():
    rows = build_plan(chain("a", "s1", hold="LH-1") + chain("b", "s2"), [R("R1", "s1"), R("R2", "s2")])
    assert {r["action"] for r in rows} <= set(ACTIONS)
    assert len({(r["request_id"], r["artefact_id"]) for r in rows}) == len(rows)


# ------------------------------------------------------------------ exceptions (failure modes of the track)
def test_legal_hold_is_retained_and_inherited_by_derived_data():
    p = plan(chain("a", "s1", hold="LH-1"), [R("R1", "s1")])
    assert p["R1", "a1"]["reason_code"] == "LEGAL_HOLD"
    assert all(r["action"] == "retain_legal_hold" for r in p.values())
    assert {r["reason_code"] for k, r in p.items() if k[1] != "a1"} == {"LEGAL_HOLD_INHERITED"}


def test_inherit_hold_false_keeps_only_the_flagged_artefact():
    p = plan(chain("a", "s1", hold="LH-1"), [R("R1", "s1")], inherit_hold=False)
    assert p["R1", "a1"]["action"] == "retain_legal_hold"
    assert all(r["action"] == "delete" for k, r in p.items() if k[1] != "a1")


def test_export_with_only_some_held_sources_is_escalated_never_deleted():
    g = chain("a", "s1", hold="LH-1") + chain("b", "s2") + [A("x1", "training_export", ["s1", "s2"], ["a4", "b4"])]
    p = plan(g, [R("R1", "s1"), R("R2", "s2")])
    assert p["R1", "x1"]["reason_code"] == p["R2", "x1"]["reason_code"] == "PARTIAL_LEGAL_HOLD"
    assert p["R2", "x1"]["action"] == "escalate"
    assert p["R2", "b4"]["action"] == "delete"               # s2's own lineage is not held


def test_unknown_origin_and_foreign_acl_are_escalated():
    g = [A("a1", "raw_video", ["s1"]), A("a2", "backup", ["s1"], ["a1"], acl=["vendor-x"]),
         A("a3", "embedding", ["s1"], ["a1"], origin=False), A("a4", "frame", ["s1"], ["ghost"])]
    p = plan(g, [R("R1", "s1")])
    assert p["R1", "a1"]["action"] == "delete"
    assert (p["R1", "a2"]["action"], p["R1", "a2"]["reason_code"]) == ("escalate", "NO_PERMISSION")
    assert (p["R1", "a3"]["action"], p["R1", "a3"]["reason_code"]) == ("escalate", "UNKNOWN_ORIGIN")
    assert (p["R1", "a4"]["action"], p["R1", "a4"]["reason_code"]) == ("escalate", "BROKEN_LINEAGE")


def test_shared_artefact_is_never_auto_deleted():
    g = [A("a1", "raw_video", ["s1"]), A("a2", "frame", ["s1", "s2"], ["a1"])]
    one = plan(g, [R("R1", "s1")])
    assert (one["R1", "a2"]["action"], one["R1", "a2"]["reason_code"]) == ("escalate", "MULTI_SUBJECT")
    both = plan(g, [R("R1", "s1"), R("R2", "s2")])
    assert both["R1", "a2"]["reason_code"] == both["R2", "a2"]["reason_code"] == "MULTI_SUBJECT_ALL_REQUESTED"
    assert both["R1", "a2"]["action"] == both["R2", "a2"]["action"] == "escalate"
    unverified = plan(g, [R("R1", "s1"), R("R2", "s2", verified=False)])
    assert unverified["R1", "a2"]["reason_code"] == "MULTI_SUBJECT"   # an unverified co-request does not count


def test_other_persons_crop_from_a_shared_frame_is_flagged_not_deleted():
    # frame shows s1+s2, the crop cut from it is s1's face only
    g = [A("a1", "raw_video", ["s1"]), A("a2", "frame", ["s1", "s2"], ["a1"]), A("a3", "face_crop", ["s1"], ["a2"])]
    p = plan(g, [R("R1", "s1"), R("R2", "s2")])
    assert p["R1", "a3"]["action"] == "delete"                                       # owner's request
    assert (p["R2", "a3"]["action"], p["R2", "a3"]["reason_code"]) == ("escalate", "DERIVED_OTHER_SUBJECT")
    assert ("R2", "a3") not in plan(g, [R("R1", "s1"), R("R2", "s2")], include_derived_other_subject=False)
    # ...and that flag must not block the owner's delete
    assert not [b for b in blocked_deletes(list(p.values())) if b[1] == "a3"]


def test_unverified_identity_deletes_nothing():
    p = plan(chain("a", "s1"), [R("R1", "s1", verified=False)])
    assert {r["action"] for r in p.values()} == {"escalate"}
    assert {r["reason_code"] for r in p.values()} == {"IDENTITY_NOT_VERIFIED"}


def test_delete_is_blocked_while_another_request_keeps_the_artefact_open():
    rows = [{"request_id": "R1", "artefact_id": "a2", "action": "delete", "reason_code": "REVIEW_OVERRIDE"},
            {"request_id": "R2", "artefact_id": "a2", "action": "escalate", "reason_code": "MULTI_SUBJECT_ALL_REQUESTED"},
            {"request_id": "R1", "artefact_id": "a1", "action": "delete", "reason_code": "OK_DELETE"}]
    assert blocked_deletes(rows) == [("R1", "a2", ["R2"])]


# ------------------------------------------------------------------ robustness
def test_plan_is_deterministic_under_input_reordering():
    g = chain("a", "s1", hold="LH-1") + chain("b", "s2") + [A("x1", "training_export", ["s1", "s2"], ["a4", "b4"])]
    reqs = [R("R2", "s2"), R("R1", "s1")]
    base = build_plan(g, reqs)
    shuffled = g[:]
    random.Random(42).shuffle(shuffled)
    assert build_plan(shuffled, reqs[::-1]) == base
    assert build_plan(g, reqs + reqs) == base                # exact duplicate requests collapse


def test_bad_input_fails_loudly():
    with pytest.raises(ValueError, match="duplicate artefact_id"):
        build_plan([A("a1", "raw_video", ["s1"]), A("a1", "frame", ["s1"])], [R("R1", "s1")])
    with pytest.raises(ValueError, match="different subjects"):
        build_plan([A("a1", "raw_video", ["s1"])], [R("R1", "s1"), R("R1", "s2")])
    with pytest.raises(ValueError, match="without request_id"):
        build_plan([A("a1", "raw_video", ["s1"])], [{"subject_id": "s1"}])


def test_lineage_cycle_terminates():
    g = [A("a1", "frame", ["s1"], ["a2"]), A("a2", "frame", ["s1"], ["a1"])]
    _, children = build_index(g)
    assert descendants({"a1"}, children) == {"a1", "a2"}
    assert len(build_plan(g, [R("R1", "s1")])) == 2


def test_request_for_unknown_subject_produces_no_rows():
    assert build_plan(chain("a", "s1"), [R("R9", "nobody")]) == []
