from unittest.mock import patch

from app.services import pnl_live_service as service


def _columns(key: str, period=lambda k: {"key": k}) -> list[str]:
    with patch.object(service, "_period", period):
        return [k for k, _ in service._comparison_periods({"key": key})]


def test_comparison_columns_include_every_earlier_quarter():
    assert _columns("1405-Q1") == ["1404-Q4", "1404-Q1", "1404"]
    assert _columns("1405-Q2") == ["1405-Q1", "1404-Q2", "1404"]
    assert _columns("1405-Q3") == ["1405-Q2", "1405-Q1", "1404-Q3", "1404"]
    assert _columns("1405-Q4") == ["1405-Q3", "1405-Q2", "1405-Q1", "1404-Q4", "1404"]
    assert _columns("1405") == ["1404"]


def test_period_unavailable_is_skipped():
    def period(key):
        if key == "1405-Q1":
            raise KeyError(key)
        return {"key": key}

    assert _columns("1405-Q3", period) == ["1405-Q2", "1404-Q3", "1404"]
