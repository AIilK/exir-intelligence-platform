# Exir Finance Command Center - V169

## Important runtime fix
This version removes Vinext/RSC from the development/build/start path. The previous error:

`transport invoke timed out` / `virtual:vinext-rsc-entry`

was caused by the Vinext RSC runtime while loading `/reconciliation`.

### Run
1. Extract this ZIP into a NEW folder. Do not run the old `V12` folder.
2. Configure `frontend/.env` (copy from `.env.example` if needed).
3. Run `RUN_ALL.bat`, or separately run `RUN_BACKEND.bat` and `RUN_FRONTEND.bat`.
4. Open `http://localhost:3000/reconciliation`.

The frontend is now plain Vite + React. `/reconciliation` is handled as a client-side route and does not enter Vinext RSC.

## Reconciliation security
- Local operator login remains protected by an HTTP-only signed cookie.
- `/__reconciliation_proxy/*` requires the signed session before proxying to FastAPI.
- FastAPI receives `X-Reconciliation-API-Key` when `RECONCILIATION_API_KEY` is configured.

## Existing finance dashboard
The existing dashboard client remains available at `/` and continues to call FastAPI directly on port 8000.
