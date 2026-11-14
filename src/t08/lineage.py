"""Núi (người 2): tìm dữ liệu liên quan. Contract: docs/T08_TEAM_PLAN.md."""


def find_related(request: dict, artefacts: list[dict]) -> list[dict]:
    """Trả bản ghi liên quan, không trùng, sắp theo artefact_id.

    TODO: index ID và cha -> con; tìm subject; duyệt có visited chống vòng lặp.
    Chốt trường hợp thiếu parent/subject với nhóm. Không sửa input, đọc GT,
    hoặc tự coi mọi bản ghi tìm thấy đều được phép xóa.
    """
    raise NotImplementedError("Member 2: implement find_related()")
