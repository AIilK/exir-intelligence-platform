# V56 — تعیین تکلیف تعهدهای پرداخت معوق

این نسخه بر پایه V55 ساخته شده و مرحله بررسی انسانی تعهدهای معوق را تکمیل می‌کند.

## رفتار جدید

- اقساط `current_year_overdue` در ابتدا `pending_review` هستند.
- خزانه برای هر قسط یکی از وضعیت‌های `paid`، `cancelled` یا `still_due` ثبت می‌کند.
- فقط `still_due` به‌عنوان تعهد فوری در Cash Flow روز جاری اضافه می‌شود.
- `paid` و `cancelled` از پیش‌بینی خارج می‌مانند.
- تصمیم‌ها در فایل محلی JSON با مسیر `data/payment_commitment_reviews.json` ذخیره می‌شوند.
- هیچ SQLite یا دیتابیس دیگری برای ذخیره این تصمیم‌ها استفاده نمی‌شود.
- پیش از ذخیره، شناسه قسط و دستور پرداخت دوباره با SQL Server راهکاران اعتبارسنجی می‌شود.
- هیچ پرداخت، انتقال بانکی یا ثبت سندی توسط این قابلیت انجام نمی‌شود.

## API

```text
PUT /api/v1/treasury/cash-bank/commitments/{installment_id}/decision
```

```json
{
  "payment_order_id": 9455,
  "decision": "still_due",
  "note": "تأیید خزانه"
}
```

برای بازگرداندن یک ردیف به صف بررسی، `decision` برابر `pending_review` ارسال می‌شود.
