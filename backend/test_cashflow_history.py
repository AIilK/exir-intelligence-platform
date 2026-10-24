from app.services.monthly_cashflow_excel_service import MonthlyCashflowExcelService


def test_historical_comparison_uses_only_available_months(monkeypatch, tmp_path):
    service = MonthlyCashflowExcelService(root=tmp_path)
    months = [
        {"jalali_year": 1405, "jalali_month": 6, "month_name": "شهریور", "snapshot_count": 2, "latest_date": "1405/06/03"},
        {"jalali_year": 1405, "jalali_month": 5, "month_name": "مرداد", "snapshot_count": 3, "latest_date": "1405/05/31"},
    ]
    analyses = {
        (1405, 5): {"status":"success", "period_label":"مرداد 1405", "snapshot_count":3, "latest_snapshot":{"jalali_date":"1405/05/31"}, "summary":{"latest_liquidity_rial":1000, "average_obligations_rial":300, "weighted_average_pressure_percent":30, "average_coverage_percent":100, "peak_pressure_percent":40, "peak_pressure_date":"1405/05/20", "shortfall_days":0}, "forecast":{"trend":"باثبات"}},
        (1405, 6): {"status":"success", "period_label":"شهریور 1405", "snapshot_count":2, "latest_snapshot":{"jalali_date":"1405/06/03"}, "summary":{"latest_liquidity_rial":800, "average_obligations_rial":400, "weighted_average_pressure_percent":50, "average_coverage_percent":100, "peak_pressure_percent":60, "peak_pressure_date":"1405/06/03", "shortfall_days":1}, "forecast":{"trend":"افزایشی"}},
    }
    monkeypatch.setattr(service, "months", lambda: months)
    monkeypatch.setattr(service, "analyze", lambda year, month: analyses[(year, month)])
    report = service.historical_comparison()
    assert report["period_count"] == 2
    assert report["current_vs_previous"]["pressure_change_percent_point"] == 20
    assert report["current_vs_previous"]["liquidity_change_rial"] == -200
