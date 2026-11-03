# فعال‌سازی تحلیل نمایندگان

پس از اجرای Backend، از داخل فرانت یا Swagger:

1. `GET /api/v1/finance/representative-mapping/template.csv` را دانلود کنید.
2. ستون‌های `representative_id` و `representative_name` را برای مشتریان تکمیل کنید.
3. فایل را با UTF-8 و فرمت CSV ذخیره کنید.
4. در `POST /api/v1/finance/representative-mapping/upload` بارگذاری کنید.
5. نتیجه را در `GET /api/v1/finance/representative-intelligence` بررسی کنید.

قواعد:

- هر `counterpart_ref` فقط یک‌بار مجاز است.
- شناسه مشتری باید در خروجی واقعی SQL وجود داشته باشد.
- ردیف ناقص پذیرفته نمی‌شود.
- فایل قبلی پیش از جایگزینی، با پسوند زمانی Backup می‌شود.
- ارتباط مشتری و نماینده حدس زده نمی‌شود.

آخرین خروجی کامل Agent بدون اجرای دوباره و هزینه API:

`GET /api/v1/finance/customer-automation/latest`
