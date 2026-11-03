from app.agents.finance_decision_agents import FinanceManagerDecisionAgent


def test_manager_uses_unified_future_and_overdue_cheques_separately(monkeypatch):
    monkeypatch.setattr('app.agents.finance_decision_agents.settings.openai_api_key', '')
    agents = {
        'collection': {'analysis': {'prediction': {'end_of_month': {'open_exposure': 999}}}},
        'cashflow': {'analysis': {'prediction': {'next_7_days': {'net_change': 0}, 'end_of_month': {}}}},
        'cheque_payment': {'analysis': {'prediction': {'next_7_days': {}, 'end_of_month': {}}}},
        'cash_bank_movement': {'analysis': {'prediction': {'actual_period': {}}}},
        'customer_behavior': {'analysis': {'prediction': {'next_7_days': {}}}},
    }
    portfolio = {
        'received_future_open_amount_rial': 1_400_000_000_000,
        'received_overdue_amount_rial': 360_000_000_000,
        'issued_future_open_amount_rial': 500_000_000_000,
        'issued_overdue_amount_rial': 100_000_000_000,
        'received_future_open_count': 100,
        'received_overdue_count': 20,
    }
    result = FinanceManagerDecisionAgent().run(agents, cheque_portfolio=portfolio)
    analysis = result['analysis']
    assert analysis['cheque_portfolio']['received_future_open_amount_rial'] == 1_400_000_000_000
    kpis = {x['label']: x for x in analysis['executive_kpis']}
    assert kpis['چک‌های دریافتی باز؛ امروز و آینده']['value_rial'] == 1_400_000_000_000
    assert kpis['چک‌های دریافتی سررسیدگذشته']['value_rial'] == 360_000_000_000
    assert kpis['چک‌های دریافتی باز؛ امروز و آینده']['value_rial'] != 999
