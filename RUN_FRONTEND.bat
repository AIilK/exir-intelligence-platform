@echo off
setlocal
cd /d "%~dp0frontend"
if not exist node_modules (
  echo Installing frontend dependencies...
  call npm install
  if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
  )
)
echo.
echo Starting plain Vite + React frontend (NO Vinext/RSC)...
echo Frontend: http://localhost:3000/reconciliation
call npm run dev
pause
