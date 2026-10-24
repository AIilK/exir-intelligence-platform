from app.services import karamad_received_cheque_sql_service as mod
from app.services.karamad_received_cheque_sql_service import KaramadReceivedChequeSQLService


def _rows():
    return [
        {"counterpart_ref": 1, "ExitRef": None, "cheque_status": "", "state_label": "", "amount": 100},
        {"counterpart_ref": 2, "ExitRef": None, "cheque_status": "نزد صندوق", "state_label": "نزد صندوق", "amount": 200},
        {"counterpart_ref": 3, "ExitRef": None, "cheque_status": "برگشتی", "state_label": "برگشتی", "amount": 300},
    ]


def test_snapshot_does_not_truncate_and_reuses_cache(monkeypatch):
    mod._received_cache.update({"loaded_at": 0.0, "rows": None, "count": 0, "total_amount_rial": 0.0})
    calls = {"n": 0}
    monkeypatch.setattr(KaramadReceivedChequeSQLService, "fetch_all", lambda self, limit=200000: calls.__setitem__("n", calls["n"] + 1) or _rows())
    svc = KaramadReceivedChequeSQLService()
    first = svc.open_received(limit=1)
    second = svc.open_received(limit=1)
    assert len(first) == 3
    assert len(second) == 3
    assert sum(r["amount"] for r in first) == 600
    assert calls["n"] == 1


def test_filter_uses_same_complete_snapshot(monkeypatch):
    mod._received_cache.update({"loaded_at": 0.0, "rows": None, "count": 0, "total_amount_rial": 0.0})
    monkeypatch.setattr(KaramadReceivedChequeSQLService, "fetch_all", lambda self, limit=200000: _rows())
    svc = KaramadReceivedChequeSQLService()
    all_rows = svc.open_received()
    selected = svc.filter_buckets(all_rows, ["برگشت نزد صندوق"])
    assert len(all_rows) == 3
    assert len(selected) == 1
    assert selected[0]["amount"] == 300
