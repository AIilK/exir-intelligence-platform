# V80 — Cheque Daily/City Filters + Received Status

- Unified date filters for received and issued cheques: all, exact day, overdue 20 days, next 7/20 days, next 1/3/6 months.
- Unified source/city filter for both cheque types: all cities + Rahkaran, Rahkaran only, or a KarAmand branch/city.
- Received cheque status now displays the business/system status from Rahkaran (`state_label`) instead of only a due-risk badge.
- KarAmand received cheques display `ثبت‌شده در کارآمد` when no native lifecycle status exists in the imported Excel.
- Bank/branch column reads `branch_name`, `bank_branch_name`, or `branch` consistently.
