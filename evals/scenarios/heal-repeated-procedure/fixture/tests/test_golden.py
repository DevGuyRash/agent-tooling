import json
import unittest
from pathlib import Path

from ledgerline.normalize import normalize_file

HERE = Path(__file__).parent


class GoldenTest(unittest.TestCase):
    def test_every_data_file_has_a_golden_file(self):
        data = {p.stem for p in (HERE / "data").glob("*.csv")}
        golden = {p.stem for p in (HERE / "golden").glob("*.json")}
        self.assertEqual(data, golden)

    def test_golden_files(self):
        for golden in sorted((HERE / "golden").glob("*.json")):
            bank = golden.stem.split("_")[0]
            with self.subTest(golden.name):
                expected = json.loads(golden.read_text())
                self.assertEqual(expected["bank"], bank)
                self.assertEqual(expected["transactions"], normalize_file(bank, HERE / "data" / f"{golden.stem}.csv"))


if __name__ == "__main__":
    unittest.main()
