@echo off
rem Finance backend only (production mode, port 8010). For development with auto-reload use RUN_BACKEND_DEV.bat.
rem Ports used across the platform: finance 8010, sales 8000, unified dashboard 5180, standalone finance UI 3000.
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe python -m venv .venv
call .venv\Scripts\activate
python -m pip install -q -r requirements-v21.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
pause
