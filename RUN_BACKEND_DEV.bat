@echo off
rem Finance backend for DEVELOPMENT: restarts on every code change (--reload). Do not use for daily work.
cd /d "%~dp0backend"
if not exist ..\.venv\Scripts\python.exe python -m venv ..\.venv
call ..\.venv\Scripts\activate
python -m pip install -q -r requirements-v21.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
pause
