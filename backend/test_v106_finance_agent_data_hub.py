from app.services.finance_agent_data_hub import FinanceAgentDataHub


def test_v106_hub_reads_current_karamad_snapshots():
    hub = FinanceAgentDataHub().build()
    k = hub["karamad"]
    assert k["record_count"] == 11239
    assert k["received_cheques"]["count"] == 2223
    assert k["issued_cheques"]["count"] == 12
    assert k["received_transfers"]["count"] == 7666
    assert k["paid_transfers"]["count"] == 1338
    assert k["paid_transfers"]["bank_to_bank_count"] == 317
    assert k["paid_transfers"]["other_count"] == 1021
    assert k["issued_cheques"]["future_data_complete"] is False
    assert k["issued_cheques"]["returns_available"] is False


def test_v106_routing_rules_keep_internal_transfers_out_of_net():
    hub = FinanceAgentDataHub().build()
    assert hub["rules"]["bank_to_bank_net_effect"] == 0
    assert hub["rules"]["petty_cash_cashflow_included"] is False
    assert "karamad received_transfers" in hub["routing"]["cash_bank_movement"]
