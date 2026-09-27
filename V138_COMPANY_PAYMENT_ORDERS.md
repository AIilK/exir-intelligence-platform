# V138 — حواله‌های پرداختی شرکت

- منبع SQL: `RPA3.PaymentOrder`
- جزئیات مبلغ: `PaymentOrderDeposit`, `PaymentOrderCashMoney`, `PaymentOrderPayableNote`
- طرف حساب: `FIN3.DL`
- Endpoint: `GET /api/v1/treasury/payment-orders/company?limit=5000`
- صفحه جدید فرانت: «حواله‌های پرداختی شرکت»
- KPI: کل، مبلغ، دارای تاریخ تأیید، در انتظار تأیید، نقد/بانکی، چکی
- دسته‌بندی مدیریتی اولیه بر پایه Description؛ State خام برای کالیبراسیون نگه داشته شده است.
- فیلتر: جستجو، دسته، State، روش پرداخت.

نکته: دسته‌بندی Description در این نسخه یک لایه مدیریتی اولیه است و هنوز جایگزین معنای رسمی State/PaymentType راهکاران نیست.
