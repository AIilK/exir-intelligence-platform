from app.services.karamad_received_cheque_sql_service import KaramadReceivedChequeSQLService


def test_status8_text_overrides_historical_status6():
    svc = KaramadReceivedChequeSQLService()
    assert svc.status_bucket("برگشت نزد صندوقبرگشتی وصول شده", 6) is None
    assert svc.status_bucket("برگشتی وصول شده", 8) is None


def test_plain_status6_stays_cashbox_return():
    svc = KaramadReceivedChequeSQLService()
    assert svc.status_bucket("برگشت نزد صندوق", 6) == "برگشت نزد صندوق"


def test_main_statuses_remain_exact():
    from app.services.karamad_received_cheque_sql_service import KARAMAD_MAIN_STATUS_REFS
    assert KARAMAD_MAIN_STATUS_REFS == {1, 2, 3, 6, 7, 10}
