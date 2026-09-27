# V123 — Received Cheque 35-row History Diagnostic

- Dashboard remains SQL-only; Excel is validation/control only.
- Adds `POST /api/v1/treasury/cheques/received/analyze-official-difference`.
- Resolves the 9 official-report-only collector cheques back to SQL without a State 1/2 gate.
- Fetches complete `ReceivableNoteTransaction` history for the 26 SQL-only + resolved 9 Excel-only cheques.
- Returns compact transition signatures plus full transaction histories.
- Does not hard-code cheque IDs and does not change production portfolio rules yet.
