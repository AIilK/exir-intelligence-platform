@echo off
setlocal
cd /d "%~dp0"
start "Exir FastAPI 8000" cmd /k "cd /d "%~dp0backend" && if not exist .venv\Scripts\python.exe python -m venv .venv && call .venv\Scripts\activate && python -m pip install -r requirements-v21.txt && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
start "Exir Frontend 3000" cmd /k "cd /d "%~dp0frontend" && if not exist node_modules npm install && npm run dev"
echo.
echo Exir Finance Command Center started.
echo Frontend: http://localhost:3000/reconciliation
 echo Backend:  http://localhost:8000
