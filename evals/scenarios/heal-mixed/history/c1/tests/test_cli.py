import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from shelfmark.cli import main


class CliTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = str(Path(self._dir.name) / "cat.json")

    def tearDown(self):
        self._dir.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--catalog", self.path, *argv])
        return code, out.getvalue()

    def test_add_and_list(self):
        self.run_cli("add", "0-306-40615-2", "--title", "The Dispossessed", "--author", "Le Guin")
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("0306406152  The Dispossessed", out)

    def test_rejects_invalid_isbn(self):
        code, _ = self.run_cli("add", "12345", "--title", "T", "--author", "A")
        self.assertEqual(code, 2)

    def test_export_json(self):
        self.run_cli("add", "9780306406157", "--title", "T", "--author", "A")
        code, out = self.run_cli("export", "--format", "json")
        self.assertEqual(json.loads(out)[0]["isbn"], "9780306406157")


if __name__ == "__main__":
    unittest.main()
