# V44 — Automatic Excel Cash Flow

## Configured folders

Place new `.xlsx` files in:

`C:\Users\Ai.WWW\Desktop\Exir_Finance_Agent_Command_Center_V12\Inbox`

Successfully processed files move to:

`C:\Users\Ai.WWW\Desktop\Exir_Finance_Agent_Command_Center_V12\Archive`

The folders are created automatically when the Backend starts and the folder
service is first used. Values can be overridden in `backend/.env`.

## Behaviour

- scans every 15 minutes;
- ignores files younger than 30 seconds;
- detects duplicates by SHA-256 content hash;
- processes only `.xlsx` files;
- detects the Jalali date from the workbook or filename;
- keeps one authoritative snapshot per Jalali date;
- moves successful files to Archive;
- leaves invalid files in Inbox and reports the error in the dashboard;
- uses latest `liquidity_rial` as Cash Flow opening balance.

## API tests

- `GET /api/v1/finance/cashflow-excel/folder/status`
- `POST /api/v1/finance/cashflow-excel/folder/scan`
- `GET /api/v1/finance/cashflow-excel/months`
- `POST /api/v1/finance/agents/run-all`

## Run

Backend:

```bat
cd backend
.venv\Scripts\activate
pip install -r requirements-v21.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bat
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

Open the `Cash Flow روزانه` page. The automatic-folder card displays the exact
path, waiting file count, last successful workbook, last error and manual scan.
