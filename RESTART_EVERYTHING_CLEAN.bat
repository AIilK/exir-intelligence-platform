@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  1) بستن هر سرور قدیمی که روی پورت 8000 (بک‌اند) یا 3000 (فرانت) روشنه
echo ============================================
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo در حال بستن پردازش قدیمی بک‌اند (PID %%p)...
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do (
    echo در حال بستن پردازش قدیمی فرانت (PID %%p)...
    taskkill /F /PID %%p >nul 2>&1
)
timeout /t 2 >nul

echo ============================================
echo  2) ساخت نسخه Production جدید فرانت (کد قدیمی کش‌شده رو دور می‌ریزه)
echo ============================================
cd /d "%~dp0frontend"
if not exist node_modules npm install
rmdir /s /q dist 2>nul
npm run build
if errorlevel 1 (
    echo ساخت نسخه Production با خطا مواجه شد. لطفاً پیام بالا رو بفرستید.
    pause
    exit /b 1
)

echo ============================================
echo  3) روشن کردن بک‌اند (پنجره جدید)
echo ============================================
cd /d "%~dp0backend"
start "Exir Backend" cmd /k "if not exist .venv\Scripts\python.exe python -m venv .venv && call .venv\Scripts\activate && python -m pip install -r requirements-v21.txt && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

echo ============================================
echo  4) روشن کردن فرانت Production (همین پنجره)
echo ============================================
cd /d "%~dp0frontend"
npm run start -- --host 0.0.0.0

pause
