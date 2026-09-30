import unittest

from billing.directory import User, UserDirectory
from billing.report import generate_report


class TestGenerateReport(unittest.TestCase):
    def test_attaches_plan_for_known_customer(self):
        directory = UserDirectory([User("ann@example.com", "Ann", "pro")])
        orders = [{"id": "1001", "email": "ann@example.com", "amount": "42.00"}]
        self.assertEqual(generate_report(orders, directory), "1001,ann@example.com,pro,42.00")

    def test_unknown_customer_reports_unknown_plan(self):
        directory = UserDirectory([])
        orders = [{"id": "1002", "email": "ghost@example.com", "amount": "9.99"}]
        self.assertEqual(generate_report(orders, directory), "1002,ghost@example.com,unknown,9.99")


if __name__ == "__main__":
    unittest.main()
