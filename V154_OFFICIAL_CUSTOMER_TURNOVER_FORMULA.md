# V154 — Official Rahkaran Customer Turnover Formula

Customer receivable/debt calculation was replaced with the validated Rahkaran voucher formula.

- Source: `FIN3.VoucherItem` + `FIN3.Voucher`
- Customer dimension: customer `FIN3.DL.Code` matched to `DLLevel4/5/6`
- Receivable SL codes:
  - `123003` — حسابهای دریافتنی تجاری
  - `123004` — حسابهای دریافتنی بابت برگشتی
  - `123011` — حسابهای دریافتنی اشخاص
- Period: active Rahkaran ledger fiscal year (`GNR3.LedgerFiscalYear`, LedgerRef=1)
- Formula: `SUM(Debit) - SUM(Credit)`
- Internal transfers between receivable SLs cancel automatically.

Validated reference: customer DL 810074 produced 14,716,628,023.4 toman for FY 1405.
