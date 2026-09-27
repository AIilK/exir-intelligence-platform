# V155 — Customer Turnover Detail Response Fix

- Fixed customer detail API response unpacking: `/customer-intelligence/{counterpart_ref}` returns the actual customer under `customer`.
- Customer detail now replaces stale portfolio/account data with the freshly calculated VoucherItem-based account position.
- Removed misleading FIN3.Account label from customer debt breakdown.
- Official formula remains: fiscal-year `FIN3.VoucherItem`, customer DL, receivable SL codes 123003/123004/123011, SUM(Debit)-SUM(Credit).
- Expected validation for Fahimi/Padina (DL code 810074): 14,716,628,023.4 toman for FY 1405.
