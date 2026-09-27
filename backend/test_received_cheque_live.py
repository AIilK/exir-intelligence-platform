"""
تست مستقیم سرویس Live SQL چک‌های دریافتی، بدون fallback خاموش.
اجرا از داخل پوشه backend:
    python test_received_cheque_live.py
"""
import traceback

try:
    from app.services.karamad_live_received_cheque_service import KaramadLiveReceivedChequeService

    result = KaramadLiveReceivedChequeService().report()
    cheques = result.get("cheques", [])
    print("تعداد کل ردیف برگشتی از SQL:", len(cheques))

    from collections import Counter
    statuses = Counter(c.get("cheque_status") or "(خالی)" for c in cheques)
    print("\nتوزیع وضعیت‌ها:")
    for status, count in statuses.most_common(20):
        print(f"  {status}: {count}")

except Exception:
    print("خطا در اجرای سرویس Live SQL چک‌های دریافتی:")
    traceback.print_exc()
