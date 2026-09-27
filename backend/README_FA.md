# فرانت مرکز فرماندهی Agentهای مالی اکسیر کادوس

## پیش‌نیاز

- Node.js نسخه 22 یا جدیدتر
- اجرای FastAPI روی پورت 8000

## اجرا در Windows

در CMD وارد پوشه فرانت شوید و اجرا کنید:

```bat
npm install
npm run dev -- --host 0.0.0.0
```

سپس در همان سیستم باز کنید:

```text
http://127.0.0.1:3000
```

از یک سیستم دیگر در شبکه داخلی:

```text
http://IP-SERVER:3000
```

## اتصال به Backend

فرانت به‌صورت پیش‌فرض از آدرس زیر استفاده می‌کند:

```text
http://HOSTNAME:8000/api/v1/finance
```

از دکمه تنظیمات بالای داشبورد می‌توانید آدرس API را تغییر دهید.

Backend باید با این دستور اجرا شود:

```bat
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Build نهایی

```bat
npm run build
```

این نسخه برای اجرای محلی شرکت به Cloudflare، Wrangler، Miniflare یا فایل
`.openai/hosting.json` وابسته نیست.
