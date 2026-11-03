from app.services.unified_cashflow_service import UnifiedDailyCashflowService


class _Snapshots:
    def latest_snapshot(self):
        return {
            "liquidity_rial": 1_500_000,
            "jalali_date": "1405/06/03",
            "filename": "14050603.xlsx",
        }

    def historical_comparison(self, months_limit=6):
        return {"period_count": 0, "periods": []}


def test_selected_cashflow_uses_portfolio_reliability_for_all_due_cheques(monkeypatch):
    def fake_forecast(self):
        assert self.opening_cash == 1_500_000
        return {
            "as_of_date": "2026-08-31",
            "timeline": [
                {"date": "2026-08-31", "issued_cheques_due": 200, "historical_average_operating_outflow": 500},
                {"date": "2026-09-01", "issued_cheques_due": 100, "historical_average_operating_outflow": 500},
            ],
        }

    def fake_cheques(self, **_kwargs):
        return {"cheques": [
            {"cheque_id": 1, "amount": 1_000, "days_to_due": 0, "recommended_reliance_percent": 90},
            {"cheque_id": 2, "amount": 2_000, "days_to_due": 1, "recommended_reliance_percent": 84},
            {"cheque_id": 3, "amount": 3_000, "days_to_due": 8, "recommended_reliance_percent": 95},
        ]}

    monkeypatch.setattr(
        "app.services.unified_cashflow_service.FinancePredictionService.cash_shortage_forecast",
        fake_forecast,
    )
    monkeypatch.setattr(
        "app.services.unified_cashflow_service.FinancePredictionService.cheque_return_predictions",
        fake_cheques,
    )
    monkeypatch.setattr(
        UnifiedDailyCashflowService,
        "_portfolio_reliability",
        lambda self: {
            "reliability_percent": 85.0,
            "return_rate_percent": 15.0,
            "resolved_cheque_count": 100,
            "source": "test",
        },
    )
    monkeypatch.setattr(
        UnifiedDailyCashflowService,
        "_operating_expense_plan",
        lambda self, today: {
            "daily_operating_expense_rial": 500,
            "daily_category_amounts_rial": {"production_procurement": 500},
            "categories": [],
            "excluded_non_operating": {"historical_amount_rial": 0},
        },
    )
    report = UnifiedDailyCashflowService(
        forecast_days=7, monthly_service=_Snapshots(), engine=object(),
    ).build()
    assert report["report_type"] == "cash_runway_forecast"
    assert report["opening_balance"]["amount_rial"] == 1_500_000
    assert report["summary"]["nominal_received_cheques_rial"] == 3_000
    assert report["summary"]["reliable_received_cheques_rial"] == 2_550
    assert report["summary"]["risk_reduction_rial"] == 450
    assert report["summary"]["issued_cheques_rial"] == 300
    assert report["summary"]["historical_other_expenses_rial"] == 0
    assert report["cashflow_policy"]["historical_other_expenses_included"] is False
    assert len(report["management_summary"]["recommendations"]) == 6
    assert report["summary"]["salary_reserve_rial"] == round(7 * (100_000_000_000 / 30), 2)
    assert report["cashflow_policy"]["petty_cash_included"] is False
    assert report["cashflow_policy"]["sql_server_write_operations"] is False
