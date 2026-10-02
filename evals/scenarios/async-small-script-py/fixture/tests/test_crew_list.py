import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from crew_list import crew_lists  # noqa: E402


class CrewListTest(unittest.TestCase):
    def test_active_by_squad(self):
        lists = crew_lists(ROOT / "samples" / "members.csv")
        self.assertEqual(lists, {"Juniors": ["Clara Rüegg", "Felix Moser"],
                                 "Masters": ["Anna Keller", "Ben Ott", "Eva Brunner"]})


if __name__ == "__main__":
    unittest.main()
