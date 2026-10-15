import unittest

from stampcard.batch import Summary
from stampcard.report import render


class RenderTest(unittest.TestCase):
    def test_layout(self):
        summary = Summary()
        summary.events, summary.applied, summary.drinks, summary.notify_failed = 5, 3, 1, 1
        summary.reject("malformed")
        summary.reject("malformed")
        summary.cards = [("C-001", 4, 1), ("C-004", 0, 0)]
        self.assertEqual(render(summary), "\n".join([
            "stampcard report",
            "events: 5",
            "applied: 3",
            "rejected: 2 (malformed: 2)",
            "free drinks: 1",
            "notify failed: 1",
            "cards:",
            "  C-001  stamps 4  drinks 1",
            "  C-004  stamps 0  drinks 0",
            "",
        ]))


if __name__ == "__main__":
    unittest.main()
