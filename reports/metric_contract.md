# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T07 |
| Primary metric (tên đúng như evaluator in ra) |PII Miss Rate |
| Tăng tốt hay giảm tốt? |  lower |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) |PII region phải redact |
| Công thức + numerator / denominator |Số vùng GT có coverage < 0.9 / tổng số vùng GT phải redact |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) |Coverage pixel của mỗi vùng GT bởi hợp các bbox redact trên cùng ảnh |
| Candidate pool cố định |Cùng tập ảnh đầu vào cho baseline và PoC; 36 dev, 24 eval |
| Review budget B / K |B = 15 candidate |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) |Chọn trên dev và chốt trước eval; không tune trên eval |
| Eval split (không dùng để tune) |eval |
| Chỉ số lỗi xấu (miss / false alarm / false reject) |	PII Miss Rate và Over-redaction rate |
| Slices sẽ báo cáo (≥2) |type=face/plate; condition=normal/small/dark/blur/occluded; size=small/medium/large |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) |Báo số mẫu và Wilson CI 95% cho tỷ lệ miss |
| Ngày giờ chốt + người chốt |17h00 + LuongVanQuyen |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.

## Coverage và guardrail

- Coverage threshold: 0.9.
- Coverage được tính bằng pixel, không dùng IoU thay thế.
- Over-redaction rate = số pixel đã che nằm ngoài GT / tổng số pixel đã che.
- Guardrail: over-redaction rate ≤ 0.3.
- Primary metric chỉ được coi là hợp lệ khi guardrail PASS.
- Ground truth chỉ được dùng trong evaluation, không được đọc trong pipeline.

### Quy định size slices

Phân nhóm theo diện tích bbox ground truth: A = w × h,
với w và h tính bằng pixel.

- small: A < 1024.
- medium: 1024 <= A < 9216.
- large: A >= 9216.

Áp dụng cùng ngưỡng cho face/plate, baseline và PoC.
Tính size từ bbox GT, không tính từ bbox detector hoặc bbox sau padding.
Chốt ngưỡng trước eval và không thay đổi sau khi xem kết quả.
Mỗi slice phải báo số vùng GT; slice không có mẫu ghi N/A.
condition=small và size=small là hai cách phân nhóm riêng biệt.