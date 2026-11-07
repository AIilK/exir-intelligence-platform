# V146 — Customer cheque drill-down history fix

## Problem
Customer profile historical KPI could report Rahkaran cheques while the detail table was empty. The KPI is historical (all approved received-cheque source rows), but the drill-down loaded only currently-open holdings plus returned cheques. Collected/closed historical cheques therefore had no detail row.

## Fix
- Added `FinancePredictionService.customer_all_cheques(counterpart_ref)`.
- Exact one-row-per-ReceivableNote history for the selected Rahkaran customer.
- Same approved Receipt/normal cheque/guarantee exclusions as customer behavior scope.
- Includes collected, returned, open/in-progress and other historical states.
- Customer Intelligence detail payload now exposes `all_cheques` while retaining `open_cheques` and `returned_cheques` for compatibility.
- Customer profile "کل چک‌ها" uses `all_cheques` when available.
- Added a "وصول‌شده" drill-down filter.
- Returned rows are not duplicated when `all_cheques` is present.

## Validation
Python syntax compilation passed for the modified backend services. Live Rahkaran SQL was not available in this build environment, so the exact Fehimi rows must be validated against the company database after restart.
