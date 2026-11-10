@echo off
setlocal
cd /d "%~dp0"

rem ---- Same as RUN_UNIFIED.bat but on separate ports, so it can run next to another copy on 5180/8000/8010.
rem ---- dashboard 5190, finance backend 8020, sales backend 8030 (backends listen on 127.0.0.1 only).
set "UNIFIED_PORT=5190"
set "FIN_PORT=8020"
set "SALES_PORT=8030"
set "FINANCE_API=http://127.0.0.1:%FIN_PORT%"
set "SALES_API=http://127.0.0.1:%SALES_PORT%"
set "FINANCE_API_URL=%FINANCE_API%"
set "SALES_API_URL=%SALES_API%"
set "SALES_HOST=127.0.0.1"
set "SALES_DIR=%~dp0..\sales"
set "FINANCE_BACKEND=%~dp0..\backend"

set "VENV_PY=%~dp0..\.venv\Scripts\python.exe"
if exist "%VENV_PY%" goto :venv_ok
echo Creating Python virtual env (.venv)...
python -m venv "%~dp0..\.venv"
if errorlevel 1 goto :err
:venv_ok
"%VENV_PY%" -m pip install -q --disable-pip-version-check -r "%FINANCE_BACKEND%\requirements-v21.txt" -r "%SALES_DIR%\backend\requirements.txt"
if errorlevel 1 goto :err

netstat -ano | findstr /R /C:":%SALES_PORT% .*LISTENING" >nul
if not errorlevel 1 goto :sales_done
echo Starting sales backend on %SALES_PORT%...
start "Sales API %SALES_PORT%" /min /d "%SALES_DIR%" cmd /k ""%VENV_PY%" backend\app.py"
:sales_done

netstat -ano | findstr /R /C:":%FIN_PORT% .*LISTENING" >nul
if not errorlevel 1 goto :finance_done
echo Starting finance backend on %FIN_PORT%...
start "Finance API %FIN_PORT%" /min /d "%FINANCE_BACKEND%" cmd /k ""%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %FIN_PORT%"
:finance_done

if exist node_modules goto :installed
echo Installing frontend packages...
call npm install --no-audit --no-fund
if errorlevel 1 goto :err
:installed
netstat -ano | findstr /R /C:":%UNIFIED_PORT% .*LISTENING" >nul
if errorlevel 1 goto :build
start "" http://localhost:%UNIFIED_PORT%
goto :eof

:build
echo Building the dashboard...
call npx vite build --logLevel warn
if errorlevel 1 goto :err

set /a WAITED=0
:wait_api
netstat -ano | findstr /R /C:":%SALES_PORT% .*LISTENING" >nul
if errorlevel 1 goto :not_yet
netstat -ano | findstr /R /C:":%FIN_PORT% .*LISTENING" >nul
if not errorlevel 1 goto :api_up
:not_yet
if %WAITED% GEQ 90 goto :api_up
if %WAITED%==0 echo Waiting for the backends...
timeout /t 3 /nobreak >nul
set /a WAITED+=3
goto :wait_api
:api_up
start "" http://localhost:%UNIFIED_PORT%
node server.mjs
goto :eof

:err
echo Setup failed.
pause
