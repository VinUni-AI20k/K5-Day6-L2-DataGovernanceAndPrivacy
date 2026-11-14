"""LeVanKhoi: baseline T08, chọn bằng --pipeline src.t08_baseline."""
from .common.context import RunContext


def run(ctx: RunContext) -> None:
    """TODO: baseline theo đề: chỉ tìm một raw theo filename, bỏ derived/backup.

    Dùng cùng input/seed/protocol với PoC; ghi actions.csv, decision và audit.
    Không đọc GT trong pipeline hay tự điền số đánh giá.
    """
    raise NotImplementedError("LeVanKhoi: implement T08 baseline")
