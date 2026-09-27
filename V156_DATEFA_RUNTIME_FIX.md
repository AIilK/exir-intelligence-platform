# V156 — Customer detail date runtime fix

- Fixed `ReferenceError: dateFa is not defined` in `CustomerCollectionDetail`.
- Latest invoice date now uses backend-provided `date_jalali`, with ISO date fallback.
- No receivable/debt formula changes in this patch.
