# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | 2A202603119 |
| Challenge | T07 · Automatic Face/Plate Redaction + Review Queue |
| Thành viên (5–6) + vai trò | 1. ____ (Detector/redactor/ranking) · 2. Nguyễn Thanh Phong (Baseline & data protocol) · 3. ____ (Human review, audit & export) · 4. ____ (QA, metric & failure analysis) · 5. Nguyễn Nhật Minh (Lead integration, decision, report & demo) |
| Git URL | https://github.com/Tphong27/K5-Day6-L2-2A202603119-NguyenThanhPhong-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | ____ |
| Tag `final-24h` (commit) | ____ |
| Deadline (giờ VN) | ____ |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? Người xuất hiện trong ảnh và chủ phương tiện có thể bị lộ dữ liệu nhận dạng nếu khuôn mặt hoặc biển số bị bỏ sót. Đơn vị sở hữu dữ liệu chịu rủi ro về quyền riêng tư, vận hành và uy tín; người sử dụng dữ liệu đầu ra chịu rủi ro nếu ảnh bị che quá mức và mất tín hiệu cần thiết cho tác vụ sau đó.
- Điểm nghẽn cụ thể: phát hiện đủ khuôn mặt/biển số nhỏ, tối, mờ hoặc bị che khuất trong khi vẫn giới hạn vùng che để không phá hủy giá trị sử dụng của ảnh. Các vùng confidence thấp cần được ưu tiên cho human review trong budget cố định B=15.
- Đầu vào → đầu ra: 60 ảnh synthetic 640×360 cùng `images.csv` và `manifest.csv` → phát hiện vùng PII → padding/redaction → xếp hạng review → reviewer approve/reject/edit/escalate → `redactions.csv`, ảnh đã redact, review queue, audit log và quyết định phát hành.
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): **HOLD** khi thiếu detector/model bắt buộc, provenance/schema lỗi, có truy cập mạng hoặc pipeline cố đọc GT. **REWORK** khi còn bbox không hợp lệ, có reviewer `escalate`, review bắt buộc chưa hoàn tất, hoặc audit/export QA không đạt. **GO** khi output đúng schema, mọi bbox hợp lệ, không còn escalation, audit đầy đủ và toàn bộ QA vận hành đều pass.
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): quyền xử lý ảnh đầu vào và thời hạn lưu trữ đã được phê duyệt; reviewer được ủy quyền truy cập dữ liệu; vùng che đạt yêu cầu nghiệp vụ; output chỉ được gọi là **redacted/pseudonymised**, không mặc nhiên được coi là anonymised hay tự động đáp ứng GDPR/pháp luật Việt Nam.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 36 ảnh | `fixtures/t07_redaction/`; synthetic từ `tools/make_fixtures.py`, seed 42 | CC0-1.0 | Có |
| eval / heldout | 24 ảnh | `fixtures/t07_redaction/`; synthetic từ `tools/make_fixtures.py`, seed 42 | CC0-1.0 | Có |

- Schema & class mapping: inventory `images.csv` gồm `image_id,path,width,height,split`; candidate region dùng `face`/`plate` và tọa độ pixel `x,y,w,h`; output bắt buộc `redactions.csv` gồm `image_id,x,y,w,h`.
- Seed: 42 · Split cố định do fixture cung cấp: 36 ảnh dev (60%) và 24 ảnh eval/heldout (40%). Nhóm không thay đổi split và không tune threshold trên eval/hidden GT.
- `manifest.csv` verified (sha256): có — `python -m tools.verify_manifests` trả `14 manifests, 0 failing`; pipeline bật `strict_provenance: true`.
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: chưa sử dụng. Fixture hiện tại hoàn toàn synthetic, không chứa PII thật. Nếu dùng dữ liệu thật tùy chọn, dữ liệu chỉ được xử lý local, không commit/upload và protocol GT phải được khai báo riêng.

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: ____
- Sơ đồ data flow (input → process → rank/QC → review → decision → report): `manifest/images → detector + padded candidate boxes → validation → risk score + top-15 review queue → approve/reject/edit/escalate → final redactions + redacted images → operational decision + evaluation report`.
- Thành phần offline (model/weights + checksum + license nếu có): detector/model chính đang chờ module của thành viên phụ trách. Phiên bản, checksum và license phải được bổ sung trước demo; pipeline không được tự tải model hay gọi API ngoài.
- Trade-offs đã cân nhắc: tăng padding giúp giảm bỏ sót pixel PII nhưng làm tăng over-redaction; detector nhạy giúp tăng recall nhưng tạo thêm false positive và tải review; blur toàn ảnh có thể đạt miss rate thấp nhưng vi phạm guardrail về over-redaction và không được dùng làm PoC chính.

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): ____
- PoC (mô tả, version/config, commit): ____
- Cùng budget / cùng heldout / cùng seed: xác nhận ____

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: ______ | ____ | ____ | ____; higher/lower? |
| Hard-slice: ______ | ____ | ____ | ____; N=__ |
| Review@B / miss / FP | ____ | ____ | ____; B=__ |
| Runtime / 100 items | ____ | ____ | ____; CPU=__ |

