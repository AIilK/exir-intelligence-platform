# V127 — KarAmand ListData received-cheque schema fix

- The KarAmand received-cheque replacement endpoint now accepts both the legacy portfolio export and the newer ListData-style export.
- New ListData schema is detected from: شماره سریال، شماره صیاد، تاریخ سررسید، مبلغ، شعبه، وضعیت فعلی.
- Current cheque status is read directly from وضعیت فعلی.
- Sayad number is used as the stable snapshot key, with serial number as fallback.
- The upload remains a full snapshot replacement; the previous KarAmand received-cheque snapshot is removed only after successful parsing.
- No Rahkaran SQL received-cheque rule was changed.

Validation performed with the available ListData control workbook: 4,299 rows parsed successfully and all nine observed current-status values were preserved.
