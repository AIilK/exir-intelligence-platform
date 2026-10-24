# Finance Intelligence V2

این نسخه مرحله اول Prediction/Decision Support مالی است و تمام ورودی‌های عددی آن از SQL Server شرکت می‌آیند.

## قابلیت‌های جدید

1. Explainable Alert Engine
2. پیش‌بینی وصول مبتنی بر چک هر مشتری
3. برآورد ریسک دیرکرد پرداخت/وصول
4. برآورد احتمال برگشت چک‌های دریافتی آینده
5. Forecast روزانه فشار و کسری نقدینگی
6. پیشنهاد اولویت وصول مشتریان

## APIها

- `GET /api/v1/finance/dashboard`
- `GET /api/v1/finance/predictions/customers`
- `GET /api/v1/finance/predictions/customers/{counterpart_ref}`
- `GET /api/v1/finance/predictions/cheque-return`
- `GET /api/v1/finance/predictions/cash-shortage`
- `GET /api/v1/finance/collection-priorities`

### Cash Shortage
برای تشخیص کسری مطلق، `opening_cash` را ارسال کنید:

`GET /api/v1/finance/predictions/cash-shortage?forecast_days=30&opening_cash=100000000000`

اگر opening_cash ارسال نشود، سیستم فقط روزهای فشار خالص و cumulative net change را گزارش می‌کند و کسری مطلق را حدس نمی‌زند.

## تفکیک داده‌ها

- `actual`: داده مستقیم ERP/SQL
- `calculated`: محاسبه قطعی روی داده واقعی
- `forecast`: برآورد توضیح‌پذیر
- `recommendation`: پیشنهاد تصمیم‌یار

## نکته مهم درباره Prediction

در V2 درصد دیرکرد و برگشت **مدل ML آموزش‌دیده نیست**. این مقادیر با نرخ‌های تجربی، Bayesian smoothing، نسبت معوق، انحراف از سیاست سررسید و ویژگی‌های فعلی چک محاسبه می‌شوند. بنابراین قابل توضیح و قابل ممیزی هستند، اما نباید به‌عنوان احتمال قطعی معرفی شوند.

پیش‌بینی وصول فعلی **مبتنی بر چک** است. برای تبدیل آن به پیش‌بینی کامل Accounts Receivable باید فاکتورهای باز فروش، تاریخ سررسید فاکتور و تاریخ واقعی تسویه نیز به مدل داده اضافه شوند.

## وب دمو V2

پوشه `web-demo-v2` در ریشه پروژه قرار دارد.

```cmd
cd web-demo-v2
python -m http.server 5500
```

سپس:

`http://127.0.0.1:5500`

برای نمایش Predictionهای جدید، Backend را روی پورت 8000 اجرا و گزینه اتصال به API واقعی را فعال کنید.
