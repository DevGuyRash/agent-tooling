"""The August customer activity report over the dev snapshot, which holds every awkward case:
customers with no orders or orders only outside August, an unassigned customer, reassignments, a
duplicated assignment, a same-day correction, and a standing order of identical amounts."""
import unittest
from pathlib import Path

from acctreport import db, reports

SEED = Path(__file__).resolve().parent.parent / "data" / "dev_seed.sql"


class DevSnapshotAugustTest(unittest.TestCase):
    def test_august(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        db.create_schema(conn)
        db.run_script(conn, SEED)
        got = [tuple(r.values()) for r in reports.customer_activity(conn, "2026-08-01", "2026-09-01")]
        self.assertEqual(got, [
            (9, "Northside Diner", "Luis Ortega", 3, 125310, "2026-08-30"),
            (3, "Maple & Main Cafe", "Dana Whitfield", 6, 110700, "2026-08-31"),
            (1, "Harbor Point Bakery", "Luis Ortega", 4, 92300, "2026-08-26"),
            (10, "Juniper Hall Catering", "Grace Okafor", 1, 67500, "2026-08-14"),
            (7, "Fern & Fig Grocers", "Priya Nair", 2, 58550, "2026-08-27"),
            (13, "Tidewater Oyster Bar", "Dana Whitfield", 1, 54400, "2026-08-18"),
            (11, "Riverside Pantry", "Tom Becker", 2, 42450, "2026-08-23"),
            (12, "Oak & Ember Pizza", "Luis Ortega", 2, 33990, "2026-08-15"),
            (2, "Copper Kettle Coffee", "Priya Nair", 2, 33160, "2026-08-20"),
            (8, "Saltbox Provisions", "Tom Becker", 2, 26550, "2026-08-21"),
            (6, "Birch Lane Market", None, 2, 21125, "2026-08-22"),
            (4, "Linden & Moss", "Priya Nair", 0, 0, None),
            (5, "Quarry Street Deli", "Luis Ortega", 0, 0, None),
            (14, "Little Fox Kitchen", "Grace Okafor", 0, 0, None),
        ])


if __name__ == "__main__":
    unittest.main()
