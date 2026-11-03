"""
تست دقیق فیلتر «پرتفوی باز» روی یک ردیف واقعی «غیرقطعی» و یک ردیف «برگشت نزذ صندوق».
اجرا از داخل پوشه backend:
    python test_open_holding_filter.py
"""
from app.services.karamad_live_received_cheque_service import KaramadLiveReceivedChequeService
from app.services.received_cheque_current_status import received_cheque_is_approved_open_holding


def main() -> None:
    """اسکریپت دستی Live SQL؛ هنگام کشف تست‌های واحد اجرا نمی‌شود."""

    result = KaramadLiveReceivedChequeService().report()
    cheques = result.get("cheques", [])

    for target_status in ("غیرقطعی", "برگشت نزذ صندوق"):
        sample = next((c for c in cheques if c.get("cheque_status") == target_status), None)
        print(f"\n=== نمونه با وضعیت: {target_status} ===")
        if not sample:
            print("هیچ نمونه‌ای پیدا نشد!")
            continue
        print("cheque_id:", sample.get("cheque_id"))
        print("source_system:", repr(sample.get("source_system")))
        print("cheque_status:", repr(sample.get("cheque_status")))
        print("state_label:", repr(sample.get("state_label")))
        verdict = received_cheque_is_approved_open_holding(sample)
        print("received_cheque_is_approved_open_holding نتیجه:", verdict)


if __name__ == "__main__":
    main()
