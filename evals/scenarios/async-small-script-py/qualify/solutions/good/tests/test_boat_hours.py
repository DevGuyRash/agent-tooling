import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from boat_hours import boat_hours  # noqa: E402


class BoatHoursTest(unittest.TestCase):
    def test_sample(self):
        hours = boat_hours(ROOT / "samples" / "boatlog-2026.csv")
        # Wotan: 85 min before its service, 115 after, one outing still out.
        self.assertEqual(hours["Wotan"], (200, 115))
        self.assertEqual(hours["Blue Heron"], (175, 175))

    def test_service_resets(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write("date,boat,crew,out,in\n2026-05-01,Aare,Eva,06:00,08:00\n2026-05-02,Aare,SERVICE,,\n"
                     "2026-05-03,Aare,\"Eva, Ben\",07:00,07:30\n")
        self.addCleanup(Path(fh.name).unlink)
        self.assertEqual(boat_hours(fh.name), {"Aare": (150, 30)})


if __name__ == "__main__":
    unittest.main()
