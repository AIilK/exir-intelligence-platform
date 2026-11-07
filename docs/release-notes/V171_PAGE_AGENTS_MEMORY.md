# V171 — Agent گزارشی هر صفحه با هشدار، پیش‌بینی و حافظه

## خلاصه
هر صفحه داشبورد یک Agent دارد که روی داده زنده راهکاران و کارآمد اجرا می‌شود، هشدار و پیش‌بینی ساختاریافته می‌سازد و
**اعداد هر اجرا را به خاطر می‌سپارد** (روند، تغییر نسبت به اجرای قبل و حدود ۷ روز قبل، تکرار هشدار).
اجرا: هر روز ساعت ۷ (زمان‌بند موجود) + دکمه «به‌روزرسانی تحلیل» در هر صفحه + «اجرای همه Agentها».

## Agentها
| صفحه | Agent | نوع |
|---|---|---|
| خلاصه مدیریتی | Finance Manager (جمع‌بندی همه صفحات) | wrap |
| پرونده مشتری | Customer Risk | wrap |
| چک‌های دریافتی / پرداختی | Received / Issued Cheques | جدید |
| نقد و حواله | Cash & Bank Movement | wrap |
| حواله‌های پرداختی شرکت | Company Payments | جدید |
| حواله‌های B2B | B2B Remittances | جدید |
| پیش‌بینی نقدینگی | Cash Flow | wrap |
| Cash Flow روزانه | Daily Cash Report | جدید |
| مرکز وصول | Collection | wrap |
| توزیع بار | Distribution | جدید |
| نمایندگان | Representative | wrap |
| سناریوساز | Scenario | wrap |
| مغایرت‌گیری (در خلاصه مدیریتی) | Bank Reconciliation | جدید |

«wrap» = منطق و متن LLM همان Agent قبلی حفظ شده؛ هشدار/پیش‌بینی ساختاریافته و حافظه اضافه شده است.
Agentهای جدید اعداد و هشدار را با قواعد قطعی می‌سازند و فقط متن تیتر/خلاصه را OpenAI بازنویسی می‌کند
(اعداد، هشدارها و پیش‌بینی‌ها هرگز توسط مدل تغییر نمی‌کنند).

## حافظه (`backend/app/services/agent_memory_store.py`)
- `agent_runs`: هر اجرا با اعداد و نتیجه کامل.
- `agent_alerts`: هشدار یکتا (`agent:type:entity`) با «اجرای متوالی»، اولین مشاهده و وضعیت
  (فعال / دیده‌شده / نادیده‌گرفته / رفع‌شده). هشداری که دیگر دیده نشود خودکار رفع‌شده می‌شود؛
  هشدار نادیده‌گرفته تا وقتی پشت‌سرهم تکرار شود ساکت می‌ماند.

## داده زنده
- `FinanceAgentDataHub`: چک‌ها و حواله‌های کارآمد از SQL زنده (fallback به ایمپورت Excel؛ `karamad.source`).
- چک‌های پرداختی کارآمد در گزارش چک پرداختی باز از `vwChequePLinesFull` (وضعیت نهایی «عادی») خوانده می‌شود؛
  Snapshot اکسل قبلی هیچ چک آینده‌ای نداشت.

## API (`/api/v1/finance`)
`GET /page-agents` · `GET /page-agents/{key}` · `POST /page-agents/{key}/run` · `POST /page-agents/run-all` ·
`GET /agent-alerts` · `PATCH /agent-alerts/{alert_key}`. مسیرهای قبلی `/agents/run-all` و `/agents/latest`
همان قالب قبلی (`agents`, `management_summary`, `data`) را برمی‌گردانند.

## رابط کاربری
- `frontend/app/page-agents.tsx` + `agents-v171.css`: کارت Agent بالای هر صفحه (وضعیت، تیتر، نوار حافظه با نمودار روند،
  هشدار با شمارنده تکرار، پیش‌بینی با اطمینان و مبنا، اقدام پیشنهادی)، صفحه «تیم Agentها»، مرکز هشدار Agentها
  و پیش‌بینی‌ها در «دقت پیش‌بینی».
