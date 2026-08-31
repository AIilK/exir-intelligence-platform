# Exir Finance Intelligence Dashboard — SQL Server

این نسخه دیگر Excel-based نیست و مستقیماً از SQL Server شرکت استفاده می‌کند.

## 1) محیط

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-treasury.txt
```

## 2) تنظیم `.env`

از `.env.example` کپی بگیرید و اطلاعات SQL Server را وارد کنید. رمز عبور را داخل Git قرار ندهید.

## 3) اجرا

```cmd
uvicorn app.main:app --reload
```

Swagger:

`http://127.0.0.1:8000/docs`

## 4) تست اتصال داشبورد

`GET /api/v1/finance/dashboard/health`

خروجی موفق باید `source=company_sql_server` و نام دیتابیس متصل را برگرداند.

## 5) داشبورد

`GET /api/v1/finance/dashboard?allowed_term_days=90&history_days=365&forecast_days=30`

`opening_cash` اختیاری است. اگر مانده نقد قطعی به سرویس داده نشود، سیستم مانده پایانی نقد را حدس نمی‌زند.

## منبع داده

- RPA3.Receipt
- RPA3.Payment
- RPA3.ReceiptReceivableNote
- RPA3.ReceivableNote
- RPA3.PayableNote
- FIN3.DL
- FIN3.Account / FIN3.Transaction در گزارش‌های حساب و پروفایل مالی

## نکته

Risk Score مشتری در نسخه فعلی Rule-based و قابل توضیح است، نه احتمال ML. Prediction جریان نقد نیز فعلاً سناریوی توضیح‌پذیر بر پایه تاریخچه و چک‌های سررسیدشونده است.
