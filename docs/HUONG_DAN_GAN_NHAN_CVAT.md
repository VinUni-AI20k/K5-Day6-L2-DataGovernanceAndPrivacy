# Hướng dẫn gắn nhãn ảnh bằng tay (CVAT) — dễ hiểu cho học sinh lớp 10

## 1. Chúng ta đang làm gì?

Máy tính chưa biết nhìn ảnh như người. Muốn nó học, người phải **chỉ cho nó**: "đây là xe ô tô", "đây là người đi bộ".
Việc chỉ này gọi là **gắn nhãn** (annotation). Cách làm: vẽ một **hình chữ nhật** quanh vật thể rồi chọn **tên** cho nó.

> Ví dụ: giống như em dùng bút khoanh tròn con mèo trong ảnh rồi viết chữ "mèo" bên cạnh.

## 2. Chuẩn bị (người quản lý máy làm một lần)

| Việc | Cách làm |
|---|---|
| Bật CVAT | Mở Docker Desktop, chờ các container `cvat_*` chạy (đã sửa xong lỗi `cvat_redis_inmem`). |
| Địa chỉ cho cả nhóm | Máy chủ đang có IP Wi-Fi `10.53.152.59` → mọi người vào: **http://10.53.152.59:8080** |
| Điều kiện | Mọi người dùng **cùng một mạng Wi-Fi** với máy chủ. IP có thể đổi khi đổi mạng — kiểm tra lại bằng lệnh `ipconfig`. |
| Cho phép máy khác vào | Windows có thể chặn cổng 8080. Cần mở tường lửa cho cổng 8080 (chỉ mạng riêng/Private). |
| Tạo tài khoản | Đăng nhập admin → tạo mỗi bạn/phụ huynh một tài khoản riêng. |

⚠️ "Qua Wi-Fi" nghĩa là chỉ những người **cùng mạng** mới vào được, không phải cả Internet. Đừng chia sẻ mật khẩu admin.

## 3. Đưa ảnh lên (tạo Task)

Bộ ảnh dùng: `fixtures/t14_auto_annotation/images/` (60 ảnh `aa_00.jpg` … `aa_59.jpg`).

1. Đăng nhập CVAT → **Projects → Create new project**, đặt tên `T14 - Gắn nhãn xe`.
2. Thêm 4 nhãn (label) đúng tên: `car`, `pedestrian`, `motorbike`, `sign`.
3. Vào project → **Create a new task** → đặt tên (ví dụ `Lô 1 - 30 ảnh`).
4. Mục **Select files** → **My computer** → chọn các ảnh. (Chia 60 ảnh thành 2 lô × 30 ảnh để 2 người làm cùng lúc.)
5. Bấm **Submit & Open**.

## 4. Cách gắn nhãn (người làm)

1. Mở Task → bấm **Job #...** (công việc được giao).
2. Bấm biểu tượng **hình chữ nhật** (hoặc phím **N**).
3. Chọn nhãn (ví dụ `car`) → bấm **Shape**.
4. **Bấm 2 góc đối diện** của vật thể (góc trên-trái, rồi góc dưới-phải).
5. Chuyển ảnh kế tiếp bằng phím **D** (ảnh trước: **F**).
6. Lưu bằng **Ctrl + S** thường xuyên.
7. Xong hết ảnh: **Menu → Finish the job**.

### Quy tắc vàng (để dữ liệu "sạch")
- Khung phải **ôm sát** vật thể, không quá rộng, không cắt mất một phần.
- Vật nào nhìn thấy rõ thì **phải gắn**, kể cả vật nhỏ.
- Không chắc là gì? Đừng đoán bừa — hỏi người phụ trách.
- Mặt người hoặc biển số rõ nét: **không** ghi lại thông tin cá nhân ra ngoài.
- Một vật = một khung. Không vẽ trùng hai khung lên cùng vật.

## 5. Kiểm tra & xuất kết quả (người phụ trách)

1. Mở lại vài ảnh ngẫu nhiên của mỗi người, xem khung có đúng không.
2. Task → **Actions → Export task dataset** → chọn **YOLO 1.1** (hoặc COCO 1.0).
3. Giải nén file `.zip`, đổi tên nhãn nếu cần cho khớp `taxonomy.yaml`: `car, pedestrian, motorbike, sign`.

## 6. Gặp sự cố?

| Hiện tượng | Cách xử lý |
|---|---|
| Máy khác không vào được | Kiểm tra cùng Wi-Fi, đúng IP, tường lửa đã mở cổng 8080. |
| Trang báo lỗi 502 | Docker chưa chạy xong, chờ 1–2 phút rồi tải lại; nếu vẫn lỗi báo người quản lý máy. |
| Mất kết nối khi đang vẽ | Bấm Ctrl+S trước; tải lại trang, công việc đã lưu vẫn còn. |
| Máy chủ chậm | Ít người cùng làm một lúc, đóng bớt chương trình khác. |
