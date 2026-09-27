from pathlib import Path

from app.services.customer_automation_service import CustomerAutomationStore
from app.services.representative_intelligence_service import RepresentativeIntelligenceService


def test_alert_lifecycle(tmp_path: Path):
    store = CustomerAutomationStore(str(tmp_path / "history.db"))
    store.upsert_alerts([{"id": "a1", "level": "critical", "title": "test"}])
    assert len(store.list_alerts()) == 1
    assert store.update_alert("a1", "resolved", "finance")
    assert len(store.list_alerts("resolved")) == 1


def test_representative_missing_mapping_is_explicit(tmp_path: Path):
    result = RepresentativeIntelligenceService(str(tmp_path / "missing.csv")).aggregate([])
    assert result["status"] == "not_ready"


def test_representative_mapping_save_and_aggregate(tmp_path: Path):
    service = RepresentativeIntelligenceService(str(tmp_path / "mapping.csv"))
    content = (
        "counterpart_ref,representative_id,representative_name\n"
        "1,rep-1,نماینده تست\n"
    ).encode("utf-8")
    saved = service.save_mapping(content, {"1"})
    assert saved["mapped_customer_count"] == 1
    result = service.aggregate([{
        "counterpart_ref": 1, "counterpart_name": "مشتری تست",
        "risk_level": "high", "risk_score": 70,
        "open_exposure": 100, "overdue_open_amount": 50,
        "expected_collection_amount": 30, "collection_gap": 70,
    }])
    assert result["status"] == "success"
    assert result["representatives"][0]["representative_name"] == "نماینده تست"
