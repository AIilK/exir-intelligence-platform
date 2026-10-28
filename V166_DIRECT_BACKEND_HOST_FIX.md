# V166 — Direct Backend Host Fix

## Root cause
Vite 8 + Vinext RSC was handling `/api/v1/*` requests instead of the intended Vite proxy, producing 404 responses for valid FastAPI routes. The browser logs showed valid FastAPI endpoints such as `/api/v1/finance/agents/latest` returning `404` from the frontend server.

## Fix
The dashboard now builds its FastAPI base URL in the browser from `window.location.hostname` and port `8000`:
- local: `http://localhost:8000`
- LAN: `http://192.168.x.x:8000`

FastAPI CORS already allows the dashboard LAN origin on port 3000 and the backend runner binds to `0.0.0.0:8000`.

The protected reconciliation proxy remains unchanged.
