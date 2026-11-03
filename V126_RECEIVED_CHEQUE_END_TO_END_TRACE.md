# V126 — Received Cheque End-to-End Trace

Diagnostic only; production dashboard rules are unchanged.

Endpoint:
`GET /api/v1/treasury/cheques/received/trace`

Supply at least one of:
- `cheque_id`
- `serial_number`
- `sayad_number`
- `document_number` (Rahkaran Receipt number)

The response shows the raw ReceivableNote master row, Gregorian/Jalali DueDate, amount in rial/toman, full ReceivableNoteTransaction history, linked Receipts, and the core values the API should expose. This is intended to isolate SQL vs API/frontend merge/date mapping mismatches.
