import unittest

import dedupe_hashset
import dedupe_scan

SAMPLE = [
    {"id": "a", "v": 1},
    {"id": "b", "v": 2},
    {"id": "a", "v": 3},
    {"id": "c", "v": 4},
    {"id": "b", "v": 5},
]


class DedupeTest(unittest.TestCase):
    def test_scan_keeps_first_occurrence(self):
        result = dedupe_scan.dedupe(SAMPLE)
        self.assertEqual([r["id"] for r in result], ["a", "b", "c"])
        self.assertEqual(result[0]["v"], 1)

    def test_hashset_keeps_first_occurrence(self):
        result = dedupe_hashset.dedupe(SAMPLE)
        self.assertEqual([r["id"] for r in result], ["a", "b", "c"])
        self.assertEqual(result[0]["v"], 1)

    def test_implementations_agree_on_empty_input(self):
        self.assertEqual(dedupe_scan.dedupe([]), [])
        self.assertEqual(dedupe_hashset.dedupe([]), [])


if __name__ == "__main__":
    unittest.main()
