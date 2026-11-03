from app.services.finance_agent_data_hub import FinanceAgentDataHub


def test_v106_hub_reads_current_karamad_snapshots():
    # V171: the hub reads Karamad live (SQL) and falls back to the manual import;
    # counts change daily, so check structure and consistency instead of fixed numbers.
    hub = FinanceAgentDataHub().build()
    k = hub["karamad"]
    assert k["source"] in {"live", "import"}
    for key in ("received_cheques", "issued_cheques", "received_transfers", "paid_transfers"):
        assert k[key]["count"] >= 0
    cheques = k["received_cheques"]
    assert cheques["count"] == (cheques["overdue_count"] + cheques["today_count"]
                                + cheques["future_count"] + cheques["unknown_due_count"])
    paid = k["paid_transfers"]
    assert paid["count"] == paid["bank_to_bank_count"] + paid["other_count"]
    assert k["issued_cheques"]["future_data_complete"] is (k["source"] == "live")
    assert k["issued_cheques"]["returns_available"] is False


def test_v106_routing_rules_keep_internal_transfers_out_of_net():
    hub = FinanceAgentDataHub().build()
    assert hub["rules"]["bank_to_bank_net_effect"] == 0
    assert hub["rules"]["petty_cash_cashflow_included"] is False
    assert "karamad received_transfers" in hub["routing"]["cash_bank_movement"]
