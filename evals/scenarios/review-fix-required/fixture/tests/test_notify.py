import unittest

from stampcard.directory import Card
from stampcard.notify import notify_reward

CARD = Card("C-001", "Ada", 0)


class NotifyRewardTest(unittest.TestCase):
    def test_sends_the_customer_a_message(self):
        sent = []
        self.assertTrue(notify_reward(CARD, sent.append))
        self.assertEqual([(m["to"], m["name"]) for m in sent], [("C-001", "Ada")])

    def test_a_failing_transport_does_not_raise(self):
        def down(message):
            raise OSError("gateway down")

        self.assertFalse(notify_reward(CARD, down))


if __name__ == "__main__":
    unittest.main()
