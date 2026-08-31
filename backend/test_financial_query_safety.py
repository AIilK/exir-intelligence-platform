import pytest

from app.services.financial_query_service import (
    FinancialQueryError,
    validate_financial_sql,
)


def test_safe_query_adds_top_limit():
    sql = validate_financial_sql(
        "SELECT p.Number FROM RPA3.Payment AS p ORDER BY p.PaymentID DESC"
    )
    assert sql.startswith("SELECT TOP (200)")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM RPA3.Payment",
        "SELECT * INTO audit_copy FROM RPA3.Payment",
        "SELECT p.Number FROM OtherSchema.Payment AS p",
        "SELECT p.Number FROM RPA3.Payment AS p; SELECT 1",
        "SELECT p.Number FROM RPA3.Payment AS p -- unsafe",
    ],
)
def test_unsafe_queries_are_rejected(sql):
    with pytest.raises(FinancialQueryError):
        validate_financial_sql(sql)
