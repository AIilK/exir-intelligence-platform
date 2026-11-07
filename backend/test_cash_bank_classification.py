from app.services.cash_bank_movement_service import CashBankMovementService
from app.agents.finance_decision_agents import FinanceManagerDecisionAgent


def _row(description: str, counterpart_name: str = "", *, movement_type: str = "bank_payment", direction: str = "outflow"):
    return {
        "MovementType": movement_type, "Direction": direction, "Channel": "bank",
        "MovementID": 1, "DocumentID": 10, "DocumentNumber": 20, "DocumentDate": None,
        "ApproveState": 3, "AmountRial": 100, "CounterPartRef": None, "CounterPartCode": None,
        "CounterPartName": counterpart_name, "CashFlowFactorRef": None, "BankAccountRef": None,
        "BankAccountNumber": None, "BankAccountIBAN": None, "CashRef": None, "Description": description,
    }


def test_company_transfer_and_petty_cash_are_not_operational_movements():
    service = CashBankMovementService(engine=object())
    assert service._movement_payload(_row("حواله شرکتی بین حساب‌ها"))["classification"] == "company_bank_transfer"
    assert service._movement_payload(_row("واریز بابت انتقال وجه بین حساب‌ها", movement_type="bank_receipt", direction="inflow"))["classification"] == "company_bank_transfer"
    assert service._movement_payload(_row("واریز بابت:  انتقال وجه", movement_type="bank_receipt", direction="inflow"))["classification"] == "company_bank_transfer"
    assert service._movement_payload(_row("برداشت جهت انتقال وجه", movement_type="bank_payment", direction="outflow"))["classification"] == "company_bank_transfer"
    assert service._movement_payload(_row("شارژ تنخواه واحد فروش"))["classification"] == "petty_cash"
    assert service._movement_payload(_row("خرید مواد اولیه"))["classification"] == "operational"


def test_finance_manager_reads_cash_bank_actual_metrics():
    manager = FinanceManagerDecisionAgent().run({}, actual_report={"summary": {"bank_receipt_rial": 3300, "bank_payment_total_rial": 1500, "bank_payment_excluding_transfer_rial": 500}})
    kpis = {item["label"]: item for item in manager["analysis"]["executive_kpis"]}
    assert kpis["حواله دریافتی"]["value_rial"] == 3300
    assert kpis["حواله پرداختی"]["value_rial"] == 1500
    assert kpis["حواله پرداختی بدون انتقال بانکی"]["value_rial"] == 500
    assert all(kpis[label]["available"] for label in (
        "حواله دریافتی",
        "حواله پرداختی",
        "حواله پرداختی بدون انتقال بانکی",
    ))
