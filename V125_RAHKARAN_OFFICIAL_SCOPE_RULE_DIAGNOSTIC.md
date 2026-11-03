# V125 — Rahkaran Official Received-Cheque Scope Rule Diagnostic

این نسخه Rule داشبورد را تغییر نمی‌دهد. Endpoint جدید با استفاده از Excel فقط به عنوان کنترل، 26 رکورد SQL-only را پیدا می‌کند و سپس تمام ستون‌های master و تاریخچه transaction آن‌ها را از SQL استخراج و پروفایل می‌کند تا شرط عمومی دامنه گزارش رسمی راهکاران کشف شود.

Endpoint:
`POST /api/v1/treasury/cheques/received/analyze-official-scope-rule`

هدف مرحله بعد: ساخت Rule عمومی SQL و Validation روی 795 چک / 757,785,104,980 ریال، بدون استفاده از Excel در Runtime.
