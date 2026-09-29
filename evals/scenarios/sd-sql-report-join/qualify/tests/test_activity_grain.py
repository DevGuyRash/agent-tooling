"""Row grain of the customer activity report: exactly one row per customer, whatever the joins match.

Each test builds a tiny database on SQLite (the engine the reports run on) with one awkward case.
"""
import unittest

from acctreport import db, reports

START, END = "2026-08-01", "2026-09-01"


class ActivityGrainTest(unittest.TestCase):
    def report(self, customers, assignments=(), orders=()):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        db.create_schema(conn)
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)
        conn.executemany("INSERT INTO account_assignments VALUES (?, ?, ?, ?)", assignments)
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
        rows = reports.customer_activity(conn, START, END)
        self.assertCountEqual([r["customer_id"] for r in rows], [c[0] for c in customers],
                              "every customer exactly once")
        return rows

    def row(self, rows, customer_id):
        return next(r for r in rows if r["customer_id"] == customer_id)

    def test_customer_without_orders_is_listed_with_zeros(self):
        rows = self.report([(1, "Quiet Co", "2026-08-18")], [(1, 1, "Luis Ortega", "2026-08-18")])
        self.assertEqual(self.row(rows, 1), {
            "customer_id": 1, "customer": "Quiet Co", "account_manager": "Luis Ortega",
            "order_count": 0, "revenue_cents": 0, "last_order_date": None})

    def test_customer_with_orders_only_outside_the_period_is_listed_with_zeros(self):
        rows = self.report([(1, "Lapsed Co", "2025-01-01")], [(1, 1, "Priya Nair", "2025-01-01")],
                           [(1, 1, "2026-07-31", 5000), (2, 1, "2026-09-01", 7000)])
        r = self.row(rows, 1)
        self.assertEqual((r["order_count"], r["revenue_cents"], r["last_order_date"]), (0, 0, None))

    def test_unassigned_customer_is_listed(self):
        rows = self.report([(1, "New Co", "2026-07-27")], [], [(1, 1, "2026-08-05", 9875)])
        r = self.row(rows, 1)
        self.assertEqual((r["account_manager"], r["order_count"], r["revenue_cents"]), (None, 1, 9875))

    def test_reassigned_customer_counts_each_order_once(self):
        rows = self.report([(1, "Moved Co", "2025-01-01")],
                           [(1, 1, "Dana Whitfield", "2025-01-01"), (2, 1, "Luis Ortega", "2026-03-02"),
                            (3, 1, "Grace Okafor", "2026-05-11")],
                           [(1, 1, "2026-08-04", 21240), (2, 1, "2026-08-11", 24510)])
        r = self.row(rows, 1)
        self.assertEqual((r["order_count"], r["revenue_cents"]), (2, 45750))

    def test_reassigned_customer_shows_current_manager(self):
        rows = self.report([(1, "Moved Co", "2025-01-01")],
                           [(1, 1, "Dana Whitfield", "2025-01-01"), (2, 1, "Luis Ortega", "2026-03-02"),
                            (3, 1, "Grace Okafor", "2026-05-11")],
                           [(1, 1, "2026-08-04", 21240)])
        self.assertEqual(self.row(rows, 1)["account_manager"], "Grace Okafor")

    def test_assignment_recorded_twice_counts_each_order_once(self):
        rows = self.report([(1, "Twice Co", "2025-09-15")],
                           [(1, 1, "Priya Nair", "2025-09-15"), (2, 1, "Priya Nair", "2025-09-15")],
                           [(1, 1, "2026-08-06", 15820), (2, 1, "2026-08-20", 17340)])
        self.assertEqual(self.row(rows, 1), {
            "customer_id": 1, "customer": "Twice Co", "account_manager": "Priya Nair",
            "order_count": 2, "revenue_cents": 33160, "last_order_date": "2026-08-20"})

    def test_same_day_reassignment_uses_the_later_entry(self):
        rows = self.report([(1, "Fixed Co", "2025-08-11")],
                           [(1, 1, "Tom Becker", "2025-08-11"), (2, 1, "Priya Nair", "2026-06-09"),
                            (3, 1, "Grace Okafor", "2026-06-09")],
                           [(1, 1, "2026-08-12", 30400)])
        r = self.row(rows, 1)
        self.assertEqual((r["account_manager"], r["order_count"], r["revenue_cents"]), ("Grace Okafor", 1, 30400))

    def test_backdated_assignment_does_not_replace_the_latest(self):
        # The sync can record an older assignment after the current one: the latest assigned_on wins, not
        # the latest entry. No orders, so the rule is checked on a zero-activity row.
        rows = self.report([(1, "Late Co", "2025-01-01")],
                           [(1, 1, "Luis Ortega", "2026-03-10"), (2, 1, "Dana Whitfield", "2025-11-20")])
        self.assertEqual(self.row(rows, 1)["account_manager"], "Luis Ortega")

    def test_identical_orders_are_all_counted(self):
        rows = self.report([(1, "Standing Co", "2025-04-21")], [(1, 1, "Dana Whitfield", "2025-04-21")],
                           [(1, 1, "2026-08-17", 18450), (2, 1, "2026-08-17", 18450), (3, 1, "2026-08-24", 18450)])
        r = self.row(rows, 1)
        self.assertEqual((r["order_count"], r["revenue_cents"]), (3, 55350))

    def test_customers_without_revenue_follow_in_customer_id_order(self):
        rows = self.report([(3, "C Co", "2025-01-01"), (1, "A Co", "2025-01-01"), (2, "B Co", "2025-01-01")],
                           [], [(1, 2, "2026-08-03", 100)])
        self.assertEqual([r["customer_id"] for r in rows], [2, 1, 3])


if __name__ == "__main__":
    unittest.main()
