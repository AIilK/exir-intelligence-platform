@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ---- paths of the two projects (next to this folder in the repo)
set "SALES_DIR=%~dp0..\sales"
set "FINANCE_BACKEND=%~dp0..\backend"

rem ---- sales backend (FastAPI, port 8000) - same as sales-dashboard\run.bat
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul || (
  echo Starting sales backend on 8000...
  start "Sales API 8000" /min cmd /k "cd /d "%SALES_DIR%" && python backend\app.py"
)

rem ---- finance backend (FastAPI, port 8010; 8000 is taken by the sales backend)
netstat -ano | findstr /R /C:":8010 .*LISTENING" >nul || (
  echo Starting finance backend on 8010...
  start "Finance API 8010" /min cmd /k "cd /d "%FINANCE_BACKEND%" && python -m uvicorn app.main:app --host 0.0.0.0 --port 8010"
)

rem ---- unified frontend (port 5180)
if not exist node_modules (
  echo Installing frontend packages...
  call npm install --no-audit --no-fund || goto :err
)
netstat -ano | findstr /R /C:":5180 .*LISTENING" >nul && (
  start "" http://localhost:5180
  goto :eof
)
timeout /t 3 /nobreak >nul
start "" http://localhost:5180
call npx vite
goto :eof

:err
echo Setup failed.
pause
