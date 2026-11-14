# Submission — Lab 6 · T14 · Auto-Annotation + Human QC Exporter

## Thông tin nhóm

| | |
|---|---|
| **Tên nhóm** | `sIx4nhd0cthAn` |
| **Track** | T14 — Auto-Annotation + Human QC Exporter |
| **Bài** | Day 06 · Data Lab · Field-to-Release PoC (K5 · L2) |
| **Repo nhóm** | https://github.com/phamphunguyenhung/K5-Day6-L2-sIx4nhd0cthAn-DataGovernanceAndPrivacy |
| **Repo đề bài (upstream)** | https://github.com/VinUni-AI20k/K5-Day6-L2-DataGovernanceAndPrivacy |
| **Người ký duyệt (`owner` trong `configs/lab.yaml`)** | _chưa chốt_ |

## Thành viên

Họ tên và MSSV lấy từ file `report/individual/<MSSV>_<HoTen>.md` trong repo public các lab trước của từng bạn.

| # | Họ và tên | MSSV | GitHub | Vai trò trong T14 |
|---|---|---|---|---|
| 1 | Trần Thành Hùng | 2A202603247 | [Hung-1812](https://github.com/Hung-1812) | _chưa phân_ |
| 2 | Hoàng Quốc Chung | 2A202604039 | [qchung2124](https://github.com/qchung2124) | _chưa phân_ |
| 3 | Nguyễn Xuân Việt | 2A202604045 | [ngxuanviet](https://github.com/ngxuanviet) | _chưa phân_ |
| 4 | Trần Nguyễn Phi Long | 2A202604058 | [CybevisKeishaa](https://github.com/CybevisKeishaa) | _chưa phân_ |
| 5 | Phạm Phú Nguyễn Hưng | 2A202604062 | [phamphunguyenhung](https://github.com/phamphunguyenhung) | _chưa phân_ |
| 6 | _chưa có thông tin_ | _chưa có_ | _chưa có_ | _chưa phân_ |

> Nhóm có 6 người, hiện mới có đủ thông tin của 5 người. Bổ sung dòng 6 khi có họ tên, MSSV và GitHub.
> Bảng này phải khớp với `reports/team_contributions.csv` và `git shortlog -sne --all`.

## Cần có trong repo khi nộp

| File | Ai tạo | Ghi chú |
|---|---|---|
| `reports/group_report.md` | nhóm | điền template mục 00–11 |
| `reports/metric_contract.md` | nhóm | chốt trước khi chạy eval |
| `reports/metrics_baseline.json`, `reports/metrics_poc.json`, `reports/table1_baseline_vs_poc.md` | **script** | không sửa tay. Cần overlay `gt/` của giảng viên, nên nhóm không tự sinh bản chính thức |
| `reports/review_queue.csv` | pipeline + người duyệt | copy từ `out/poc/review_queue.csv` sau khi đã điền cột `reviewer`, `decision` |
| `reports/decision_log.csv` | pipeline | copy từ `out/poc/decision_log.csv` |
| `reports/team_contributions.csv` | nhóm | khớp `git shortlog -sne --all` |
| `src/pipeline.py`, `src/t14_tools.py`, `src/baseline_t14.py`, `tests/test_t14.py` | nhóm | code T14 và ≥2 test (success + failure) |

**Không nộp:** file `.env`, token, ảnh người hoặc biển số thật chưa có quyền.

## Chạy lại (giảng viên dùng đúng các lệnh này)

```bash
make setup
python -m src.main --config configs/lab.yaml --track t14 --output out/poc --run-name poc --offline --seed 42
python -m src.main --config configs/lab.yaml --track t14 --pipeline src.baseline_t14 --output out/baseline --run-name baseline --offline --seed 42
pytest -q
git shortlog -sne --all
```

## Mốc và tag

| Mốc | Việc | Lệnh |
|---|---|---|
| Phút 170–180 | Freeze demo | `make tag-demo` (tag `demo-180m`) |
| +24h | Bản nộp cuối | `make tag-final` (tag `final-24h`), rồi `git push <remote> final-24h` |
