# V120 — Rahkaran future received cheques

Root cause confirmed from live SQL: future ReceivableNote rows exist through 2027-03-20 and have State 1/2, but their latest ReceivableNoteTransaction description is a neutral receipt operation such as `برگ دریافت چک ...`. V117/V119 only used State 1/2 as fallback when the description was empty, so these valid future notes were dropped.

Fix: after excluding terminal outcomes, State 1/2 is now the holding fallback even when the latest description is non-empty. State 1 maps to نزد صندوق and State 2 to نزد بانک; explicit مأمور وصول text remains its own bucket. No upper DueDate limit is applied for period=all.
