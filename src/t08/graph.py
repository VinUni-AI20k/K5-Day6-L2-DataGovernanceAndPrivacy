"""Đồ thị lineage của T08 (người B)."""
import json
from collections import defaultdict
from pathlib import Path


def load_graph(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {a["artefact_id"]: a for a in data["artefacts"]}


def children_map(arts) -> dict:
    ch = defaultdict(list)
    for aid, a in arts.items():
        for p in a["parent_ids"]:
            ch[p].append(aid)
    return {k: sorted(v) for k, v in ch.items()}


def ancestors(arts, aid) -> set:
    seen, stack = set(), list(arts[aid]["parent_ids"])
    while stack:
        p = stack.pop()
        if p in seen or p not in arts:
            continue
        seen.add(p)
        stack.extend(arts[p]["parent_ids"])
    return seen


def scope(arts, children, subject_id) -> list:
    """Lineage để TÌM (BFS xuống con), subject_ids để QUYẾT (chỉ giữ artefact có subject)."""
    start = [aid for aid, a in arts.items() if subject_id in a["subject_ids"]]
    found, queue = set(start), list(start)
    while queue:
        x = queue.pop(0)
        for c in children.get(x, []):
            if c not in found and subject_id in arts[c]["subject_ids"]:
                found.add(c)
                queue.append(c)
    return sorted(found)


def lineage_warnings(arts) -> list:
    """Con có subject mà KHÔNG cha nào có -> catalog của cha thiếu subject (bỏ qua training_export)."""
    out = []
    for aid, a in sorted(arts.items()):
        if not a["parent_ids"] or a["type"] == "training_export":
            continue
        parent_subj = set()
        for p in a["parent_ids"]:
            parent_subj |= set(arts[p]["subject_ids"]) if p in arts else set()
        extra = sorted(set(a["subject_ids"]) - parent_subj)
        if extra:
            out.append({"artefact_id": aid, "parents": a["parent_ids"], "missing_in_parent": extra})
    return out
