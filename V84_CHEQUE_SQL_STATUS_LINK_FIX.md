# V84 — Cheque SQL Status Link Fix

## Fixed
- Removed the accidental `PayableNoteTransaction` / `PayableNoteID` status-document lookup from `get_open_received_cheques`.
- Restored the missing `OUTER APPLY ... AS status_link` in `get_open_issued_cheques` before `status_link` is referenced in SELECT/WHERE.
- Kept the V83 business rule only for issued cheques: an approved status/collection document marks the issued cheque as posted and excludes it from open obligations / future cash flow.

## Regression tests
- Received-cheque SQL contains no payable-note status-link references.
- Issued-cheque SQL defines `status_link` before using it.
- Open issued cheques still exclude cheques with a qualifying collection/status document.
