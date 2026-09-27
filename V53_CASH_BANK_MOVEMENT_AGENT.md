# V53 — Cash & Bank Movement Agent

این نسخه بخش مستقل «نقد و حواله» را به مرکز فرماندهی مالی اضافه می‌کند.

## منبع قطعی جریان نقد

- دریافت نقدی: `RPA3.ReceiptCashMoney` با سند `Receipt.ApproveState = 3`
- واریز و حواله ورودی: `RPA3.ReceiptDeposit` با سند قطعی
- پرداخت نقدی: `RPA3.PaymentCashMoney` با سند قطعی
- برداشت و حواله خروجی: `RPA3.PaymentDeposit` با سند قطعی
- انتقال داخلی: `TransferDeposit` و `TransferCashMoney`؛ اثر خالص شرکت صفر

چک‌ها، استرداد چک و مبلغ سربرگ Receipt/Payment در گردش نقدی دوباره شمرده نمی‌شوند.

## API

```text
GET /api/v1/treasury/cash-bank/movements
GET /api/v1/treasury/cash-bank/transfers
```

فیلترهای گزارش: امروز، ۷ روز، ۳۰ روز، ۳/۶/۱۲ ماه، بازه دلخواه، قطعی، غیرقطعی و همه وضعیت‌ها. خروجی ریزها صفحه‌بندی دارد و سقف کلی ۱۰۰ ردیف ندارد.

## Agent و اتصال مدیریتی

`Cash & Bank Movement Agent` گردش واقعی را تحلیل می‌کند و خروجی آن در `agents.cash_bank_movement` قرار می‌گیرد. خلاصه و داده خام نیز در `data.cash_bank_movements` و `data.internal_transfers` ذخیره می‌شود. Finance Manager Agent سه KPI دریافت قطعی، پرداخت قطعی و خالص واقعی را دریافت می‌کند.

## Forecast

میانگین دریافت و پرداخت عملیاتی Forecast فقط از ریز نقدی و بانکی قطعی محاسبه می‌شود. چک دریافتی قابل اتکا و چک پرداختی آینده جداگانه به Forecast اضافه می‌شوند؛ بنابراین دوباره‌شماری سربرگ‌های شامل چک حذف شده است.
