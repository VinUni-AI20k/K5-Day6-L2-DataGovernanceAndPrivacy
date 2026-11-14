# Protocol nhãn nội bộ — T02 Raw QC Triage

Repo học viên **không có** `fixtures/t02_raw_qc/gt/`. Không có nhãn thì nhóm không
chốt được ngưỡng, không đo được baseline, và không biết PoC tốt lên hay xấu đi.
Tài liệu này mô tả bộ nhãn nhóm tự gán để dùng thay thế, cùng giới hạn của nó.

Nhãn nội bộ **không phải** ground truth của giảng viên. Mọi con số đo trên nó
phải ghi rõ là "đo trên nhãn nội bộ, N=…", không được trình bày như điểm chính thức.

## 1. Phạm vi

| Hạng mục | Quyết định |
|---|---|
| Split được gán nhãn | `dev` (56 ảnh) — **toàn bộ**, không lấy mẫu |
| Split **không** gán nhãn | `eval` (40 ảnh) |
| Số người gán | 2, độc lập |
| Công cụ | `reports/internal_label_sheet_t02_<A\|B>.html`, mở offline bằng trình duyệt |

Gán hết 56 ảnh `dev` thay vì lấy mẫu vì số lượng đủ nhỏ (khoảng 10 phút một người),
và như vậy không phải chịu thêm sai số lấy mẫu khi ước lượng tỷ lệ lỗi.

**`eval` để nguyên.** Quy tắc 1 của lab cấm tune trên split eval. Nếu nhóm tự gán nhãn
eval rồi chỉnh ngưỡng theo đó thì vi phạm, dù nhãn là nhãn của nhóm. Chỉ khi đã chốt
và đóng băng tham số thì mới được gán một lần duy nhất để báo cáo, và phải ghi rõ
"gán sau khi freeze" kèm thời điểm.

## 2. Bảng phân loại

Dùng đúng từ vựng của schema giảng viên (`gt/labels.csv`) để số liệu so sánh được:

| `defect_type` | Nghĩa | `is_defect` |
|---|---|---:|
| `none` | Ảnh dùng được, không cần chụp lại | 0 |
| `blur` | Nhoè toàn ảnh hoặc nhoè vùng chính, mất chi tiết | 1 |
| `glare` | Cháy sáng, kể cả **cháy cục bộ** ở vùng quan trọng dù tổng thể ảnh vẫn ổn | 1 |
| `dark` | Thiếu sáng tới mức không đọc được nội dung | 1 |
| `compression` | Vỡ khối JPEG, nhiễu bậc thang thấy rõ | 1 |

`severity`: `0` nhẹ (vẫn dùng được, ghi nhận), `1` vừa (nên chụp lại), `2` nặng (bỏ).

### Hai quy ước dễ gây lệch nhau, chốt trước

**Ảnh đêm không mặc nhiên là `dark`.** Trong fixture này ảnh đêm của `cam_A` có độ nét
trung vị 1578, cao hơn ảnh ngày (944). Ảnh tối nhưng vẫn nhìn rõ nội dung thì gán `none`.
Chỉ gán `dark` khi nội dung thực sự không đọc được.

**`cam_B` mềm hơn `cam_A` theo hệ thống**, độ nét trung vị 236 so với 944 ở ảnh ban ngày.
Đó là đặc tính quang học, không phải lỗi. Khi gán nhãn `cam_B` phải so với ảnh `cam_B`
khác, không so với `cam_A`.

Hai quy ước này ứng với failure mode số 1 và số 3 mà handout bắt phải phân tích.

## 3. Quy trình

1. Mỗi người mở file sheet của mình, gán hết 56 ảnh, bấm **Export CSV**.
2. Đổi tên file tải về thành `reports/internal_labels_t02_A.csv` và `..._B.csv`.
3. Chạy `python tools/merge_internal_labels.py` để đo mức đồng thuận và xuất danh sách
   ảnh hai người gán khác nhau.
4. Ảnh lệch nhau: hai người xem lại cùng nhau, chốt một nhãn, ghi lý do vào cột `note`.
   Không lấy trung bình, không bỏ phiếu đa số với hai người.
5. Kết quả cuối lưu ở `reports/internal_labels_t02_final.csv`, là file duy nhất
   pipeline và báo cáo được phép dùng.

## 4. Ngưỡng chấp nhận

| Chỉ số | Ngưỡng | Nếu không đạt |
|---|---|---|
| Cohen's κ trên `is_defect` | ≥ 0,70 | Xem lại quy ước ở mục 2, gán lại từ đầu |
| Tỷ lệ đồng thuận `defect_type` | ≥ 0,70 | Gộp các loại hay nhầm nhau, ghi vào report |
| Số ảnh chưa gán | 0 | Gán nốt trước khi dùng |

κ dưới 0,70 nghĩa là chính nhóm còn chưa thống nhất "thế nào là lỗi". Chỉnh ngưỡng
thuật toán theo một bộ nhãn như vậy là chỉnh theo nhiễu.

## 5. Giới hạn phải nêu trong báo cáo

- N=56, chỉ trên `dev`. Khoảng tin cậy của mọi tỷ lệ rất rộng; không kết luận mạnh từ chênh lệch vài ảnh.
- Người gán nhãn cũng là người viết thuật toán → có thiên lệch xác nhận. Giảm bớt bằng cách
  gán nhãn **trước** khi nhìn điểm số của pipeline, và ghi lại thời điểm.
- Bảng phân loại là của nhóm suy ra từ handout, chưa chắc khớp cách giảng viên gán.
  Sai lệch hệ thống ở đây sẽ không lộ ra cho tới khi chấm bằng `gt/` thật.
- Nhãn nội bộ dùng để **chốt ngưỡng và bắt lỗi logic**, không dùng để tuyên bố thành tích.
