import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from chorelog.cli import main


class CliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = str(Path(tmp.name) / "chores.log")

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--file", self.log, *argv])
        return code, out.getvalue()

    def test_add_then_report(self):
        self.run_cli("add", "mara", "dishes", "--date", "2026-09-14")
        self.run_cli("add", "ines", "laundry", "--date", "2026-09-14")
        self.run_cli("add", "mara", "trash", "--date", "2026-09-15")
        code, out = self.run_cli("report")
        self.assertEqual(code, 0)
        self.assertEqual(out, "mara: 2\nines: 1\n")

    def test_report_on_an_empty_log(self):
        code, out = self.run_cli("report")
        self.assertEqual((code, out), (0, "no entries\n"))


if __name__ == "__main__":
    unittest.main()
