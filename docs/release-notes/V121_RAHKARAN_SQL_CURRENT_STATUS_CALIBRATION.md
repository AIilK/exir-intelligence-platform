# V121 — Rahkaran SQL Current Status Calibration

- Dashboard source remains 100% Rahkaran SQL; Excel is not used as runtime data.
- Latest approved ReceivableNoteTransaction now exposes BankAccountRef, DocumentItemType, DocumentRef and DocumentNumber in addition to State/Description.
- A non-null latest BankAccountRef is treated as strong SQL evidence for the bank holding bucket.
- Explicit collector text remains collector; waiting-for-collector is excluded.
- Terminal descriptions (returned/protested/collected/cashed/transferred to third party) are excluded.
- State 1/2 remain fallback only after stronger current-operation evidence.
- `period=all` remains unbounded by DueDate.

## New audit endpoint
`GET /api/v1/treasury/cheques/received/status-signatures`

This groups Rahkaran rows by master State, latest transaction State, DocumentItemType, presence of BankAccountRef and description class. It is intended to calibrate the official Rahkaran `وضعیت فعلی` logic from SQL without making Excel the dashboard source.

Official ListData remains validation/reference only. Runtime finance numbers are not read from it.
