# V147 — Customer Collection Position

- Correct Rahkaran customer mapping: ReceiptReceivableNote.CounterPartRef -> FIN3.DL.DLID -> FIN3.DL.ReferenceID -> Party -> Customer/Account.
- Reads authoritative receivable balance from FIN3.Account (active receivable account).
- Keeps account receivable balance separate from open received cheques because cheque receipt posts Dr Notes Receivable / Cr Accounts Receivable.
- Customer profile now shows:
  - Open account receivable (uncovered by cheque)
  - Open cheques held by company
  - Total collection exposure = positive open AR + open cheques
  - Cheque coverage percentage
  - Customer credit balance when Account.Balance is negative
- No predictive cash-remittance claim is made from uncovered balance yet; B2B history remains a separate behavioral signal.
