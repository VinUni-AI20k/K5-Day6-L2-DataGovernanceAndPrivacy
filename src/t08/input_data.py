"""LeVanKhoi: đọc JSON; pipeline.load() kiểm manifest trước khi gọi hàm này."""
import json
from pathlib import Path


def load_input(input_dir: Path) -> dict:
    # Chỉ đọc input; không sửa fixture hoặc manifest để vượt kiểm tra hash.
    with (input_dir / "requests.json").open(encoding="utf-8") as stream:
        requests = json.load(stream)
    with (input_dir / "data_graph.json").open(encoding="utf-8") as stream:
        graph = json.load(stream)
    if not isinstance(graph, dict):
        raise ValueError("data_graph.json must contain an object")
    artefacts = graph.get("artefacts")
    for label, rows, key in (
        ("requests", requests, "request_id"),
        ("artefacts", artefacts, "artefact_id"),
    ):
        if not isinstance(rows, list):
            raise ValueError(f"{label} must be a list")
        if any(not isinstance(row, dict) or not isinstance(row.get(key), str)
               or not row[key].strip() for row in rows):
            raise ValueError(f"Every {label} record needs a non-empty {key}")
        ids = [row[key] for row in rows]
        # ID trùng khiến một quyết định có thể bị áp nhầm vào nhiều bản ghi.
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate {key} in {label}")
    return {"requests": requests, "artefacts": artefacts}
