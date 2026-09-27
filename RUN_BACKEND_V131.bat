@echo off
cd /d %~dp0backend
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
