@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ---- paths of the projects next to this folder in the repo
set "SALES_DIR=%~dp0..\sales"
set "FINANCE_BACKEND=%~dp0..\backend"
set "FINANCE_FRONTEND=%~dp0..\frontend"

echo Project folder: %~dp0
echo.

rem ---- sales backend (FastAPI, port 8000)
call :listening 8000
if errorlevel 1 (
  echo Starting sales backend on 8000...
  start "Sales API 8000" /min cmd /k "cd /d "%SALES_DIR%" && python -m pip install -q -r backend\requirements.txt && python backend\app.py"
) else echo Sales backend already running on 8000.

rem ---- finance backend (FastAPI, port 8010; 8000 is taken by the sales backend)
call :listening 8010
if errorlevel 1 (
  echo Starting finance backend on 8010...
  start "Finance API 8010" /min cmd /k "cd /d "%FINANCE_BACKEND%" && python -m uvicorn app.main:app --host 0.0.0.0 --port 8010"
) else echo Finance backend already running on 8010.

rem ---- standalone finance frontend (port 3000; talks to 8010 via frontend\.env.local)
call :listening 3000
if errorlevel 1 (
  if not exist "%FINANCE_FRONTEND%\.env.local" (
    echo Creating frontend\.env.local pointing to finance backend 8010...
    > "%FINANCE_FRONTEND%\.env.local" echo BACKEND_BASE_URL=http://127.0.0.1:8010
  )
  if not exist "%FINANCE_FRONTEND%\node_modules" (
    echo Installing finance frontend packages...
    pushd "%FINANCE_FRONTEND%"
    call npm install --no-audit --no-fund
    popd
  )
  echo Starting finance frontend on 3000...
  start "Finance UI 3000" /min cmd /k "cd /d "%FINANCE_FRONTEND%" && npx --no-install vite"
) else echo Finance frontend already running on 3000.

rem ---- unified frontend (port 5180)
call :listening 5180
if not errorlevel 1 (
  echo.
  echo Unified dashboard is already running on 5180 - opening the browser.
  echo To restart it, close the old server windows first.
  start "" http://localhost:5180
  timeout /t 8 >nul
  goto :eof
)
if not exist node_modules (
  echo Installing unified frontend packages...
  call npm install --no-audit --no-fund || goto :err
)
echo Starting unified dashboard on 5180...
timeout /t 3 /nobreak >nul
start "" http://localhost:5180
call npx --no-install vite
if errorlevel 1 goto :err
goto :eof

rem ---- returns 0 when the given port is listening, 1 otherwise
:listening
netstat -ano | findstr /R /C:":%~1 .*LISTENING" >nul
exit /b %errorlevel%

:err
echo.
echo Setup failed - see the messages above.
pause
exit /b 1
