import unittest

from app.services.financial_calculation_service import (
    calculate_aggregate,
    calculate_percentage,
)


class FinancialCalculationTests(unittest.TestCase):
    def test_percentage_uses_decimal_and_half_up_rounding(self):
        result = calculate_percentage(
            "2150000000",
            "3795890000",
            precision=2,
        )
        self.assertEqual(result["result"], "56.64")

    def test_sum_accepts_grouped_numbers(self):
        result = calculate_aggregate(
            "sum",
            ["2,150,000,000", "23,890,000", "500,000,000"],
            precision=0,
        )
        self.assertEqual(result["result"], "2673890000")

    def test_average_is_exactly_rounded(self):
        result = calculate_aggregate(
            "average",
            ["10", "11", "11"],
            precision=2,
        )
        self.assertEqual(result["result"], "10.67")

    def test_percentage_rejects_zero_total(self):
        with self.assertRaises(ValueError):
            calculate_percentage("10", "0")


if __name__ == "__main__":
    unittest.main()
