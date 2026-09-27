# V128 — KarAmand received-cheque refresh fix

- Fixes stale dashboard KPI/agent numbers after replacing the KarAmand received-cheque snapshot.
- After upload, the frontend now reloads both the unified Treasury cheque rows and the latest rebuilt Finance Agent pack.
- Upload response now includes `snapshot_verification` with before/after count and amount, so replacement can be audited immediately.
- No Rahkaran SQL rule was changed.

## Validation on the uploaded KarAmand file
- Parsed business rows: 2,261 (summary/footer row excluded)
- Full snapshot amount: 1,177,968,456,344 rial
- Open by latest explicit status: 1,970 cheques
- Open amount: 1,011,019,402,636 rial = 101,101,940,263.6 toman
- Status counts: 1,727 `واگذار شده`, 243 `نزد صندوق`, 291 unknown.
- Targeted backend regression tests: 6 passed.
- Frontend production build could not be executed in this sandbox because the local `vinext` binary/dependencies are not installed.
