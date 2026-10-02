import unittest

from .helpers import DatabaseCase

STATIONS = [
    (1, "HB01", "Harbour Square", "harbour", 24, None),
    (2, "HB04", "Ferry Terminal", "harbour", 30, None),
    (3, "OT2", "Market Cross", "old-town", 16, None),
    (4, "OT9", "Tannery Yard", "old-town", 12, "2024-05-01"),
]


class StationsTest(unittest.TestCase, DatabaseCase):
    def setUp(self):
        self.make_db(STATIONS)

    def test_in_service_by_code(self):
        status, out, _ = self.dockops("stations")
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(), ["code  station         area      docks",
                                            "HB01  Harbour Square  harbour      24",
                                            "HB04  Ferry Terminal  harbour      30",
                                            "OT2   Market Cross    old-town     16"])

    def test_area_and_retired(self):
        status, out, _ = self.dockops("stations", "--area", "old-town", "--retired")
        self.assertEqual(status, 0)
        self.assertEqual(out.splitlines(), ["code  station       area      docks  retired",
                                            "OT2   Market Cross  old-town     16",
                                            "OT9   Tannery Yard  old-town     12  2024-05-01"])

    def test_unknown_area(self):
        status, out, err = self.dockops("stations", "--area", "docklands")
        self.assertEqual((status, out), (2, ""))
        self.assertEqual(err, "dockops: no stations in area 'docklands'\n")
