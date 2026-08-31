# Exir AI Platform — اصلاحات این نسخه

## اصلاح‌شده

- `POST /api/v1/query/ask` از حالت تکراری خارج شد و فقط یک مسیر دارد.
- `QueryService.execute_sql` با `Connection` و `QueryExecutor(config)` واقعی هماهنگ شد.
- `Query Plan` و Response Schema یکدست شدند.
- Schemaهای تکراری Query حذف شدند.
- Mock LLM فقط در `app/llm/mock_client.py` نگه داشته شد.
- فایل‌های Legacy بدون استفاده در Query حذف شدند.
- Finance Dashboard دیگر Excel-based نیست.
- Dashboard مستقیم از `get_sqlserver_engine()` و SQL Server شرکت استفاده می‌کند.
- Customer Cheque Risk بر اساس `CounterPartRef` از داده ERP محاسبه می‌شود.
- ریسک شامل سابقه واخواست، مبلغ واخواست، میانگین/بیشترین مدت چک، چک خارج از سقف سیاست و مبلغ چک باز است.
- Cash Flow Scenario، Cheque Risk، Anomaly Control و Payment Plan داخل Dashboard یکپارچه شدند.
- Health endpoint منبع SQL را بررسی می‌کند.
- Importهای `openai` و `pyodbc` طوری اصلاح شدند که نبودن پکیج در زمان import کل API را از کار نیندازد و خطای قابل فهم بدهد.
- ODBC Driver پیش‌فرض به Driver 18 تغییر کرد.
- `.venv` و `__pycache__` از بسته نهایی حذف شدند.

## تست انجام‌شده

- `python -m compileall app` موفق
- Import کامل `app.main` موفق
- OpenAPI generation موفق
- فقط یک `/api/v1/query/ask` در OpenAPI
- تست‌های Rule Engine و Financial SQL Safety: 7 passed

## نکته تست SQL واقعی

شبکه داخلی SQL Server شرکت از محیط ساخت این بسته قابل دسترس نیست؛ بنابراین اجرای Query روی سرور شرکت باید روی سیستم داخل شبکه با `.env` واقعی تست شود.

## اجرای سریع

```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-treasury.txt
copy .env.example .env
```

اطلاعات SQL را در `.env` قرار دهید، سپس:

```cmd
uvicorn app.main:app --reload
```

ابتدا:

`GET /api/v1/finance/dashboard/health`

سپس:

`GET /api/v1/finance/dashboard?allowed_term_days=90&history_days=365&forecast_days=30`
