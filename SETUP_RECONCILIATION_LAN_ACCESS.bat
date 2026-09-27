@echo off
chcp 65001 >nul
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo برای تنظیم فایروال، دسترسی Administrator لازم است.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$name='Exir Reconciliation Frontend - LAN';" ^
  "$existing=Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue;" ^
  "if(-not $existing){New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000 -Profile Private -RemoteAddress LocalSubnet | Out-Null};" ^
  "Write-Host 'دسترسی پورت 3000 فقط برای شبکه داخلی Private فعال شد.' -ForegroundColor Green"

echo.
echo تنظیم شبکه انجام شد. اکنون RUN_RECONCILIATION_LAN.bat را اجرا کنید.
pause
