import unittest

from .helpers import DatabaseCase

STATIONS = [(1, "HB01", "Harbour Square", "harbour", 24, None), (2, "HB04", "Ferry Terminal", "harbour", 30, None),
            (3, "OT2", "Market Cross", "old-town", 16, None)]
TRIPS = [
    (1, 10, None, "ride", 2, 1, "2025-03-03 08:00:00", "2025-03-03 08:20:00"),
    (2, 11, None, "ride", 2, 3, "2025-03-03 09:00:00", "2025-03-03 09:20:00"),
    (3, 12, None, "ride", 3, 3, "2025-03-03 10:00:00", "2025-03-03 10:00:20"),
    (4, 13, None, "service", 1, 2, "2025-03-03 11:00:00", "2025-03-03 11:20:00"),
    (5, 14, None, "ride", 1, None, "2025-03-03 23:59:00", None),
]


class RebalanceTest(unittest.TestCase, DatabaseCase):
    def setUp(self):
        self.make_db(STATIONS, TRIPS)

    def test_day(self):
        status, out, _ = self.dockops("rebalance", "--from", "2025-03-03")
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(), ["code  station         out  in  net",
                                            "HB04  Ferry Terminal    2   0   -2",
                                            "HB01  Harbour Square    1   1    0",
                                            "OT2   Market Cross      0   1   +1",
                                            "stations: 3, out: 3, in: 2"])

    def test_no_rides(self):
        self.assertEqual(self.dockops("rebalance", "--from", "2025-03-05")[:2], (0, "no rides in range\n"))

    def test_errors(self):
        self.assertEqual(self.dockops("rebalance", "--from", "2025-02-30")[0], 2)
        self.assertEqual(self.dockops("rebalance", "--from", "2025-03-03", "--area", "docklands")[0], 2)
