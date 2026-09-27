# V119 — Rahkaran received cheques: SQL only, all due dates

- Base: V117 (not V118).
- Rahkaran received-cheque open portfolio remains SQL-driven.
- Excel/ListData is validation only and is not used as dashboard source.
- `period=all` has no upper due-date horizon and no row limit.
- UI default label is now `همه سررسیدها (بدون سقف تاریخ)`.
- Added `کل آینده`, `بعد از ۶ ماه`, and `تا ۱۲ ماه` views.
- Added read-only diagnostic endpoint:
  - `GET /api/v1/treasury/cheques/received/sql-scope`
  - reports SQL min/max due date and monthly open-cheque coverage.
- Open holdings remain restricted to:
  - نزد مأمور وصول
  - نزد بانک
  - نزد صندوق
