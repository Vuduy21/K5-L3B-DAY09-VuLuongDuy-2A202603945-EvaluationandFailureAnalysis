# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: C-002@55, swarm tin ticket hơn DB

| Trường | Nội dung |
|---|---|
| Trial | `swarm C-002@55`, item `E-002`, trong `reports/baseline_v1.json` (run ID `E-swarm-20261118-32a9`); đây là trial duy nhất fail trong 70 trial của baseline. |
| Triệu chứng | Grader Lab 8: `status resolved != denied`. Ledger hoàn 20.000đ (1 dòng) trong khi nhãn là 0đ. `refund_amount_correct` và `db_fact_kept` đều False. Cùng claim ở seed 11, 22, 33, 44 đúng. |
| Bước sai đầu tiên | Event 3, `model_override {"delay_days": 5}`: ticket nói "trễ 5 ngày", dòng order ghi 2 ngày. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` chỉ có `facts: {}` và tool đọc; event 2 `investigator` trả order hiển thị đúng (`visible: true`, delay 2 ngày), nên dữ liệu đầu vào đúng. Event 3 là lúc số 5 đè số 2. Event 4 `quote` (20.000đ, clause SHIP-LATE-03) chỉ là hệ quả: với 2 ngày quote là 0 (`no_entitlement`). |
| Failure mode | FM-03 `ticket_trust` (xem `docs/failure_taxonomy.md`). |
| Đối chứng | `fixed C-002@55`: không có event `model_override`; event 3 `quote` = 0 (`no_entitlement`), reply "chưa đủ điều kiện hoàn", ledger 0, Lab 8 PASS. |
| Regression test | `tests/test_lab9_trace_case.py`: `test_swarm_seed_55_overrides_db_with_ticket` (bắt lỗi: có `model_override` trước `quote`, `DbFactKept` và `RefundAmountCorrect` đều False), `test_seeded_regression_trips_the_same_graders` (cùng lỗi trên variant), `test_fixed_never_overrides_db_fact` (5 seed, `fixed` pass). Đã chạy: lỗi fail đúng chỗ, `fixed` pass. |
| Chưa chắc chắn | Trace chỉ cho thấy swarm dùng số của ticket khi `seed % 5 == 0`; không chứng minh được vì sao với một LLM thật. Lỗi chỉ xuất hiện ở 1 trong 5 seed nên một lần chạy đơn lẻ có thể không thấy. Mock LLM nên "model" ở đây là mã giả lập, không phải suy luận thật. |

Tái lập:
```bash
cd src
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55
python -m pytest -q -m student -o addopts= -k lab9_trace
```

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
