# Cách làm việc · Nhóm T08

Kế hoạch chi tiết: [docs/PLAN_T08.md](docs/PLAN_T08.md). File này chỉ là luật chơi Git, đọc trong 3 phút.

## 1. Cài đặt lần đầu

```powershell
git clone https://github.com/nguyenloc2004/K5-Day6-L2B-DataGovernanceAndPrivacy.git
cd K5-Day6-L2B-DataGovernanceAndPrivacy
git config user.name  "Họ Tên"        # phải khớp reports/team_contributions.csv
git config user.email "email@cua.ban"
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q      # phải xanh
```

Gửi tên và email Git cho leader để điền `reports/team_contributions.csv`.

## 2. Ai sửa file nào

Mỗi file chỉ một người sửa. Cần sửa file của người khác thì nhắn người đó.

| Người | File sở hữu |
|---|---|
| M1 Leader | `src/pipeline.py`, `src/t08/contracts.py`, `configs/`, `requirements.txt`, `reports/team_contributions.csv` |
| M2 Data & lineage | `src/t08/loader.py`, `src/t08/lineage.py` |
| M3 Policy | `src/t08/policy.py`, `configs/t08_policy.yaml` |
| M4 QA & metric | `src/t08/baseline.py`, `tests/test_t08_*.py`, `tests/data/t08_mini/` |
| M5 Review & report | `src/t08/audit.py`, `reports/*.md`, `demo/` |

## 3. Năm luật Git

1. **Không push thẳng lên `main`.** Mọi thay đổi đi qua Pull Request.
2. **Tên nhánh:** `m<số>/<việc>`, ví dụ `m2/lineage-bfs`. Mỗi nhánh làm một việc, tối đa khoảng 45 phút.
3. **Test xanh mới mở PR.** Chạy `pytest -q` sau khi rebase.
4. **Merge bằng "Create a merge commit", không dùng Squash.** Squash làm mất tên tác giả, mà giảng viên chấm bằng `git shortlog -sne --all`.
5. **Commit message:** `feat|fix|test|docs(t08-<module>): <nội dung>`. Commit chỉ sửa khoảng trắng không được tính.

## 4. Vòng lặp cho mỗi việc

```powershell
git switch main; git pull
git switch -c m2/lineage-bfs
# ... code, commit nhỏ ...
git add src/t08/lineage.py
git commit -m "feat(t08-lineage): scope theo subject_ids"
git pull --rebase origin main
.venv\Scripts\python -m pytest -q
git push -u origin m2/lineage-bfs
# Mở PR trên GitHub → người duyệt bấm Merge → xóa nhánh
```

**Người duyệt PR:** M2 ↔ M3 duyệt cho nhau, M4 ↔ M5 duyệt cho nhau, M1 duyệt mọi PR chạm `src/pipeline.py`. Cố duyệt xong trong 5 phút.

## 5. Lệnh chạy (Windows, không cần `make`)

```powershell
# PoC
.venv\Scripts\python -m src.main --config configs/lab.yaml --track t08 --output out/poc --run-name poc --offline --seed 42
# Baseline
.venv\Scripts\python -m src.main --track t08 --pipeline src.t08.baseline --output out/baseline --run-name baseline --offline --seed 42
# Test
.venv\Scripts\python -m pytest -q
```

Xóa thư mục `out/` trước khi chạy lấy số chính thức (audit log chỉ ghi nối thêm).

## 6. Các mốc

| Phút | Mốc |
|---|---|
| 15 | Mỗi người có 1 commit đầu; khung chạy exit 0 |
| 30 | Chốt `reports/metric_contract.md` |
| 50 | Merge 1: có baseline |
| 90 | Merge 2: PoC ra đủ dòng, test xanh |
| 145 | Merge 3: vòng review chạy đủ. Từ đây chỉ sửa lỗi, không thêm tính năng |
| 170–180 | Leader gắn tag `demo-180m` và push tag |
| +24h | Leader gắn tag `final-24h` và push tag |

Đến mốc, ai cũng merge phần đã xong (miễn test xanh) rồi rebase lên `main`.

## 7. Quyết định đã chốt

- Legal hold **không lan** xuống bản phái sinh: chỉ file có `legal_hold` mới `retain_legal_hold`, bản phái sinh `delete`.
- Artefact nhiều chủ thể: `escalate`.
- Review budget B = 60.
- **Không hard-code artefact ID** trong code. Giảng viên chấm bằng bộ dữ liệu ẩn khác fixture.
