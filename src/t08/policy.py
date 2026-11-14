"""Vinh (người 3): policy. Chốt quy tắc trước khi đánh giá."""


def propose_action(request: dict, artefact: dict, actor: str) -> dict:
    """Trả action row theo docs/T08_TEAM_PLAN.md.

    TODO: xét hold đang hiệu lực, quyền actor, origin_known, nhiều subject,
    xác minh request; trả action/reason_code/reason/score/needs_review.
    Actor thực hiện không mặc định đồng nghĩa config owner (người ký duyệt).
    """
    raise NotImplementedError("Member 3: implement propose_action()")
