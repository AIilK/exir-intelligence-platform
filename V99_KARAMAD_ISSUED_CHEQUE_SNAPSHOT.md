# V99 — KarAmand Issued Cheque Registered Snapshot

- Added a dedicated parser for the KarAmand issued-cheque register export (`شناسه`, `شماره چک`, `اسناد پرداختنی`, `تاریخ ثبت`, `تاریخ سررسید`, `مبلغ`, `تفضیلی`, `شماره صیادی`).
- The final aggregate row (without cheque id) is ignored.
- The uploaded source contains 14 real registered issued cheques totaling 89,755,000,000 rial (8.9755B toman).
- Snapshot semantics: each new issued-cheque Excel replaces the previous KarAmand issued-cheque snapshot; it is not appended.
- UI now allows updating issued-cheque KarAmand snapshot from the cheque source page.
- KarAmand issued-cheque page shows all registered rows, not only the Rahkaran 20-day open-cheque window.
- Explicit data-quality message: future coverage is incomplete; absence of future rows does not mean absence of future commitments.
- Current source reports no returned issued cheques; no return rate is inferred.
- Known future registered cheques can still appear as known commitments, but they are labeled as incomplete future coverage.
- Issued-cheque rows flow into KarAmand customer history using the `تفضیلی` customer/counterparty field when available.

Validation:
- 9 backend tests passed for issued snapshot parsing/replacement plus existing KarAmand/open-issued behavior.
