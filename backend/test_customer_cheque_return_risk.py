from app.services.customer_cheque_return_risk import attach_return_risk


def _cheque(status, amount=100, days=10, term=None):
    return {"cheque_status": status, "amount_rial": amount, "days_until_due": days, "term_days": term}


def test_clean_history_gives_low_risk_and_marks_resolved_rows():
    rows = [_cheque("وصول شده") for _ in range(20)] + [_cheque("در جریان وصول")]
    summary = attach_return_risk(rows)

    assert rows[0]["return_risk"]["state"] == "collected"
    risk = rows[-1]["return_risk"]
    assert risk["state"] == "open" and risk["level"] == "low"
    assert summary["open_cheque_count"] == 1 and summary["high_risk_open_count"] == 0


def test_bad_history_overdue_and_large_amount_gives_high_risk():
    rows = [_cheque("برگشت خورده") for _ in range(4)] + [_cheque("وصول شده") for _ in range(4)]
    rows.append(_cheque("نزد صندوق", amount=500, days=-12, term=150))
    summary = attach_return_risk(rows)

    assert rows[0]["return_risk"]["state"] == "returned"
    risk = rows[-1]["return_risk"]
    assert risk["level"] == "high"
    assert risk["probability_percent"] <= 95
    assert len(risk["reasons"]) >= 4
    assert summary["high_risk_open_count"] == 1


def test_small_history_is_smoothed_by_prior():
    rows = [_cheque("برگشتی"), _cheque("وصول"), _cheque("باز")]
    attach_return_risk(rows)
    # one bounce out of two must not read as a 50% probability
    assert rows[-1]["return_risk"]["probability_percent"] < 30


def test_in_collection_is_open_and_old_karamad_bank_cheque_is_collected():
    rows = [
        _cheque("در جریان وصول"),
        _cheque("واگذار شده", days=-45),
        _cheque("وضعیت 10", days=-400),
        {"state_label": "وضعیت 10", "master_state": 3, "amount": 100, "days_to_due": -400},
    ]
    summary = attach_return_risk(rows)
    assert rows[0]["return_risk"]["state"] == "open"
    assert rows[1]["return_risk"]["state"] == "collected"
    assert rows[2]["return_risk"]["state"] == "unresolved"
    assert rows[3]["return_risk"]["state"] == "collected"
    assert summary["unresolved_cheque_count"] == 1


def test_external_history_sets_base_rate_when_feed_has_only_open_cheques():
    rows = [_cheque("برگشتی نزد مشتری", days=-60) for _ in range(4)] + [_cheque("واگذار شده", days=20)]
    summary = attach_return_risk(rows, {"collected_count": 200, "returned_count": 4, "average_amount_rial": 100})
    assert summary["resolved_cheque_count"] == 204
    assert rows[-1]["return_risk"]["level"] == "low"
