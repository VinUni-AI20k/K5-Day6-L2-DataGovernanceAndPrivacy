# reports/

| File | Ai tạo | Cách tạo |
|---|---|---|
| `group_report.md` | nhóm | điền template |
| `metric_contract.md` | nhóm | điền ở phút 30 |
| `metrics_baseline.json` | **script** | `python -m src.evaluate --track tXX --pred out/baseline/<file> --run-name baseline --out reports/metrics_baseline.json` |
| `metrics_poc.json` | **script** | `python -m src.evaluate --track tXX --pred out/poc/<file> --run-name poc --out reports/metrics_poc.json` |
| `table1_baseline_vs_poc.md` | **script** | `python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md` |
| `dev_labels.csv` | user + tool | `python tools/record_dev_labels.py --file reports/label_batches/<batch>.txt` |
| `t02_calibration.json/.md` | **script** | `python tools/_t02_calibrate.py` (56 nhãn dev; provenance + LOSO) |
| `t02_dev_eval.json/.md` | **script** | `python tools/_t02_dev_eval.py` (proxy dev, không phải eval) |
| `review_queue.csv` | pipeline + reviewer | copy từ `out/poc/review_queue.csv` sau khi review (có cột reviewer/decision) |
| `decision_log.csv` | pipeline | copy từ `out/poc/decision_log.csv` |
| `team_contributions.csv` | nhóm | khớp với `git shortlog -sne --all` |

Các file metrics/table **không được sửa tay** — giảng viên sẽ chạy lại lệnh để đối chiếu.