## 05 · Evaluation protocol

- Công thức primary metric, đơn vị đánh giá, TP/FP/FN, denominator: PII Miss Rate = số vùng GT có pixel coverage < 0.9 / tổng số vùng GT cần redact; đơn vị đánh giá là vùng PII; lower is better. Primary chỉ hợp lệ khi over-redaction rate ≤ 0.3.
- Threshold / budget B / K và lúc chốt: coverage threshold 0.9, review budget B=15, over-redaction guardrail 0.3 và seed 42; các giá trị được đóng băng trong config trước khi chạy eval.
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: ____
- Lệnh evaluate chính xác: `python -m src.evaluate --track t__ --pred ... --out ...`

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| | | | | |
| | | | | |

- Failure case 1 (ảnh/metadata + root cause): ____
- Failure case 2: ____
- Latency / compute (máy, CPU, ms/item): ____

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): `out/poc/review_queue.csv`, tối đa 15 vùng; score cao hơn cho confidence thấp, box nhỏ/sát biên và ảnh tối, mờ hoặc có dấu hiệu detector không ổn định.
- Cách override + audit log (`out/poc/audit_log.jsonl`): reviewer có thể `approve`, `reject`, `edit`, `escalate` hoặc `skip`; mọi reject/edit/escalate phải lưu reviewer, action, region ID, before, after, reason và timestamp trong audit log append-only.
- Decision policy + `reason_code` + owner: owner cấu hình là `Nguyen Thanh Phong (Data Owner)`; `reason_code` cụ thể sẽ được sinh theo lỗi provenance/schema/offline, bbox/review/audit chưa đạt hoặc QA pass. Decision runtime không dùng hidden PII Miss Rate vì production pipeline không được đọc GT.
- Khi nào HOLD/REWORK thay vì tự động release: HOLD cho lỗi điều kiện tiên quyết hoặc vi phạm governance; REWORK cho lỗi có thể sửa trong bbox/review/audit/export; chỉ GO khi tất cả kiểm tra vận hành đã pass.

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/<track> --config configs/lab.yaml --output out/ --offline --seed 42
python -m src.evaluate --track t__ --pred out/<file> --out reports/metrics_poc.json
pytest -q
```

- Output của `pytest -q`: ____
- Máy / CPU / OS / Python: ____ · git sha: ____

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: bỏ sót mặt/biển số có thể làm lộ dữ liệu cá nhân; ảnh raw không được đưa lên cloud hoặc repository công khai; model/weights phải được ghi nguồn, phiên bản, checksum và license trước khi sử dụng.
- Điều chưa biết; false alarms; nếu scale 10× thì sao: hiệu năng trên dữ liệu synthetic không bảo đảm tổng quát cho ảnh thật; false positive và padding lớn làm giảm utility; khi dữ liệu tăng 10× cần đo lại throughput, dung lượng ảnh đầu ra, kích thước review queue và năng lực reviewer.
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận: output được mô tả là redacted/pseudonymised, không phải anonymised được bảo đảm. Cơ sở pháp lý, quyền truy cập, retention, mục đích sử dụng và quy trình xử lý sự cố cần DPO/legal/domain owner phê duyệt.
- Kế hoạch cải tiến: đánh giá theo slice `face/plate`, `normal/small/dark/blur/occluded` và kích thước; hiệu chỉnh padding/threshold trên dev; bổ sung failure tests; đo runtime; cải thiện ranking để budget 15 tập trung vào vùng rủi ro nhất.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Người 1 — để trống | | Detector, redactor & ranking | Chờ branch/commit | |
| Nguyễn Thanh Phong | `Nguyen Thanh Phong(K18) <phongnthe182099@fpt.edu.vn>` | Baseline & data protocol | Chờ branch/commit | |
| Người 3 — để trống | | Human review, audit & export | Chờ branch/commit | |
| Người 4 — để trống | | QA, metric & failure analysis | Chờ branch/commit | |
| Nguyễn Nhật Minh | `nminnnnn <nminnnnn@users.noreply.github.com>` | Lead integration, decision policy, report & demo | `8f1f13a` — integration contract, validation schema và demo plan | |
| Member 6 (nếu có) | | Research / ablation / debate | | |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| | | |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
