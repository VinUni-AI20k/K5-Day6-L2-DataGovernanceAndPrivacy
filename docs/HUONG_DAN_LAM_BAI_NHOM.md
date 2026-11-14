# Hướng dẫn làm bài nhóm T14 (6 người)

Nhóm `sIx4nhd0cthAn` · Track T14 Auto-Annotation + Human QC Exporter. Mỗi người làm đúng phần trong issue của mình.

## 1. Phân công

| Issue | Người | Việc |
|---|---|---|
| #1 | Trần Thành Hùng | B, C: metric contract, baseline |
| #2 | Hoàng Quốc Chung | D: label-map validation và test |
| #3 | Nguyễn Xuân Việt | E: PoC pipeline, review queue |
| #4 | Trần Nguyễn Phi Long | F: human review, CVAT |
| #5 | Phạm Phú Nguyễn Hưng | G, I, J, K: export/QA, eval, decision, hồ sơ nhóm |
| #6 | Bùi Văn Thịnh | H: failure analysis |

**Review thủ công (HTML):** Hùng, Chung, Long cùng duyệt toàn bộ queue (30 box), mỗi người độc lập. Hưng chốt box lệch phiếu ở `admin.html` và xuất CSV.

## 2. Báo cáo: viết bằng file Markdown (.md), không làm HTML

Mỗi người nộp 1 file: `reports/individual/<MSSV>_<HoTen>.md`, gồm:

1. **Việc đã làm**: task nào (B–K), file nào đã sửa hoặc tạo.
2. **Lệnh đã chạy**: copy nguyên lệnh và output chính.
3. **Bằng chứng**: đường dẫn file trong `out/` hoặc `reports/`, số liệu thật.
4. **Hạn chế**: phần chưa xong hoặc chưa chắc.

Điền thêm đúng mục của mình trong `reports/group_report.md` (xem issue) và dòng của mình trong `reports/team_contributions.csv`.
HTML chỉ là trang web review dùng chung (`web/public/`), không ai phải viết HTML riêng.

## 3. Cách review trên trang HTML

1. Mở link web (Hưng gửi sau khi deploy) và nhập **tên thật** của bạn cùng passcode nhóm.
2. Mỗi box là một thẻ: ô đỏ là box cần duyệt, ô xám là box khác trong ảnh.
3. **Phóng to ảnh:** bấm vào ảnh để mở toàn màn hình.
   - `+` / `−` (nút hoặc phím), `Vừa khung`, `100%`
   - Nhấn giữ Ctrl hoặc Shift và lăn chuột: zoom tại con trỏ
   - Nhấp đúp: zoom 3x tại điểm bấm, nhấp đúp lần nữa: về vừa khung
   - Kéo chuột: di chuyển ảnh. `Esc`: đóng
4. Quyết định cho từng box:
   - **Giữ (đúng)**: box và class đúng.
   - **Xóa (sai)**: không có object, hoặc box sai hẳn.
   - **Sửa…**: chọn class mới, hoặc nhập đủ cả 4 số x, y, w, h (theo pixel của ảnh gốc).
   - **Cần admin xem**: không chắc.
   - **Bỏ qua**: xem sau (không tính là đã duyệt).
5. Ghi `ghi chú` khi sửa hoặc xóa. Tiêu chí gán nhãn: `docs/HUONG_DAN_GAN_NHAN_CVAT.md`.
6. Có thể bật "chỉ hiện box chưa duyệt". Mỗi lần bấm được lưu kèm tên và thời gian.
7. Không bàn nhau trước khi nộp, để tính được độ đồng thuận.

**Admin (Hưng):** vào `admin.html`, chốt các box lệch phiếu, bấm **Tải review_queue_reviewed.csv**. Kiểm tra CSV: đủ 30 dòng, mỗi dòng có `reviewer` và `decision`, không trùng `item_id`.

## 4. Chạy local để kiểm tra phần của mình

```powershell
python -m pytest -q
python -m tools.preflight
```

Cả hai phải xanh trước khi mở PR.

## 5. Quy tắc git

- Mỗi người một branch `feat/t14-<ten-khong-dau>`, tách từ `feat/t14-pipeline`.
- **Mỗi người 1 commit**: `git rebase -i` không dùng được trong môi trường này thì dùng `git reset --soft <base>` rồi commit lại.
- Author phải đúng tên bạn (`git config user.name`, `user.email`). `team_contributions.csv` phải khớp `git shortlog -sne --all`.
- Không push main, không deploy. Chỉ Hưng deploy khi cần.
- Số liệu phải có bằng chứng, không điền số ước đoán.

## 6. Thứ tự phụ thuộc

`A → B → C`, `D → E → F → G → I → J`, `H` sau khi có C và E. `K` làm song song.
Ai cần output của người trước thì chờ commit của người đó, hoặc báo trong issue.
