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


if __name__ == "__main__":
    main()
