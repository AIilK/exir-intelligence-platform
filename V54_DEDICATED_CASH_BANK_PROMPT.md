# V54 — Dedicated Cash & Bank Movement Prompt

در V54، `Cash & Bank Movement Agent` علاوه بر کلاس و Rule Engine مستقل، Prompt تخصصی مستقل نیز دارد.

مسیر Prompt:

```text
backend/app/agents/cash_bank_movement_prompts.py
```

پروفایل قابل حسابرسی خروجی:

```text
metadata.prompt_profile = cash_bank_movement_v1
```

Prompt به‌عنوان `instructions` در Responses API ارسال می‌شود. مدل اجازه تغییر اعداد محاسبه‌شده، دوباره‌شماری چک، جمع‌کردن انتقال داخلی در خالص شرکت یا ترکیب سند غیرقطعی با جریان قطعی را ندارد.
