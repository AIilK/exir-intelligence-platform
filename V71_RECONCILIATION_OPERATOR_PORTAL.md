# V71 — پنل مستقل اپراتور مغایرت‌گیری

## نتیجه

- مسیر مستقل کاربر: `/reconciliation`
- بارگذاری صورتحساب XLS/XLSX/CSV با تشخیص خودکار بانک، حساب و ستون‌ها
- نمایش خلاصه سندخورده، نیازمند بررسی، بدون سند و انتقال داخلی
- دانلود مستقیم خروجی Excel
- عدم نمایش منو یا لینک Finance Command Center
- محدودیت یک ایمیل مشخص در Server Component و API Proxy
- محافظت Endpointهای مغایرت Backend با کلید داخلی مستقل
- SQL Server همچنان فقط‌خواندنی است و فایل اصلی بانک ذخیره نمی‌شود

## تنظیم Backend (`backend/.env`)

```env
RECONCILIATION_API_KEY=یک-کلید-طولانی-و-تصادفی
```

## تنظیم Frontend (`frontend/.env.local`)

```env
BACKEND_BASE_URL=http://127.0.0.1:8000
RECONCILIATION_API_KEY=همان-کلید-Backend
RECONCILIATION_OPERATOR_EMAIL=operator@example.com
RECONCILIATION_OPERATOR_USERNAME=reconciliation.operator
RECONCILIATION_OPERATOR_PASSWORD=یک-رمز-قوی
RECONCILIATION_SESSION_SECRET=یک-عبارت-تصادفی-حداقل-۲۴-کاراکتری
DASHBOARD_ALLOWED_EMAILS=manager@example.com,finance.manager@example.com
```

`RECONCILIATION_API_KEY` نباید با پیشوند `NEXT_PUBLIC_` تعریف شود. برای اینکه
اپراتور حتی با واردکردن آدرس `/` به داشبورد نرسد، در محیط عملیاتی حتماً
`DASHBOARD_ALLOWED_EMAILS` نیز تنظیم شود. ایمیل اپراتور را فقط زمانی در این
فهرست قرار دهید که عمداً باید به کل داشبورد هم دسترسی داشته باشد.

## دسترسی

در اجرای محلی، `/reconciliation` به صفحه ورود داخلی خودش هدایت می‌شود و دیگر
به `/signin-with-chatgpt` وابسته نیست. در محیط ChatGPT/Sites، احراز هویت ایمیلی
نیز همچنان قابل استفاده است.
بررسی ایمیل در مرورگر انجام نمی‌شود؛ بنابراین تغییر JavaScript یا واردکردن
مستقیم URL محدودیت را دور نمی‌زند.
