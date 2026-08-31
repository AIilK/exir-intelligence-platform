# Exir Kadous - Finance Intelligence Dashboard MVP

این نسخه برای نمایش خودکار وضعیت مالی، پیش‌بینی جریان نقد، هشدارها، Risk Score و پیشنهاد اقدام ساخته شده است و برای استفاده از آن لازم نیست مدیر سؤال تایپ کند.

## 1) نصب

در پوشه backend:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-treasury.txt
```

## 2) فایل داده

فایل نمونه همراه پروژه در مسیر زیر قرار دارد:

```text
data/cashflow0510.xlsx
```

برای فایل دیگر می‌توانید در `.env` یا Environment Variable بنویسید:

```text
FINANCE_DASHBOARD_EXCEL_PATH=data/cashflow0510.xlsx
```

## 3) اجرا

```cmd
uvicorn app.main:app --reload
```

سپس Swagger:

```text
http://127.0.0.1:8000/docs
```

Endpoint اصلی:

```text
GET /api/v1/finance/dashboard
```

مثال سیاست چک 90 روزه:

```text
GET /api/v1/finance/dashboard?allowed_term_days=90
```

اگر شرکت برای یک تست سقف 3 ماه را 90 روز در نظر می‌گیرد همین مقدار را استفاده کنید. برای سیاست متفاوت مقدار را تغییر دهید.

## 4) خروجی اصلی

Dashboard یک JSON یکپارچه می‌دهد شامل:

- `kpis`: مانده بانک، چک باز، برگشتی، issued و تعداد هشدار بحرانی
- `cashflow_forecast`: پیش‌بینی تعهدی 30/60/90 روزه
- `cheque_risk`: وضعیت Cleared / Received / Under Collection / Returned / Issued / Paid
- `counterparty_risk`: Risk Score توضیح‌پذیر طرف‌های مقابل
- `alerts`: هشدارهای بحرانی و مهم
- `recommendations`: پیشنهاد اقدام برای مدیر مالی
- `executive_summary`: خلاصه مدیریتی آماده نمایش در بالای داشبورد

## 5) نکته مهم درباره Prediction

نسخه اول **مدل ML تقلبی نمی‌سازد**. پیش‌بینی Cash Flow بر اساس تاریخ و مبلغ تعهدات ثبت‌شده انجام می‌شود و Risk Score بر اساس قواعد قابل توضیح است.

برای ساخت احتمال واقعی مثل «احتمال برگشت این مشتری 37%» باید از ERP تاریخچه مشتری با شناسه ثابت، تاریخ دریافت/سررسید، نتیجه وصول، مبلغ، مانده، دیرکرد و سابقه برگشتی استخراج و مدل آموزش داده شود.

## 6) مرحله اتصال به SQL Server

بعد از تأیید خروجی MVP، تنها Reader اکسل با Repository SQL Server جایگزین می‌شود. Serviceهای Risk/Alert/Recommendation و API می‌توانند ثابت بمانند.
