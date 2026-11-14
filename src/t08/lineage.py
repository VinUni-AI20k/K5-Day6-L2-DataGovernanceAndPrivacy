"""Núi: duyệt quan hệ cha-con, không xem việc liên quan là quyền xóa."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


def find_related(request: dict[str, Any], artefacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    subject = request.get("subject_id")
    if not subject:
        return []
    by_id = {a["artefact_id"]: a for a in artefacts}
    if len(by_id) != len(artefacts):
        raise ValueError("Duplicate artefact_id")
    children = defaultdict(list)
    for art in artefacts:
        for parent in art.get("parent_ids", []):
            children[parent].append(art["artefact_id"])
    # Tìm cả bản nằm ngoài nhánh raw nhưng đã được gắn subject, như export.
    seeds = sorted(a["artefact_id"] for a in artefacts if subject in a.get("subject_ids", []))
    queue = deque((key, [key]) for key in seeds)
    visited, result = set(), []
    while queue:
        key, path = queue.popleft()
        if key in visited:
            continue
        visited.add(key)  # Chặn vòng lặp và một node xuất hiện từ nhiều cha.
        art = by_id[key]
        tags = art.get("subject_ids", [])
        # Crop có nhãn người khác không trở thành mục tiêu chỉ vì cha là ảnh chung.
        if tags and subject not in tags:
            continue
        copy = dict(art)
        copy["_scope_inferred"] = subject not in tags
        copy["_evidence_path"] = path
        result.append(copy)
        for child in sorted(children[key]):
            queue.append((child, path + [child]))
    return sorted(result, key=lambda a: a["artefact_id"])

