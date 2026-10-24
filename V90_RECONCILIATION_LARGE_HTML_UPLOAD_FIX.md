# V90 — رفع Failed to fetch برای HTML بانک ملت

- Route آپلود فرانت دیگر `request.formData()` را روی فایل‌های بانک Parse نمی‌کند.
- multipart اصلی به صورت raw به FastAPI ارسال می‌شود؛ مناسب HTML/PDF چندمگابایتی بانک ملت.
- Content-Type و boundary اصلی حفظ می‌شوند.
- خطای Backend به جای پیام مبهم Failed to fetch با جزئیات بیشتری نمایش داده می‌شود.
- Excel/CSV/PDF/HTML همچنان از همان endpoint خودکار استفاده می‌کنند.
