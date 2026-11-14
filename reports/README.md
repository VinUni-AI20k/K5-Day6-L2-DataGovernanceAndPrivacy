# reports/ (T14)

| File | Ai tạo | Cách tạo |
|---|---|---|
| `group_report.md` | nhóm | điền template |
| `metric_contract.md` | nhóm | điền ở phút 30 |
| `metrics_baseline.json` | **script** | `make eval-baseline` |
| `metrics_poc.json` | **script** | `make eval-poc` |
| `table1_baseline_vs_poc.md` | **script** | `make compare` |
| `review_queue.csv` | pipeline + reviewer | copy từ `out/poc/review_queue.csv` sau khi review |
| `decision_log.csv` | pipeline | copy từ `out/poc/decision_log.csv` |
| `team_contributions.csv` | nhóm | khớp với `git shortlog -sne --all` |

Các file metrics/table **không được sửa tay**.
