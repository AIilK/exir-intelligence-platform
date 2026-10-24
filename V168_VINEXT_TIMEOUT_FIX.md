# V168 / V169 - Reconciliation SPA runtime fix

- Reconciliation is now served by plain Vite + React instead of Vinext RSC.
- Removes the `virtual:vinext-rsc-entry` / `transport invoke timed out` failure seen on `/reconciliation`.
- Local reconciliation authentication and HTTP-only session cookie are implemented in the Vite dev middleware.
- The protected `/__reconciliation_proxy` still forwards to FastAPI and sends `X-Reconciliation-API-Key`.
- `/api/reconciliation/me` exposes only the signed-in reconciliation username to the browser.
- The old Next/Vinext app files are kept as source/reference, but `npm run dev`, `build`, and `start` no longer invoke Vinext.
