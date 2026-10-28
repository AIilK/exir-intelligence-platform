# اجرای Customer Behavior Agent

## ۱. تنظیم فایل .env

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.6-luna
CUSTOMER_BEHAVIOR_AGENT_ENABLED=true
CUSTOMER_BEHAVIOR_AGENT_MODEL=
CUSTOMER_BEHAVIOR_AGENT_MAX_CUSTOMERS=25
```

اگر `CUSTOMER_BEHAVIOR_AGENT_MODEL` خالی باشد، `OPENAI_MODEL` استفاده می‌شود.
اگر API Key خالی یا مدل موقتاً unavailable باشد، اتوماسیون متوقف نمی‌شود و
خروجی قاعده‌محور با `fallback_used=true` برمی‌گردد.

## ۲. نصب و اجرا

```bat
.venv\Scripts\activate
pip install -r requirements-treasury.txt
uvicorn app.main:app --reload
```

## ۳. تست

ابتدا:

```text
GET /api/v1/finance/customer-agent/status
```

سپس:

```text
POST /api/v1/finance/customer-automation/run
```

در پاسخ موفق باید این مسیر وجود داشته باشد:

```json
{
  "agent": {
    "metadata": {
      "agent_name": "Customer Behavior Agent",
      "agent_mode": "llm",
      "llm_enabled": true,
      "llm_configured": true,
      "model": "gpt-5.6-luna",
      "fallback_used": false
    },
    "analysis": {
      "headline": "...",
      "human_summary": "...",
      "good_signals": [],
      "bad_signals": [],
      "future_outlook": "...",
      "recommended_actions": [],
      "next_best_action": "..."
    }
  }
}
```

اگر `agent_mode=rules_only` باشد، مقدار `fallback_reason` علت را نشان می‌دهد.

## ایمنی داده

فقط Summary و حداکثر ۲۵ مشتری اولویت‌دار برای مدل ارسال می‌شوند. SQL خام،
اطلاعات حساب بانکی و کل دیتابیس برای مدل ارسال نمی‌شود. مدل اجازه تولید یا
تغییر اعداد مالی را ندارد.
