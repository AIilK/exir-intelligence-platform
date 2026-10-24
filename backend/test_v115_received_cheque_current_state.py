from pathlib import Path

from app.services.received_cheque_current_status import (
    current_received_holding_label,
    current_received_status_apply,
    received_cheque_open_expression,
)


ROOT = Path(__file__).parent
TREASURY = (ROOT / "app" / "services" / "treasury_service.py").read_text(encoding="utf-8")
PREDICTION = (ROOT / "app" / "services" / "finance_prediction_service.py").read_text(encoding="utf-8")
INSIGHT = (ROOT / "app" / "services" / "treasury_insight_service.py").read_text(encoding="utf-8")


def section(text: str, name: str, next_name: str | None = None) -> str:
    start = text.index(f"def {name}")
    end = text.index(f"def {next_name}", start) if next_name else len(text)
    return text[start:end]


def test_latest_received_transaction_is_the_current_status_basis():
    sql = current_received_status_apply("note", "current_status")
    assert "ReceivableNoteTransaction" in sql
    assert "rnt.[ReceivableNoteRef] = note.[ReceivableNoteID]" in sql
    assert "rnt.[State] > 0" not in sql
    assert "rnt.[Date] DESC" in sql
    assert "ReceivableNoteTransactionID] DESC" in sql


def test_business_open_starts_from_master_states_1_and_2_and_only_excludes_terminal_history():
    expr = received_cheque_open_expression("note", "current_status")
    assert "note.[State] IN (1, 2)" in expr
    assert "COALESCE(current_status.[CurrentChequeState], note.[State])" not in expr
    assert "مسترد" in expr
    assert "واخواست" in expr
    assert "وصول شده" in expr
    assert "واگذار" in expr and "غیر" in expr

def test_open_received_endpoint_uses_latest_business_status():
    s = section(TREASURY, "get_open_received_cheques", "get_open_issued_cheques")
    assert "current_received_status_apply" in s
    assert "received_cheque_open_predicate" in s
    # The gate now lives in the shared helper, preventing historical transaction
    # states from widening the open portfolio beyond master states 1/2.
    assert "received_cheque_open_predicate" in s
    assert "CurrentStatusTransactionID" in s


def test_due_and_agent_queries_use_same_current_status_basis():
    due = section(TREASURY, "get_cheque_due_report", "get_received_cheques_by_status")
    assert "received_cheque_open_predicate" in due
    assert "current_received_status_apply" in due
    assert "received_cheque_open_predicate" in PREDICTION
    assert "current_received_status_apply" in PREDICTION
    assert "received_cheque_open_predicate" in INSIGHT


def test_holding_label_keeps_collector_bank_and_cashbox_separate():
    assert current_received_holding_label(1, "") == "نزد صندوق"
    assert current_received_holding_label(2, "") == "نزد بانک"
    assert current_received_holding_label(6, "واگذاری به مأمور وصول") == "نزد مأمور وصول"
