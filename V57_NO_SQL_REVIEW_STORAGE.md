# V57 — ذخیره تعیین تکلیف بدون SQL

این نسخه ذخیره SQLite مربوط به تصمیم‌های خزانه را حذف می‌کند.

## روش ذخیره

- تصمیم‌های `paid`، `cancelled` و `still_due` در فایل
  `backend/data/payment_commitment_reviews.json` نگهداری می‌شوند.
- نوشتن فایل به‌شکل Atomic انجام می‌شود تا فایل نیمه‌کاره باقی نماند.
- SQL Server راهکاران فقط با دسترسی Read-only برای اعتبارسنجی شناسه قسط خوانده می‌شود.
- هیچ `INSERT`، `UPDATE` یا `DELETE` روی SQL Server، SQLite یا دیتابیس دیگری اجرا نمی‌شود.

مسیر فایل از `.env` قابل تنظیم است:

```text
PAYMENT_COMMITMENT_REVIEW_FILE=./data/payment_commitment_reviews.json
```
