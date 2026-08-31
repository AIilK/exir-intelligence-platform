@echo off
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe python -m venv .venv
call .venv\Scripts\activate
python -m pip install -r requirements-v21.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
