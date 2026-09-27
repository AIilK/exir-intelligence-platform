# V73 — دسترسی پنل مغایرت از سیستم دیگر شبکه

## راه‌اندازی یک‌باره

1. روی سیستم سرور، روی `SETUP_RECONCILIATION_LAN_ACCESS.bat` راست‌کلیک و
   `Run as administrator` را اجرا کنید. این فایل فقط TCP/3000 را برای
   `Private + LocalSubnet` باز می‌کند.
2. در `frontend/.env.local` مقدار زیر برای شبکه HTTP داخلی باشد:

```env
BACKEND_BASE_URL=http://127.0.0.1:8000
RECONCILIATION_COOKIE_SECURE=false
```

3. کلید `RECONCILIATION_API_KEY` در `frontend/.env.local` و `backend/.env`
   باید کاملاً یکسان باشد.

## اجرای روزانه

روی سیستم سرور `RUN_RECONCILIATION_LAN.bat` را اجرا کنید. فایل، Backend و
Frontend را بالا می‌آورد و دو آدرس نشان می‌دهد:

```text
http://COMPUTER-NAME:3000/reconciliation
http://192.168.x.x:3000/reconciliation
```

از سیستم اپراتور ابتدا آدرس نام کامپیوتر را باز کنید. اگر نام در شبکه resolve
نشد، آدرس IP نمایش‌داده‌شده را استفاده کنید.

## محدوده دسترسی

- فقط پورت 3000 برای شبکه داخلی باز می‌شود.
- Backend روی 8000 از طریق Proxy سمت سرور استفاده می‌شود و لازم نیست در
  فایروال به اشتراک گذاشته شود.
- SQL Server فقط‌خواندنی باقی می‌ماند.
- ورود اپراتور همچنان با نام کاربری، رمز و Session امضاشده انجام می‌شود.
- در صورت فعال‌سازی HTTPS، مقدار `RECONCILIATION_COOKIE_SECURE=true` شود.
