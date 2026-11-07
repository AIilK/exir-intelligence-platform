"""امتیاز ریسک هیبرید (app/services/hybrid_risk_service.py): قواعد ثابت، بدون هوش مصنوعی."""
from app.services.hybrid_risk_service import score_branch


def _file(open_rial=0.0, high_rial=0.0, returned_rial=0.0, receivable=0.0, sales=0.0):
    return {
        "branch_id": 1, "branch_name": "هیبرید آزمایشی",
        "cheques": {"summary": {
            "open": {"amount_rial": open_rial, "count": 10}, "high": {"amount_rial": high_rial, "count": 2},
            "returned": {"amount_rial": returned_rial, "count": 1},
        }},
        "debt": {"open_account_receivable_rial": receivable, "debtor_customer_count": 5, "customer_count": 20},
        "sales_stats": {"current_year_sales_rial": sales},
    }


def _points(result):
    return {c["key"]: c["points"] for c in result["components"]}


def test_clean_hybrid_scores_low():
    # 30 days of sales in cheques, 30 days collection period, no risky or returned cheques
    r = score_branch(_file(open_rial=30_000, receivable=30_000, sales=365_000), days_elapsed=365)
    assert r["score"] == 0 and r["level"] == "low"
    assert r["reasons"] == ["همه شاخص‌های ریسک در محدوده عادی است."]


def test_each_component_saturates_at_its_weight():
    r = score_branch(_file(open_rial=200_000, high_rial=200_000, returned_rial=100_000, receivable=200_000, sales=365_000),
                     days_elapsed=365)
    p = _points(r)
    assert p == {"high_risk_cheques": 35, "returned_cheques": 25, "collection_period": 25, "cheque_holding": 15}
    assert r["score"] == 100 and r["level"] == "critical"


def test_partial_components_and_level_boundaries():
    # half of open cheques high risk -> 17.5; collection period 97.5 days -> half of 25; others 0
    r = score_branch(_file(open_rial=20_000, high_rial=10_000, receivable=97_500, sales=365_000), days_elapsed=365)
    p = _points(r)
    assert p["high_risk_cheques"] == 17.5
    assert p["collection_period"] == 12.5
    assert p["returned_cheques"] == 0 and p["cheque_holding"] == 0
    assert r["score"] == 30 and r["level"] == "medium"


def test_no_sales_this_year_does_not_divide_by_zero():
    r = score_branch(_file(open_rial=0, returned_rial=5_000, receivable=10_000, sales=0), days_elapsed=200)
    assert r["metrics"]["collection_period_days"] is None
    assert _points(r)["collection_period"] == 0 and _points(r)["cheque_holding"] == 0
    assert _points(r)["returned_cheques"] == 25  # 50% of exposure is an open returned cheque
