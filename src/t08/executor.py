"""Nam (người 5): chỉ thao tác trạng thái mock trong output, không xóa file thật."""
import pandas as pd

from ..common.context import RunContext


def execute_mock(ctx: RunContext, final: pd.DataFrame) -> pd.DataFrame:
    """TODO: dry_run=True chỉ lập kế hoạch, không log là đã xóa.

    dry_run=False cập nhật mock state trong out/ cho hành động hợp lệ đã duyệt.
    Chống thực hiện lặp theo item_id, giữ audit append-only; phân biệt planned,
    reviewed, executed. Không sửa fixture/manifest hoặc truy cập URI thật.
    Trả bảng quyết định cuối; lưu bằng chứng thực hiện riêng để kiểm chứng.
    """
    raise NotImplementedError("Member 5: implement execute_mock()")
