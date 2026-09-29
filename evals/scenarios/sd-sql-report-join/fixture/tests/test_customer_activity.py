import io
import unittest

from acctreport import cli, db, reports

CUSTOMERS = [
    (1, "Alder Street Bakery", "2025-01-10"),
    (2, "Beacon Coffee", "2025-02-14"),
    (3, "Cobble Hill Deli", "2025-03-03"),
]
ASSIGNMENTS = [
    (1, 1, "Dana Whitfield", "2025-01-10"),
    (2, 2, "Luis Ortega", "2025-02-14"),
    (3, 3, "Dana Whitfield", "2025-03-03"),
]
ORDERS = [
    (1, 1, "2026-07-30", 12000),  # before the period
    (2, 1, "2026-08-01", 25000),  # first day of the period
    (3, 1, "2026-08-19", 17550),
    (4, 2, "2026-08-08", 9900),
    (5, 2, "2026-09-01", 40000),  # the day after the period
    (6, 3, "2026-08-12", 31000),
    (7, 3, "2026-08-28", 4500),
]


def make_db():
    conn = db.connect(":memory:")
    db.create_schema(conn)
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", CUSTOMERS)
    conn.executemany("INSERT INTO account_assignments VALUES (?, ?, ?, ?)", ASSIGNMENTS)
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", ORDERS)
    return conn


class CustomerActivityTest(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        self.addCleanup(self.conn.close)

    def activity(self):
        return reports.customer_activity(self.conn, "2026-08-01", "2026-09-01")

    def test_one_row_per_customer_highest_revenue_first(self):
        self.assertEqual(self.activity(), [
            {"customer_id": 1, "customer": "Alder Street Bakery", "account_manager": "Dana Whitfield",
             "order_count": 2, "revenue_cents": 42550, "last_order_date": "2026-08-19"},
            {"customer_id": 3, "customer": "Cobble Hill Deli", "account_manager": "Dana Whitfield",
             "order_count": 2, "revenue_cents": 35500, "last_order_date": "2026-08-28"},
            {"customer_id": 2, "customer": "Beacon Coffee", "account_manager": "Luis Ortega",
             "order_count": 1, "revenue_cents": 9900, "last_order_date": "2026-08-08"},
        ])

    def test_period_includes_start_and_excludes_end(self):
        rows = {r["customer_id"]: r for r in self.activity()}
        self.assertEqual(rows[1]["order_count"], 2)  # 2026-08-01 counts, 2026-07-30 does not
        self.assertEqual(rows[2]["order_count"], 1)  # 2026-09-01 belongs to September

    def test_printed_report(self):
        out = io.StringIO()
        cli.print_activity(self.activity(), "2026-08-01", "2026-09-01", out)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "Customer activity, 2026-08-01 up to 2026-09-01")
        self.assertIn("Alder Street Bakery", lines[2])
        self.assertIn("$425.50", lines[2])
        self.assertEqual(len(lines), 5)


class FormatCentsTest(unittest.TestCase):
    def test_format_cents(self):
        self.assertEqual(cli.format_cents(0), "$0.00")
        self.assertEqual(cli.format_cents(5), "$0.05")
        self.assertEqual(cli.format_cents(123456), "$1,234.56")


if __name__ == "__main__":
    unittest.main()
