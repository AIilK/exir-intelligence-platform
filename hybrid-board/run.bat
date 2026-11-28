@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Hybrid target board on its own port (default 2000), open to the local network (no login on this page).
rem Needs the sales dashboard (port 8000) running. Only this PC: set BOARD_HOST=127.0.0.1 before running.
rem Other PCs need Windows Firewall to allow the port once (as administrator):
rem   netsh advfirewall firewall add rule name="Hybrid board 2000" dir=in action=allow protocol=TCP localport=2000 profile=private,domain
if "%BOARD_PORT%"=="" set BOARD_PORT=2000
set PY=..\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
start "" http://127.0.0.1:%BOARD_PORT%
"%PY%" -X utf8 server.py
