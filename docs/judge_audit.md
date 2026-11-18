# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (judge ở chế độ replay, nhãn judge nằm sẵn trong CSV).
FAIL là lớp dương vì việc của judge là tìm lỗi. Ngưỡng: κ ≥ 0.6, P ≥ 0.8, R ≥ 0.7.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt cả ba | **dùng** (kèm sửa rubric, xem dưới) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không** (κ và R trượt) | **loại** |

Ma trận nhầm lẫn (tp / fp / fn / tn): tone 24 / 4 / 6 / 66; helpful 9 / 0 / 21 / 70.

## ≥5 case audit thủ công (10 bất đồng của tone_ok)
Cột "Ai đúng" là phán đoán của tôi dựa trên cột `note` của người gán nhãn trong CSV (repo không có file rubric tone, nên rubric dưới đây được suy ra từ các ghi chú đó). Người duyệt nên đối chiếu lại với rubric thật của LogiX.

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách. Rubric: thêm "xưng hô chuẩn: LogiX / anh/chị; không dùng 'nha', 'nhé' kiểu thân mật". |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Gọi "bạn" với khách lớn tuổi. Rubric: cấm "bạn" và "bạn ơi" khi nói với khách; judge nhầm "thân thiện" với "đúng mực". |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Giọng ra lệnh dù có "Dạ". Rubric: câu cấm/ra lệnh ("không cần…", "đừng…") là FAIL kể cả khi mở bằng "Dạ"; thêm ví dụ phản mẫu. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Ngắn nhưng đủ ý; judge phạt vì thiếu lời xin lỗi. Rubric: chỉ yêu cầu xin lỗi khi khách khiếu nại hoặc kết quả xấu; thông báo kết quả tốt không cần. |
| 5 | H-051 "…đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | CS LogiX cho phép dùng "refund". Rubric: từ vay mượn trong danh sách cho phép (refund, ship) không bị phạt. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống. Đây thực chất là lỗi cam kết sai (cùng họ FM-08), không phải lỗi giọng: chuyển cho grader code đối chiếu ledger, và rubric tone thêm điều "không hứa hẹn ngoài kết quả hệ thống". |
| 7 | H-070 "…cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Emoji không hợp ngữ cảnh khiếu nại. Rubric: cấm emoji trong phản hồi cho claim. |
| 8 | H-081 "…đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** (người đọc nhầm ticket) | Ghi chú của chính người gán nhãn: nhãn sai. Hành động: sửa nhãn thành FAIL ở bản eval riêng, không sửa CSV công khai. Nếu sửa, κ lên 0.784, P 0.893, R 0.806. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người (nhưng mờ) | Lặp "Dạ" là lỗi gõ, không phải lỗi giọng. Rubric: tách "lỗi chính tả/gõ" khỏi "tone"; lỗi gõ nhỏ không FAIL tone. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ… xin loi vi su bat tien." | PASS | FAIL | Người | Dịch máy mất dấu tiếng Việt. Rubric: thêm "phải có dấu tiếng Việt đầy đủ". |

Mô thức chung của 10 ca: judge sai ở 9/10 ca, theo hai hướng. Judge bỏ lọt khi một dấu hiệu bề mặt tốt ("Dạ", "thân thiện") che lỗi xưng hô hoặc giọng (ca 1, 2, 3, 7, 10, trong đó ca 6 là lỗi cam kết). Judge phạt thừa khi thiếu một dấu hiệu bề mặt nhưng nội dung đủ (ca 4, 5, 9). Cả hai hướng đều xuất phát từ rubric thiếu quy tắc rõ, không phải judge "dở". Chỉ có ca 8 là nhãn người sai.

## Kết luận
- **Loại `helpful`.** Precision = 1.0 nhưng recall = 0.3 (bắt 9 trên 30 lỗi thật, bỏ lọt 21), κ = 0.375. Phân rã theo lý do người gán nhãn (`human_failure`): judge bỏ lọt **18/18** ca "sai tiền" và 3/3 ca "sai xưng hô", và bắt **được toàn bộ** ca "giọng cụt" (4), "không hỏi lại mã đơn" (3) và "trả lời lạc đề" (2). Judge không có ledger nên không kiểm được số tiền: một reply trôi chảy mà nói sai số tiền luôn qua. Dùng nó làm gate sẽ cho lỗi tiền lọt qua mà vẫn xanh. Số tiền phải do code chấm, tức metric `reply_amount_matches_ledger` (FM-08) mà tôi đã thêm ở M3.
- **Dùng `tone_ok` làm tín hiệu theo dõi, chưa làm gate chặn cứng.** Qua cả ba ngưỡng, nhưng R = 0.8 nghĩa là 1/5 lỗi giọng vẫn lọt, và 9/10 bất đồng đều do rubric thiếu quy tắc. Sau khi thêm các quy tắc ở bảng và sửa nhãn H-081, cần hiệu chuẩn lại trên nhãn người mới.
- **Hiệu chỉnh tỉ lệ lỗi (Rogan-Gladen):** tone quan sát 0.28 → hiệu chỉnh 0.30 (khớp tỉ lệ lỗi thật 30/100); helpful quan sát 0.09 → hiệu chỉnh 0.30. Judge helpful báo ít lỗi hơn thực tế đến 3 lần.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (n = 100, cùng phân phối), nên κ chưa phải số held-out. Cần nhãn người mới trước khi tin vào chỉ số này. Phán đoán "ai đúng" ở trên dựa trên ghi chú trong CSV, không phải rubric chính thức.
