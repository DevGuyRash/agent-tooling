import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orders_data import load_orders
from report import generate_nightly_report


class ReportTest(unittest.TestCase):
    def test_revenue_matches_known_total(self):
        summary = generate_nightly_report(load_orders())
        self.assertEqual(len(summary), 12)
        self.assertAlmostEqual(sum(summary.values()), 42291.5, places=2)

    def test_every_customer_present(self):
        summary = generate_nightly_report(load_orders())
        self.assertIn("Atlas Freight", summary)
        self.assertIn("Lonestar Provisions", summary)


if __name__ == "__main__":
    unittest.main()
