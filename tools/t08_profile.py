"""Người C · Data & fixtures — khảo sát data_graph.json, in "case catalog" để cả nhóm dùng.

Chạy:  .\\.venv\\Scripts\\python.exe -m tools.t08_profile
Ra:    reports/t08_data_profile.md (UTF-8; script tự ghi file để tránh lỗi mã hoá khi pipe trên PowerShell)
Chỉ đọc input (không đọc gt/). Code độc lập với src/t08 của B để kiểm chéo.
"""
import builtins
import json
from collections import Counter
from pathlib import Path

ROOT = Path("fixtures/t08_deletion")
OUT = Path("reports/t08_data_profile.md")
_lines: list[str] = []


def print(*args):  # noqa: A001 — gom dòng để ghi file UTF-8
    _lines.append(" ".join(str(a) for a in args))


def main():
    _profile()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    builtins.print(f"wrote {OUT} ({len(_lines)} lines)")


def _profile():
    arts = {a["artefact_id"]: a for a in json.loads((ROOT / "data_graph.json").read_text(encoding="utf-8"))["artefacts"]}
    reqs = json.loads((ROOT / "requests.json").read_text(encoding="utf-8"))
    print("# T08 · Data profile (tự sinh bằng tools/t08_profile.py)\n")
    print(f"- Artefact: **{len(arts)}** · Request: **{len(reqs)}**")
    print(f"- Theo type: {dict(Counter(a['type'] for a in arts.values()))}")
    print(f"- identity_verified=false: {[r['request_id'] for r in reqs if not r.get('identity_verified')]}\n")

    print("## Case catalog (ngoại lệ cài sẵn)\n")
    print("| artefact | type | subject_ids | lý do |")
    print("|---|---|---|---|")
    for aid, a in sorted(arts.items()):
        why = []
        if a.get("legal_hold"):
            why.append(f"legal_hold={a['legal_hold']}")
        if "data-platform" not in a["acl"]:
            why.append(f"acl={a['acl']}")
        if not a.get("origin_known", True):
            why.append("origin_known=false")
        if len(a["subject_ids"]) > 1:
            why.append(f"multi-subject ({len(a['subject_ids'])})")
        if why:
            subj = a["subject_ids"] if len(a["subject_ids"]) <= 3 else f"{len(a['subject_ids'])} subjects"
            print(f"| {aid} | {a['type']} | {subj} | {'; '.join(why)} |")

    # cây con của raw bị legal hold (để gán nhãn LEGAL_HOLD_INHERITED)
    children = {}
    for aid, a in arts.items():
        for p in a["parent_ids"]:
            children.setdefault(p, []).append(aid)
    print("\n## Cây con của artefact bị legal hold\n")
    for aid, a in sorted(arts.items()):
        if a.get("legal_hold"):
            seen, stack = set(), [aid]
            while stack:
                for c in children.get(stack.pop(), []):
                    if c not in seen:
                        seen.add(c)
                        stack.append(c)
            print(f"- {aid} ({a['legal_hold']}): {len(seen)} hậu duệ → {sorted(seen)}")

    print("\n## Số artefact trong phạm vi mỗi request (subject_id ∈ subject_ids)\n")
    for r in reqs:
        n = sum(r["subject_id"] in a["subject_ids"] for a in arts.values())
        print(f"- {r['request_id']} · {r['subject_id']}: {n}")

    _notes(arts, children)


def _brief(a):
    return f"type={a['type']}, subject_ids={a['subject_ids']}, parent_ids={a['parent_ids']}, acl={a['acl']}"


def _notes(arts, children):
    """Ghi chú kiểm tay 3 case (C2.3) — số liệu lấy thẳng từ data_graph.json để tái lập được."""
    print("\n## Ghi chú kiểm tay 3 case (C2)\n")
    a11 = arts["a0011"]
    print(f"- **a0011** ({_brief(a11)}).")
    for p in a11["parent_ids"]:
        print(f"  - cha {p}: {_brief(arts[p])}")
    for c in sorted(children.get("a0011", [])):
        print(f"  - con {c}: {_brief(arts[c])}")
    print("  → frame **dùng chung 2 người**: xoá theo yêu cầu của subj_01 sẽ xoá luôn dữ liệu của subj_00 "
          "⇒ phải `escalate` (R7). Con a0012 (face_crop) chỉ mang subj_00 → không thuộc phạm vi DR-001 "
          "(*lineage để TÌM, `subject_ids` để QUYẾT*).")
    # catalog mâu thuẫn: con có subject mà KHÔNG cha nào có -> data-catalog REWORK
    bad = []
    for aid, a in sorted(arts.items()):
        if a["parent_ids"]:
            par_subj = set().union(*(arts[p]["subject_ids"] for p in a["parent_ids"]))
            miss = sorted(set(a["subject_ids"]) - par_subj)
            if miss and a["type"] != "training_export":
                bad.append(f"{aid} (thiếu ở cha: {miss})")
    print(f"  → Lineage mâu thuẫn (con có subject mà cha không có, trừ export): **{len(bad)}** artefact: "
          f"{bad} ⇒ `data-catalog` cần REWORK.")
    a156 = arts["a0156"]
    print(f"- **a0156** ({_brief(a156)}, uri={a156['uri']}).")
    print("  → backup nằm ở kho có ACL `vendor-x`, đội data-platform **không có quyền xoá** ⇒ `escalate` (R4), "
          "cần nhà cung cấp xác nhận xoá.")
    a211 = arts["a0211"]
    held_par = [p for p in a211["parent_ids"] if _held_ancestor(p, arts)]
    print(f"- **a0211** (training_export, {len(a211['subject_ids'])} subjects, {len(a211['parent_ids'])} cha).")
    print(f"  → cha có tổ tiên/bản thân bị legal hold: {held_par} "
          f"(a0046 = {arts['a0046']['type']} của {arts['a0046']['subject_ids']}, cha raw a0043 giữ "
          f"{arts['a0043']['legal_hold']}) ⇒ `retain_legal_hold` (R3) ở **mọi** request chạm tới export này, "
          "dù R6/R7 cũng khớp — luật đầu tiên khớp thắng.")


def _held_ancestor(aid, arts):
    stack, seen = [aid], set()
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        if arts[x].get("legal_hold"):
            return True
        stack.extend(arts[x]["parent_ids"])
    return False


if __name__ == "__main__":
    main()
