# V105 — KarAmand Transfer Snapshots + Bank-to-Bank Split

- Imported the new full KarAmand received-transfer and paid-transfer exports as replaceable snapshots.
- Received transfers: 7,666 rows in the supplied snapshot.
- Paid transfers: 1,338 rows in the supplied snapshot.
- Paid-transfer summary now separates:
  - total paid transfers
  - internal bank-to-bank transfers
  - all other paid transfers
- Internal bank-to-bank transfers remain excluded from net Cash Flow (zero company-level effect).
- Unified customer files automatically consume these refreshed transfer snapshots.
- Future imports of received/paid transfer exports replace the previous snapshot rather than leaving stale rows behind.
