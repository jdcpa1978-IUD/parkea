import unittest
from datetime import datetime, timedelta, timezone

from src.services.access import _exit_time_and_minutes


class ExitTimeTests(unittest.TestCase):
    def test_naive_database_timestamp_uses_database_timezone(self):
        entered_at = datetime(2026, 10, 25, 22, 0)
        now = datetime(2026, 10, 25, 23, 30, tzinfo=timezone(timedelta(hours=-5)))

        exit_at, minutes = _exit_time_and_minutes(entered_at, now)

        self.assertEqual(minutes, 90)
        self.assertEqual(exit_at, datetime(2026, 10, 25, 23, 30))
        self.assertIsNone(exit_at.tzinfo)

    def test_timezone_aware_timestamps_remain_aware(self):
        entered_at = datetime(2026, 10, 26, 3, 0, tzinfo=timezone.utc)
        now = datetime(2026, 10, 26, 3, 30, tzinfo=timezone.utc)

        exit_at, minutes = _exit_time_and_minutes(entered_at, now)

        self.assertEqual(minutes, 30)
        self.assertEqual(exit_at, now)
        self.assertIsNotNone(exit_at.tzinfo)


if __name__ == "__main__":
    unittest.main()
