from app.services.received_cheque_current_status import (
    current_received_holding_label,
    received_cheque_is_approved_open_holding,
    received_cheque_open_expression,
)


def test_python_holding_filter_accepts_only_three_business_locations():
    assert received_cheque_is_approved_open_holding({"cheque_status": "نزد صندوق"})
    assert received_cheque_is_approved_open_holding({"cheque_status": "نزد بانک"})
    assert received_cheque_is_approved_open_holding({"cheque_status": "واگذار شده"})
    assert received_cheque_is_approved_open_holding({"current_status_description": "تحویل مأمور وصول"})

    assert not received_cheque_is_approved_open_holding({"cheque_status": "برگشتی نزد مشتری"})
    assert not received_cheque_is_approved_open_holding({"current_status_description": "در انتظار واگذاری به مأمور وصول"})
    assert not received_cheque_is_approved_open_holding({"current_status_description": "واخواست شده"})
    assert not received_cheque_is_approved_open_holding({"current_status_description": "وصول شده"})


def test_labels_do_not_turn_waiting_for_collector_into_collector():
    assert current_received_holding_label(1, "در انتظار واگذاری به مأمور وصول") == "وضعیت خارج از سبد باز"
    assert current_received_holding_label(1, "نزد مأمور وصول") == "نزد مأمور وصول"
    assert current_received_holding_label(2, "نزد بانک") == "نزد بانک"
    assert current_received_holding_label(1, "نزد صندوق") == "نزد صندوق"


def test_sql_expression_is_three_holdings_and_excludes_waiting_collector():
    sql = received_cheque_open_expression("note", "current_status")
    for token in ("نزد مأمور وصول", "نزد بانک", "نزد صندوق", "در انتظار"):
        assert token in sql
    assert "note.[State] IN (1, 2)" in sql
