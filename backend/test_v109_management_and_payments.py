from datetime import date
from app.services.cash_bank_movement_service import CashBankMovementService
from app.agents.finance_decision_agents import FinanceManagerDecisionAgent
from test_cash_bank_classification import _row


class Result:
    def __init__(self, rows): self.rows = rows
    def mappings(self): return self
    def all(self): return self.rows
    def one(self): return self.rows[0]


class Engine:
    def __init__(self, rows): self.rows = rows
    def connect(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, statement, params):
        sql = str(statement)
        if "SELECT m.*" in sql:
            assert "OFFSET" not in sql  # all rows must be classified before paging
            return Result(self.rows)
        if "COUNT_BIG" in sql: return Result([{"TotalCount": len(self.rows)}])
        return Result([])


def test_full_period_totals_and_branch_are_independent_of_page(monkeypatch):
    from app.services.karamad_manual_import_service import KaramadManualImportService
    def karamad(*args, **kwargs):
        return {"movements": [{"direction": "outflow", "amount_rial": 250, "classification": "operational", "transfer_id": 1}], "company_bank_transfers": [{"direction": "outflow", "amount_rial": 70, "classification": "company_bank_transfer", "transfer_id": 2}], "petty_cash_movements": []}
    monkeypatch.setattr(KaramadManualImportService, "actual_movements", karamad)
    monkeypatch.setattr(KaramadManualImportService, "summary", lambda self: {"available_branches": ["رشت"]})
    rows = []
    for description, amount, kind, direction in [
        ("خرید", 1000, "bank_payment", "outflow"),
        ("خرید", 500, "bank_payment", "outflow"),
        ("بابت انتقال", 300, "bank_payment", "outflow"),
        ("تنخواه", 200, "bank_payment", "outflow"),
        ("بابت انتقال", 900, "bank_receipt", "inflow"),
        ("وصول فروش", 4000, "bank_receipt", "inflow"),
    ]:
        row = _row(description, movement_type=kind, direction=direction)
        row.update(AmountRial=amount, DocumentDate=date(2026, 9, 8), MovementID=len(rows) + 1)
        rows.append(row)
    service = CashBankMovementService(Engine(rows))
    first = service.report(limit=1, offset=0)
    second = service.report(limit=1, offset=1)
    assert first["summary"] == second["summary"]
    s = first["summary"]
    assert s["bank_payment_total_rial"] == 2320
    assert s["bank_payment_internal_transfer_rial"] == 370
    assert s["bank_payment_excluding_transfer_rial"] == 1950
    assert s["bank_payment_rial"] == 1750  # excludes both transfer and petty cash
    assert s["net_rial"] == 2250
    assert sum(d["net_rial"] for d in first["daily"]) == 2250
    assert first["pagination"]["total_count"] == 4
    assert len(first["movements"]) == 1
    assert first["movements"] != second["movements"]
    branch = service.report(branch="رشت")["summary"]
    assert branch["bank_payment_total_rial"] == 320
    assert branch["bank_payment_excluding_transfer_rial"] == 250


def test_manager_ignores_generated_numbers_and_preserves_missing_opening():
    agents = {"cashflow": {"analysis": {"summary": "ساختگی", "prediction": {"end_of_month": {"net_change": 999999}}}}}
    report = {"summary": {"inflow_rial": 1000, "outflow_rial": 400, "net_rial": 600, "bank_payment_total_rial": 900, "bank_payment_excluding_transfer_rial": 500}}
    forecast = {"opening_cash": None, "management_summary": {"coverage_percent": 250, "key_points": [{"label": "مانده پایان بازه", "amount_rial": 500}]}}
    result = FinanceManagerDecisionAgent().run(agents, actual_report=report, cashflow_report=forecast)
    a = result["analysis"]
    kpis = {k["label"]: k for k in a["executive_kpis"]}
    assert kpis["حواله پرداختی"]["value_rial"] == 900
    assert [k["label"] for k in a["executive_kpis"] if k["group"] == "actual"] == ["حواله دریافتی", "حواله پرداختی", "حواله پرداختی بدون انتقال بانکی"]
    assert not kpis["مانده پیش‌بینی‌شده پایان بازه"]["available"]
    assert not kpis["پوشش چک‌های پرداختی و حقوق"]["available"]
    assert a["management_status"] == "attention"
    assert len(a["recommended_actions"]) == 3
    assert "999999" not in str(result)
    assert result["metadata"]["mode"] == "rules"


def test_manager_reports_real_closing_and_shortage():
    forecast = {"opening_cash": 100, "timeline": [{"date_jalali": "1405/06/17", "projected_inflow": 50, "projected_outflow": 200}], "management_summary": {"coverage_percent": 75, "first_shortage_date_jalali": "1405/06/17", "key_points": [{"label": "مانده پایان بازه", "amount_rial": -50}]}}
    a = FinanceManagerDecisionAgent().run({}, cashflow_report=forecast)["analysis"]
    k = {x["label"]: x for x in a["executive_kpis"]}
    assert k["مانده پیش‌بینی‌شده پایان بازه"]["value_rial"] == -50
    assert k["خالص تغییر نقدینگی ۷ روز نخست"]["value_rial"] == -150
    assert a["management_status"] == "critical"
    assert a["report_context"]["first_shortage"] == "1405/06/17"
