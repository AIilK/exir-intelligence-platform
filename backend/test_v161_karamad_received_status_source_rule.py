from app.services.karamad_received_cheque_sql_service import KaramadReceivedChequeSQLService


def test_empty_status_is_non_certain():
    svc = KaramadReceivedChequeSQLService()
    assert svc.status_bucket("") == "غیر قطعی"
    assert svc.status_bucket("   ") == "غیر قطعی"
    assert svc.status_bucket(None) == "غیر قطعی"


def test_unknown_non_empty_status_is_not_non_certain():
    svc = KaramadReceivedChequeSQLService()
    assert svc.status_bucket("یک وضعیت ناشناخته") == "سایر"


def test_returned_without_customer_destination_is_box():
    svc = KaramadReceivedChequeSQLService()
    assert svc.status_bucket("برگشتی") == "برگشت نزد صندوق"
    assert svc.status_bucket("واخواست شده") == "برگشت نزد صندوق"


def test_returned_for_customer_is_customer():
    svc = KaramadReceivedChequeSQLService()
    assert svc.status_bucket("برگشت نزد مشتری") == "برگشت نزد مشتری"


def test_status_ref_is_authoritative_even_when_status_name_is_empty():
    svc = KaramadReceivedChequeSQLService()
    assert svc.status_bucket("", 1) == "غیر قطعی"
    assert svc.status_bucket("", 2) == "نزد صندوق"
    assert svc.status_bucket("   ", 7) == "برگشتی نزد مشتری"


def test_status_ref_7_and_10_stay_distinct():
    svc = KaramadReceivedChequeSQLService()
    assert svc.status_bucket("برگشتی نزد مشتری", 7) == "برگشتی نزد مشتری"
    assert svc.status_bucket("برگشتی نزد صندوق", 10) == "برگشتی نزد صندوق"


def test_only_six_main_status_refs_are_in_portfolio():
    from app.services.karamad_received_cheque_sql_service import KARAMAD_MAIN_STATUS_REFS
    assert KARAMAD_MAIN_STATUS_REFS == {1, 2, 3, 6, 7, 10}
