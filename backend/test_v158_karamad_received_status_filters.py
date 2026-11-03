from app.services.karamad_received_cheque_sql_service import KaramadReceivedChequeSQLService


def test_empty_status_is_explicitly_non_certain():
    assert KaramadReceivedChequeSQLService.status_bucket("") == "غیر قطعی"
    assert KaramadReceivedChequeSQLService.status_bucket("وضعیت نامشخص") == "غیر قطعی"


def test_returned_without_destination_is_returned_to_cashbox_bucket():
    assert KaramadReceivedChequeSQLService.status_bucket("برگشتی") == "برگشت نزد صندوق"
    assert KaramadReceivedChequeSQLService.status_bucket("واخواست شده") == "برگشت نزد صندوق"


def test_returned_customer_remains_customer_bucket():
    assert KaramadReceivedChequeSQLService.status_bucket("برگشتی نزد مشتری") == "برگشت نزد مشتری"
