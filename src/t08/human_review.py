"""Anh (người 4): dùng common.review để tạo queue và áp quyết định có audit."""
import pandas as pd

from ..common.context import RunContext


def build_queue(ctx: RunContext, proposed: pd.DataFrame) -> pd.DataFrame:
    """TODO: dùng item_id ghép request + artefact; xếp score, xuất queue CSV.

    Chốt budget, cách xử lý case chưa duyệt và danh sách cần review với nhóm.
    """
    raise NotImplementedError("Member 4: implement build_queue()")


def apply_review(ctx: RunContext, proposed: pd.DataFrame) -> pd.DataFrame:
    """TODO: đọc review_queue_reviewed.csv; kiểm ID/action/reviewer; log diff.

    Không coi chưa duyệt là đã approve. Kiểm lại policy khi override.
    Chốt trạng thái phê duyệt với executor trước khi nối vào pipeline.
    """
    raise NotImplementedError("Member 4: implement apply_review()")
