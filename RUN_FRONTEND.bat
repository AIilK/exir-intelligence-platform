@echo off
cd /d "%~dp0frontend"
if not exist node_modules npm install
npm run dev -- --host 0.0.0.0
pause
