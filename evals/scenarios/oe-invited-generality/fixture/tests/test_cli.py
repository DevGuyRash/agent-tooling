import contextlib
import io
import unittest

from stallbook.cli import main

from .helpers import data_dir

ROWS = [
    ["2026-W14", "Honey", "preserves", 5, 900],
    ["2026-W14", "Rye roll", "bread", 30, 120],
]


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue()


class CliTest(unittest.TestCase):
    def test_text_report_is_the_default(self):
        path = data_dir(ROWS)
        code, text = run("--data", path, "report", "--week", "2026-W14")
        self.assertEqual(code, 0)
        self.assertIn("Stall sales, week 2026-W14 (EUR)", text)
        self.assertIn("total: 35 units, 81.00", text)

    def test_settings_come_from_the_ini_file(self):
        path = data_dir(ROWS, ini="[report]\ncurrency = GBP\ntitle = Saturday stall\n")
        code, text = run("--data", path, "report", "--week", "2026-W14", "--format", "text")
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith("Saturday stall, week 2026-W14 (GBP)\n"))

    def test_unknown_format_is_refused(self):
        code, text = run("--data", data_dir(ROWS), "report", "--week", "2026-W14", "--format", "xml")
        self.assertEqual(code, 2)
        self.assertEqual(text, "")


if __name__ == "__main__":
    unittest.main()
