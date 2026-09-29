"""The customer activity report over one small month that holds every awkward case at once."""
import unittest

from acctreport import db, reports

CUSTOMERS = [
    (1, "Harbor Point Bakery", "2025-06-02"),   # reassigned in March
    (2, "Copper Kettle Coffee", "2025-09-15"),  # its assignment synced twice
    (3, "Maple & Main Cafe", "2025-04-21"),     # standing order: same amount weekly, twice on one day
    (4, "Linden & Moss", "2025-11-03"),         # ordered in July and on Sept 1, not in August
    (5, "Quarry Street Deli", "2026-08-18"),    # new, no orders yet
    (6, "Birch Lane Market", "2026-07-27"),     # no account manager yet
    (7, "Fern & Fig Grocers", "2025-08-11"),    # reassigned, then corrected the same day
]
ASSIGNMENTS = [
    (1, 3, "Dana Whitfield", "2025-04-21"),
    (2, 1, "Dana Whitfield", "2025-06-02"),
    (3, 7, "Tom Becker", "2025-08-11"),
    (4, 2, "Priya Nair", "2025-09-15"),
    (5, 2, "Priya Nair", "2025-09-15"),
    (6, 4, "Priya Nair", "2025-11-03"),
    (7, 1, "Luis Ortega", "2026-03-02"),
    (8, 7, "Grace Okafor", "2026-06-09"),
    (9, 7, "Priya Nair", "2026-06-09"),
    (10, 5, "Luis Ortega", "2026-08-18"),
]
ORDERS = [
    (1, 4, "2026-07-28", 21100),
    (2, 1, "2026-08-04", 21240),
    (3, 6, "2026-08-05", 9875),
    (4, 2, "2026-08-06", 15820),
    (5, 3, "2026-08-10", 18450),
    (6, 3, "2026-08-17", 18450),
    (7, 3, "2026-08-17", 18450),
    (8, 1, "2026-08-19", 19875),
    (9, 2, "2026-08-20", 17340),
    (10, 7, "2026-08-27", 28150),
    (11, 4, "2026-09-01", 20000),
]


class AugustActivityTest(unittest.TestCase):
    def test_august_report(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        db.create_schema(conn)
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", CUSTOMERS)
        conn.executemany("INSERT INTO account_assignments VALUES (?, ?, ?, ?)", ASSIGNMENTS)
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", ORDERS)
        got = [(r["customer_id"], r["account_manager"], r["order_count"], r["revenue_cents"], r["last_order_date"])
               for r in reports.customer_activity(conn, "2026-08-01", "2026-09-01")]
        self.assertEqual(got, [
            (3, "Dana Whitfield", 3, 55350, "2026-08-17"),
            (1, "Luis Ortega", 2, 41115, "2026-08-19"),
            (2, "Priya Nair", 2, 33160, "2026-08-20"),
            (7, "Priya Nair", 1, 28150, "2026-08-27"),
            (6, None, 1, 9875, "2026-08-05"),
            (4, "Priya Nair", 0, 0, None),
            (5, "Luis Ortega", 0, 0, None),
        ])


if __name__ == "__main__":
    unittest.main()
