@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "frontend\.env.local" (
  echo فایل frontend\.env.local پیدا نشد.
  echo ابتدا frontend\.env.example را با نام .env.local کپی و مقادیر امنیتی را تنظیم کنید.
  pause
  exit /b 1
)

if not exist "backend\.env" (
  echo فایل backend\.env پیدا نشد.
  echo ابتدا backend\.env.example را با نام .env کپی و RECONCILIATION_API_KEY را تنظیم کنید.
  pause
  exit /b 1
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$ip=Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object {$_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown'} ^| Select-Object -First 1 -ExpandProperty IPAddress; if($ip){$ip}"`) do set "EXIR_LAN_IP=%%I"

echo.
echo پنل مغایرت‌گیری از سیستم‌های شبکه با یکی از این آدرس‌ها باز می‌شود:
echo http://%COMPUTERNAME%:3000/reconciliation
if defined EXIR_LAN_IP echo http://%EXIR_LAN_IP%:3000/reconciliation
echo.
echo فقط آدرس بالا را به اپراتور مغایرت‌گیری بدهید.
echo Backend از طریق Proxy داخلی فرانت فراخوانی می‌شود و پورت 8000 نیاز به اشتراک‌گذاری ندارد.
echo.

start "Exir Finance Backend" "%ComSpec%" /k call "%~dp0RUN_BACKEND.bat"

cd /d "%~dp0frontend"
if not exist node_modules npm install
npm run dev -- --host 0.0.0.0
pause
