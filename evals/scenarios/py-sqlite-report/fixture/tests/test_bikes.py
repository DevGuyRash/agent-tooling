import unittest

from .helpers import DatabaseCase

STATIONS = [(1, "HB01", "Harbour Square", "harbour", 24, None), (2, "OT2", "Market Cross", "old-town", 16, None)]
TRIPS = [
    (1, 2207, 50311, "ride", 1, 2, "2025-03-02 08:01:10", "2025-03-02 08:15:40"),
    (2, 2207, None, "ride", 2, 2, "2025-03-02 17:30:00", "2025-03-02 17:30:40"),
    (3, 2207, None, "service", 2, 1, "2025-03-03 06:10:00", "2025-03-03 06:42:05"),
    (4, 2207, 50311, "ride", 1, None, "2025-03-03 09:00:00", None),
    (5, 3100, None, "ride", 1, 2, "2025-03-03 09:05:00", "2025-03-03 09:20:00"),
]


class BikeTest(unittest.TestCase, DatabaseCase):
    def setUp(self):
        self.make_db(STATIONS, TRIPS)

    def test_newest_first(self):
        status, out, _ = self.dockops("bike", "2207", "--last", "3")
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(), ["started              from  to    min  kind",
                                            "2025-03-03 09:00:00  HB01  -     out  ride",
                                            "2025-03-03 06:10:00  OT2   HB01   32  service",
                                            "2025-03-02 17:30:00  OT2   OT2     0  ride"])

    def test_unknown_bike(self):
        status, out, err = self.dockops("bike", "9999")
        self.assertEqual((status, out, err), (1, "", "dockops: no trips for bike 9999\n"))
