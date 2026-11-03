@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem If the dashboard is already running, just open the browser
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul && (
  echo Dashboard is already running.
  start "" http://127.0.0.1:8000
  goto :eof
)
if not exist "frontend\dist\index.html" (
  echo Building frontend...
  pushd frontend
  call npm install || goto :err
  call npm run build || goto :err
  popd
)
python -m pip install -q -r backend\requirements.txt || goto :err
start "" http://127.0.0.1:8000
python backend\app.py
goto :eof
:err
echo Setup failed.
pause
