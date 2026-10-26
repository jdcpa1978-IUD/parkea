import unittest
from datetime import date

from src.main import add_months


class AddMonthsTests(unittest.TestCase):
    def test_handles_end_of_month(self):
        self.assertEqual(add_months(date(2025, 1, 31), 1), date(2025, 2, 28))

    def test_handles_leap_year(self):
        self.assertEqual(add_months(date(2024, 1, 31), 1), date(2024, 2, 29))

    def test_handles_year_boundary(self):
        self.assertEqual(add_months(date(2025, 12, 15), 2), date(2026, 2, 15))


if __name__ == "__main__":
    unittest.main()
