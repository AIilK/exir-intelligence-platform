import pytest
from fastapi import HTTPException

from app.api.reconciliation_access import require_reconciliation_api_key
from app.core.config import settings


def test_reconciliation_access_accepts_exact_server_key(monkeypatch):
    monkeypatch.setattr(settings, "reconciliation_api_key", "safe-test-key")
    assert require_reconciliation_api_key("safe-test-key") is None


@pytest.mark.parametrize("provided", [None, "", "wrong-key", "safe-test-key-changed"])
def test_reconciliation_access_rejects_missing_or_changed_key(monkeypatch, provided):
    monkeypatch.setattr(settings, "reconciliation_api_key", "safe-test-key")
    with pytest.raises(HTTPException) as raised:
        require_reconciliation_api_key(provided)
    assert raised.value.status_code == 403


def test_reconciliation_access_fails_closed_without_configuration(monkeypatch):
    monkeypatch.setattr(settings, "reconciliation_api_key", "")
    with pytest.raises(HTTPException) as raised:
        require_reconciliation_api_key("anything")
    assert raised.value.status_code == 403
