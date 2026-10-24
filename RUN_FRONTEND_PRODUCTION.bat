@echo off
cd /d "%~dp0frontend"
if not exist node_modules npm install
echo در حال ساخت نسخه Production...
npm run build
echo در حال اجرای نسخه Production...
npm run start -- --host 0.0.0.0
pause
