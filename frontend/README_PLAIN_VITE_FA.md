# V161 — Plain Vite + React

این نسخه بدون Vinext و بدون RSC اجرا می‌شود.

## اجرا

```bash
npm install
npm run dev
```

Frontend:
- http://localhost:3000/

Backend باید روی:
- http://127.0.0.1:8000

یا مقدار `BACKEND_BASE_URL` در `.env` تنظیم شود.

## نکته
منطق داشبورد، ظاهر، CSS، APIهای مالی و منطق چک‌های دریافتی کارآمد در `app/dashboard-client.tsx` حفظ شده‌اند. فقط لایه اجرای Frontend از Vinext/RSC به Vite + React تغییر کرده است.
