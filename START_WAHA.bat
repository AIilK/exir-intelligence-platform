@echo off
rem WAHA (واتساپ) را با Docker اجرا می‌کند: http://127.0.0.1:3010
rem بار اول یک کلید API تصادفی می‌سازد، در waha\.env و backend\.env (WAHA_API_KEY) می‌نویسد.
rem بعد از اجرا: در اپ صفحه «ارسال واتساپ» ← «اتصال شماره» ← QR را با واتساپ گوشی اسکن کنید.
chcp 65001 >nul
cd /d "%~dp0waha"
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running. Start Docker Desktop and run this file again.
  pause
  exit /b 1
)
if not exist .env (
  powershell -NoProfile -Command "$k=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N'); Set-Content -Encoding ascii .env ('WAHA_API_KEY='+$k); $b='..\backend\.env'; if(-not (Select-String -Quiet -Path $b -Pattern '^WAHA_API_KEY=' -ErrorAction SilentlyContinue)){ Add-Content -Encoding utf8 $b ([Environment]::NewLine+'WAHA_API_KEY='+$k) }"
  echo New WAHA API key created in waha\.env and backend\.env
)
docker compose up -d
echo.
echo WAHA is running on http://127.0.0.1:3010  (restart the backend once if the key was just created)
pause
