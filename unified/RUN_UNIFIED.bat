@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem ---- only port 5180 is open to the network. The two backends listen on 127.0.0.1 and are reached
rem ---- through the 5180 proxy (vite.config.js); the standalone finance UI (3000) is not started.
rem ---- Paths may contain ")" (e.g. "...-main (1)"), so no ( ) blocks use these variables.
set "SALES_DIR=%~dp0..\sales"
set "FINANCE_BACKEND=%~dp0..\backend"

rem ---- sales backend (FastAPI, 127.0.0.1:8000). Packages: run "python -m pip install -r backend\requirements.txt" once.
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if not errorlevel 1 goto :sales_done
echo Starting sales backend...
start "Sales API" /min /d "%SALES_DIR%" cmd /k "set SALES_HOST=127.0.0.1&& python backend\app.py"
:sales_done

rem ---- finance backend (FastAPI, 127.0.0.1:8010)
netstat -ano | findstr /R /C:":8010 .*LISTENING" >nul
if not errorlevel 1 goto :finance_done
echo Starting finance backend...
start "Finance API" /min /d "%FINANCE_BACKEND%" cmd /k python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
:finance_done

rem ---- unified dashboard (port 5180): production build, much faster to open than the dev server
if exist node_modules goto :installed
echo Installing frontend packages...
call npm install --no-audit --no-fund
if errorlevel 1 goto :err
:installed
netstat -ano | findstr /R /C:":5180 .*LISTENING" >nul
if errorlevel 1 goto :build
start "" http://localhost:5180
goto :eof

:build
echo Building the dashboard...
call npx vite build --logLevel warn
if errorlevel 1 goto :err

rem ---- wait (up to ~90s) for both backends so the first page load has data
set /a WAITED=0
:wait_api
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if errorlevel 1 goto :not_yet
netstat -ano | findstr /R /C:":8010 .*LISTENING" >nul
if not errorlevel 1 goto :api_up
:not_yet
if %WAITED% GEQ 90 goto :api_up
if %WAITED%==0 echo Waiting for the backends...
timeout /t 3 /nobreak >nul
set /a WAITED+=3
goto :wait_api
:api_up
start "" http://localhost:5180
call npx vite preview
goto :eof

:err
echo Setup failed.
pause
