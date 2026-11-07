# V120 — Rahkaran received cheque full SQL horizon fix

## Root cause
V119 still required `ReceivableNote.State IN (1,2)` before a cheque could enter the open portfolio. The Rahkaran ListData control export proves that valid current holdings continue after 1405/10/30 (including Bahman and Esfand 1405), so master state is not a safe current-holding gate.

## Fix
- Removed the mandatory master-state 1/2 gate.
- Latest approved `ReceivableNoteTransaction` now wins when present.
- Effective state 1/2 is treated as active bank/cashbox holding.
- Explicit latest-operation text can identify collector/bank/cashbox.
- Terminal states 3/4/10 and terminal descriptions are excluded.
- Master state is used only as fallback when no current transaction exists.
- No due-date upper bound is applied to `period=all`.

## Control evidence
The supplied Rahkaran ListData contains approved open holdings after 1405/10/30, including rows in 1405/11 and 1405/12 with current status `نزد بانک` and `نزد صندوق`.
