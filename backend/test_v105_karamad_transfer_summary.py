from app.services.karamad_manual_import_service import KaramadManualImportService


def _row(kind, amount, classification):
    return {
        "source_kind": kind,
        "source_kinds": [kind],
        "direction": "inflow" if kind == "received_transfers" else "outflow",
        "amount_rial": amount,
        "classification": classification,
        "registration_date_jalali": "1405/06/01",
        "registration_month": "1405/06",
        "branch": "تهران",
    }


def test_paid_transfer_breakdown_uses_paid_transfer_source_only(tmp_path):
    service = KaramadManualImportService(
        inbox=tmp_path / "inbox",
        archive=tmp_path / "archive",
        state_path=tmp_path / "state.json",
    )
    state = service._empty_state()
    state["records"] = {
        "a": _row("received_transfers", 100, "operational"),
        "b": _row("paid_transfers", 200, "company_bank_transfer"),
        "c": _row("paid_transfers", 300, "operational"),
        "d": _row("paid_transfers", 50, "petty_cash"),
    }
    summary = service.summary(state=state)
    assert summary["received_transfer_total_count"] == 1
    assert summary["received_transfer_total_rial"] == 100
    assert summary["paid_transfer_total_count"] == 3
    assert summary["paid_transfer_total_rial"] == 550
    assert summary["paid_transfer_bank_to_bank_count"] == 1
    assert summary["paid_transfer_bank_to_bank_rial"] == 200
    assert summary["paid_transfer_other_count"] == 2
    assert summary["paid_transfer_other_rial"] == 350
