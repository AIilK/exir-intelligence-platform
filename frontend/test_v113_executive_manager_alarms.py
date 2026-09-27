from app.agents.management_report import build_management_report


def test_manager_separates_future_overdue_and_builds_alarms():
    portfolio = {
        "received_future_open_count": 10,
        "received_future_open_amount_rial": 1_400_000_000_000,
        "received_overdue_count": 3,
        "received_overdue_amount_rial": 360_000_000_000,
        "issued_future_open_count": 4,
        "issued_future_open_amount_rial": 100_000_000_000,
        "issued_overdue_count": 1,
        "issued_overdue_amount_rial": 20_000_000_000,
    }
    cashflow = {
        "opening_cash": 50_000_000_000,
        "timeline": [
            {"date_jalali":"1405/06/18","projected_inflow":1_000_000_000,"projected_outflow":2_000_000_000,"projected_cash":49_000_000_000},
            {"date_jalali":"1405/06/19","projected_inflow":1_000_000_000,"projected_outflow":60_000_000_000,"projected_cash":-10_000_000_000},
        ],
        "management_summary": {"first_shortage_date_jalali":"1405/06/19","key_points":[],"coverage_percent":80,"fixed_outflows_rial":100_000_000_000},
    }
    result = build_management_report({}, portfolio, {}, cashflow)["analysis"]
    assert result["report_context"]["version"] == "v113"
    assert result["cheque_portfolio"]["received_future_open_amount_rial"] == 1_400_000_000_000
    assert result["cheque_portfolio"]["received_overdue_amount_rial"] == 360_000_000_000
    codes = {x["code"] for x in result["alarms"]}
    assert "cash_shortage" in codes
    assert "issued_overdue" in codes
    assert "received_overdue" in codes
    assert result["alarm_summary"]["critical"] >= 2
    assert result["future_outlook"]["7_days"]["available"] is True
    assert len(result["agent_requests"]) >= 6
