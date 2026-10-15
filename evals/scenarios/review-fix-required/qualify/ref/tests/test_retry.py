import unittest

from stampcard.directory import Card
from stampcard.notify import notify_reward

CARD = Card("C-001", "Ada", 0)


class Flaky:
    def __init__(self, failures):
        self.failures, self.calls = failures, 0

    def __call__(self, message):
        self.calls += 1
        if self.calls <= self.failures:
            raise OSError("gateway down")


class RetryTest(unittest.TestCase):
    def test_a_failed_notification_is_retried_after_1_then_2_seconds(self):  # R9
        waits, transport = [], Flaky(2)
        self.assertTrue(notify_reward(CARD, transport, sleep=waits.append))
        self.assertEqual((transport.calls, waits), (3, [1, 2]))

    def test_it_gives_up_after_four_attempts(self):
        waits, transport = [], Flaky(99)
        self.assertFalse(notify_reward(CARD, transport, sleep=waits.append))
        self.assertEqual((transport.calls, waits), (4, [1, 2, 4]))


if __name__ == "__main__":
    unittest.main()
